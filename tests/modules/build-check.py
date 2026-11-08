#!/usr/bin/env python3
"""tests/modules 项目级验收（MOD-U2..U5）。

用 tests/modules/projects/ 下的真实 project.toml 项目 fixture，把自举编译器
的「发现 → 索引 → 三层解析 → 模块语义 → 独立对象/接口 → 链接运行 →
对象缓存」整条管线过一遍。每个用例复制到 tmp/modcheck/ 后执行：

    run     用例       yh run   退出码 == 期望值（程序退出码）
    fail    用例       yh build 非零退出且 stderr 含期望诊断子串
    ok      用例       yh build 退出 0
    iface   用例+方法  构建成功后破坏依赖接口，再构建必须拒绝
    rebind  用例+方法  构建后新增本地同名模块，必须重绑定并重编译

usage: python3 tests/modules/build-check.py [--compiler-path ./yh]
                                          [--jobs N]
    用例之间互不依赖（每个用例在自己独占的 tmp/modcheck/<用例> 目录里重新
    复制 fixture 并构建），因此可并发执行；--jobs 缺省 min(4, CPU 核数)，
    --jobs 1 恢复串行。每个用例内部还会 fork 模块 worker，故上限比纯语法
    语料低。
退出码：全部通过 0；有失败 1。
"""

import argparse
import concurrent.futures
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PROJ = HERE / "projects"
WORK = ROOT / "tmp" / "modcheck"

# 并发用例数缺省上限：一个用例就是若干次完整项目构建（每次还会 fork 模块
# worker），上限 4 兼顾核数不多的机器与并发构建的内存占用。
DEFAULT_JOBS = max(1, min(4, os.cpu_count() or 1))
COMPILER_PATH = None
COMPILER_FLAGS = []
COMPILER_BUILD_FLAGS = []
COMPILER_BACKEND = None
COMPILER_TARGET = None
COMPILER_OPT_LEVEL = None



def windows_support_link(project_root=None):
    """返回编译器 [link-windows-x64] 的 support 库清单（TOML 片段）。

    Windows 上零 CRT 链接只带 kernel32 与栈探测桩；用到 C 运行时的 fixture
    （引入 check 的 strtod/malloc 等）必须显式带 VC 运行时，否则 lld-link
    报 undefined symbol: strtod。这里直接复用编译器自身清单，避免两处漂移。
    """
    if COMPILER_TARGET is None or "windows" not in COMPILER_TARGET:
        return ""
    source = (project_root or ROOT) / "compiler" / "project.toml"
    text = source.read_text(encoding="utf-8")
    marker = "[link-windows-x64]"
    if marker not in text:
        return ""
    segment = text[text.index(marker):]
    match = re.search(r"\nsupport = \[(.*?)\]", segment, re.S)
    if not match:
        return ""
    lines = []
    for item in match.group(1).split(","):
        item = item.strip().strip('"')
        if not item:
            continue
        resolved = (Path(source).parent / item).resolve()
        lines.append('  "' + str(resolved).replace(chr(92), "/") + '",')
    if not lines:
        return ""
    return "[link-windows-x64]\nsupport = [\n" + "\n".join(lines) + "\n]\n"


def artifact_root(project):
    """返回当前后端与目标配置的项目产物根目录。"""
    root = Path(project) / ".build"
    if COMPILER_BACKEND == "llvm":
        return (root / "targets" / COMPILER_TARGET / "llvm"
                / f"O{COMPILER_OPT_LEVEL}")
    return root


def backend_text_files(project):
    """列出当前后端保留的模块文本（LLVM IR 或旧后端汇编）。

    旧后端 RS3b 起按文件对象布局 asm/<tag>/<stem>.s，递归收集。
    """
    if COMPILER_BACKEND == "llvm":
        return sorted((artifact_root(project) / "llvm").glob("*.ll"))
    return sorted((artifact_root(project) / "asm").rglob("*.s"))


def validate_llvm_stats(proc):
    """验证 LLVM 项目构建的覆盖计数没有漏记或静默回退。"""
    lines = [line for line in (proc.stdout + proc.stderr).splitlines()
             if line.startswith("yh-stats ")]
    if not lines:
        return "LLVM 构建未输出 --stats 计数"
    rows = [dict(item.split("=", 1) for item in line.split()[1:]
                  if "=" in item) for line in lines]
    checked = sum(int(row.get("checked_functions", "0")) for row in rows)
    emitted = sum(int(row.get("backend_emitted_functions", "0")) for row in rows)
    fallback = sum(int(row.get("fallback_functions", "0")) for row in rows)
    if emitted > checked or fallback != 0:
        return f"LLVM 计数不一致：checked={checked} emitted={emitted} fallback={fallback}"
    return None


def exit_code(rc: int) -> int:
    """把退出码归一化为 POSIX 语义（只看低 8 位）。

    POSIX 的等待状态只暴露 `code & 0xFF`（`return 1023` 表现为 255），
    Windows 的 GetExitCodeProcess 拿到完整 32 位。门禁按 8 位比较两边，
    崩溃（负数）保持原样。
    """
    return rc & 0xFF if rc >= 0 else rc


def run_ok(run, expect: int) -> bool:
    """运行结果是否达到期望退出码（按 POSIX 8 位语义比较）。"""
    return run is not None and exit_code(run.returncode) == exit_code(expect)


def sh(cmd, cwd, env=None):
    """运行命令；调用当前编译器时在 argv 中明确注入选定后端参数。"""
    cmd = list(cmd)
    if cmd and COMPILER_PATH is not None:
        executable = str(cmd[0])
        is_compiler = executable == str(COMPILER_PATH) or executable == "yh"
        if is_compiler and COMPILER_FLAGS:
            cmd[1:1] = COMPILER_FLAGS
        if is_compiler and COMPILER_BUILD_FLAGS:
            try:
                build_at = cmd.index("build")
            except ValueError:
                build_at = -1
            if build_at >= 0:
                cmd[build_at + 1:build_at + 1] = COMPILER_BUILD_FLAGS
    e = dict(__import__("os").environ)
    e.setdefault("YH_CACHE", "off")
    if env:
        e.update(env)
    # WSL 的 ARM64 过渡种子经 QEMU 执行 LLVM 项目构建时，O2 大型用例
    # 可能超过旧的 300 秒；原生候选门仍会独立覆盖相同用例。
    timeout = 1800 if COMPILER_BACKEND == "llvm" else 300
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                            env=e, timeout=timeout)
    if COMPILER_BACKEND == "llvm" and any(
            line.startswith("yh-stats ")
            for line in (result.stdout + result.stderr).splitlines()):
        error = validate_llvm_stats(result)
        if error:
            return subprocess.CompletedProcess(
                cmd, 1, result.stdout, result.stderr + "\nLL9 stats: " + error)
    return result


def stat_value(line, name, default=-1):
    """从一行 yh-stats 读取整数计数器。"""
    marker = name + "="
    if marker not in line:
        return default
    return int(line.split(marker, 1)[1].split()[0])


def has_two_edge_phi(path):
    """读取 yh SSA 缓存头，确认存在四块 CFG 中的双前驱 phi。"""
    data = path.read_bytes()
    if len(data) < 128 or struct.unpack_from("<Q", data, 16)[0] != 0x3141535352494859:
        return False
    if struct.unpack_from("<Q", data, 24)[0] != 9:
        return False
    _, _, type_count, inst_count, phi_count, input_count, call_count, arg_count, symbol_size, block_count, _ = \
        struct.unpack_from("<11q", data, 32)
    if (type_count <= 0 or inst_count < 0 or phi_count != 1 or input_count != 2
            or call_count != 0 or arg_count != 0 or symbol_size != 0
            or block_count != 4):
        return False
    inst_offset = 128 + type_count * 24
    return any(struct.unpack_from("<q", data, inst_offset + i * 56)[0] == 6
               for i in range(inst_count))


def count_ir_op(path, wanted):
    """统计一个已生成 SSA 缓存中的指定操作码。"""
    data = path.read_bytes()
    if len(data) < 128 or struct.unpack_from("<Q", data, 16)[0] != 0x3141535352494859:
        return -1
    _, _, type_count, inst_count, _, _, _, _, _, _, _ = struct.unpack_from("<11q", data, 32)
    inst_offset = 128 + type_count * 24
    if type_count < 0 or inst_count < 0 or inst_offset + inst_count * 56 > len(data):
        return -1
    return sum(struct.unpack_from("<q", data, inst_offset + i * 56)[0] == wanted
               for i in range(inst_count))


def has_ir_term(path, wanted):
    """检查 SSA 缓存是否含有指定的基本块终结符。"""
    data = path.read_bytes()
    if len(data) < 128 or struct.unpack_from("<Q", data, 16)[0] != 0x3141535352494859:
        return False
    _, _, type_count, inst_count, phi_count, input_count, call_count, arg_count, symbol_size, block_count, _ = \
        struct.unpack_from("<11q", data, 32)
    offset = (128 + type_count * 24 + inst_count * 56 + phi_count * 16
              + input_count * 16 + call_count * 56 + arg_count * 16
              + ((symbol_size + 7) // 8) * 8)
    if min(type_count, inst_count, phi_count, input_count, call_count,
           arg_count, symbol_size, block_count) < 0:
        return False
    if offset + block_count * 56 > len(data):
        return False
    return any(struct.unpack_from("<q", data, offset + i * 56 + 24)[0] == wanted
               for i in range(block_count))


CASES = []


# —— W2-9：Windows 零 CRT 下的「宿主 C/POSIX 运行时」边界 ——
# 这些用例验证的是宿主 libc/信号/套接字/归档语义；Windows 目标按方案 D2 走
# 零 CRT（只链 kernel32），没有 libm/libc/dup2/system/socket。它们不是产品缺陷，
# 而是决定点 W1-2b-2（零 CRT 还是接 UCRT）未定前的明确边界，按 SKIP 记录。
WINDOWS_SKIP = {
    "s2-libs-core-modules": "libs/math 依赖宿主 libm（cos/pow），零 CRT 无 libm（W1-2b-2）",
    "net0-sys-socket-loopback": "Winsock 未接线（W2-7 的 socket 桩返回 -ENOSYS）",
    "net1-net-tcp-loopback": "Winsock 未接线（W2-7 的 socket 桩返回 -ENOSYS）",
    "cabi-automatic-values-and-callbacks": "C 互操作桩依赖宿主 libc/libm（W1-2b-2）",
    "r2b-ast-check-module": "fixture 走宿主 libc（strtod）浮点解析（W1-2b-2）",
    "llvm-target-identity": "fixture 走宿主 libc（strtod）浮点解析（W1-2b-2）",
    "llvm-front-zero-output": "fixture 走宿主 libc（strtod）浮点解析（W1-2b-2）",
    "llvm-checked-snapshot": "fixture 走宿主 libc（strtod）浮点解析（W1-2b-2）",
    "llvm-snapshot-lowering": "fixture 走宿主 libc（strtod）浮点解析（W1-2b-2）",
    "r3-system-compat-build": "system() 是 POSIX shell 语义，Windows 无等价物",
    "r3-system-compat-check": "system() 是 POSIX shell 语义，Windows 无等价物",
    "r3-system-compat-run": "system() 是 POSIX shell 语义，Windows 无等价物",
    "r3-dup2-os-api": "dup2 是 POSIX fd 语义，零 CRT 运行时没有 dup2",
    "r3-envp-main": "Windows 入口目前只构造 argv，envp 为空（W2-9 待补）",
    "link-shared-group": "共享库（.so/.dylib）不是 COFF 目标；Windows 用 .lib/.dll",
    "u3-c-paths-with-spaces-use-argv": "C 互操作桩依赖宿主 libc/libm（W1-2b-2）",
}
WINDOWS_SKIP_PREFIX = {
    "u3-c-": "C 源/对象互操作依赖宿主 libc/libm（W1-2b-2）",
    "link-static-groups": "归档组（ar/.a + --start-group）是 ELF/Darwin 语义；"
                          "COFF 的 .lib 输入由 test-windows-target 覆盖",
}


WINDOWS_ACP_LOSSY_CASES = (
    "r3-directory-filenames-are-byte-safe",
    "r3-directory-enumeration-grows-past-one-batch",
)


def windows_acp_lossy(text="雪"):
    """Windows 进程 ACP 无法表示 text 时返回该 ACP 编号，否则返回 None。

    project_dir.windows.x64.yh 的目录枚举用 FindFirstFileA、gen.read_source
    用 CRT open()，两者都按进程 ACP 解释路径字节：英文 runner 的 ACP=1252
    会把「雪」替换成 '?'（不可逆），编译器随后打不开这个文件，两个 R3
    目录扫描用例必然失败。ACP=936（GBK）或 65001（UTF-8 manifest）能表示，
    仍照常实测——这是既有 Windows 路径层遗留（W2-9 / VENC-2 P2），不是
    用例本身失效。判定用 kernel32.GetACP() 而非 locale，避免 Windows 上
    Python 文件系统编码恒为 UTF-8 的假阴性。
    """
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        acp = int(ctypes.windll.kernel32.GetACP())
        text.encode("cp" + str(acp))
    except UnicodeEncodeError:
        return acp
    except Exception:
        # 拿不到 ACP 或未知码页：不擅自跳过，保留原断言结果。
        return None
    return None


def windows_skip_reason(name: str):
    """Windows 零 CRT / ACP 边界下应跳过的用例原因；不跳过返回 None。"""
    if name in WINDOWS_ACP_LOSSY_CASES:
        acp = windows_acp_lossy()
        if acp is not None:
            return (f"Windows 目录枚举 FindFirstFileA：进程 ACP={acp} 无法表示"
                    "非 ASCII 文件名（W2-9 / VENC-2 遗留，见 docs/todo.md）")
    reason = WINDOWS_SKIP.get(name)
    if reason:
        return reason
    for prefix, text in WINDOWS_SKIP_PREFIX.items():
        if name.startswith(prefix):
            return text
    return None


def case(name, kind, fixture, sub, expect=None, msg=None, stdout=None):
    CASES.append(dict(name=name, kind=kind, fixture=fixture, sub=sub,
                      expect=expect, msg=msg, stdout=stdout))


# —— MOD-U4：两项目真实链接运行（含跨模块聚合/浮点/间接调用/限定字面量） ——
case("u4-basic-run", "run", "basic", "app", 255)
case("ct3-same-module-multifile", "comptime-local", "comptimelocal", ".")
case("ct5a-layout-const-deps", "comptime-layout-deps", "comptimelayoutdeps", ".")
case("ct5b-cross-module-body", "comptime-cross-module", "comptimecross", ".")
case("ct2-expanded-ast-ssa", "comptime-expanded-ast", "comptimeexpanded", ".", 0)
case("ct2-expanded-ast-node-budget", "comptime-expanded-budget", "comptimeexpandedfail", ".",
     msg="编译期 for 展开 AST 节点超过 100000")
case("u4-iso-run", "run", "iso", "host", 15)
case("u4-aggfloat-run", "run", "aggfloat", "host", 29)
case("u4-enumexp-run", "run", "enumexp", "host", 10)
case("u4-pub-signature-type-closure", "run", "typeclosure", "signature-host", 23)
case("u4-pub-field-type-closure", "run", "typeclosure", "field-host", 23)
case("s1-libs-io-write", "stdlib-run", "libsio", ".", 23,
     stdout="yh libs io ok\n")
case("s2-libs-core-modules", "stdlib-run", "libsbase", ".", 0,
     stdout="yh libs base ok\n")
case("hash-sha256", "stdlib-run", "hashsha", ".", 0,
     stdout="hash sha256 ok\n")
# —— ST1/ST6：string 公开面与跨库 smoke（断言已迁入 libs/string/tests.test.yh） ——
case("st1-string-model", "stdlib-run", "stringmodel", ".", 0,
     stdout="string model ok\n")
case("st6-string-interop", "stdlib-run", "stringinterop", ".", 0,
     stdout="string interop ok\n")
# —— JSON：断言已迁入 libs/json/json.test.yh，这里保留公开面/链接 smoke ——
case("j1-json-model", "stdlib-run", "jsonmodel", ".", 0,
     stdout="json model ok\n")
# —— FMT/I：字符串插值端到端（文本/表达式/字段/下标/uint/i64/spec/转义） ——
case("fmt-interp", "stdlib-run", "fmtinterp", ".", 0,
     stdout="Hello, Bob! n=7 sum=12 p=3,4 idx=10 u=42 w=99\n"
            "hex=0007 f=1.50 bool=true literal=${n}\n"
            "plain $5 and ${x} and $x\n"
            "v=hi\n")
case("os0-os-result-model", "stdlib-run", "osmodel", ".", 0,
     stdout="os model ok\n")
case("os5-io-write-result", "stdlib-run", "osio", ".", 0,
     stdout="os io ok\n")
# —— NET0/NET1：sys 网络原语与 net 的 TCP 环回（不联网、不查 DNS） ——
case("net0-sys-socket-loopback", "stdlib-run", "netsys", ".", 0,
     stdout="sys net ok\n")
case("net1-net-tcp-loopback", "stdlib-run", "netecho", ".", 0,
     stdout="net tcp ok\n")
# —— OS6：可执行文件附近的默认标准库发现（空 YH_STDLIB 触发默认路径） ——
case("os6-default-stdlib", "default-stdlib-run", "osmodel", ".", 0,
     stdout="os model ok\n")
case("u4-pub-const-wide-values", "run", "pubconst", "host", 0)
case("u3-import-used-via-field-type", "run", "importfield", "host", 0)
case("u1-extern-abs-module", "run", "externabs", "host", 0)
case("u3-c-source-object-library-mix", "run", "cinterop", ".", 0)
case("cabi-automatic-values-and-callbacks", "cabi-run", "autoabi", ".", 0)
case("i1-inline-ssa-and-fallback", "inline", "inline", ".")
# 非 inline 函数声明在 inline 函数之前：验证按文件切分的替换位移
# 在 pass 1 不会把后续函数的序言推掉（曾导致汇编首行只剩 `29, sp`）。
case("i1-inline-order-after-noninline", "run", "inlineorder", ".", 0)
case("r1-token-replay-run", "run", "tokenreplay", ".", 42)
case("r2b-ast-check-module", "run", "astcheck", ".", 0)
case("llvm-float-cross-module", "run", "llvmfloat", ".", 0)
case("llvm-yh-cross-module-call", "run", "llvmyhimport", ".", 0)
case("llvm-cabi-scalar-cross-module", "run", "llvmabi", ".", 0)
case("support-buffer-tools", "run", "support", ".", 0)
case("gen3-split-narrow-ports", "run", "gen-split", ".", 0)
case("f4-ct-facts-mirror", "run", "ctfacts", ".", 0)
case("token-state-cursor", "run", "token", ".", 0)
case("llvm-target-identity", "run", "llvmtarget", ".", 0)
case("llvm-front-zero-output", "run", "llvmfront", ".", 0)
case("llvm-module-ownership", "run", "llvmmodule", ".", 0)
case("llvm-checked-snapshot", "run", "llvmchecked", ".", 0)
case("llvm-snapshot-lowering", "checked-lower", "llvmlower", ".", 0)
case("llvm-global-private-data", "run", "llvmprivate", ".", 0)
case("r2c-build-lowers-ssa-cfg", "ir", "irfront", ".", 230)
case("r2a-ssa-cross-module-call", "ir-call", "ircallmodule", ".", 41)
case("r2b-interface-ready-scheduler", "scheduler", "scheduler", ".")
case("r2b-interface-ready-diamond", "scheduler-diamond", "scheduler-diamond", ".")
case("r3-system-mode", "legacy-system", "legacy-system", ".")
case("r3-systemless-link-cache-mode", "mode-cache", "systemless", ".")
case("r3-dup2-os-api", "run", "dup2-api", ".", 0)
case("r3-mkdir-os-api", "run", "mkdir-api", ".", 0)
case("r3-capture-uses-host-file-flags", "host-capture", "systemless", ".")
case("r3-envp-main", "envp-run", "envp-api", ".")
case("r3-target-specific-sources", "platform-source", "platformsource", ".")
case("r3-linux-syscall-intrinsic", "linux-syscall-asm", "linuxsyscall", ".")
case("r3-darwin-getattrlistbulk-api", "darwin-dir-api", "darwindirapi", ".")
case("r3-os-directory-enumeration", "directory-scan", "directoryscan", ".")
case("link-static-groups", "linkgroups", "linkgroups", ".", 0)
case("link-shared-group", "linkshared", "linkshared", ".", 0)
case("link-bad-section", "fail", "linkbad", ".", msg="非法的链接节名")
case("link-missing-target", "fail", "linkmissingtarget", ".", msg="project.os 必填")
case("link-bad-suffix", "fail", "linkbadsuffix", ".", msg="后缀不符合当前目标")
# —— MOD-U2：清单与三层解析 ——
case("u2-toml-syntax", "fail", "tomlbad", ".", msg="project.toml")
case("u2-toml-unknown-field", "fail", "tomlunknown", ".", msg="未知字段")
# —— 清单精简（2026-09-30）：name 必须标识符、author 放行、入口 = main 模块 ——
case("p1-name-not-identifier", "fail", "tomlnamebad", ".", msg="project.name")
case("u2-transitive-rejected", "fail", "transitive", "host", msg="模块不存在")
case("u2-ambiguous-deps", "fail", "ambiguity", "host", msg="歧义")
# —— 2026-10-24 路径预算：项目名/模块名与构建目录长度上限 ——
# 标记与派生路径写进 512/600/700 字节定长缓冲，超限必须在源头拒绝，
# 不能依赖 gen.append_str 的隐式 NUL 终止。
case("u7-module-name-too-long", "fail", "longname", ".", msg="模块名过长")
# —— MOD-U3：模块语义 ——
# 2026-10-02 pub struct 一等化：字段一律公开，跨模块字段访问与位置式构造
# 由 fail 用例转为 run 正向用例；符号级可见性（非 pub fn）仍被拒绝。
case("u3-import-cycle", "fail", "cycle", "a", msg="环")
case("u3-entry-not-importable", "fail", "cycleentry", "host", msg="入口模块不可")
case("u3-pub-field-access", "run", "pubpriv", "host", 2)
case("u3-private-fn", "fail", "pubpriv", "host2", msg="导出")
case("u3-positional-pub-construct", "run", "pubpriv", "host3", 1)
case("u3-private-let-accessor", "run", "modstate", "host", 7)
case("u3-private-let-access", "fail", "modstate", "host2",
     msg="模块没有导出该名字")
# —— 模块私有类型（2026-10-12，ADR-0013）：pub 可选，缺省即模块私有 ——
case("u3-private-type-module-api", "run", "privtype", "host", 0)
case("u3-private-type-not-exported", "fail", "privtype", "host2",
     msg="模块没有导出该类型")
case("u3-private-enum-member-not-exported", "fail", "privtype", "host3",
     msg="模块没有导出该名字")
case("u3-private-type-in-pub-signature", "fail", "privtype", "badpub",
     msg="pub 接口引用了非 pub 类型")
case("u3-private-type-in-pub-field", "fail", "privtype", "badfield",
     msg="pub 接口引用了非 pub 类型")
case("u3-private-type-in-pub-alias", "fail", "privtype", "badalias",
     msg="pub 接口引用了非 pub 类型")
case("u3-private-type-pointer-in-pub", "fail", "privtype", "badptr",
     msg="pub 接口引用了非 pub 类型")
case("u3-duplicate-decl", "fail", "dupdecl", "host", msg="重定义")
case("u3-unused-import", "fail", "unusedimp", "host", msg="导入未使用")
# —— UF1（2026-10-27）：未使用函数检查 ——
# 同包跨文件的私有调用算「已使用」（math.helper 只在 another.yh 里被调用）；
# 孤立且没 pub 的私有函数在模块构建里也必须报错。
case("uf1-module-scope-use", "run", "unusedfn", "host", 42)
case("uf1-unused-function", "fail", "unusedfn", "dead", msg="函数未使用")
case("u3-import-clash", "fail", "clashname", "host", msg="导入名冲突")
# —— PC1（2026-10-25）：函数级 IR 缓存命中率回归 ——
# 键里混入 arena 下标时实测全量 miss；这里固定三条断言：冷编全 miss、
# 等价重编全命中、改一个函数体只失效该函数。
case("pc1-function-cache-hits", "firc", "firchits", ".")

# —— OS1–OS5：Linux 文件/目录/环境/进程/时间/内存（只在 Linux 内核运行） ——
OS_LINUX_CASES = [
    dict(name="os1-sys-raw", kind="stdlib-run", fixture="sysraw", sub=".",
         expect=0, msg=None, stdout="sys raw ok\n"),
    dict(name="os1-sys-files", kind="stdlib-run", fixture="sysfiles", sub=".",
         expect=0, msg=None, stdout="sys files ok\n"),
    dict(name="os1-os-files", kind="stdlib-run", fixture="osfiles", sub=".",
         expect=0, msg=None, stdout="os files ok\n"),
    dict(name="os1-sys-eintr", kind="stdlib-run", fixture="syseintr", sub=".",
         expect=0, msg=None, stdout="sys eintr ok\n"),
    dict(name="os4-sys-process", kind="stdlib-run", fixture="sysprocess", sub=".",
         expect=0, msg=None, stdout="sys process ok\n"),
    dict(name="os4-os-process", kind="stdlib-run", fixture="osprocess", sub=".",
         expect=0, msg=None, stdout="os process ok\n"),
    dict(name="os5-sys-time", kind="stdlib-run", fixture="systime", sub=".",
         expect=0, msg=None, stdout="sys time ok\n"),
    dict(name="os5-sys-memory", kind="stdlib-run", fixture="sysmemory", sub=".",
         expect=0, msg=None, stdout="sys memory ok\n"),
    dict(name="os2-sys-dirs", kind="stdlib-run", fixture="sysdirs", sub=".",
         expect=0, msg=None, stdout="sys dirs ok\n"),
    dict(name="os2-os-dirs", kind="stdlib-run", fixture="osdirs", sub=".",
         expect=0, msg=None, stdout="os dirs ok\n"),
    dict(name="os3-env-query", kind="envp-run", fixture="osenv", sub=".",
         expect=0, msg=None, stdout="os env ok\n"),
]
if sys.platform.startswith("linux"):
    CASES.extend(OS_LINUX_CASES)

# —— W2-7：Windows 平台变体（libs/sys、libs/os、libs/time 的 .windows.yh）——
# 与 Linux 侧共用大部分夹具：文件 API、进程 spawn/wait、时钟、内存映射的实现
# 换了后端（CreateFileA/FindFirstFileA/CreateProcessA/VirtualAlloc/
# QueryPerformanceCounter），断言面不变。目录用例换成 osdirswin：
# Linux 的 osdirs 直接构造 getdents64 原始记录（Windows 没有这个概念）。
OS_WINDOWS_CASES = [
    dict(name="os1-sys-files-win", kind="stdlib-run", fixture="sysfiles", sub=".",
         expect=0, msg=None, stdout="sys files ok\n"),
    dict(name="os1-os-files-win", kind="stdlib-run", fixture="osfiles", sub=".",
         expect=0, msg=None, stdout="os files ok\n"),
    dict(name="os2-os-dirs-win", kind="stdlib-run", fixture="osdirswin", sub=".",
         expect=0, msg=None, stdout="os dirs win ok\n"),
    dict(name="os4-os-process-win", kind="stdlib-run", fixture="osprocess", sub=".",
         expect=0, msg=None, stdout="os process ok\n"),
    dict(name="os5-sys-time-win", kind="stdlib-run", fixture="systime", sub=".",
         expect=0, msg=None, stdout="sys time ok\n"),
    dict(name="os5-sys-memory-win", kind="stdlib-run", fixture="sysmemory", sub=".",
         expect=0, msg=None, stdout="sys memory ok\n"),
]
if sys.platform.startswith("win"):
    CASES.extend(OS_WINDOWS_CASES)


def copy_proj(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    if src.name == "astcheck":
        # 探针直接使用当前编译器的 AST arena 与 check 实现。
        for module in ("proj", "support", "token", "lex", "comptime", "ir", "backend", "ast", "check", "cache"):
            source = ROOT / "compiler" / module
            if source.is_dir():
                ignore = shutil.ignore_patterns("llvm_bridge.yh") if module == "backend" else None
                shutil.copytree(source, dst / module, ignore=ignore)
        # C0 起 ast 依赖 cache，cache 依赖标准库 hash；fixture 复制真实模块时
        # 必须把这两层一起带上，否则会在模块解析阶段报 cache/hash 不存在。
        shutil.copytree(ROOT / "libs" / "hash", dst / "hash",
                        ignore=shutil.ignore_patterns(".build"))
    # 只有引入 check（内部用 strtod 等 C 运行时符号）的 fixture 需要 VC 运行时；
    # 其余 fixture 加上会与 yh 自有 memcpy/malloc 运行时入口冲突（duplicate symbol）。
    link_section = windows_support_link() if src.name in ("ctfacts", "gen-split", "llvmfront") else ""
    if link_section:
        host_manifest = dst / "project.toml"
        if host_manifest.is_file():
            host_manifest.write_text(host_manifest.read_text() + "\n" + link_section)
    if src.name in ("irfront", "llvmmodule"):
        # ir 现为编译器根项目普通模块（不带清单）；fixture 仍以路径依赖
        # 方式复用其源码测跨项目解析，拷入后补最小清单使其可被发现。
        shutil.copytree(ROOT / "compiler" / "ir", dst / "ir")
        (dst / "ir" / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "yh_ir"\nsource = "."\n')
    if src.name == "support":
        # GEN1：support 是真实模块，fixture 以路径依赖消费其公开字节工具。
        shutil.copytree(ROOT / "compiler" / "support", dst / "support")
        (dst / "support" / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "support"\nsource = "."\n')
    if src.name == "token":
        # GEN1：token 依赖 support；放进 token 依赖项目内保持单项目发现。
        shutil.copytree(ROOT / "compiler" / "token", dst / "token")
        shutil.copytree(ROOT / "compiler" / "support", dst / "token" / "support")
        (dst / "token" / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "token"\nsource = "."\n')
    if src.name in ("llvmtarget", "llvmfront"):
        # 目标模型测试复用实际 gen/proj 源码，并以项目依赖检验公开类型/接口。
        # GEN1 起 gen → support/token；三者各自成项目，路径指向同一份 support。
        shutil.copytree(ROOT / "compiler" / "support", dst / "support")
        (dst / "support" / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "support"\nsource = "."\n')
        shutil.copytree(ROOT / "compiler" / "token", dst / "token")
        (dst / "token" / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "token"\nsource = "."\n'
            '[dependencies]\nsupport = { path = "../support" }\n')
        # F4 收尾：gen 模块已删除，fixture 不再需要它的子项目。
        shutil.copytree(ROOT / "compiler" / "proj", dst / "proj")
        (dst / "proj" / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "proj"\nsource = "."\n'
            '[dependencies]\nsupport = { path = "../support" }\n'
            'token = { path = "../token" }\n')
        # F2-K2：语义动作（ty_*/sym_*/scope_*）已从 gen 迁到 check，前端 fixture
        # 需要连 check 及其依赖（ast/comptime）一起拷贝，否则 import check 解析失败。
        for mod, deps in (("ir", ""), ("cache", "support token hash"), ("comptime", "support token proj"), ("ast", "support token proj comptime"),
                          ("check", "support token proj ast comptime ir cache hash")):
            shutil.copytree(ROOT / "compiler" / mod, dst / mod)
            lines = [f'[project]', 'os = "host"', 'arch = "host"', f'name = "{mod}"', 'source = "."', '', '[dependencies]']
            for dep in deps.split():
                lines.append(f'{dep} = {{ path = "../{dep}" }}')
            (dst / mod / "project.toml").write_text("\n".join(lines) + "\n")
        # cache 依赖标准库 hash：作为子项目拷入并补最小清单。
        shutil.copytree(ROOT / "libs" / "hash", dst / "hash",
                        ignore=shutil.ignore_patterns(".build"))
        (dst / "hash" / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "hash"\nsource = "."\n')
        # 链 B：lex 自带 LexCtx（词法游标），front_stage 初始化时会复位它。
        shutil.copytree(ROOT / "compiler" / "lex", dst / "lex")
        (dst / "lex" / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "lex"\nsource = "."\n'
            '[dependencies]\nsupport = { path = "../support" }\n'
            'token = { path = "../token" }\n')
    if src.name in ("ctfacts", "gen-split"):
        # GEN3：拆分后的公开面回归——直接 import support/token/check，
        # 需要与 ctfacts 同一套真实模块（check 的传递依赖一并拷入）。
        core = dst / "compiler"
        core.mkdir()
        for module in ("proj", "support", "token", "lex", "comptime", "ir", "backend",
                       "ast", "check", "cache"):
            shutil.copytree(ROOT / "compiler" / module, core / module,
                            ignore=shutil.ignore_patterns("llvm_bridge.yh"))
        shutil.copytree(ROOT / "libs" / "hash", core / "hash",
                        ignore=shutil.ignore_patterns(".build"))
        (core / "hash" / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "hash"\nsource = "."\n')
        (core / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "gensplitcore"\nsource = "."\n'
            '[dependencies]\nhash = { path = "hash" }\n')
        fixture_link = windows_support_link()
    if src.name == "ctfacts_disabled":
        # F4-0：验证 CT 零拷贝镜像与 gen 类型表逐行一致（含表扩容后重新绑定）。
        core = dst / "compiler"
        core.mkdir()
        for module in ("proj", "support", "token", "lex", "comptime", "ir", "backend",
                       "ast", "check", "cache"):
            shutil.copytree(ROOT / "compiler" / module, core / module,
                            ignore=shutil.ignore_patterns("llvm_bridge.yh"))
        shutil.copytree(ROOT / "libs" / "hash", core / "hash",
                        ignore=shutil.ignore_patterns(".build"))
        (core / "hash" / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "hash"\nsource = "."\n')
        (core / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "ctfactscore"\nsource = "."\n'
            '[dependencies]\nhash = { path = "hash" }\n')
    if src.name == "llvmchecked":
        # 快照 fixture 消费真实 AST/语义实现，并在模块内构造和释放原 arena。
        # backend 里的 llvm_bridge.yh 只声明内嵌桥的 C ABI，fixture 不链接桥，
        # 因此拷入时排除它（其余 backend 源码保持真实）。
        core = dst / "compiler"
        core.mkdir()
        for module in ("proj", "support", "token", "lex", "ast", "comptime", "ir", "backend", "check", "cache"):
            shutil.copytree(ROOT / "compiler" / module, core / module,
                            ignore=shutil.ignore_patterns("llvm_bridge.yh"))
        shutil.copytree(ROOT / "libs" / "hash", core / "hash",
                        ignore=shutil.ignore_patterns(".build"))
        (core / "project.toml").write_text('[project]\nos = "host"\narch = "host"\nname = "checkedcore"\nsource = "."\n')
        # 快照 fixture 现在属于 check 模块；文件名排在 checked_model.yh 之后，
        # 保证 CheckedModule 等类型先声明。
        shutil.copyfile(src / "fixture.yh", core / "check" / "checked_snapshot_fixture.yh")
    if src.name == "llvmlower":
        # 纯快照 lowering fixture 复用真实前端（parse/lex）与 lowering 实现，
        # fixture 作为同模块的第二个文件随 main/ 一起构建；同样排除桥绑定。
        core = dst / "compiler"
        core.mkdir()
        for module in ("proj", "support", "token", "lex", "ast", "parse", "comptime", "ir", "backend", "builtin", "check", "lower", "cache"):
            shutil.copytree(ROOT / "compiler" / module, core / module,
                            ignore=shutil.ignore_patterns("llvm_bridge.yh"))
        shutil.copytree(ROOT / "libs" / "hash", core / "hash",
                        ignore=shutil.ignore_patterns(".build"))
        (core / "project.toml").write_text('[project]\nos = "host"\narch = "host"\nname = "lowercore"\nsource = "."\n')
        shutil.copyfile(src / "fixture.yh", dst / "main" / "fixture.yh")


def main():
    global WORK, COMPILER_PATH, COMPILER_FLAGS, COMPILER_BUILD_FLAGS, COMPILER_BACKEND
    global COMPILER_TARGET, COMPILER_OPT_LEVEL
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler-path", default=str(ROOT / "yh"))
    ap.add_argument("--backend", choices=("llvm",),
                    help="显式选择编译后端（LLVM 是唯一后端）")
    ap.add_argument("--target", help="显式选择输出目标 triple")
    ap.add_argument("--opt-level", choices=("0", "2"),
                    help="显式选择 LLVM 优化级别")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--jobs", type=int, default=DEFAULT_JOBS,
                    help=f"并发用例数（缺省 {DEFAULT_JOBS}；1 为串行）")
    ap.add_argument("--workdir", default=str(WORK),
                    help="用例工作目录（缺省 tmp/modcheck；可指向快速文件系统）")
    args = ap.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    COMPILER_PATH = Path(compiler)
    COMPILER_BACKEND = args.backend
    COMPILER_TARGET = args.target
    COMPILER_OPT_LEVEL = args.opt_level
    if COMPILER_BACKEND == "llvm":
        # 显式 LLVM 模式下未给 --target/--opt-level 时按宿主默认补齐：
        # 默认后端就是 LLVM，门禁不应要求调用方重复传宿主 triple。
        if not COMPILER_TARGET:
            import platform
            machine = platform.machine().lower()
            if sys.platform == "darwin":
                COMPILER_TARGET = "aarch64-apple-darwin" if machine in ("arm64", "aarch64") \
                    else "x86_64-apple-darwin"
            elif sys.platform.startswith("win"):
                # Windows 宿主：产物在 targets/x86_64-pc-windows-msvc 下（W2-7）。
                COMPILER_TARGET = "x86_64-pc-windows-msvc"
            elif machine in ("x86_64", "amd64"):
                COMPILER_TARGET = "x86_64-unknown-linux-gnu"
            else:
                COMPILER_TARGET = "aarch64-unknown-linux-gnu"
        if not COMPILER_OPT_LEVEL:
            COMPILER_OPT_LEVEL = "0"
    COMPILER_FLAGS = []
    COMPILER_BUILD_FLAGS = []
    if args.backend:
        COMPILER_FLAGS += ["--backend", args.backend]
    if args.target:
        COMPILER_FLAGS += ["--target", args.target]
    if args.opt_level:
        COMPILER_FLAGS += [f"-O{args.opt_level}"]
    if args.backend == "llvm":
        COMPILER_FLAGS += ["--stats"]
        COMPILER_BUILD_FLAGS += ["--emit-llvm"]
    WORK = Path(args.workdir)
    WORK.mkdir(parents=True, exist_ok=True)
    if not sys.platform.startswith("linux") and not args.quiet:
        print(f"SKIP {len(OS_LINUX_CASES)} 个 Linux 专属 os/sys 用例"
              f"（宿主 {sys.platform}，未计为通过）")
    failed = 0

    def report(ok, name, detail=""):
        nonlocal failed
        # 非 CASES 列表里的断言（stdlib 三层、system 兼容等）也走同一套平台边界。
        if sys.platform.startswith("win"):
            skip_reason = windows_skip_reason(name)
            if skip_reason is not None:
                print(f"SKIP {name}（{skip_reason}）")
                return
        if not ok:
            failed += 1
            print(f"FAIL {name}: {detail}")
        elif not args.quiet:
            print(f"OK   {name}")

    def run_case(c):
        """跑一个 CASES 用例，返回收集到的断言结果列表。

        每个用例在自己的 dst 目录里重新复制 fixture，彼此不共享路径，
        因此可以并发；并发时断言结果不能就地打印，先收集再由 main 打印。
        """
        out = []

        def report(ok, name, detail=""):
            """收集一条断言结果，由 main 按 CASES 顺序统一打印。"""
            out.append((ok, name, detail))

        if sys.platform.startswith("win"):
            reason = windows_skip_reason(c["name"])
            if reason is not None:
                out.append(("skip", c["name"], reason))
                return out

        dst = WORK / f"{c['fixture'].replace('/', '_')}--{c['name']}"
        copy_proj(PROJ / c["fixture"], dst)
        if c["kind"] == "firc":
            if COMPILER_BACKEND != "llvm":
                report(False, c["name"], "函数级缓存回归只覆盖 LLVM 后端")
                return out
            root = artifact_root(dst)
            # 模块标记 = 项目名 + 模块名；按 glob 匹配，避免把项目名写死。
            source = dst / "main.yh"
            original = source.read_text(encoding="utf-8")

            def cache_stats(proc):
                """取 ir_functions 最大的 stats 行：worker 行才有缓存计数。"""
                rows = [line for line in (proc.stdout + proc.stderr).splitlines()
                        if line.startswith("yh-stats ") and "ir_functions=" in line]
                if not rows:
                    return (-1, -1, -1)
                line = max(rows, key=lambda row: stat_value(row, "ir_functions", -1))
                return (stat_value(line, "ir_functions", -1),
                        stat_value(line, "ir_cache_hits", -1),
                        stat_value(line, "ir_cache_misses", -1))

            cold = sh([compiler, "build", "--stats"], cwd=dst)
            total, hits, misses = cache_stats(cold)
            report(cold.returncode == 0 and total > 0 and hits == 0 and misses == total,
                   c["name"] + ":cold-miss",
                   f"冷编应全 miss：rc={cold.returncode} total={total} "
                   f"hits={hits} misses={misses}\n{cold.stderr[-400:]}")
            # PC3：上一轮没完成链接（.build 刚清空）时不写函数级缓存。
            records = list(root.glob("firc/*/*.fir"))
            report(cold.returncode == 0 and not records,
                   c["name"] + ":cold-no-write",
                   f"全冷构建写了 {len(records)} 条函数缓存记录，PC3 要求为 0")

            def force_recompile():
                for pattern in ("manifest/*-main.manifest", "obj/*-main.o"):
                    for path in root.glob(pattern):
                        path.unlink()

            # 首次等价重编：缓存还是空的（冷编没写），全 miss 并落盘。
            force_recompile()
            primed = sh([compiler, "build", "--stats"], cwd=dst)
            total_p, hits_p, misses_p = cache_stats(primed)
            report(primed.returncode == 0 and total_p == total and hits_p == 0
                   and misses_p == total,
                   c["name"] + ":prime-miss",
                   f"首轮重编应全 miss：total={total_p} hits={hits_p} "
                   f"misses={misses_p}\n{primed.stderr[-400:]}")
            force_recompile()
            hot = sh([compiler, "build", "--stats"], cwd=dst)
            total2, hits2, misses2 = cache_stats(hot)
            report(hot.returncode == 0 and total2 == total and hits2 == total
                   and misses2 == 0,
                   c["name"] + ":hot-all-hit",
                   f"等价重编未全命中：total={total2} hits={hits2} misses={misses2}"
                   f"\n{hot.stderr[-400:]}")
            source.write_text(original.replace("    return x + 1;",
                                               "    return x + 2;", 1),
                              encoding="utf-8")
            edit = sh([compiler, "build", "--stats"], cwd=dst)
            total3, hits3, misses3 = cache_stats(edit)
            report(edit.returncode == 0 and total3 == total and misses3 == 1
                   and hits3 == total - 1,
                   c["name"] + ":one-function-miss",
                   f"单函数改动未只失效该函数：total={total3} hits={hits3} "
                   f"misses={misses3}\n{edit.stderr[-400:]}")
            source.write_text(original, encoding="utf-8")
            return out

        if c["kind"] == "linkgroups":
            cc = "clang" if sys.platform == "darwin" else "gcc"

            def make_archive(src_name, lib_name):
                obj = dst / "lib" / (Path(src_name).stem + ".o")
                lib = dst / "lib" / lib_name
                lib.parent.mkdir(parents=True, exist_ok=True)
                r = sh([cc, "-c", src_name, "-o", str(obj)], cwd=dst)
                if r.returncode != 0:
                    return r
                return sh(["ar", "rcs", str(lib), str(obj)], cwd=dst)

            def link_count(proc):
                lines = [line for line in proc.stderr.splitlines()
                         if line.startswith("yh-stats ")]
                return max([stat_value(line, "link", 0) for line in lines] or [0])

            for src_name, lib_name in (("c/a.c", "liba.a"), ("c/b.c", "libb.a"),
                                       ("c/a_target.c", "liba_target.a"),
                                       ("c/extra.c", "libextra.a")):
                prepared = make_archive(src_name, lib_name)
                if prepared.returncode != 0:
                    report(False, c["name"], f"准备归档失败: {prepared.stderr[-400:]}")
                    return out
            first = sh([compiler, "build", "--stats"], cwd=dst)
            program = dst / ".build" / "linkgroups"
            run = sh([str(program)], cwd=dst) if program.exists() else None
            report(first.returncode == 0 and run is not None and run.returncode == 79,
                   c["name"] + ":default-all",
                   f"默认全链失败: build={first.returncode}, "
                   f"run={run.returncode if run else None}\n{first.stderr[-500:]}")
            second = sh([compiler, "build", "--stats"], cwd=dst)
            report(second.returncode == 0 and link_count(second) == 0,
                   c["name"] + ":hot-cache",
                   f"第二次构建未命中链接缓存: link={link_count(second)}\n"
                   f"{second.stderr[-400:]}")
            single = sh([compiler, "build", "--link", "a"], cwd=dst)
            report(single.returncode != 0 and "link_probe_b" in (single.stdout + single.stderr),
                   c["name"] + ":single-group",
                   f"--link a 不应混入 b 组符号: rc={single.returncode}\n"
                   f"{single.stderr[-400:]}")
            unknown = sh([compiler, "build", "--link", "nope"], cwd=dst)
            report(unknown.returncode != 0 and "未知的 --link 组" in (unknown.stdout + unknown.stderr),
                   c["name"] + ":unknown-group",
                   f"未知组没有明确诊断: rc={unknown.returncode}\n{unknown.stderr[-400:]}")
            hidden = dst / "lib" / "libb.a"
            backup = dst / "lib" / "libb.a.hidden"
            hidden.rename(backup)
            unselected = sh([compiler, "build", "--link", "a"], cwd=dst)
            report(unselected.returncode != 0
                   and "库文件不存在" not in (unselected.stdout + unselected.stderr),
                   c["name"] + ":unselected-missing",
                   f"未选组缺文件不应在链接前报错: rc={unselected.returncode}\n"
                   f"{unselected.stderr[-400:]}")
            selected_missing = sh([compiler, "build", "--link", "b"], cwd=dst)
            report(selected_missing.returncode != 0
                   and "库文件不存在" in (selected_missing.stdout + selected_missing.stderr),
                   c["name"] + ":selected-missing",
                   f"选中组缺文件没有明确诊断: rc={selected_missing.returncode}\n"
                   f"{selected_missing.stderr[-400:]}")
            backup.rename(hidden)
            # 同路径替换归档内容必须触发重新链接。
            (dst / "c" / "a_target.c").write_text(
                "int link_probe_a(void) { return 51; }\n", encoding="utf-8")
            prepared = make_archive("c/a_target.c", "liba_target.a")
            changed = sh([compiler, "build", "--stats"], cwd=dst)
            run_changed = sh([str(program)], cwd=dst) if program.exists() else None
            report(prepared.returncode == 0 and changed.returncode == 0
                   and link_count(changed) > 0
                   and run_changed is not None and run_changed.returncode == 80,
                   c["name"] + ":archive-content",
                   f"归档内容变化未重链或运行值不符: prepared={prepared.returncode}, "
                   f"build={changed.returncode}, link={link_count(changed)}, "
                   f"run={run_changed.returncode if run_changed else None}\n"
                   f"{changed.stderr[-400:]}")
            shutil.rmtree(dst / "lib")
            checked = sh([compiler, "check"], cwd=dst)
            report(checked.returncode == 0, c["name"] + ":check-no-files",
                   f"check 不应检查库文件: rc={checked.returncode}\n{checked.stderr[-400:]}")
            return out
        if c["kind"] == "linkshared":
            cc = "clang" if sys.platform == "darwin" else "gcc"
            lib = dst / "lib" / ("libdyn.dylib" if sys.platform == "darwin" else "libdyn.so")
            lib.parent.mkdir(parents=True, exist_ok=True)
            if sys.platform == "darwin":
                prepared = sh([cc, "-dynamiclib", "-o", str(lib), "c/dyn.c"], cwd=dst)
            else:
                prepared = sh([cc, "-shared", "-fPIC", "-o", str(lib), "c/dyn.c"], cwd=dst)
            if prepared.returncode != 0:
                report(False, c["name"], f"准备共享库失败: {prepared.stderr[-400:]}")
                return out
            built = sh([compiler, "build"], cwd=dst)
            ran = sh([compiler, "run", "--link", "dyn"], cwd=dst)
            report(prepared.returncode == 0 and built.returncode == 0
                   and ran.returncode == 31,
                   c["name"] + ":run-shared",
                   f"共享库链接/运行失败: prep={prepared.returncode}, "
                   f"build={built.returncode}, run={ran.returncode}\n"
                   f"{ran.stderr[-500:]}")
            bad = sh([compiler, "run", "--link", "missing"], cwd=dst)
            report(bad.returncode != 0 and "未知的 --link 组" in (bad.stdout + bad.stderr),
                   c["name"] + ":unknown-group",
                   f"共享库未知组没有诊断: rc={bad.returncode}\n{bad.stderr[-400:]}")
            return out
        if c["kind"] == "cabi-run":
            # 两个窄参数探针和整数转换必须进入选定的真实后端并保持 C ABI。
            built = sh([compiler, "build", "--stats"], cwd=dst)
            lines = [line for line in built.stderr.splitlines()
                     if line.startswith("yh-stats ")]
            program = dst / ".build" / "autoabi"
            run = sh([str(program)], cwd=dst) if program.exists() else None
            if COMPILER_BACKEND == "llvm":
                checked = sum(stat_value(line, "checked_functions", 0) for line in lines)
                emitted = sum(stat_value(line, "backend_emitted_functions", 0)
                              for line in lines)
                text = "\n".join(path.read_text() for path in backend_text_files(dst))
                # Linux/AArch64 按 AAPCS64 不写 signext/zeroext；该属性断言只适用于
                # 需要寄存器级窄型承诺的 SysV/Darwin 目标。
                attrs_ok = COMPILER_TARGET.startswith("aarch64-unknown-linux") \
                    or ("signext" in text and "zeroext" in text)
                report(built.returncode == 0 and checked >= 3 and emitted == checked
                       and attrs_ok
                       and run_ok(run, c["expect"]),
                       c["name"],
                       f"C 双向 ABI/LLVM 覆盖失败: rc={built.returncode}, "
                       f"checked={checked}, emitted={emitted}, "
                       f"run={run.returncode if run else None}\n{built.stderr[-400:]}")
            else:
                lowered = sum(stat_value(line, "ir_functions", 0) for line in lines)
                ir_files = list((artifact_root(dst) / "ir").glob("*.ir"))
                casts = sum(count_ir_op(path, 24) for path in ir_files)
                report(built.returncode == 0 and lowered >= 3 and casts >= 3
                       and run_ok(run, c["expect"]),
                       c["name"],
                       f"C 双向调用或 SSA 覆盖失败: rc={built.returncode}, "
                       f"ir_functions={lowered}, cast_ops={casts}, "
                       f"run={run.returncode if run else None}\n{built.stderr[-400:]}")
            return out
        if c["kind"] == "comptime-local":
            built = sh([compiler, "build"], cwd=dst)
            asm_files = backend_text_files(dst)
            asm = "\n".join(path.read_text() for path in asm_files)
            program = dst / ".build" / "comptimelocal"
            run = sh([str(program)], cwd=dst) if program.exists() else None
            report(built.returncode == 0 and "combine" not in asm
                   and run is not None and run.returncode == 0
                   and "模块编译期警告" in built.stderr
                   and "未选中的编译警告" not in built.stderr,
                   c["name"],
                   f"跨文件编译期求值、独立诊断、未选分支或无发码失败: "
                   f"build={built.returncode}, run={run.returncode if run else None}\n"
                   f"{built.stderr[-500:]}\n"
                   f"{asm[-600:]}")
            return out
        if c["kind"] == "comptime-cross-module":
            host = dst / "host"
            built = sh([compiler, "build"], cwd=host)
            program = host / ".build" / "comptimecross_host"
            run = sh([str(program)], cwd=host) if program.exists() else None
            iface_dir = artifact_root(host) / "iface"
            public_iface = iface_dir / "ctmath-api.s.i"
            body_iface = iface_dir / "ctmath-api.s.ct"
            base_body_iface = iface_dir / "ctmath-base.s.ct"
            asm_files = backend_text_files(host)
            asm = "\n".join(path.read_text() for path in asm_files)
            # 三个 iface 都可能缺失（构建失败时）：先判存在再读，
            # 否则门禁抛 FileNotFoundError 而不是给出可读的失败原因。
            public_text = public_iface.read_text(encoding="utf-8")                 if public_iface.exists() else ""
            body_body = body_iface.read_text(encoding="utf-8")                 if body_iface.exists() else ""
            base_body = base_body_iface.read_text(encoding="utf-8")                 if base_body_iface.exists() else ""
            iface_ok = (public_iface.exists() and body_iface.exists()
                        and base_body_iface.exists()
                        and "yh-iface v3" in public_iface.read_text()
                        and "@[comptime]\npub fn double_after_bump" in public_iface.read_text()
                        and "__yhct_bump" in body_iface.read_text()
                        and "__yhct_double_after_bump" in body_iface.read_text()
                        and "const __yhct_OFFSET__ctmath__base_ int = 1;" in base_body
                        and "const __yhct_FACTOR__ctmath__base_ f64 = 1.25;"
                            in base_body
                        and 'const __yhct_LABEL__ctmath__base_ *char = '
                            '"CT5B_STRING_CLOSURE";' in base_body
                        and "let factor f64 = __yhct_FACTOR__ctmath__base_;"
                            in base_body
                        and "let offset BaseOffset__ctmath__base_ = "
                            "BaseOffset__ctmath__base_{amount: "
                            "__yhct_OFFSET__ctmath__base_};" in base_body
                        and "let offsets [2]BaseOffset__ctmath__base_ = "
                            "[offset, BaseOffset__ctmath__base_{amount: 0}];"
                            in base_body
                        and "let pointer *BaseOffset__ctmath__base_ = 0;"
                            in base_body
                        and "let converted int = value.to_type(int);" in base_body
                        and "geometry." not in base_body
                        and "dimensions." not in base_body
                        and "Point__ctmath__types_" in base_body
                        and "sizeof(Point__ctmath__types_)" in base_body
                        and "let typed int = value.to_type(int);" in base_body
                        and "sizeof(BaseOffset__ctmath__base_)" in base_body
                        and "sizeof(*BaseOffset__ctmath__base_)" in base_body
                        and "sizeof(**BaseOffset__ctmath__base_)" in base_body
                        and "CT5B_STRING_CLOSURE" not in asm
                        and "let offset Offset =" not in base_body
                        and "Offset" not in base_body.replace(
                            "BaseOffset__ctmath__base_", "")
                        and "Scalar" not in base_body
                        and "Offset{" not in base_body
                        and "__yhct_" not in asm)
            report(built.returncode == 0 and run is not None
                   and run.returncode == 0 and iface_ok,
                   c["name"],
                   f"跨模块编译期函数正文/私有闭包未执行: build={built.returncode}, "
                   f"run={run.returncode if run else None}, interface={iface_ok}\n"
                   f"{built.stderr[-500:]}")
            string_closure_ok = (
                'const __yhct_LABEL__ctmath__base_ *char = '
                '"CT5B_STRING_CLOSURE";' in base_body
                and "CT5B_STRING_CLOSURE" not in asm)
            report(built.returncode == 0 and string_closure_ok,
                   "ct5b-string-pointer-constant-closure",
                   f"字符串指针常量闭包或 .data 隔离失败: build={built.returncode}, "
                   f"sidecar={string_closure_ok}\n{built.stderr[-500:]}\n"
                   f"{asm[-400:]}")
            if built.returncode == 0 and run is not None and run.returncode == 0:
                source = dst / "math" / "src" / "base" / "base.yh"
                original = source.read_text()
                source.write_text(original.replace(
                    'const LABEL *char = "CT5B_STRING_CLOSURE";',
                    "const LABEL *char = 0;", 1))
                try:
                    unsupported_pointer = sh([compiler, "build"], cwd=host)
                finally:
                    source.write_text(original)
                report(unsupported_pointer.returncode != 0
                       and "跨模块 CT 闭包暂只支持直接或引用式的字符串字面量指针常量"
                           in unsupported_pointer.stderr,
                       "ct5b-nonliteral-pointer-constant-rejected",
                       f"非字面量指针常量未按阶段边界拒绝: "
                       f"build={unsupported_pointer.returncode}\n"
                       f"{unsupported_pointer.stderr[-500:]}")
                host_main = host / "src" / "main" / "main.yh"
                original_host_main = host_main.read_text()
                host_main.write_text(original_host_main.replace(
                    "$math.double_after_bump(20)",
                    "$math.double_after_bump(0)", 1))
                try:
                    pointer_eval = sh([compiler, "build"], cwd=host)
                finally:
                    host_main.write_text(original_host_main)
                # 2026-10-07 起字符串字面量指针常量可在编译期正文里求值
                # （按来源字节登记只读池），该路径必须构建成功。
                report(pointer_eval.returncode == 0,
                       "ct5b-string-pointer-constant-evaluable",
                       f"字符串指针常量在编译期正文里求值失败: "
                       f"build={pointer_eval.returncode}\n"
                       f"{pointer_eval.stderr[-500:]}")
                # 跨模块编译期调用的单字节指针形参：直接字面量与「以字符串字面量初始化的
                # 本地/导入 pub const 指针常量」都就地登记只读池，标签号是**本地**的。
                # 后者 2026-10-07 起放行（此前实测会读到无关字面量 head_of(MINE) 得 104105
                # = "hi"）；值正确性由 comptimecross 的 `TEXT_ARG - 65` 断言覆盖（main 非零
                # 即 FAIL），这里只锁构建成功。
                host_main.write_text(original_host_main.replace(
                    "const ANSWER int = $math.double_after_bump(20);",
                    'const MINE *char = "AB";\n'
                    "const ANSWER int = $math.head_of(MINE);", 1))
                try:
                    pointer_arg = sh([compiler, "build"], cwd=host)
                finally:
                    host_main.write_text(original_host_main)
                report(pointer_arg.returncode == 0,
                       "ct5b-crossmodule-pointer-arg-accepted",
                       f"跨模块单字节指针实参（本地字面量初始化常量）未被接受: "
                       f"build={pointer_arg.returncode}\n"
                       f"{pointer_arg.stderr[-500:]}")
                original_ct = body_iface.read_text()
                corrupt_ct = original_ct.replace(
                    "fn __yhct_double_after_bump__ctmath__api_(value int) int",
                    "fn __yhct_double_after_bump__ctmath__api_(value int) i64", 1)
                if corrupt_ct == original_ct:
                    report(False, "ct5b-corrupt-body-signature-rejected",
                           "找不到待破坏的公开 CT 隐藏正文签名")
                else:
                    body_iface.write_text(corrupt_ct)
                    try:
                        corrupt = sh([compiler, "build"], cwd=host)
                        repaired_ct = body_iface.read_text() == original_ct
                    finally:
                        body_iface.write_text(original_ct)
                    if COMPILER_BACKEND == "llvm":
                        # LLVM manifest 包含持久接口摘要；损坏 sidecar 应触发提供方重编译并修复。
                        repaired = corrupt.returncode == 0 and repaired_ct
                        report(repaired, "ct5b-corrupt-body-signature-rejected",
                               f"损坏的 .s.ct 未触发提供方重编译: build={corrupt.returncode}, "
                               f"repaired={repaired_ct}\n"
                               f"{corrupt.stdout[-300:]} {corrupt.stderr[-300:]}")
                    else:
                        report(corrupt.returncode != 0
                               and "公开 CT 函数与 .s.ct 正文签名不匹配" in corrupt.stderr,
                               "ct5b-corrupt-body-signature-rejected",
                               f"损坏的 .s.ct 签名未被拒绝: build={corrupt.returncode}\n"
                               f"{corrupt.stderr[-500:]}")
                header = original_ct.split("\n", 1)[0]
                corruptions = [
                    ("ct5b-corrupt-body-version-rejected",
                     original_ct.replace("// yh-ctiface v1",
                                         "// yh-ctiface v9", 1),
                     "CT 接口版本或目标不兼容"),
                    ("ct5b-truncated-body-rejected", header + "\n",
                     "公开 CT 函数与 .s.ct 正文签名不匹配"),
                    ("ct5b-malformed-body-rejected",
                     header + "\n@[comptime]\nfn broken(",
                     "ctmath-api.s.ct"),
                    ("ct5b-corrupt-column-map-rejected",
                     original_ct.replace("// yh-ctcol v1 ",
                                         "// yh-ctcol v1 8193 ", 1),
                     "CT 列映射格式无效"),
                ]
                for corrupt_name, corrupt_text, expected_error in corruptions:
                    if corrupt_text == original_ct:
                        report(False, corrupt_name,
                               "损坏输入与有效 .s.ct 内容相同")
                        continue
                    body_iface.write_text(corrupt_text)
                    try:
                        corrupt = sh([compiler, "build"], cwd=host)
                        repaired_ct = body_iface.read_text() == original_ct
                    finally:
                        body_iface.write_text(original_ct)
                    if COMPILER_BACKEND == "llvm":
                        repaired = corrupt.returncode == 0 and repaired_ct
                        report(repaired, corrupt_name,
                               f"损坏的 .s.ct 未触发提供方重编译: "
                               f"build={corrupt.returncode}, repaired={repaired_ct}\n"
                               f"{corrupt.stdout[-300:]} {corrupt.stderr[-300:]}")
                    else:
                        report(corrupt.returncode != 0
                               and expected_error in corrupt.stderr,
                               corrupt_name,
                               f"损坏的 .s.ct 未按预期拒绝: build={corrupt.returncode}\n"
                               f"{corrupt.stderr[-500:]}")
                source_text = source.read_text()
                source_line = next(i for i, line in enumerate(
                    source_text.splitlines(), 1)
                    if "let factor f64 = FACTOR;" in line)
                source_col = (source_text.splitlines()[source_line - 1]
                              .index("FACTOR") + 1)
                original_base_ct = base_body_iface.read_text()
                invalid_base_ct = original_base_ct.replace(
                    "let factor f64 = __yhct_FACTOR__ctmath__base_;",
                    'let factor f64 = "not a float";', 1)
                if invalid_base_ct == original_base_ct:
                    report(False, "ct5b-source-map-semantic-diagnostic",
                           "找不到待破坏的浮点常量引用")
                else:
                    base_body_iface.write_text(invalid_base_ct)
                    try:
                        mapped = sh([compiler, "build"], cwd=host)
                        repaired_base_ct = base_body_iface.read_text() == original_base_ct
                    finally:
                        base_body_iface.write_text(original_base_ct)
                    expected_location = (
                        f"math/src/base/base.yh:{source_line}:{source_col}:")
                    if COMPILER_BACKEND == "llvm":
                        repaired = mapped.returncode == 0 and repaired_base_ct
                        report(repaired, "ct5b-source-map-semantic-diagnostic",
                               f"损坏的 CT 正文接口未触发提供方重编译: "
                               f"build={mapped.returncode}, repaired={repaired_base_ct}\n"
                               f"{mapped.stdout[-300:]} {mapped.stderr[-300:]}")
                    else:
                        report(mapped.returncode != 0
                               and expected_location in mapped.stderr,
                               "ct5b-source-map-semantic-diagnostic",
                               f"导入正文诊断未映射回定义源码: expected={expected_location}\n"
                               f"{mapped.stderr[-500:]}")
                host_main = host / "src" / "main" / "main.yh"
                original_host_main = host_main.read_text()
                host_main.write_text(original_host_main.replace(
                    "$math.double_after_bump(20)",
                    "$math.double_after_bump(21)", 1))
                try:
                    compile_error = sh([compiler, "build"], cwd=host)
                finally:
                    host_main.write_text(original_host_main)
                diag_line = next(i for i, line in enumerate(
                    source_text.splitlines(), 1)
                    if "$compile_error(\"CT5B_SOURCE_MAP\")" in line)
                diag_col = (source_text.splitlines()[diag_line - 1]
                            .index("$compile_error") + 1)
                expected_diag_location = (
                    f"math/src/base/base.yh:{diag_line}:{diag_col}:")
                report(compile_error.returncode != 0
                       and expected_diag_location in compile_error.stderr
                       and "CT5B_SOURCE_MAP" in compile_error.stderr,
                       "ct5b-source-map-compile-error",
                       f"跨模块编译期诊断未映射回定义源码: "
                       f"expected={expected_diag_location}\n"
                       f"{compile_error.stderr[-500:]}")
                original = source.read_text()
                source.write_text(original.replace("const OFFSET int = 1;",
                                                   "const OFFSET int = 2;", 1))
                changed = sh([compiler, "build"], cwd=host)
                rerun = sh([str(program)], cwd=host) if program.exists() else None
                report(changed.returncode == 0 and rerun is not None
                       and rerun.returncode == 2,
                       "ct5b-transitive-body-invalidates-importer",
                       f"私有闭包函数变化后导入方仍复用了旧 CT 结果: "
                       f"build={changed.returncode}, run={rerun.returncode if rerun else None}\n"
                       f"{changed.stderr[-500:]}")
            return out
        if c["kind"] == "comptime-layout-deps":
            built = sh([compiler, "build"], cwd=dst)
            program = dst / ".build" / "comptimelayoutdeps"
            run = sh([str(program)], cwd=dst) if program.exists() else None
            report(built.returncode == 0 and run is not None
                   and run.returncode == 0,
                   c["name"],
                   f"同模块跨源文件 typed CT 布局依赖未按值依赖完成: "
                   f"build={built.returncode}, run={run.returncode if run else None}\n"
                   f"{built.stderr[-500:]}")
            return out
        if c["kind"] == "comptime-expanded-ast":
            built = sh([compiler, "build", "--stats"], cwd=dst)
            lines = [line for line in built.stderr.splitlines()
                     if line.startswith("yh-stats ")]
            program = dst / ".build" / "comptimeexpanded"
            run = sh([str(program)], cwd=dst) if program.exists() else None
            if COMPILER_BACKEND == "llvm":
                checked = sum(stat_value(line, "checked_functions", 0) for line in lines)
                emitted = sum(stat_value(line, "backend_emitted_functions", 0)
                              for line in lines)
                ir_files = backend_text_files(dst)
                report(built.returncode == 0 and checked >= 3 and emitted == checked
                       and bool(ir_files) and run is not None
                       and run_ok(run, c["expect"]),
                       c["name"],
                       f"编译期展开结果未交给 LLVM 后端: build={built.returncode}, "
                       f"checked={checked}, emitted={emitted}, "
                       f"llvm_modules={len(ir_files)}, run={run.returncode if run else None}\n"
                       f"{built.stderr[-500:]}")
            else:
                lowered = sum(stat_value(line, "ir_functions", 0) for line in lines)
                report(built.returncode == 0 and lowered >= 3
                       and run_ok(run, c["expect"]),
                       c["name"],
                       f"普通函数展开未进入稳定 SSA: build={built.returncode}, "
                       f"ir_functions={lowered}, run={run.returncode if run else None}\n"
                       f"{built.stderr[-500:]}")
            return out
        if c["kind"] == "comptime-expanded-budget":
            checked = sh([compiler, "check"], cwd=dst / c["sub"])
            report(checked.returncode != 0
                   and c["msg"] in (checked.stderr + checked.stdout),
                   c["name"],
                   f"实际展开 AST 节点越界未被精确拒绝: rc={checked.returncode}\n"
                   f"{(checked.stderr + checked.stdout)[-500:]}")
            return out
        if c["kind"] == "checked-lower":
            # 纯快照 lowering：受检快照 → 模块 SSA。scalar 必须全量降低并统计出
            # 5 个运行期函数（comptime 不计入）、4 个直接调用与合流/循环携带 phi；
            # pointer 自 LL5 首片起走取址/解引用内存驻留并成功降低；aggregate
            # 仍必须带真实来源整模块拒绝，不发布部分产物。
            built = sh([compiler, "build"], cwd=dst)
            program = dst / ".build" / "llvmlower"
            run = sh([str(program), str(dst / "input" / "scalar.yh"), "0"],
                     cwd=dst) if program.exists() else None
            lower_ok = (built.returncode == 0 and run is not None
                        and run.returncode == 0
                        and "lower-snapshot=ok functions=5 phis=" in run.stdout
                        and " calls=4" in run.stdout
                        and "phis=0" not in run.stdout)
            pointer = sh([str(program), str(dst / "input" / "pointer.yh"), "0"],
                         cwd=dst) if program.exists() else None
            pointer_ok = (pointer is not None and pointer.returncode == 0
                          and "lower-snapshot=ok" in pointer.stdout
                          and "functions=2" in pointer.stdout)
            aggregate = sh([str(program), str(dst / "input" / "aggregate.yh"), "0"],
                           cwd=dst) if program.exists() else None
            aggregate_ok = (aggregate is not None and aggregate.returncode == 0
                            and "lower-snapshot=ok" in aggregate.stdout
                            and "functions=2" in aggregate.stdout)
            slice_ok = sh([str(program), str(dst / "input" / "slice.yh"), "0"],
                          cwd=dst) if program.exists() else None
            slice_lowered = (slice_ok is not None and slice_ok.returncode == 0
                             and "lower-snapshot=ok" in slice_ok.stdout
                             and "functions=2" in slice_ok.stdout)
            global_run = sh([str(program), str(dst / "input" / "global.yh"), "0"],
                            cwd=dst) if program.exists() else None
            global_lowered = (global_run is not None and global_run.returncode == 0
                              and "lower-snapshot=ok" in global_run.stdout
                              and "functions=2" in global_run.stdout)
            rejected = sh([str(program), str(dst / "input" / "globalrejectdepth.yh"), "1"],
                          cwd=dst) if program.exists() else None
            rejects = (rejected is not None and rejected.returncode == 0
                       and "lower-rejected=ok" in rejected.stdout
                       and "rejected_pointer_depth" in rejected.stderr
                       and ".yh:" in rejected.stderr)
            # LA2b：互递归/函数内字符串、嵌套同名局部绑定与中间函数失败。
            mutual = sh([str(program), str(dst / "input" / "mutual.yh"), "0"],
                        cwd=dst) if program.exists() else None
            mutual_ok = (mutual is not None and mutual.returncode == 0
                         and "lower-snapshot=ok functions=4" in mutual.stdout)
            shadow = sh([str(program), str(dst / "input" / "shadow.yh"), "0"],
                        cwd=dst) if program.exists() else None
            shadow_ok = (shadow is not None and shadow.returncode == 0
                         and "lower-snapshot=ok functions=1" in shadow.stdout)
            failmid = sh([str(program), str(dst / "input" / "failmid.yh"), "1"],
                         cwd=dst) if program.exists() else None
            failmid_ok = (failmid is not None and failmid.returncode == 0
                          and "lower-rejected=ok" in failmid.stdout
                          and "首片不支持此绑定类型或参数布局" in failmid.stderr
                          and "failmid.yh:6:" in failmid.stderr)
            # LA3.3 C2：受检 AST 切片离线往返，重建快照后 lowering 身份一致。
            check_slice = sh([str(program), str(dst / "input" / "checkcache.yh"), "2"],
                             cwd=dst) if program.exists() else None
            check_slice_ok = (check_slice is not None
                              and check_slice.returncode == 0
                              and "check-slice=ok" in check_slice.stdout)
            report(lower_ok and pointer_ok and aggregate_ok and slice_lowered
                   and global_lowered and rejects and mutual_ok and shadow_ok
                   and failmid_ok and check_slice_ok, c["name"],
                   f"快照 lowering 覆盖或拒绝路径失败: lower_ok={lower_ok}, "
                   f"pointer_ok={pointer_ok}, aggregate_ok={aggregate_ok}, "
                   f"slice_ok={slice_lowered}, global_ok={global_lowered}, rejects={rejects}, "
                   f"mutual_ok={mutual_ok}, shadow_ok={shadow_ok}, failmid_ok={failmid_ok}, "
                   f"check_slice_ok={check_slice_ok}, "
                   f"build={built.returncode}, run={run.returncode if run else None}, "
                   f"stdout={(run.stdout if run else '')[-120:]!r}\n"
                   f"{(run.stderr if run else built.stderr)[-400:]}")
            return out
        if c["kind"] == "host-capture":
            target = "aarch64-unknown-linux-gnu" if sys.platform == "darwin" else "aarch64-apple-darwin"
            checked = sh([compiler, "-target", target, "check"], cwd=dst)
            report(checked.returncode == 0, c["name"],
                   f"交叉目标不应改变宿主文件标志: rc={checked.returncode}\n"
                   f"{checked.stderr[-400:]} {checked.stdout[-200:]}")
            return out
        if c["kind"] == "stdlib-run":
            run = sh([compiler, "run"], cwd=dst / c["sub"],
                     env={"YH_STDLIB": str(ROOT / "libs")})
            report(run_ok(run, c["expect"])
                   and run.stdout.endswith(c["stdout"]),
                   c["name"],
                   f"退出码 {run.returncode} 期望 {c['expect']}，"
                   f"输出结尾 {run.stdout[-120:]!r} 期望 {c['stdout']!r}\n"
                   f"{run.stderr[-400:]}")
            return out
        if c["kind"] == "default-stdlib-run":
            # 构建门通常把编译器暂存到 $TMPDIR/yh-fast，不能依赖暂存目录旁
            # 恰好有 libs。这里复制一个最小安装布局：
            #   <root>/bin/yh + <root>/share/yh/libs
            # 并以空 YH_STDLIB 启动，真实验证安装布局的默认发现。
            install = dst / "default-install"
            bin_dir = install / "bin"
            libs_dir = install / "share" / "yh" / "libs"
            bin_dir.mkdir(parents=True, exist_ok=True)
            installed_compiler = bin_dir / Path(compiler).name
            try:
                shutil.copy2(compiler, installed_compiler)
                # Windows 安装布局还带 `<exe>/windows-sdk`（just install 会复制），
                # 里面是零 CRT 的 kernel32 导入库；不复制的话装好的编译器只会报
                # 「找不到 Windows 导入库」，默认标准库发现的结论就无从验证。
                if sys.platform == "win32":
                    sdk_env = os.environ.get("YH_WINDOWS_SDK", "")
                    sdk = Path(sdk_env) if sdk_env else ROOT / "tmp" / "llvm-migration" / "windows-sdk"
                    if (sdk / "lib" / "kernel32.lib").is_file():
                        shutil.copytree(sdk, bin_dir / "windows-sdk", dirs_exist_ok=True)
                shutil.copytree(ROOT / "libs", libs_dir,
                                ignore=shutil.ignore_patterns(".build"))
                run = sh([str(installed_compiler), "run"],
                         cwd=dst / c["sub"], env={"YH_STDLIB": ""})
                report(run_ok(run, c["expect"])
                       and run.stdout.endswith(c["stdout"]),
                       c["name"],
                       f"默认标准库发现失败: 退出码 {run.returncode} 期望 {c['expect']}，"
                       f"输出结尾 {run.stdout[-120:]!r} 期望 {c['stdout']!r}\n"
                       f"{run.stderr[-400:]}")
            finally:
                shutil.rmtree(install, ignore_errors=True)
            return out
        if c["kind"] == "envp-run":
            run = sh([compiler, "run"], cwd=dst,
                     env={"YH_ENV_TEST": "present",
                          "YH_STDLIB": str(ROOT / "libs")})
            report(run.returncode == 0, c["name"],
                   f"main(argc, argv, envp) 未收到进程环境: rc={run.returncode}\n"
                   f"{run.stderr[-400:]} {run.stdout[-200:]}")
            return out
        if c["kind"] == "inline":
            built = sh([compiler, "build", "--stats"], cwd=dst)
            asm_files = backend_text_files(dst)
            asm = "\n".join(path.read_text() for path in asm_files)
            binary = dst / ".build" / "example_inline"
            run = sh([str(binary)], cwd=dst) if binary.exists() else None
            if COMPILER_BACKEND == "llvm":
                required_calls = ("call i32 @\"plus_three_",
                                  "call i32 @\"conditional_",
                                  "call i32 @\"public_plus_two_")
                calls_ok = all(symbol in asm for symbol in required_calls)
                report(built.returncode == 0 and calls_ok and run is not None
                       and run.returncode == 0 and run.stdout == "A",
                       c["name"],
                       f"O0 LLVM IR 未保留被调函数或实参副作用: calls={calls_ok}, "
                       f"run={run.returncode if run else None}, "
                       f"stdout={run.stdout if run else ''!r}\n"
                       f"{built.stderr[-400:]}\n{asm[-800:]}")
            else:
                calls = [line for line in asm.splitlines()
                         if line.startswith("\tbl\t")]
                expanded = not any("plus_three" in line for line in calls)
                fallback = any("conditional" in line for line in calls)
                report(built.returncode == 0 and expanded and fallback
                       and any("public_plus_two" in line for line in calls)
                       and run is not None and run.returncode == 0 and run.stdout == "A",
                       c["name"],
                       f"private 标量未展开、复杂/导出函数未回退或实参副作用次数错误: "
                       f"expanded={expanded}, fallback={fallback}, "
                       f"public_fallback={any('public_plus_two' in line for line in calls)}, "
                       f"run={run.returncode if run else None}, "
                       f"stdout={run.stdout if run else ''!r}\n"
                       f"{built.stderr[-400:]}\n{asm[-800:]}")
            source = dst / "src" / "main.yh"
            original = source.read_text()
            source.write_text(original.replace("value + 3", "value + 4", 1))
            changed = sh([compiler, "build", "--stats"], cwd=dst)
            changed_lines = [line for line in changed.stderr.splitlines()
                             if line.startswith("yh-stats ")]
            changed_stats = changed_lines[-1] if changed_lines else ""
            rerun = sh([str(binary)], cwd=dst) if binary.exists() else None
            report(changed.returncode == 0
                   and stat_value(changed_stats, "link") == 1
                   and rerun is not None and rerun.returncode == 1,
                   "i1-inline-callee-invalidates-caller-cache",
                   f"被内联函数体变化后调用方仍复用旧 SSA: "
                   f"link={stat_value(changed_stats, 'link')}, "
                   f"run={rerun.returncode if rerun else None}\n"
                   f"{changed.stderr[-400:]}")
            return out
        if c["kind"] == "ir-call":
            built = sh([compiler, "build", "--stats"], cwd=dst)
            lines = [line for line in built.stderr.splitlines()
                     if line.startswith("yh-stats ")]
            counter = ("backend_emitted_functions" if COMPILER_BACKEND == "llvm"
                       else "ir_functions")
            lowered = sum(stat_value(line, counter, 0) for line in lines)
            asm_files = backend_text_files(dst)
            asm = "\n".join(path.read_text() for path in asm_files)
            symbol_prefix = "_" if sys.platform == "darwin" else ""
            program = dst / ".build" / "ircallmodule"
            run = sh([str(program)], cwd=dst) if program.exists() else None
            if COMPILER_BACKEND == "llvm":
                calls_ok = ("twice__ircallmodule__api_" in asm
                            and "log_note__ircallmodule__api_" in asm)
            else:
                calls_ok = (f"\tbl\t{symbol_prefix}twice__ircallmodule__api_" in asm
                            and f"\tbl\t{symbol_prefix}log_note__ircallmodule__api_" in asm)
            expected_lowered = (lowered >= 4 if COMPILER_BACKEND == "llvm"
                                else lowered == 4)
            report(built.returncode == 0 and expected_lowered and calls_ok
                   and run is not None and run.returncode == 41,
                   c["name"],
                   f"跨模块 SSA 目标或运行结果错误: rc={built.returncode}, "
                   f"{counter}={lowered}, calls={calls_ok}, "
                   f"run={run.returncode if run else None}\n"
                   f"{built.stderr[-500:]}")
            api_source = dst / "src" / "api" / "api.yh"
            original_api = api_source.read_text()
            api_source.write_text(original_api.replace("value * 2", "value * 3"))
            changed = sh([compiler, "build", "--stats"], cwd=dst)
            changed_lines = [line for line in changed.stderr.splitlines()
                             if line.startswith("yh-stats ")]
            last = changed_lines[-1] if changed_lines else ""
            rerun = sh([str(program)], cwd=dst) if program.exists() else None
            changed_emitted = sum(stat_value(line, "backend_emitted_functions", 0)
                                  for line in changed_lines)
            module_rebuilt = (changed_emitted > 0 if COMPILER_BACKEND == "llvm"
                              else stat_value(last, "asm") == 1)
            report(changed.returncode == 0 and module_rebuilt
                   and stat_value(last, "link") == 1
                   and rerun is not None and rerun.returncode == 61,
                   "r2b-cross-module-call-relink",
                   f"公开函数体变化未仅重编提供模块并重新链接: "
                   f"emitted={changed_emitted}, asm={stat_value(last, 'asm')}, "
                   f"link={stat_value(last, 'link')}, "
                   f"run={rerun.returncode if rerun else None}\n{changed.stderr[-500:]}")
            return out
        if c["kind"] == "platform-source":
            native = "aarch64-apple-darwin" if sys.platform == "darwin" \
                else "aarch64-unknown-linux-gnu"
            cross = "aarch64-unknown-linux-gnu" if native == "aarch64-apple-darwin" \
                else "aarch64-apple-darwin"
            expected = 31 if sys.platform == "darwin" else 32
            run = sh([compiler, "run"], cwd=dst)
            report(run.returncode == expected, c["name"],
                   f"本机目标源选择错误: rc={run.returncode}, 期望 {expected}\n"
                   f"{run.stderr[-400:]} {run.stdout[-200:]}")
            checked = sh([compiler, "-target", cross, "check"], cwd=dst)
            report(checked.returncode == 0, "r3-cross-target-source-selection",
                   f"交叉目标未选择对应源文件: target={cross}, rc={checked.returncode}\n"
                   f"{checked.stderr[-400:]} {checked.stdout[-200:]}")
            return out
        if c["kind"] == "darwin-dir-api":
            darwin = sh([compiler, "-target", "aarch64-apple-darwin", "check"], cwd=dst)
            report(darwin.returncode == 0, "r3-getattrlistbulk-darwin-available",
                   f"Darwin 目标未登记目录 OS API: rc={darwin.returncode}\n"
                   f"{darwin.stderr[-400:]}")
            linux = sh([compiler, "-target", "aarch64-unknown-linux-gnu", "check"], cwd=dst)
            report(linux.returncode != 0 and "未声明" in linux.stderr,
                   "r3-getattrlistbulk-not-linux-api",
                   f"Linux 目标意外导入 Darwin API: rc={linux.returncode}\n"
                   f"{linux.stderr[-400:]}")
            return out
        if c["kind"] == "directory-scan":
            # Windows 的 Win32 路径不允许换行等控制字符（NTFS 允许，但
            # CreateFile 直接报 EINVAL），所以“换行”这个名字按平台退化；
            # 空格、引号、非 ASCII 仍然覆盖。
            odd_tag = "space ' 雪" if sys.platform.startswith("win") \
                else "line\nbreak space ' 雪"
            odd_name = dst / (odd_tag + ".yh")
            odd_name.write_text("module main;\npub const DIR_NAME_PROBE int = 1;\n")
            (dst / ".ignored.yh").write_text("module main;\n@\n")
            names = sh([compiler, "check"], cwd=dst)
            report(names.returncode == 0,
                   "r3-directory-filenames-are-byte-safe",
                   f"空格、引号、非 ASCII 或换行文件名扫描失败: rc={names.returncode}\n"
                   f"{names.stderr[-500:]}")
            for i in range(520):
                (dst / f"filler-{i:04d}.yh").write_text("module main;\n")
            (dst / "z-overflow.yh").write_text(
                "module main;\npub const DIR_NAME_PROBE int = 2;\n")
            many = sh([compiler, "check"], cwd=dst)
            report(many.returncode != 0 and "重复的顶层声明" in many.stderr,
                   "r3-directory-enumeration-grows-past-one-batch",
                   f"目录条目超过 512 后未检查末尾源码: rc={many.returncode}\n"
                   f"{many.stderr[-500:]}")
            return out
        if c["kind"] == "linux-syscall-asm":
            if COMPILER_BACKEND == "llvm":
                # 本用例的源文件是 Linux/x64 专属（main.linux.x64.yh）。
                # 只有目标为 Linux 时才验证正向运行；Darwin 等其它目标下
                # 只保留「目标门控拒绝」断言，避免把跨目标的预期拒绝
                # 当成后端缺陷（与运行语料的 // platform: 筛选同思路）。
                target_linux = COMPILER_TARGET is not None and "linux" in COMPILER_TARGET
                if target_linux:
                    emitted = sh([compiler, "--emit-asm", "main.linux.x64.yh"], cwd=dst)
                    asm = emitted.stdout
                    built = sh([compiler, "build"], cwd=dst)
                    program = dst / ".build" / "linuxsyscall"
                    run = sh([str(program)], cwd=dst) if program.exists() else None
                    report(emitted.returncode == 0 and "syscall" in asm
                           and "linux_syscall6" in asm and built.returncode == 0
                           and run is not None and run.returncode == 0,
                           c["name"],
                           f"Linux x64 syscall 运行时/函数值入口失败: "
                           f"emit={emitted.returncode}, build={built.returncode}, "
                           f"run={run.returncode if run else None}\n"
                           f"{emitted.stderr[-400:]}\n{asm[-1000:]}")
                    report("linux_syscall6" in asm and "syscall" in asm,
                           "r3-linux-syscall-function-value-has-local-entry",
                           "Linux syscall 函数值没有 LLVM ABI 入口")
                darwin = sh([compiler, "-target", "aarch64-apple-darwin", "--emit-asm",
                             "main.linux.x64.yh"], cwd=dst)
                report(darwin.returncode != 0 and "未声明" in darwin.stderr,
                       "r3-linux-syscall-is-target-gated",
                       f"Darwin 目标意外接受 Linux 系统调用接口: "
                       f"rc={darwin.returncode}\n{darwin.stderr[-400:]}")
            else:
                emitted = sh([compiler, "-target", "aarch64-unknown-linux-gnu", "--emit-asm",
                              "main.linux.arm64.yh"], cwd=dst)
                asm = emitted.stdout
                report(emitted.returncode == 0 and "mov\tx8, x0" in asm
                       and "mov\tx0, x1" in asm and "mov\tx5, x6" in asm
                       and "svc\t#0" in asm
                       and "\n\tbl\tlinux_syscall6\n" not in asm,
                       c["name"],
                       f"Linux AArch64 syscall 没有内联发射: rc={emitted.returncode}\n"
                       f"{emitted.stderr[-400:]}\n{asm[-1200:]}")
                report("\nlinux_syscall6:\n" in asm,
                       "r3-linux-syscall-function-value-has-local-entry",
                       "Linux syscall intrinsic 的函数值引用没有本地 ABI 入口，可能产生未定义符号")
                darwin = sh([compiler, "-target", "aarch64-apple-darwin", "--emit-asm",
                             "main.linux.arm64.yh"], cwd=dst)
                report(darwin.returncode != 0 and "未声明" in darwin.stderr,
                       "r3-linux-syscall-is-target-gated",
                       f"Darwin 目标意外接受 Linux 系统调用接口: "
                       f"rc={darwin.returncode}\n{darwin.stderr[-400:]}")
            return out
        if c["kind"] == "mode-cache":
            first = sh([compiler, "build", "--legacy-system", "--stats"], cwd=dst)
            first_stats = [line for line in first.stderr.splitlines()
                           if line.startswith("yh-stats ")]
            first_stats = first_stats[-1] if first_stats else ""
            report(first.returncode == 0 and stat_value(first_stats, "link") == 1,
                   "r3-link-cache-first-profile",
                   f"兼容配置首次构建未链接: rc={first.returncode}\n{first.stderr[-400:]}")
            switched = sh([compiler, "build", "--stats"], cwd=dst)
            switched_stats = [line for line in switched.stderr.splitlines()
                              if line.startswith("yh-stats ")]
            switched_stats = switched_stats[-1] if switched_stats else ""
            report(switched.returncode == 0
                   and stat_value(switched_stats, "asm") == 0
                   and stat_value(switched_stats, "link") == 1,
                   "r3-link-cache-profile-isolation",
                   f"切换默认配置后应复用对象并重新链接: {switched_stats}\n"
                   f"{switched.stderr[-400:]}")
            hot = sh([compiler, "build", "--stats"], cwd=dst)
            hot_stats = [line for line in hot.stderr.splitlines()
                         if line.startswith("yh-stats ")]
            hot_stats = hot_stats[-1] if hot_stats else ""
            report(hot.returncode == 0 and stat_value(hot_stats, "asm") == 0
                   and stat_value(hot_stats, "link") == 0,
                   "r3-link-cache-same-profile-hit",
                   f"相同默认配置未命中链接缓存: {hot_stats}\n{hot.stderr[-400:]}")
            return out
        if c["kind"] == "legacy-system":
            default = sh([compiler, "build"], cwd=dst)
            report(default.returncode != 0,
                   "r3-system-hidden-by-default",
                   f"默认配置仍暴露 system: rc={default.returncode}\n"
                   f"{default.stderr[-400:]}")
            compat = sh([compiler, "build", "--legacy-system"], cwd=dst)
            report(compat.returncode == 0 and (dst / ".build" / "legacy_system").exists(),
                   "r3-system-compat-build",
                   f"兼容配置未提供 system: rc={compat.returncode}\n"
                   f"{compat.stderr[-400:]}")
            strict_after = sh([compiler, "build"], cwd=dst)
            report(strict_after.returncode != 0,
                   "r3-system-cache-mode-isolation",
                   f"默认配置复用了兼容缓存: rc={strict_after.returncode}\n"
                   f"{strict_after.stderr[-400:]}")
            checked = sh([compiler, "check", "--legacy-system"], cwd=dst)
            report(checked.returncode == 0,
                   "r3-system-compat-check",
                   f"兼容配置语义检查失败: rc={checked.returncode}\n"
                   f"{checked.stderr[-400:]}")
            run = sh([compiler, "run", "--legacy-system"], cwd=dst)
            report(run.returncode == 0, "r3-system-compat-run",
                   f"兼容配置运行失败: rc={run.returncode}\n{run.stderr[-400:]}")
            return out
        if c["kind"] == "ir":
            if COMPILER_BACKEND == "llvm":
                r = sh([compiler, "build", "--stats"], cwd=dst)
                lines = [line for line in r.stderr.splitlines()
                         if line.startswith("yh-stats ")]
                checked = sum(stat_value(line, "checked_functions", 0)
                              for line in lines)
                emitted = sum(stat_value(line, "backend_emitted_functions", 0)
                              for line in lines)
                llvm_files = backend_text_files(dst)
                llvm_ir = "\n".join(path.read_text() for path in llvm_files)
                built = dst / ".build" / "irfront"
                report(r.returncode == 0 and checked == 56 and emitted == checked
                       and built.exists() and bool(llvm_files),
                       c["name"],
                       f"LLVM 未完整发射项目函数: rc={r.returncode}, checked={checked}, "
                       f"emitted={emitted}, modules={len(llvm_files)}\n{r.stderr[-500:]}")
                report("phi i32" in llvm_ir and "icmp slt" in llvm_ir,
                       "llvm-control-flow-and-comparison",
                       "LLVM IR 缺少分支合流或有符号比较")
                operations = ("sdiv i64", "srem i64", "udiv i64", "urem i64",
                              "and i64", "or i64", "xor i64", "shl i64",
                              "lshr i64", "ashr i64")
                missing_operations = [op for op in operations if op not in llvm_ir]
                report(not missing_operations, "llvm-integer-operation-lowering",
                       f"LLVM IR 缺少整数操作: {missing_operations}")
                calls = ("call_nine__irfront__main_", "call_tick__irfront__main_",
                         "log_unit__irfront__main_", "log_noop__irfront__main_",
                         "discarded_result__irfront__main_")
                missing_calls = [name for name in calls if name not in llvm_ir]
                report(not missing_calls, "llvm-direct-call-lowering",
                       f"LLVM IR 缺少直接调用: {missing_calls}")
                rcheck = sh([compiler, "check", "--stats"], cwd=dst)
                check_lines = [line for line in rcheck.stderr.splitlines()
                               if line.startswith("yh-stats ")]
                check_ir = sum(stat_value(line, "ir_functions", 0)
                               for line in check_lines)
                check_functions = sum(stat_value(line, "ast_functions", 0)
                                      for line in check_lines)
                report(rcheck.returncode == 0 and check_ir == 0
                       and check_functions == 56,
                       "r2b-check-stops-before-ir",
                       f"yh check 越过 IR 边界或函数上下文缺失: "
                       f"rc={rcheck.returncode}, ir_functions={check_ir}, "
                       f"ast_functions={check_functions}\n{rcheck.stderr[-400:]}")
                run = sh([str(built)], cwd=dst) if built.exists() else None
                report(run_ok(run, c["expect"]),
                       "r2b-built-program-runs",
                       f"程序退出码 {run.returncode if run else '未生成'} "
                       f"期望 {c['expect']}")
                return out
            # Windows 检出（core.autocrlf）下工作树是 CRLF：本用例随后会改写
            # 源文件触发增量构建，行尾差异会使 IR 缓存键全量失效；先统一规范
            # 化为 LF（与后续 751 行的字节比较基准一致，替换前 normalize 亦同）。
            ir_main = dst / "main" / "main.yh"
            ir_main.write_bytes(ir_main.read_bytes().replace(b"\r\n", b"\n"))
            r = sh([compiler, "build", "--stats"], cwd=dst)
            built = dst / ".build" / "irfront"
            build_stat = next((line for line in r.stderr.splitlines()
                               if line.startswith("yh-stats ")), "")
            build_ir = int(build_stat.split("ir_functions=", 1)[1].split()[0]) \
                if "ir_functions=" in build_stat else 0
            build_functions = stat_value(build_stat, "ast_functions", 0)
            initial_ir_misses = stat_value(build_stat, "ir_cache_misses")
            report(r.returncode == 0 and build_ir == 54 and initial_ir_misses >= 54
                   and build_functions == 56 and built.exists(),
                   c["name"],
                   f"build 未生成/缓存 SSA: rc={r.returncode}, ir_functions={build_ir}, "
                   f"ast_functions={build_functions}, ir_cache_misses={initial_ir_misses}\n"
                   f"{r.stderr[-400:]}")
            asm_files = backend_text_files(dst)
            asm = "\n".join(path.read_text() for path in asm_files)
            backend_functions = asm.count(".p2align 2")
            report(backend_functions == build_ir,
                   "r2a-ssa-backend-owns-functions",
                   f"已降低的 SSA 函数没有全部由新后端发射: "
                   f"ssa={build_ir}, backend={backend_functions}\n{asm[-600:]}")
            phi_caches = list((artifact_root(dst) / "ir").glob("*.ir"))
            report(sum(has_two_edge_phi(path) for path in phi_caches) >= 2,
                   "r2c-branch-assignment-phi",
                   "参数/局部在 if/else 两侧更新后，持久 SSA 中缺少双前驱 phi 四块 CFG")
            less_count = sum(count_ir_op(path, 12) for path in phi_caches)
            report(less_count == 7, "r2a-ssa-folded-comparison",
                   f"编译期常量小于比较未折叠，预期动态小于比较保留，实际 IR_OP_LT={less_count}")
            integer_ops = {16: 3, 17: 3, 18: 1, 19: 1, 20: 1, 21: 1, 22: 2}
            actual_ops = {op: sum(count_ir_op(path, op) for path in phi_caches)
                          for op in integer_ops}
            report(actual_ops == integer_ops, "r2a-ssa-integer-operations",
                   f"除模、位运算或移位未由 SSA 降低并简化: {actual_ops}")
            call_ops = sum(count_ir_op(path, 23) for path in phi_caches)
            symbol_prefix = "_" if sys.platform == "darwin" else ""
            report(call_ops == 36
                   and f"\tbl\t{symbol_prefix}call_nine__irfront__main_" in asm
                   and asm.count(f"\tbl\t{symbol_prefix}call_tick__irfront__main_") == 2
                   and asm.count(f"\tbl\t{symbol_prefix}log_unit__irfront__main_") == 3
                   and f"\tbl\t{symbol_prefix}log_noop__irfront__main_" in asm
                   and f"\tbl\t{symbol_prefix}discarded_result__irfront__main_" in asm,
                   "r2a-ssa-direct-call-abi",
                   f"直接调用未完整降低、保序或传递第九参数: calls={call_ops}")
            rcheck = sh([compiler, "check", "--stats"], cwd=dst)
            check_stat = next((line for line in rcheck.stderr.splitlines()
                               if line.startswith("yh-stats ")), "")
            check_ir = int(check_stat.split("ir_functions=", 1)[1].split()[0]) \
                if "ir_functions=" in check_stat else -1
            check_functions = stat_value(check_stat, "ast_functions", 0)
            report(rcheck.returncode == 0 and check_ir == 0 and check_functions == 56,
                   "r2b-check-stops-before-ir",
                   f"yh check 越过 IR 边界或函数上下文缺失: rc={rcheck.returncode}, "
                   f"ir_functions={check_ir}, ast_functions={check_functions}\n"
                   f"{rcheck.stderr[-400:]}")

            source = dst / "main" / "main.yh"
            # Windows 检出（core.autocrlf）下工作树是 CRLF，直接字节匹配会
            # 失败；比较与改写都在规范化（LF）文本上进行。
            original = source.read_bytes().replace(b"\r\n", b"\n")
            main_body = (b"return choose_true() + choose_false() + from_param(7) + "
                         b"local_left() + local_right()\n"
                         b"        + branch_update(10, true) + branch_update(10, false) "
                         b"+ backend_add_params(1, 2)\n"
                         b"        + branch_local(true) + branch_local(false)\n"
                         b"        + compare_eq(2, 3) + compare_eq(3, 3)\n"
                         b"        + compare_ne(2, 3) + compare_ne(3, 3)\n"
                         b"        + compare_lt(2, 3) + compare_lt(3, 2)\n"
                         b"        + compare_le(2, 3) + compare_le(3, 2)\n"
                         b"        + compare_gt(3, 2) + compare_gt(2, 3)\n"
                         b"        + compare_ge(3, 3) + compare_ge(2, 3) + unsigned_score()\n"
                         b"        + folded_signed_lt();")
            changed_main = (b"return choose_true() + choose_false() + from_param(7) + "
                            b"local_left() + local_right()\n"
                            b"        + branch_update(10, true) + branch_update(10, false) "
                            b"+ backend_add_params(1, 2)\n"
                            b"        + branch_local(true) + branch_local(false)\n"
                            b"        + compare_eq(2, 3) + compare_eq(3, 3)\n"
                            b"        + compare_ne(2, 3) + compare_ne(3, 3)\n"
                            b"        + compare_lt(2, 3) + compare_lt(3, 2)\n"
                            b"        + compare_le(2, 3) + compare_le(3, 2)\n"
                            b"        + compare_gt(3, 2) + compare_gt(2, 3)\n"
                            b"        + compare_ge(3, 3) + compare_ge(2, 3) + unsigned_score()\n"
                            b"        + folded_signed_lt() + 0;")
            if original.count(main_body) != 1:
                report(False, "r2c-ir-cache-fixture", "入口函数体不匹配预期")
            else:
                source.write_bytes(original.replace(main_body, changed_main, 1))
                hot_ir = sh([compiler, "build", "--stats"], cwd=dst)
                hot_stats = next((line for line in hot_ir.stderr.splitlines()
                                  if line.startswith("yh-stats ")), "")
                hot_hits = stat_value(hot_stats, "ir_cache_hits")
                hot_misses = stat_value(hot_stats, "ir_cache_misses")
                # 回退函数（形态不支持，如全局赋值、逻辑或）从不写缓存，
                # 每次构建都会计入 miss；期望失效数 = 修改函数 1 + 回退数。
                ir_fallbacks = build_functions - build_ir
                report(hot_ir.returncode == 0 and hot_hits == build_ir - 1
                       and hot_misses == 1 + ir_fallbacks,
                       "r2c-function-ir-cache-hit",
                       f"main 函数变化后未精确失效一个 IR 缓存: hits={hot_hits}, "
                       f"misses={hot_misses}\n{hot_ir.stderr[-400:]}")

                local_body = (b"fn local_left() int {\n    let item int = 13;\n"
                              b"    item += 1;\n    item *= 2;\n    item -= 1;\n"
                              b"    return item;\n}")
                changed_local = (b"fn local_left() int {\n    let item int = 14;\n"
                                 b"    item += 1;\n    item *= 2;\n    item -= 1;\n"
                                 b"    return item;\n}")
                changed_source = source.read_bytes()
                if changed_source.count(local_body) != 1:
                    report(False, "r2c-function-ir-cache-invalidate",
                           "local_left 函数体不匹配预期")
                else:
                    source.write_bytes(changed_source.replace(local_body, changed_local, 1))
                    body_ir = sh([compiler, "build", "--stats"], cwd=dst)
                    body_stats = next((line for line in body_ir.stderr.splitlines()
                                       if line.startswith("yh-stats ")), "")
                    body_hits = stat_value(body_stats, "ir_cache_hits")
                    body_misses = stat_value(body_stats, "ir_cache_misses")
                    report(body_ir.returncode == 0 and body_hits == build_ir - 1
                           and body_misses == 1 + ir_fallbacks,
                           "r2c-function-ir-cache-invalidate",
                           f"单个含局部变量函数变化未精确失效: hits={body_hits}, "
                           f"misses={body_misses}\n"
                           f"{body_ir.stderr[-400:]}")
                    current_source = source.read_bytes()
                    source.write_bytes(current_source.replace(changed_local, local_body, 1))
                    ir_files = sorted((artifact_root(dst) / "ir").glob("*.ir"))
                    if len(ir_files) < 35:
                        report(False, "r2c-function-ir-cache-corrupt",
                               f"函数 IR 缓存数不足: {len(ir_files)}")
                    else:
                        for ir_file in ir_files:
                            ir_file.write_bytes(b"corrupt IR cache\n")
                        current_source = source.read_bytes()
                        stable_main = changed_main
                        touched_main = changed_main.replace(b" + 0;", b" + 0 + 0;", 1)
                        if current_source.count(stable_main) != 1:
                            report(False, "r2c-function-ir-cache-corrupt",
                                   "入口函数体不匹配缓存损坏探针")
                        else:
                            source.write_bytes(current_source.replace(stable_main, touched_main, 1))
                            corrupt_ir = sh([compiler, "build", "--stats"], cwd=dst)
                            corrupt_stats = next((line for line in corrupt_ir.stderr.splitlines()
                                                  if line.startswith("yh-stats ")), "")
                            corrupt_hits = stat_value(corrupt_stats, "ir_cache_hits")
                            corrupt_misses = stat_value(corrupt_stats, "ir_cache_misses")
                            report(corrupt_ir.returncode == 0 and corrupt_hits == 0
                                   and corrupt_misses >= 35,
                                   "r2c-function-ir-cache-corrupt",
                                   f"损坏函数缓存未拒绝并重建: hits={corrupt_hits}, "
                                   f"misses={corrupt_misses}\n{corrupt_ir.stderr[-400:]}")
            run = sh([str(built)], cwd=dst) if built.exists() else None
            report(run_ok(run, c["expect"]),
                   "r2b-built-program-runs",
                   f"程序退出码 {run.returncode if run else '未生成'} 期望 {c['expect']}")
            return out
        if c["kind"] == "scheduler":
            api_source = dst / "src" / "api" / "api.yh"
            extra = "".join(
                f"pub fn private_{i:04d}() int {{ return {i % 10}; }}\n"
                for i in range(600)
            )
            api_source.write_text(api_source.read_text() + "\n" + extra)
            r = sh([compiler, "build", "--stats"], cwd=dst)
            stats = [line for line in r.stderr.splitlines()
                     if line.startswith("yh-stats ") and "workers_peak=" in line]
            parent_stats = stats[-1] if stats else ""
            peak = stat_value(parent_stats, "workers_peak")
            early = stat_value(parent_stats, "iface_early")
            built = dst / ".build" / "scheduler"
            report(r.returncode == 0 and peak >= 2 and early >= 1
                   and built.exists(),
                   "r2b-interface-ready-parallel-build",
                   f"接口就绪前未并行推进消费者: rc={r.returncode}, peak={peak}, "
                   f"early={early}\n{r.stderr[-500:]}")
            iface_dir = artifact_root(dst) / "iface"
            persisted = list(iface_dir.glob("*.s.i"))
            session_files = list(iface_dir.glob("*.session-*"))
            report(r.returncode == 0 and len(persisted) == 2 and not session_files,
                   "r2b-session-interface-commit",
                   f"持久接口提交或本轮临时接口清理失败: "
                   f"persistent={len(persisted)}, session={len(session_files)}")
            # 头行架构随目标走（arm64/x64），用例只看「v1 且无属性扩展」：
            # 架构标记必须是支持值之一，但不得写死 arm64（x86_64 目标是 arch=x64）。
            plain_v1 = all(
                re.match(r"// yh-iface v1 arch=(arm64|x64) suffix=",
                         p.read_text()) for p in persisted)
            report(plain_v1, "u1-attribute-free-iface-keeps-v1",
                   "无属性公开接口没有保持 v1 头行")
            if built.exists():
                run = sh([str(built)], cwd=dst)
                report(run.returncode == 42, "r2b-scheduled-program-runs",
                       f"程序退出码 {run.returncode} 期望 42")
            else:
                report(False, "r2b-scheduled-program-runs", "调度后没有生成程序")

            # 接口成功发布后，提供方私有函数仍可能检查失败；本轮不得链接。
            built.unlink(missing_ok=True)
            # 私有函数体内引用未定义名字：检查必须在 pass2 报错并阻止链接。
            # 用一个 pub 入口引用它，避免被 UF1（未使用函数检查）先拦下来，
            # 保证这条断言仍然验证「正文检查失败」而不是「未使用」。
            api_source.write_text(api_source.read_text() +
                                  "\nfn broken_private() int { return missing_name; }\n"
                                  "pub fn broken_entry() int { return broken_private(); }\n")
            failed_build = sh([compiler, "build"], cwd=dst)
            report(failed_build.returncode != 0 and not built.exists(),
                   "r2b-worker-failure-stops-link",
                   f"worker 失败后错误地产生最终程序: rc={failed_build.returncode}\n"
                   f"{failed_build.stderr[-400:]}")

            spaced = WORK / "scheduler argv ' with spaces"
            copy_proj(PROJ / "scheduler", spaced)
            launcher_dir = spaced / ".launcher"
            launcher_dir.mkdir(exist_ok=True)
            # Windows：PATH 查找只认带扩展名的可执行文件，且普通用户默认没有
            # 创建符号链接的特权（WinError 1314）——改用副本 + .exe 名字。
            windows_host = sys.platform.startswith("win")
            launcher = launcher_dir / ("yh.exe" if windows_host else "yh")
            try:
                launcher.symlink_to(COMPILER_PATH)
            except OSError:
                shutil.copyfile(COMPILER_PATH, launcher)
                launcher.chmod(0o755)
            path_env = str(launcher_dir) + os.pathsep + \
                os.environ.get("PATH", "")
            # Windows 上 subprocess 的 ["yh.exe"] 走 CreateProcess 的 PATH 搜索
            # 与 POSIX execvp 不同（实测找不到带引号目录里的副本），改用
            # 启动器全路径；PATH 仍然前置，编译器内部按 PATH 找工具的行为不变。
            spaced_cmd = [str(launcher), "build"] if windows_host                 else ["yh", "build"]
            spaced_build = sh(spaced_cmd, cwd=spaced,
                              env={"PATH": path_env})
            spaced_program = spaced / ".build" / "scheduler"
            report(spaced_build.returncode == 0 and spaced_program.exists(),
                   "r2b-fork-worker-space-paths",
                   f"PATH 启动及含空格/引号项目路径未能由 fork 快照 worker 构建: "
                   f"rc={spaced_build.returncode}\n"
                   f"{spaced_build.stderr[-400:]} {spaced_build.stdout[-300:]}")
            return out
        if c["kind"] == "scheduler-diamond":
            base_source = dst / "src" / "base" / "base.yh"
            extra = "".join(
                f"pub fn private_{i:04d}() int {{ return {i % 10}; }}\n"
                for i in range(600)
            )
            base_source.write_text(base_source.read_text() + "\n" + extra)
            r = sh([compiler, "build", "--stats"], cwd=dst)
            stats = [line for line in r.stderr.splitlines()
                     if line.startswith("yh-stats ") and "workers_peak=" in line]
            parent_stats = stats[-1] if stats else ""
            peak = stat_value(parent_stats, "workers_peak")
            early = stat_value(parent_stats, "iface_early")
            built = dst / ".build" / "scheduler_diamond"
            report(r.returncode == 0 and peak >= 3 and early >= 2
                   and built.exists(),
                   "r2b-diamond-branches-parallel",
                   f"菱形 DAG 未并行启动两个分支并提前推进: rc={r.returncode}, "
                   f"peak={peak}, early={early}\n{r.stderr[-500:]}")
            iface_dir = artifact_root(dst) / "iface"
            persisted = list(iface_dir.glob("*.s.i"))
            session_files = list(iface_dir.glob("*.session-*"))
            report(r.returncode == 0 and len(persisted) == 4 and not session_files,
                   "r2b-diamond-session-commit",
                   f"菱形 DAG 接口提交/会话清理失败: "
                   f"persistent={len(persisted)}, session={len(session_files)}")
            if built.exists():
                run = sh([str(built)], cwd=dst)
                report(run.returncode == 42, "r2b-diamond-program-runs",
                       f"程序退出码 {run.returncode} 期望 42")
            else:
                report(False, "r2b-diamond-program-runs", "菱形调度后没有生成程序")
            return out
        if c["name"] == "u3-c-source-object-library-mix":
            cc = "clang" if sys.platform == "darwin" else "gcc"
            # WSL 的 ARM64 过渡种子需要把 crossbin/gcc 放在 PATH 首位；
            # x64 LLVM 用例的 C fixture 必须由宿主 gcc 生成同机型对象。
            if (COMPILER_BACKEND == "llvm" and COMPILER_TARGET
                    and COMPILER_TARGET.startswith("x86_64-")
                    and sys.platform == "linux"):
                cc = "/usr/bin/gcc"
            obj = dst / "vendor" / "prebuilt.o"
            obj.parent.mkdir(parents=True, exist_ok=True)
            prepared = sh([cc, "-c", "vendor/prebuilt.c", "-o",
                           "vendor/prebuilt.o"], cwd=dst)
            if prepared.returncode != 0:
                report(False, c["name"],
                       f"测试预编译对象失败: {prepared.stderr[-400:]}")
                return out
        r = sh([compiler, "run"] if c["kind"] == "run" else [compiler, "build"],
               cwd=dst / c["sub"])
        if c["kind"] == "run":
            report(exit_code(r.returncode) == exit_code(c["expect"]), c["name"],
                   f"退出码 {r.returncode} 期望 {c['expect']}\n{r.stderr[-400:]}")
            if c["name"] == "u3-c-source-object-library-mix":
                c_source = dst / "cdep" / "c" / "mathshim.c"
                original_c = c_source.read_text()
                before_objects = {p.name: p.read_bytes()
                                  for p in (artifact_root(dst) / "obj").glob("c-*.o")}
                changed_c = original_c.replace("lrint(value)", "lrint(value + 1.0)")
                c_source.write_text(changed_c)
                changed_build = sh([compiler, "build", "--stats"], cwd=dst)
                changed_objects = [p.name for p in (artifact_root(dst) / "obj").glob("c-*.o")
                                   if before_objects.get(p.name) != p.read_bytes()]
                changed_stats = [line for line in changed_build.stderr.splitlines()
                                 if line.startswith("yh-stats ")]
                changed_stats = changed_stats[-1] if changed_stats else ""
                c_binary = dst / ".build" / "example_cinterop"
                changed_run = sh([str(c_binary)], cwd=dst) if c_binary.exists() else None
                report(changed_c != original_c and changed_build.returncode == 0
                       and stat_value(changed_stats, "link") == 1
                       and changed_run is not None and changed_run.returncode == 1,
                       "u3-c-source-invalidates-link-cache",
                       f"依赖 C 源变化未重编译并重新链接: changed={changed_c != original_c}, "
                       f"objects={changed_objects}, link={stat_value(changed_stats, 'link')}, "
                       f"run={changed_run.returncode if changed_run else None}\n"
                       f"{changed_build.stdout[-200:]} {changed_build.stderr[-400:]}")
                c_source.write_text(original_c)
                restored = sh([compiler, "run"], cwd=dst)
                report(restored.returncode == 0, "u3-c-source-restore-build",
                       f"恢复依赖 C 源后构建/运行失败: rc={restored.returncode}\n"
                       f"{restored.stderr[-400:]}")

                c_header = dst / "cdep" / "c" / "value.h"
                original_header = c_header.read_text()
                c_header.write_text("#define CDEP_BIAS 1\n")
                header_build = sh([compiler, "build", "--stats"], cwd=dst)
                header_stats = [line for line in header_build.stderr.splitlines()
                                if line.startswith("yh-stats ")]
                header_stats = header_stats[-1] if header_stats else ""
                header_run = sh([str(c_binary)], cwd=dst) if c_binary.exists() else None
                report(header_build.returncode == 0
                       and stat_value(header_stats, "link") == 1
                       and header_run is not None and header_run.returncode == 1,
                       "u3-c-header-invalidates-link-cache",
                       f"依赖头文件变化未触发 C 重编译和链接: "
                       f"link={stat_value(header_stats, 'link')}, "
                       f"run={header_run.returncode if header_run else None}\n"
                       f"{header_build.stderr[-400:]}")
                c_header.write_text(original_header)
                header_restored = sh([compiler, "run"], cwd=dst)
                report(header_restored.returncode == 0,
                       "u3-c-header-restore-build",
                       f"恢复依赖头文件后构建/运行失败: "
                       f"rc={header_restored.returncode}\n{header_restored.stderr[-400:]}")

                prebuilt_source = dst / "vendor" / "prebuilt.c"
                original_prebuilt_source = prebuilt_source.read_text()
                prebuilt_source.write_text(original_prebuilt_source.replace("return 42;", "return 41;"))
                changed_object = sh([cc, "-c", "vendor/prebuilt.c", "-o",
                                     "vendor/prebuilt.o"], cwd=dst)
                object_build = sh([compiler, "build", "--stats"], cwd=dst)
                object_stats = [line for line in object_build.stderr.splitlines()
                                if line.startswith("yh-stats ")]
                object_stats = object_stats[-1] if object_stats else ""
                object_run = sh([str(c_binary)], cwd=dst) if c_binary.exists() else None
                report(changed_object.returncode == 0 and object_build.returncode == 0
                       and stat_value(object_stats, "link") == 1
                       and object_run is not None and object_run.returncode == 3,
                       "u3-c-object-content-invalidates-link-cache",
                       f"预编译对象内容变化未触发重新链接: "
                       f"link={stat_value(object_stats, 'link')}, "
                       f"run={object_run.returncode if object_run else None}\n"
                       f"{changed_object.stderr[-300:]} {object_build.stderr[-400:]}")
                prebuilt_source.write_text(original_prebuilt_source)
                restored_object = sh([cc, "-c", "vendor/prebuilt.c", "-o",
                                      "vendor/prebuilt.o"], cwd=dst)
                object_restored = sh([compiler, "run"], cwd=dst)
                report(restored_object.returncode == 0 and object_restored.returncode == 0,
                       "u3-c-object-restore-build",
                       f"恢复预编译对象后构建/运行失败: "
                       f"rc={object_restored.returncode}\n{object_restored.stderr[-400:]}")

                c_source.write_text("int broken( {\n")
                broken = sh([compiler, "build"], cwd=dst)
                report(broken.returncode != 0,
                       "u3-c-source-failure-does-not-use-stale-object",
                       f"无效 C 源意外复用了旧对象: rc={broken.returncode}\n"
                       f"{broken.stderr[-400:]}")
                c_source.write_text(original_c)
                recovered = sh([compiler, "run"], cwd=dst)
                report(recovered.returncode == 0, "u3-c-source-recovery",
                       f"C 编译失败后恢复构建失败: rc={recovered.returncode}\n"
                       f"{recovered.stderr[-400:]}")

                spaced = WORK / "cinterop argv with spaces"
                copy_proj(PROJ / "cinterop", spaced)
                space_obj = spaced / "vendor" / "prebuilt.o"
                space_obj.parent.mkdir(parents=True, exist_ok=True)
                prepared_space = sh([cc, "-c", "vendor/prebuilt.c", "-o",
                                     "vendor/prebuilt.o"], cwd=spaced)
                space_run = sh([compiler, "run"], cwd=spaced) \
                    if prepared_space.returncode == 0 else None
                report(space_run is not None and space_run.returncode == 0,
                       "u3-c-paths-with-spaces-use-argv",
                       f"含空格项目路径未能编译/链接: "
                       f"run={space_run.returncode if space_run else None}\n"
                       f"{prepared_space.stderr[-300:]} "
                       f"{space_run.stderr[-400:] if space_run else ''}")
            if c["name"] == "u1-extern-abs-module":
                # run 形态不会自动带 --emit-llvm；显式补一次 build，确保下面的
                # noreturn 检查读到本轮 LLVM 文本（fresh workdir 没有旧 .ll）。
                sh([compiler, "build"], cwd=dst / c["sub"])
                ir_files = list((artifact_root(dst / c["sub"]) / "ir").glob("*.ir"))
                asm_files = backend_text_files(dst / c["sub"])
                asm = "\n".join(path.read_text() for path in asm_files)
                if COMPILER_BACKEND == "llvm":
                    noreturn_ok = "unreachable" in asm and "@llvm.trap()" in asm
                else:
                    noreturn_ok = (any(has_ir_term(path, 4) for path in ir_files)
                                   and "brk\t#0" in asm)
                report(noreturn_ok, "u2-noreturn-ssa-and-trap",
                       "接口 noreturn 未形成 LLVM unreachable 或后端陷阱")
                iface = artifact_root(dst / c["sub"]) / "iface" / \
                    "example_externabs_lib-lib.s.i"
                iface_text = iface.read_text() if iface.exists() else ""
                report(iface_text.startswith("// yh-iface v2")
                       and "@[extern, noreturn]\npub fn _Exit" in iface_text
                       and "@[inline]\npub fn plus_two" in iface_text,
                       "u1-attribute-iface-v2",
                       f"属性接口未升级 v2 或未按固定顺序归一化: {iface_text[:240]!r}")
                lib_source = dst / "lib" / "src" / "l.yh"
                original_lib = lib_source.read_text()
                old_stop_attr = "@[noreturn]\npub fn stop"
                changed_lib = original_lib.replace(old_stop_attr, "pub fn stop", 1)
                lib_source.write_text(changed_lib)
                attr_build = sh([compiler, "build", "--stats"], cwd=dst / "host")
                attr_iface = iface.read_text() if iface.exists() else ""
                host_asm = backend_text_files(dst / "host")
                main_text = next((path.read_text() for path in host_asm
                                  if "example_externabs_host-main" in str(path)), "")
                if COMPILER_BACKEND == "llvm":
                    # LLVM 后端会给跨模块符号追加 ABI 后缀 `$yhllvmv1`，
                    # 因此只匹配名字前缀，不假设裸名结尾。
                    stop_call = 'call void @"stop__example_externabs_lib__lib_'
                    stop_pos = main_text.find(stop_call)
                    # 只看本函数体：文件尾还有 weak runtime helper 定义，
                    # 同样含 unreachable，截到文件尾会把它们误当调用方控制流。
                    after_stop = ""
                    if stop_pos >= 0:
                        tail = main_text[stop_pos:]
                        end = tail.find("\n}")
                        after_stop = tail if end < 0 else tail[:end]
                    five = after_stop.find("add i32 0, 5")
                    control_ok = (stop_pos >= 0
                                  and "call void @llvm.trap()" not in after_stop
                                  and "unreachable" not in after_stop
                                  and five >= 0
                                  and after_stop.find("ret i32 ", five) >= 0)
                else:
                    control_ok = ("\tbrk\t#0" not in main_text
                                  and "movz\tx0, #5" in main_text)
                report(changed_lib != original_lib and attr_build.returncode == 0
                       and "@[noreturn]\npub fn stop" not in attr_iface
                       and control_ok,
                       "u2-attribute-interface-invalidates-caller-ir",
                       f"noreturn 属性变化未更新接口与调用方控制流:\n"
                       f"{attr_build.stderr[-500:]}\n{main_text[-500:]}")
                lib_source.write_text(original_lib)
                attr_restored = sh([compiler, "run"], cwd=dst / "host")
                report(attr_restored.returncode == 0,
                       "u2-attribute-interface-restore",
                       f"恢复 noreturn 属性后构建/运行失败: "
                       f"rc={attr_restored.returncode}\n{attr_restored.stderr[-400:]}")
        else:
            ok = r.returncode != 0 and c["msg"] in (r.stderr + r.stdout)
            if c["name"] == "u3-unused-import":
                repeat = WORK / "unusedimp-diagnostic-repeat"
                for _ in range(8):
                    copy_proj(PROJ / c["fixture"], repeat)
                    repeated = sh([compiler, "build"], cwd=repeat / c["sub"])
                    ok = ok and repeated.returncode != 0 and c["msg"] in (
                        repeated.stderr + repeated.stdout)
            report(ok, c["name"],
                   f"退出码 {r.returncode}，期望诊断含「{c['msg']}」\n{(r.stderr + r.stdout)[-400:]}")

        return out

    jobs = max(1, args.jobs)
    if jobs == 1:
        case_results = [run_case(c) for c in CASES]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            case_results = list(pool.map(run_case, CASES))
    # 结果按 CASES 顺序打印，输出与串行时逐行一致（便于比对回归）。
    skipped = 0
    for case_result in case_results:
        for ok, name, detail in case_result:
            if ok == "skip":
                skipped += 1
                if not args.quiet:
                    print(f"SKIP {name}（{detail}）")
                continue
            report(ok, name, detail)
    if skipped and not args.quiet:
        print(f"（跳过 {skipped} 例：Windows 零 CRT 的宿主 C/POSIX 运行时边界，见 W1-2b-2 / W2-9）")

    # —— stdlib 三层（YH_STDLIB） ——
    std = (WORK / "stdlib")
    copy_proj(PROJ / "stdlib", std)
    r = sh([compiler, "run"], cwd=std / "host-only", env={"YH_STDLIB": str(std)})
    report(r.returncode == 101, "u2-stdlib-fallback",
           f"退出码 {r.returncode} 期望 101（标准库层）\n{r.stderr[-300:]}")
    r = sh([compiler, "run"], cwd=std / "host-shadow", env={"YH_STDLIB": str(std)})
    report(r.returncode == 201, "u2-stdlib-shadowed",
           f"退出码 {r.returncode} 期望 201（本地遮蔽标准库）\n{r.stderr[-300:]}")

    # —— MOD-U4：接口不兼容拒绝（破坏依赖接口后必须拒绝重建） ——
    dst = WORK / "ifacebad"
    copy_proj(PROJ / "ifacebad", dst)
    r = sh([compiler, "build"], cwd=dst / "host")
    if r.returncode != 0:
        report(False, "u4-iface-corrupt", f"首次构建失败: {r.stderr[-300:]}")
    else:
        # 找到 geom 的接口文件并破坏头行
        bad = None
        for p in (artifact_root(dst / "host") / "iface").glob("*geom*.s.i"):
            bad = p
        if bad is None:
            report(False, "u4-iface-corrupt", "未找到 geom.s.i")
        else:
            bad.write_text("// yh-iface v999 arch=x99 suffix=x\n")
            r2 = sh([compiler, "build"], cwd=dst / "host")
            if COMPILER_BACKEND == "llvm":
                repaired = (r2.returncode == 0
                            and not bad.read_text().startswith("// yh-iface v999"))
                report(repaired, "u4-iface-corrupt",
                       f"损坏接口未触发提供方重编译修复: "
                       f"{r2.returncode} {(r2.stderr + r2.stdout)[-300:]}")
            else:
                report(r2.returncode != 0 and "接口不兼容" in (r2.stderr + r2.stdout),
                       "u4-iface-corrupt",
                       f"破坏接口后未被拒绝: {r2.returncode} {(r2.stderr + r2.stdout)[-300:]}")

    # —— ADR-0007 P2：四模块接口探针（gen/lex/parse/cmd） ——
    dst = WORK / "fourdir"
    copy_proj(PROJ / "fourdir", dst)
    r = sh([compiler, "build"], cwd=dst)
    if r.returncode != 0:
        report(False, "p2-fourdir-probe", f"构建失败: {r.stderr[-400:]}")
    else:
        mods = sorted(p.name for p in dst.rglob("*.s.i"))
        report(mods == ["example_fourdir-gen.s.i", "example_fourdir-lex.s.i",
                        "example_fourdir-main.s.i", "example_fourdir-parse.s.i"],
               "p2-fourdir-iface", f"接口文件: {mods}")
        r2 = sh([str(dst / ".build/example_fourdir")], cwd=dst)
        report(r2.returncode == 118, "p2-fourdir-run",
               f"退出码 {r2.returncode} 期望 118 (bump1+touch3+scan7+with_tok6+via101)")

    dst = WORK / "fourdirbad"
    copy_proj(PROJ / "fourdirbad", dst)
    r = sh([compiler, "build"], cwd=dst)
    # 2026-10-02 pub struct 一等化：字段全公开后，四目录布局改验
    # 非导出函数（gen.hidden）跨模块调用被拒。
    report(r.returncode != 0 and "导出" in (r.stderr + r.stdout),
           "p2-fourdir-nonpub-symbol", f"非导出符号未被拒绝: {(r.stderr + r.stdout)[-300:]}")

    # —— project.toml 增强：as 别名 + KEY.MOD 跨项目导入 + 目录唯一模块 ——
    dst = WORK / "keyimp"
    copy_proj(PROJ / "keyimp", dst)
    r = sh([compiler, "build"], cwd=dst / "host")
    if r.returncode != 0:
        report(False, "u6-keyimp-run", f"构建失败: {r.stderr[-300:]}")
    else:
        r2 = sh([str(dst / "host" / ".build/example_keyimp")], cwd=dst / "host")
        report(r2.returncode == 34, "u6-keyimp-run",
               f"退出码 {r2.returncode} 期望 34")

    dst = WORK / "alias"
    copy_proj(PROJ / "alias", dst)
    r = sh([compiler, "build"], cwd=dst / "host")
    if r.returncode != 0:
        report(False, "u6-alias-run", f"构建失败: {r.stderr[-300:]}")
    else:
        r2 = sh([str(dst / "host" / ".build/example_alias")], cwd=dst / "host")
        report(r2.returncode == 7, "u6-alias-run",
               f"退出码 {r2.returncode} 期望 7")

    dst = WORK / "dirconflict"
    copy_proj(PROJ / "dirconflict", dst)
    r = sh([compiler, "build"], cwd=dst / "host")
    report(r.returncode != 0 and "每目录一个模块" in (r.stderr + r.stdout),
           "u6-dir-conflict", f"目录冲突未被拒绝: {(r.stderr + r.stdout)[-300:]}")

    # —— MOD-U5：重绑定与冷热一致 ——
    dst = WORK / "u5_rebind"
    copy_proj(PROJ / "basic", dst)
    r1 = sh([compiler, "build"], cwd=dst / "app")
    report(r1.returncode == 0 and "[编译] main" in r1.stdout,
           "u5-cold-builds", f"{r1.returncode} {r1.stdout[-200:]}")
    r2 = sh([compiler, "build"], cwd=dst / "app")
    report(r2.returncode == 0 and "[缓存]" in r2.stdout and "[编译]" not in r2.stdout,
           "u5-hot-cache-hits", f"二次构建未全部命中缓存: {r2.stdout[-200:]}")
    # 新增本地 json（与第三方同源码、不带 project.toml）→ json/main 必须重编译
    (dst / "app" / "src" / "json").mkdir(parents=True, exist_ok=True)
    shutil.copy(dst / "json" / "src" / "codec.yh", dst / "app" / "src" / "json" / "codec.yh")
    r3 = sh([compiler, "build"], cwd=dst / "app")
    recompiled = r3.returncode == 0 and "[编译] main" in r3.stdout and "[编译] json" in r3.stdout
    report(recompiled, "u5-rebind-local-json",
           f"新增本地 json 未触发重编译: {r3.stdout[-200:]} {r3.stderr[-200:]}")
    # 重绑定后产物与原第三方版本一致（同源码，冷热一致）
    r4 = sh([compiler, "run"], cwd=dst / "app")
    report(exit_code(r4.returncode) == 255, "u5-rebind-run-same",
           f"重绑定后运行退出码 {r4.returncode} 期望 255（POSIX 只暴露低 8 位）")

    # —— 清单精简：yh version 读 version + author 放行 + 产物名取 name ——
    dst = WORK / "authorproj"
    copy_proj(PROJ / "authorproj", dst)
    r = sh([compiler, "version"], cwd=dst)
    rc = sh([compiler, "version", "--contracts"], cwd=dst)
    keys = ("iface-min=", "iface-max=", "ctiface=", "ir-function=", "ir-module=")
    contracts_ok = rc.returncode == 0 and all(k in rc.stdout for k in keys)
    report(r.returncode == 0 and r.stdout.strip() == "authorproj 1.2.3" and contracts_ok,
           "p1-version-cmd",
           f"yh version 输出 {r.stdout.strip()!r} 期望 'authorproj 1.2.3'；"
           f"contracts 输出 {rc.stdout.strip()!r}")
    # —— 单文件输出形态：--emit-asm 必须是目标汇编，不是 LLVM IR ——
    # 2026-10-24 A3 门面重构时 API_ASM/API_LLVM_TEXT 两个分支的参数写反，
    # 全量门禁仍绿（语料只编译+运行，不看 --emit-asm 文本）。这里锁形态。
    hello = ROOT / "tests" / "yh-run" / "run" / "01-hello.yh"
    # 直接调用二进制，不经 sh() 注入的 --backend/--target：
    # 本用例锁的是"给定 --emit-asm 时的输出形态"，argv 必须精确。
    rasm = subprocess.run([compiler, "--emit-asm", str(hello)],
                          cwd=dst, capture_output=True, text=True)
    asm = rasm.stdout
    asm_ok = (rasm.returncode == 0 and "source_filename" not in asm
              and (".globl" in asm or ".section" in asm or ".text" in asm))
    report(asm_ok, "p1-emit-asm-form",
           f"--emit-asm 输出不是目标汇编: {asm[:120]!r}")

    r = sh([compiler, "build"], cwd=dst)
    report(r.returncode == 0 and (dst / ".build" / "authorproj").exists(),
           "p1-outname-from-name", f"产物名未取 project.name: {r.stdout[-200:]}")
    if (dst / ".build" / "authorproj").exists():
        r2 = sh([str(dst / ".build" / "authorproj")], cwd=dst)
        report(r2.returncode == 42, "p1-outname-runs",
               f"产物退出码 {r2.returncode} 期望 42")

    total = len(CASES) + 39
    print(f"project cases: 通过 {total - failed}/{total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
