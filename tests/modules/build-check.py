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
退出码：全部通过 0；有失败 1。
"""

import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PROJ = HERE / "projects"
WORK = ROOT / "tmp" / "modcheck"


def sh(cmd, cwd, env=None):
    e = dict(__import__("os").environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          env=e, timeout=300)


def stat_value(line, name, default=-1):
    """从一行 yh-stats 读取整数计数器。"""
    marker = name + "="
    if marker not in line:
        return default
    return int(line.split(marker, 1)[1].split()[0])


def has_two_edge_phi(path):
    """读取 yh SSA 缓存头，确认存在四块 CFG 中的双前驱 phi。"""
    data = path.read_bytes()
    if len(data) < 120 or struct.unpack_from("<Q", data, 16)[0] != 0x3141535352494859:
        return False
    if struct.unpack_from("<Q", data, 24)[0] != 4:
        return False
    _, _, type_count, inst_count, phi_count, input_count, call_count, arg_count, symbol_size, block_count, _ = \
        struct.unpack_from("<11q", data, 32)
    if (type_count <= 0 or inst_count < 0 or phi_count != 1 or input_count != 2
            or call_count != 0 or arg_count != 0 or symbol_size != 0
            or block_count != 4):
        return False
    inst_offset = 120 + type_count * 24
    return any(struct.unpack_from("<q", data, inst_offset + i * 56)[0] == 6
               for i in range(inst_count))


def count_ir_op(path, wanted):
    """统计一个已生成 SSA 缓存中的指定操作码。"""
    data = path.read_bytes()
    if len(data) < 120 or struct.unpack_from("<Q", data, 16)[0] != 0x3141535352494859:
        return -1
    _, _, type_count, inst_count, _, _, _, _, _, _, _ = struct.unpack_from("<11q", data, 32)
    inst_offset = 120 + type_count * 24
    if type_count < 0 or inst_count < 0 or inst_offset + inst_count * 56 > len(data):
        return -1
    return sum(struct.unpack_from("<q", data, inst_offset + i * 56)[0] == wanted
               for i in range(inst_count))


CASES = []


def case(name, kind, fixture, sub, expect=None, msg=None):
    CASES.append(dict(name=name, kind=kind, fixture=fixture, sub=sub,
                      expect=expect, msg=msg))


# —— MOD-U4：两项目真实链接运行（含跨模块聚合/浮点/间接调用/限定字面量） ——
case("u4-basic-run", "run", "basic", "app", 255)
case("u4-iso-run", "run", "iso", "host", 15)
case("u4-aggfloat-run", "run", "aggfloat", "host", 29)
case("u4-enumexp-run", "run", "enumexp", "host", 10)
case("r1-token-replay-run", "run", "tokenreplay", ".", 42)
case("r2a-ssa-phi-verifier", "run", "irverify", ".", 0)
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
# —— MOD-U2：清单与三层解析 ——
case("u2-toml-syntax", "fail", "tomlbad", ".", msg="project.toml")
case("u2-toml-unknown-field", "fail", "tomlunknown", ".", msg="未知字段")
# —— 清单精简（2026-09-30）：name 必须标识符、author 放行、入口 = main 模块 ——
case("p1-name-not-identifier", "fail", "tomlnamebad", ".", msg="project.name")
case("u2-transitive-rejected", "fail", "transitive", "host", msg="模块不存在")
case("u2-ambiguous-deps", "fail", "ambiguity", "host", msg="歧义")
# —— MOD-U3：模块语义 ——
# 2026-10-02 pub struct 一等化：字段一律公开，跨模块字段访问与位置式构造
# 由 fail 用例转为 run 正向用例；符号级可见性（非 pub fn）仍被拒绝。
case("u3-import-cycle", "fail", "cycle", "a", msg="环")
case("u3-entry-not-importable", "fail", "cycleentry", "host", msg="入口模块不可")
case("u3-pub-field-access", "run", "pubpriv", "host", 2)
case("u3-private-fn", "fail", "pubpriv", "host2", msg="导出")
case("u3-positional-pub-construct", "run", "pubpriv", "host3", 1)
case("u3-duplicate-decl", "fail", "dupdecl", "host", msg="重定义")
case("u3-unused-import", "fail", "unusedimp", "host", msg="导入未使用")
case("u3-import-clash", "fail", "clashname", "host", msg="导入名冲突")


def copy_proj(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    if src.name in ("irverify", "irfront"):
        # ir 现为编译器根项目普通模块（不带清单）；fixture 仍以路径依赖
        # 方式复用其源码测跨项目解析，拷入后补最小清单使其可被发现。
        shutil.copytree(ROOT / "compiler" / "ir", dst / "ir")
        (dst / "ir" / "project.toml").write_text(
            "[project]\nname = \"yh_ir\"\nsource = \".\"\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler-path", default=str(ROOT / "yh"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    WORK.mkdir(parents=True, exist_ok=True)
    failed = 0

    def report(ok, name, detail=""):
        nonlocal failed
        if not ok:
            failed += 1
            print(f"FAIL {name}: {detail}")
        elif not args.quiet:
            print(f"OK   {name}")

    for c in CASES:
        dst = WORK / c["fixture"].replace("/", "_")
        copy_proj(PROJ / c["fixture"], dst)
        if c["kind"] == "host-capture":
            target = "linux" if sys.platform == "darwin" else "darwin"
            checked = sh([compiler, "-target", target, "check"], cwd=dst)
            report(checked.returncode == 0, c["name"],
                   f"交叉目标不应改变宿主文件标志: rc={checked.returncode}\n"
                   f"{checked.stderr[-400:]} {checked.stdout[-200:]}")
            continue
        if c["kind"] == "envp-run":
            run = sh([compiler, "run"], cwd=dst,
                     env={"YH_ENV_TEST": "present"})
            report(run.returncode == 0, c["name"],
                   f"main(argc, argv, envp) 未收到进程环境: rc={run.returncode}\n"
                   f"{run.stderr[-400:]} {run.stdout[-200:]}")
            continue
        if c["kind"] == "ir-call":
            built = sh([compiler, "build", "--stats"], cwd=dst)
            lines = [line for line in built.stderr.splitlines()
                     if line.startswith("yh-stats ")]
            lowered = sum(stat_value(line, "ir_functions", 0) for line in lines)
            asm_path = dst / ".build" / "asm" / "ircallmodule-main.s"
            asm = asm_path.read_text() if asm_path.exists() else ""
            symbol_prefix = "_" if sys.platform == "darwin" else ""
            program = dst / ".build" / "ircallmodule"
            run = sh([str(program)], cwd=dst) if program.exists() else None
            report(built.returncode == 0 and lowered == 4
                   and f"\tbl\t{symbol_prefix}twice__ircallmodule__api_" in asm
                   and f"\tbl\t{symbol_prefix}log_note__ircallmodule__api_" in asm
                   and run is not None and run.returncode == 41,
                   c["name"],
                   f"跨模块 SSA 目标或运行结果错误: rc={built.returncode}, "
                   f"ir_functions={lowered}, run={run.returncode if run else None}\n"
                   f"{built.stderr[-500:]}")
            api_source = dst / "src" / "api" / "api.yh"
            original_api = api_source.read_text()
            api_source.write_text(original_api.replace("value * 2", "value * 3"))
            changed = sh([compiler, "build", "--stats"], cwd=dst)
            changed_lines = [line for line in changed.stderr.splitlines()
                             if line.startswith("yh-stats ")]
            last = changed_lines[-1] if changed_lines else ""
            rerun = sh([str(program)], cwd=dst) if program.exists() else None
            report(changed.returncode == 0 and stat_value(last, "asm") == 1
                   and stat_value(last, "link") == 1
                   and rerun is not None and rerun.returncode == 61,
                   "r2b-cross-module-call-relink",
                   f"公开函数体变化未仅重编提供模块并重新链接: "
                   f"asm={stat_value(last, 'asm')}, link={stat_value(last, 'link')}, "
                   f"run={rerun.returncode if rerun else None}\n{changed.stderr[-500:]}")
            continue
        if c["kind"] == "platform-source":
            native = "darwin" if sys.platform == "darwin" else "linux"
            cross = "linux" if native == "darwin" else "darwin"
            expected = 31 if native == "darwin" else 32
            run = sh([compiler, "run"], cwd=dst)
            report(run.returncode == expected, c["name"],
                   f"本机目标源选择错误: rc={run.returncode}, 期望 {expected}\n"
                   f"{run.stderr[-400:]} {run.stdout[-200:]}")
            checked = sh([compiler, "-target", cross, "check"], cwd=dst)
            report(checked.returncode == 0, "r3-cross-target-source-selection",
                   f"交叉目标未选择对应源文件: target={cross}, rc={checked.returncode}\n"
                   f"{checked.stderr[-400:]} {checked.stdout[-200:]}")
            continue
        if c["kind"] == "darwin-dir-api":
            darwin = sh([compiler, "-target", "darwin", "check"], cwd=dst)
            report(darwin.returncode == 0, "r3-getattrlistbulk-darwin-available",
                   f"Darwin 目标未登记目录 OS API: rc={darwin.returncode}\n"
                   f"{darwin.stderr[-400:]}")
            linux = sh([compiler, "-target", "linux", "check"], cwd=dst)
            report(linux.returncode != 0 and "未声明" in linux.stderr,
                   "r3-getattrlistbulk-not-linux-api",
                   f"Linux 目标意外导入 Darwin API: rc={linux.returncode}\n"
                   f"{linux.stderr[-400:]}")
            continue
        if c["kind"] == "directory-scan":
            odd_name = dst / "line\nbreak space ' 雪.yh"
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
            continue
        if c["kind"] == "linux-syscall-asm":
            emitted = sh([compiler, "-target", "linux", "--emit-asm", "main.yh"], cwd=dst)
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
            darwin = sh([compiler, "-target", "darwin", "check"], cwd=dst)
            report(darwin.returncode != 0 and "未声明" in darwin.stderr,
                   "r3-linux-syscall-is-target-gated",
                   f"Darwin 目标意外接受 Linux 系统调用接口: rc={darwin.returncode}\n"
                   f"{darwin.stderr[-400:]}")
            continue
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
            continue
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
            continue
        if c["kind"] == "ir":
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
            asm_path = dst / ".build" / "asm" / "irfront-main.s"
            asm = asm_path.read_text() if asm_path.exists() else ""
            backend_functions = asm.count(".p2align 2")
            report(backend_functions == build_ir,
                   "r2a-ssa-backend-owns-functions",
                   f"已降低的 SSA 函数没有全部由新后端发射: "
                   f"ssa={build_ir}, backend={backend_functions}\n{asm[-600:]}")
            phi_caches = list((dst / ".build" / "ir").glob("*.ir"))
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
                   and "\tstr\tx9, [sp, #0]" in asm
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
            original = source.read_bytes()
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
                    ir_files = sorted((dst / ".build" / "ir").glob("*.ir"))
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
            report(run is not None and run.returncode == c["expect"],
                   "r2b-built-program-runs",
                   f"程序退出码 {run.returncode if run else '未生成'} 期望 {c['expect']}")
            continue
        if c["kind"] == "scheduler":
            api_source = dst / "src" / "api" / "api.yh"
            extra = "".join(
                f"fn private_{i:04d}() int {{ return {i % 10}; }}\n"
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
            iface_dir = dst / ".build" / "iface"
            persisted = list(iface_dir.glob("*.s.i"))
            session_files = list(iface_dir.glob("*.session-*"))
            report(r.returncode == 0 and len(persisted) == 2 and not session_files,
                   "r2b-session-interface-commit",
                   f"持久接口提交或本轮临时接口清理失败: "
                   f"persistent={len(persisted)}, session={len(session_files)}")
            if built.exists():
                run = sh([str(built)], cwd=dst)
                report(run.returncode == 42, "r2b-scheduled-program-runs",
                       f"程序退出码 {run.returncode} 期望 42")
            else:
                report(False, "r2b-scheduled-program-runs", "调度后没有生成程序")

            # 接口成功发布后，提供方私有函数仍可能检查失败；本轮不得链接。
            built.unlink(missing_ok=True)
            api_source.write_text(api_source.read_text() +
                                  "\nfn broken_private() int { return missing_name; }\n")
            failed_build = sh([compiler, "build"], cwd=dst)
            report(failed_build.returncode != 0 and not built.exists(),
                   "r2b-worker-failure-stops-link",
                   f"worker 失败后错误地产生最终程序: rc={failed_build.returncode}\n"
                   f"{failed_build.stderr[-400:]}")

            spaced = WORK / "scheduler argv ' with spaces"
            copy_proj(PROJ / "scheduler", spaced)
            path_env = str(Path(compiler).parent) + ":" + \
                __import__("os").environ.get("PATH", "")
            spaced_build = sh(["yh", "build"], cwd=spaced,
                              env={"PATH": path_env})
            spaced_program = spaced / ".build" / "scheduler"
            report(spaced_build.returncode == 0 and spaced_program.exists(),
                   "r2b-fork-worker-space-paths",
                   f"PATH 启动及含空格/引号项目路径未能由 fork 快照 worker 构建: "
                   f"rc={spaced_build.returncode}\n"
                   f"{spaced_build.stderr[-400:]} {spaced_build.stdout[-300:]}")
            continue
        if c["kind"] == "scheduler-diamond":
            base_source = dst / "src" / "base" / "base.yh"
            extra = "".join(
                f"fn private_{i:04d}() int {{ return {i % 10}; }}\n"
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
            iface_dir = dst / ".build" / "iface"
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
            continue
        r = sh([compiler, "run"] if c["kind"] == "run" else [compiler, "build"],
               cwd=dst / c["sub"])
        if c["kind"] == "run":
            report(r.returncode == c["expect"], c["name"],
                   f"退出码 {r.returncode} 期望 {c['expect']}\n{r.stderr[-400:]}")
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
        for p in dst.rglob("*geom*.s.i"):
            bad = p
        if bad is None:
            report(False, "u4-iface-corrupt", "未找到 geom.s.i")
        else:
            bad.write_text("// yh-iface v999 arch=x99 suffix=x\n")
            r2 = sh([compiler, "build"], cwd=dst / "host")
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
    report(r4.returncode == 255, "u5-rebind-run-same",
           f"重绑定后运行退出码 {r4.returncode} 期望 255")

    # —— 清单精简：yh version 读 version + author 放行 + 产物名取 name ——
    dst = WORK / "authorproj"
    copy_proj(PROJ / "authorproj", dst)
    r = sh([compiler, "version"], cwd=dst)
    report(r.returncode == 0 and r.stdout.strip() == "authorproj 1.2.3",
           "p1-version-cmd", f"yh version 输出 {r.stdout.strip()!r} 期望 'authorproj 1.2.3'")
    r = sh([compiler, "build"], cwd=dst)
    report(r.returncode == 0 and (dst / ".build" / "authorproj").exists(),
           "p1-outname-from-name", f"产物名未取 project.name: {r.stdout[-200:]}")
    if (dst / ".build" / "authorproj").exists():
        r2 = sh([str(dst / ".build" / "authorproj")], cwd=dst)
        report(r2.returncode == 42, "p1-outname-runs",
               f"产物退出码 {r2.returncode} 期望 42")

    total = len(CASES) + 22
    print(f"project cases: 通过 {total - failed}/{total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
