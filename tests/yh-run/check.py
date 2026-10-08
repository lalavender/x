#!/usr/bin/env python3
"""tests/yh-run 运行语义校验。

对 tests/yh-run/ 下三组 .yh 用例做「编译 + 运行 + 比对」的端到端验收：

    run/   编译 <compiler> <file> -o <workdir>/<name> 后运行，比对标准输出
           与退出码。期望写在源文件注释里：
               // expect: 第一行输出          （首行，必须有）
               // expect-more: 后续行输出      （按出现顺序逐行比对）
               // exit: N                     （期望退出码，缺省 0）
               // stdin-hex: <十六进制>        （可选，注入进程标准输入）
               // argv: a b c                 （可选，附加命令行参数）
    fail/  编译必须失败。首行写 `// fail: 原因` 说明预期拒绝的理由；
           编译器若因信号崩溃（ICE）同样算 FAIL 并保留诊断。
    pass/  编译必须成功，不运行。

产物统一放 <workdir>（缺省 tmp/yh-run-work，在仓库 tmp/ 下，已被
gitignore）。并发运行多套校验时用 --workdir 指定不同目录，避免多个
进程同时读写同一批产物文件。--cross 模式额外用
-Wl,-oformat=elf64-aarch64 -sysroot -B 交叉编译成 Linux ELF，经
`docker exec yh-build` 在 aarch64 Linux 容器内运行并比对；
docker 或 sysroot 不可用时全部打印 SKIP，不算失败。

用法：
    python3 tests/yh-run/check.py           # 本机 Darwin/Mach-O 全量校验
    python3 tests/yh-run/check.py --quiet   # 只打印失败项与汇总
    python3 tests/yh-run/check.py --cross   # 交叉 ELF + 容器运行对比
    python3 tests/yh-run/check.py --compiler ./stage1 --workdir tmp/w1
                                            # 指定编译器与产物目录（自举差分）

退出码：全部通过（SKIP 不算失败）0；有 FAIL 1。
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # tests/yh-run
ROOT = HERE.parent.parent                        # 仓库根
DEFAULT_COMPILER = ROOT / "yh"
DEFAULT_WORK = ROOT / "tmp" / "yh-run-work"      # 缺省产物目录（tmp/ 下）
RUN_DIR = HERE / "run"
FAIL_DIR = HERE / "fail"
PASS_DIR = HERE / "pass"

# 交叉编译所需的 sysroot 与容器（与主会话交叉链路约定一致）。
SYSROOT = ROOT / "tmp" / "sysroot"
CROSS_CONTAINER = "yh-build"

COMPILE_TIMEOUT = 60     # 编译超时（秒）
RUN_TIMEOUT = 15         # 运行超时（秒）

# 期望注释的标记；行内容在第一个空格之后原样保留（允许行内空格/制表符）。
EXPECT_RE = re.compile(r"^//\s*expect:\s?(.*)$")
MORE_RE = re.compile(r"^//\s*expect-more:\s?(.*)$")
EXIT_RE = re.compile(r"^//\s*exit:\s*(-?\d+)\s*$")
FAIL_RE = re.compile(r"^//\s*fail:\s?(.*)$")
FAIL_CONTAINS_RE = re.compile(r"^//\s*fail-contains:\s?(.*)$")
# 标准输入注入（十六进制字节串，可为空）与附加命令行参数。
STDIN_HEX_RE = re.compile(r"^//\s*stdin-hex:\s?([0-9a-fA-F]*)\s*$")
ARGV_RE = re.compile(r"^//\s*argv:\s?(.*)$")

# 汇总里每种状态的打印标签。
LABELS = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}


def diag_tail(proc, limit=6):
    """从子进程输出里截取尾部诊断行（去空行），用于失败报告。"""
    text = (proc.stdout or "") + (proc.stderr or "")
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-limit:]


def signal_name(returncode):
    """subprocess 用负数表示信号终止，翻译成人可读的形式。"""
    return f"信号 {-returncode}"


def compile_src(src, out, cross=False, compiler=None):
    """编译一个用例，返回 (proc, timed_out)。

    cross=True 时追加交叉编译参数，产物为 Linux aarch64 ELF。
    compiler 缺省用仓库根的 yh。
    """
    cmd = [str(compiler or YH_BIN), str(src), "-o", str(out)]
    if cross:
        cmd += [
            "-Wl,-oformat=elf64-aarch64",
            "-sysroot", str(SYSROOT),
            "-B", str(SYSROOT),
        ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=COMPILE_TIMEOUT)
        return proc, False
    except subprocess.TimeoutExpired:
        return None, True


def parse_expectations(path):
    """解析 run/ 用例的期望注释，返回 (输出行列表, 退出码, 问题列表)。"""
    expect_lines = []
    exit_code = None
    problems = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        m = EXPECT_RE.match(line)
        if m:
            expect_lines.append(m.group(1))
            continue
        m = MORE_RE.match(line)
        if m:
            expect_lines.append(m.group(1))
            continue
        m = EXIT_RE.match(line)
        if m and exit_code is None:
            exit_code = int(m.group(1))
    if exit_code is None:
        exit_code = 0
    if not expect_lines and "// exit:" not in text:
        problems.append("用例缺少 // expect: 或 // exit: 期望注释")
    return expect_lines, exit_code, problems


def diff_output(expected, actual_stdout):
    """逐行比对期望输出与实际 stdout，返回差异描述列表（空即一致）。"""
    actual = actual_stdout.rstrip("\n").split("\n") if actual_stdout else []
    diffs = []
    for i in range(max(len(expected), len(actual))):
        want = expected[i] if i < len(expected) else "<缺行>"
        got = actual[i] if i < len(actual) else "<缺行>"
        if want != got:
            diffs.append(f"第 {i + 1} 行：期望 [{want}] 实际 [{got}]")
    return diffs


def parse_stdin_argv(path):
    """解析 run/ 用例的 stdin-hex 与 argv 注释，返回 (输入字节串, 参数列表)。

    没有相应注释时返回 (None, [])——进程标准输入保持继承，参数为空。
    """
    stdin_bytes = None
    argv_extra = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = STDIN_HEX_RE.match(line)
        if m:
            stdin_bytes = bytes.fromhex(m.group(1))
            continue
        m = ARGV_RE.match(line)
        if m:
            argv_extra = m.group(1).split()
    return stdin_bytes, argv_extra


def run_program(argv, timeout=RUN_TIMEOUT, input_bytes=None):
    """运行一个可执行文件/容器命令，返回 (proc, timed_out)。

    input_bytes 非 None 时以二进制模式经管道注入标准输入（覆盖现有
    用例不注入的旧行为），输出按 UTF-8 解码（非法字节替换），
    保证 NUL 等二进制数据不破坏文本比对。
    """
    try:
        proc = subprocess.run([str(a) for a in argv], capture_output=True,
                              timeout=timeout, input=input_bytes)
        proc.stdout = (proc.stdout or b"").decode("utf-8", "replace")
        proc.stderr = (proc.stderr or b"").decode("utf-8", "replace")
        return proc, False
    except subprocess.TimeoutExpired:
        return None, True


def cross_ready():
    """交叉运行环境是否可用：sysroot 存在且容器可执行命令。"""
    if not SYSROOT.is_dir():
        return False, f"缺少 sysroot：{SYSROOT}"
    try:
        proc = subprocess.run(["docker", "exec", CROSS_CONTAINER, "true"],
                              capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False, "docker 不可用或容器未运行"
    if proc.returncode != 0:
        return False, f"容器 {CROSS_CONTAINER} 不可用"
    return True, ""


def check_run_case(path, cross):
    """run/ 用例：编译并运行，比对输出与退出码。"""
    stem = path.stem
    out = WORK / (f"{stem}-linux" if cross else stem)
    proc, timed_out = compile_src(path, out, cross)
    if timed_out:
        return "FAIL", "编译超时"
    if proc.returncode != 0:
        why = "编译器崩溃（" + signal_name(proc.returncode) + "）" \
            if proc.returncode < 0 else f"编译失败（退出码 {proc.returncode}）"
        return "FAIL", why + "\n    " + "\n    ".join(diag_tail(proc))
    if not out.exists():
        return "FAIL", f"编译器未产出 {out.name}"

    expect_lines, exit_code, problems = parse_expectations(path)
    if problems:
        return "FAIL", "；".join(problems)

    if cross:
        # 容器把仓库根挂在 /work，按仓库相对路径定位 ELF。
        container_path = Path("/work") / out.relative_to(ROOT)
        argv = ["docker", "exec", CROSS_CONTAINER, container_path]
    else:
        argv = [out]
    stdin_bytes, argv_extra = parse_stdin_argv(path)
    if argv_extra:
        argv = argv + argv_extra
    if stdin_bytes is not None and cross:
        # docker exec 缺省不转发宿主 stdin，注入输入时必须 -i。
        argv.insert(2, "-i")
    run, run_timeout = run_program(argv, input_bytes=stdin_bytes)
    if run_timeout:
        return "FAIL", "运行超时"
    if run.returncode < 0:
        return "FAIL", "运行崩溃（" + signal_name(run.returncode) + "）"
    diffs = diff_output(expect_lines, run.stdout)
    if run.returncode != exit_code:
        diffs.append(f"退出码：期望 {exit_code} 实际 {run.returncode}")
    if diffs:
        return "FAIL", "；".join(diffs[:5])
    return "PASS", ""


def check_fail_case(path, cross):
    """fail/ 用例：编译须干净拒绝；可选 fail-contains 约束诊断类别。"""
    out = WORK / (stem_linux(path) if cross else path.stem)
    proc, timed_out = compile_src(path, out, cross)
    if timed_out:
        return "FAIL", "编译超时"
    if proc.returncode < 0:
        return "FAIL", "编译器崩溃（" + signal_name(proc.returncode) + "）\n    " \
            + "\n    ".join(diag_tail(proc))
    if proc.returncode == 0:
        return "FAIL", "预期编译被拒绝，实际编译通过"
    expected = ""
    for line in path.read_text().splitlines():
        match = FAIL_CONTAINS_RE.match(line)
        if match:
            expected = match.group(1)
            break
    if expected and expected not in proc.stderr:
        return "FAIL", f"诊断未包含预期文本 {expected!r}\n    " \
            + "\n    ".join(diag_tail(proc))
    return "PASS", ""


def stem_linux(path):
    """交叉模式下 fail/ 用例的产物名。"""
    return f"{path.stem}-linux"


def check_pass_case(path, cross):
    """pass/ 用例：编译必须成功，不运行。"""
    out = WORK / (stem_linux(path) if cross else path.stem)
    proc, timed_out = compile_src(path, out, cross)
    if timed_out:
        return "FAIL", "编译超时"
    if proc.returncode < 0:
        return "FAIL", "编译器崩溃（" + signal_name(proc.returncode) + "）\n    " \
            + "\n    ".join(diag_tail(proc))
    if proc.returncode != 0:
        return "FAIL", f"编译失败（退出码 {proc.returncode}）\n    " \
            + "\n    ".join(diag_tail(proc))
    return "PASS", ""


def list_cases(directory):
    """按文件名排序列出某目录下的 .yh 用例。"""
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.yh"))


def main():
    global YH_BIN, WORK
    parser = argparse.ArgumentParser(description="tests/yh-run 运行语义校验")
    parser.add_argument("--quiet", action="store_true", help="只打印失败项与汇总")
    parser.add_argument("--cross", action="store_true",
                        help="交叉编译为 Linux ELF 并在 docker 容器内运行对比")
    parser.add_argument("--compiler", default=str(DEFAULT_COMPILER),
                        help="yh 编译器路径（缺省仓库根 yh；自举时指向 stage1/stage2）")
    parser.add_argument("--workdir", default=str(DEFAULT_WORK),
                        help="产物目录（缺省 tmp/yh-run-work；并发运行时各自指定）")
    parser.add_argument("--filter", default="",
                        help="只跑相对路径含任一子串的用例（逗号分隔；自举差分子集用）")
    args = parser.parse_args()

    YH_BIN = Path(args.compiler).resolve()
    WORK = Path(args.workdir)
    filters = [f for f in args.filter.split(",") if f]

    def case_allowed(rel: str) -> bool:
        if not filters:
            return True
        return any(f in rel for f in filters)

    # 全局环境检查：编译器缺失或交叉环境不可用时，全部用例 SKIP。
    global_skip = None
    if not YH_BIN.exists():
        global_skip = f"找不到编译器 {YH_BIN}，请先构建"
    cross_note = ""
    if args.cross:
        ok, note = cross_ready()
        if not ok:
            global_skip = note
        cross_note = f"（sysroot：{SYSROOT}，容器：{CROSS_CONTAINER}）"

    WORK.mkdir(parents=True, exist_ok=True)

    groups = [
        ("run", RUN_DIR, check_run_case),
        ("fail", FAIL_DIR, check_fail_case),
        ("pass", PASS_DIR, check_pass_case),
    ]

    results = []  # (目录名, 相对路径, 状态, 说明)
    for name, directory, checker in groups:
        for path in list_cases(directory):
            rel = f"{name}/{path.name}"
            if not case_allowed(rel):
                continue
            if global_skip:
                results.append((name, rel, "SKIP", global_skip))
                continue
            status, detail = checker(path, args.cross)
            results.append((name, rel, status, detail))

    # 明细打印：--quiet 时略过 PASS 行。
    for _, rel, status, detail in results:
        if args.quiet and status == "PASS":
            continue
        if status == "PASS":
            print(f"{LABELS[status]}  {rel}")
        elif status == "SKIP":
            print(f"{LABELS[status]}  {rel} —— {detail}")
        else:
            print(f"{LABELS[status]}  {rel} —— {detail}")

    # 汇总。
    print()
    total_fail = 0
    for name in ("run", "fail", "pass"):
        rows = [r for r in results if r[0] == name]
        if not rows:
            continue
        n_pass = sum(1 for r in rows if r[2] == "PASS")
        n_fail = sum(1 for r in rows if r[2] == "FAIL")
        n_skip = sum(1 for r in rows if r[2] == "SKIP")
        total_fail += n_fail
        print(f"{name}: 通过 {n_pass}/{len(rows)}"
              + (f"，失败 {n_fail}" if n_fail else "")
              + (f"，跳过 {n_skip}" if n_skip else ""))
    mode = "交叉 ELF" if args.cross else "Darwin Mach-O"
    print(f"总计：通过 {sum(1 for r in results if r[2] == 'PASS')}/{len(results)}"
          f"（{mode}）{cross_note}")
    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()
