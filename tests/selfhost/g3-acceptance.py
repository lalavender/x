#!/usr/bin/env python3
"""B8 / G3 自举正式验收。

在运行中的 aarch64 Linux 容器 `yh-build` 内，按 `make bootstrap` 的产物
执行 G3 的完整验收流程，并把源码、汇编、ELF、工具链版本与 SHA-256 归档到
`tmp/bootstrap/artifacts/`。

验收项（对应 docs/02-plan/yh-自举实施方案-v2.md B8 与 G3 判据）：

  1. 前置：docker 容器、tmp/sysroot、stage1/2/3 产物存在；
  2. 分代全量：stage1、stage2、stage3 各自跑全部语法语料（66 正例 +
     29 反例）与运行语料（run + fail + pass），要求无崩溃、无超时、无 SKIP；
  3. stage3 自解析 + 自编；
  4. 固定点：stage2 与 stage3 对 compiler.yh **及全部代表程序**的发射
     逐字节一致；同一 stage 重复发射一致（无时间戳/随机）；
  5. 汇编中不得出现宿主绝对路径或时间戳；
  6. 归档产物与 SHA-256（stage2.s 与 stage3.s 的哈希必须相等）。

用法：
    python3 tests/selfhost/g3-acceptance.py            # 全量验收
    python3 tests/selfhost/g3-acceptance.py --skip-archive

前置：PATH 需含 docker（本机在 /opt/homebrew/bin）；容器 yh-build 运行中，
仓库挂载于 /work，且已构建 tmp/bootstrap/{stage1,stage2,stage3}。

退出码：全部通过 0；任一项失败 1。
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent      # tests/selfhost
ROOT = HERE.parent.parent                    # 仓库根
CONTAINER = "yh-build"
BOOTSTRAP = ROOT / "tmp" / "bootstrap"       # 本机侧产物目录（容器内 /work/tmp/bootstrap）
ARTIFACTS = BOOTSTRAP / "artifacts"
STAGES = ("stage1", "stage2", "stage3")


def docker(args, **kw):
    """在容器内执行 shell 命令，返回 CompletedProcess（不检查退出码）。"""
    return subprocess.run(["docker", "exec", CONTAINER, "sh", "-c", args],
                          capture_output=True, text=True, **kw)


def host_python(args, env=None):
    """本机执行测试驱动脚本（驱动内含 docker exec，路径自动映射）。"""
    return subprocess.run([sys.executable] + args, capture_output=True,
                          text=True, env=env, cwd=str(ROOT))


def check(cond, msg):
    """打印并累计验收结果。"""
    print(("  ✓ " if cond else "  ✗ ") + msg)
    return bool(cond)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-archive", action="store_true",
                    help="跳过产物与哈希归档")
    args = ap.parse_args()

    ok = True

    # ---- 1) 前置检查 ----
    print("== 1. 前置检查 ==")
    r = docker("true")
    ok &= check(r.returncode == 0, "容器 %s 可用" % CONTAINER)
    ok &= check((ROOT / "tmp" / "sysroot").is_dir(), "tmp/sysroot 存在")
    for s in STAGES:
        r = docker("test -x /work/tmp/bootstrap/%s" % s)
        ok &= check(r.returncode == 0, "%s 产物存在且可执行" % s)
    if not ok:
        print("前置不满足，中止。")
        return 1

    # ---- 2) 分代全量语料 ----
    print("== 2. 分代全量语料（语法 + 运行） ==")
    for s in STAGES:
        env = {"PATH": "/opt/homebrew/bin:" + __import__("os").environ.get("PATH", ""),
               "YH_STAGE": "/work/tmp/bootstrap/" + s}
        # 语法（正例 66 + 反例 29）
        r = host_python(["tests/yh/check.py", "--compiler",
                         "--compiler-path", str(ROOT / "tests/yh/container-yh.sh"),
                         "--quiet"], env=env)
        syn_ok = r.returncode == 0 and "66/66" in r.stdout and "29/29" in r.stdout
        ok &= check(syn_ok, "%s 语法语料 66/66 + 29/29" % s)
        # 运行（run + fail + pass），交叉 ELF 在容器内执行。
        # macOS Docker 挂载偶发元数据延迟（ELF 刚写完权限位短暂不可见，
        # 曾致 run/16「permission denied」假失败），失败重试一次；
        # 重试仍失败才是真回归。
        run_ok = False
        tail = ""
        for attempt in (1, 2):
            r = host_python(["tests/yh-run/check.py", "--compiler",
                             str(ROOT / "tests/yh/container-yh-cc.sh"), "--cross",
                             "--workdir", str(ROOT / "tmp" / ("g3-run-" + s)),
                             "--quiet"], env=env)
            run_ok = (r.returncode == 0 and "失败 0" not in r.stdout
                      and "SKIP" not in r.stdout
                      and re.search(r"总计：通过 \d+/\d+（交叉 ELF）", r.stdout) is not None)
            tail = (r.stdout.strip().splitlines() or [""])[-1]
            if run_ok:
                break
            if attempt == 1:
                print("    （运行语料存在失败，重试一次以排除挂载竞态）")
        ok &= check(run_ok, "%s 运行语料：%s" % (s, tail))

    # ---- 3) stage3 自解析 ----
    print("== 3. stage3 自解析 ==")
    r = docker("cd /work/tmp/bootstrap && ./stage3 --syntax-check compiler.yh")
    ok &= check(r.returncode == 0, "stage3 自解析 compiler.yh")

    # ---- 3b) `-o` 兼容层：自举编译器直接产出可执行 ----
    print("== 3b. `-o` 兼容层（自举编译器直出可执行） ==")
    for s in STAGES:
        r = docker(
            'cd /tmp && rm -f /tmp/o_%s /tmp/o_%s.yh-tmp.s && '
            '/work/tmp/bootstrap/%s -o /tmp/o_%s /work/tests/yh-run/run/36-driver-o.yh '
            '&& /tmp/o_%s; echo "rc=$?"; '
            'test -f /tmp/o_%s.yh-tmp.s && echo "TMP_LEFT" || true'
            % (s, s, s, s, s, s))
        want_ok = r.returncode == 0 and "rc=5" in r.stdout
        ok &= check(want_ok, "%s -o 产出可执行且运行正确（rc=5）" % s)
        ok &= check("TMP_LEFT" not in r.stdout, "%s -o 清理临时汇编文件" % s)
    # 错误源：-o 必须非零退出且不产出可执行
    r = docker(
        'cd /tmp && rm -f /tmp/o_bad && '
        '/work/tmp/bootstrap/stage1 -o /tmp/o_bad /work/tests/yh-run/fail/01-undeclared-var.yh '
        '2>/dev/null; echo "rc=$?"; test -f /tmp/o_bad && echo "LEAK" || true')
    ok &= check("rc=1" in r.stdout and "LEAK" not in r.stdout,
                "stage1 -o 对错误源非零退出且不产出文件")

    # ---- 4) 固定点 ----
    print("== 4. 汇编固定点（stage2 vs stage3） ==")
    # 4a. compiler.yh
    r = docker("cd /work/tmp/bootstrap && cmp -s stage2.s stage3.s")
    ok &= check(r.returncode == 0, "compiler.yh：stage2.s == stage3.s")
    # 4b. 全部代表程序
    r = docker(
        'cd /work/tmp/bootstrap; bad=0; n=0; list=""; '
        'for f in /work/tests/yh-run/run/*.yh; do '
        '  b=$(basename "$f" .yh); n=$((n+1)); '
        '  ./stage2 --emit-asm "$f" > /tmp/x2.s 2>/dev/null; '
        '  ./stage3 --emit-asm "$f" > /tmp/x3.s 2>/dev/null; '
        '  if ! cmp -s /tmp/x2.s /tmp/x3.s; then bad=$((bad+1)); list="$list $b"; fi; '
        'done; echo "$((n-bad))/$n$list"')
    fp = r.stdout.strip()
    ok &= check(fp.startswith(tuple(str(i) + "/" for i in range(0, 1000)))
                and "/" in fp and fp.split("/")[1].split()[0]
                == fp.split("/")[0], "全部代表程序固定点：%s" % fp)
    # 4c. 重复发射确定性
    r = docker("cd /work/tmp/bootstrap && ./stage2 --emit-asm compiler.yh > /tmp/d1.s "
               "&& ./stage2 --emit-asm compiler.yh > /tmp/d2.s && cmp -s /tmp/d1.s /tmp/d2.s")
    ok &= check(r.returncode == 0, "同一 stage 重复发射逐字节一致（无时间戳/随机）")

    # ---- 5) 无宿主路径/时间戳 ----
    print("== 5. 发射内容洁净度 ==")
    r = docker("grep -cE '/Users/|/opt/homebrew|/work/|20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
               "/work/tmp/bootstrap/stage2.s || true")
    n_bad = int((r.stdout.strip() or "0").splitlines()[-1])
    ok &= check(n_bad == 0, "stage2.s 无宿主绝对路径/时间戳（命中 %d）" % n_bad)

    # ---- 5b) 诊断质量：反例必须非零退出、有位置诊断、不泄漏汇编 ----
    print("== 5b. 诊断质量（stage1 对全部反例） ==")
    r = docker(
        'cd /work/tmp/bootstrap; bad_rc=0; bad_diag=0; bad_leak=0; n=0; '
        'for f in /work/tests/yh-run/fail/*.yh /work/tests/yh/rejected/*.yh '
        '         /work/tests/yh-run/fail/*.yh; do '
        '  n=$((n+1)); '
        '  out=$(./stage1 --emit-asm "$f" 2>/tmp/e.txt); rc=$?; '
        '  [ $rc -eq 0 ] && bad_rc=$((bad_rc+1)); '
        '  grep -qE "^[^:]+:[0-9]+:[0-9]+: 错误:" /tmp/e.txt || bad_diag=$((bad_diag+1)); '
        '  [ -n "$out" ] && bad_leak=$((bad_leak+1)); '
        'done; echo "$n $bad_rc $bad_diag $bad_leak"')
    parts = r.stdout.split()
    if len(parts) == 4:
        n, brc, bdiag, bleak = (int(x) for x in parts)
        ok &= check(brc == 0, "反例全部非零退出（%d 个，异常 %d）" % (n, brc))
        ok &= check(bdiag == 0, "反例全部带「文件:行:列: 错误:」诊断（异常 %d）" % bdiag)
        ok &= check(bleak == 0, "反例无汇编泄漏到 stdout（异常 %d）" % bleak)
    else:
        ok &= check(False, "诊断质量检查输出异常：%r" % r.stdout)

    # ---- 6) 归档 ----
    if not args.skip_archive:
        print("== 6. 归档产物与 SHA-256 ==")
        r = docker(
            'cd /work/tmp/bootstrap && mkdir -p artifacts && '
            'cp compiler.yh artifacts/ && '
            'cp stage2.s artifacts/ && cp stage3.s artifacts/ && '
            'cp stage1 artifacts/stage1.bin && cp stage2 artifacts/stage2.bin && '
            'cp stage3 artifacts/stage3.bin && '
            '{ echo "== 容器环境 =="; head -2 /etc/os-release; uname -m; echo; '
            '  echo "== gcc =="; gcc --version | head -1; echo; '
            '  echo "== as =="; as --version | head -1; echo; '
            '  echo "== ld =="; ld --version | head -1; } > artifacts/toolchain.txt 2>&1 && '
            'cd artifacts && rm -f SHA256SUMS && '
            'sha256sum compiler.yh stage1.bin stage2.bin stage3.bin stage2.s stage3.s '
            'toolchain.txt > SHA256SUMS && cat SHA256SUMS')
        sums = {}
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
                sums[parts[1]] = parts[0]
        ok &= check(len(sums) >= 7, "SHA-256 归档（%d 文件）" % len(sums))
        ok &= check(sums.get("stage2.s") == sums.get("stage3.s") is not None,
                    "stage2.s 与 stage3.s 哈希相等（固定点密码学证据）")

    print()
    print("G3 验收：%s" % ("通过" if ok else "未通过"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
