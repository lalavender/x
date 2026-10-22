#!/usr/bin/env python3
"""LA0：冻结 yh 编译入口、check、lowering 与失败发布的外部行为。

本 harness 只通过命令行观察编译器，不按函数名或文件布局断言实现：
    entries   单文件/项目/run 的退出码、LLVM 文本、汇编与失败发布
    check     库文件 check、负例诊断、无工具 PATH、无后端产物
    lowering  lowering fixture 的 O0/O2 运行与 LLVM 文本

基线与候选使用同一源码绝对路径、SDK/标准库环境和构建参数；未传 --target，
候选始终使用自身默认目标。所有临时产物都在 tmp/llvm-architecture/ 下。

usage:
    python3 tests/selfhost/llvm-architecture.py --compiler-path ./yh --case all
    python3 tests/selfhost/llvm-architecture.py --compiler-path ./yh \
        --baseline-compiler /path/to/previous/yh
    python3 tests/selfhost/llvm-architecture.py --compiler-path ./yh --self-test
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "modules" / "projects" / "llvmarchitecture"
WORK_ROOT = ROOT / "tmp" / "llvm-architecture"
BASELINE_ROOT = WORK_ROOT / "baseline"
ENTRY = FIXTURE / "cases" / "entry.yh"
LIBRARY = FIXTURE / "cases" / "library.yh"
INVALID = FIXTURE / "cases" / "invalid.yh"
LOWERING = FIXTURE / "cases" / "lowering.yh"
PROJECT_NAME = "llvm_architecture"


class Failure(Exception):
    """一项外部行为不符合冻结预期。"""


def digest(path: Path) -> str:
    """返回文件内容的 SHA-256，用于发布回归与基线摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd, cwd, env=None, timeout=1800):
    """用 argv 调用命令，保留 stdout/stderr 供断言与失败摘要。"""
    return subprocess.run([str(item) for item in cmd], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=timeout)


def require(condition, message, proc=None):
    """断言外部行为；失败时附带命令输出，避免只看抽象结论。"""
    if condition:
        return
    detail = ""
    if proc is not None:
        detail = f"\n退出码: {proc.returncode}\nstdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
    raise Failure(message + detail)


def file_manifest(root: Path):
    """列出工作目录内的文件与大小，失败时用于核对残留产物。"""
    root = root.resolve()
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rows.append(f"{path.relative_to(root)}={path.stat().st_size}")
    return rows


def manifest_state(project: Path):
    """读取项目成功发布的 manifest 集合；失败发布不得改写它们。"""
    build = project / ".build"
    state = {}
    if build.exists():
        for path in sorted(build.rglob("*.manifest")):
            if path.is_file():
                state[str(path.relative_to(project))] = digest(path)
    return state


def copy_fixture(destination: Path, fixture: Path = FIXTURE) -> Path:
    """复制 fixture，项目路径 deliberately 含空格与中文。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture, destination)
    return destination


def llvm_text_for_file(compiler: Path, source: Path, opt: int, cwd: Path) -> str:
    """取单文件 --emit-llvm 的 LLVM 文本，并确认基本目标/函数结构。"""
    proc = run([compiler, f"-O{opt}", "--emit-llvm", "--emit-asm", source], cwd)
    require(proc.returncode == 0, f"单文件 LLVM 文本发射失败：{source}", proc)
    text = proc.stdout
    require("target triple" in text, f"LLVM 文本缺少 target triple：{source}", proc)
    require("define" in text, f"LLVM 文本缺少函数定义：{source}", proc)
    return text


def llvm_text_for_project(compiler: Path, project: Path, opt: int):
    """构建项目并收集 .build 下的 LLVM 文本，按相对路径排序。"""
    shutil.rmtree(project / ".build", ignore_errors=True)
    proc = run([compiler, f"-O{opt}", "--emit-llvm", "build"], project)
    require(proc.returncode == 0, f"项目 LLVM 文本构建失败：{project}", proc)
    root = project / ".build"
    texts = {}
    for path in sorted(root.rglob("*.ll")):
        texts[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
    require(texts, f"项目没有生成 LLVM 文本：{project}", proc)
    for name, text in texts.items():
        require("target triple" in text, f"{name} 缺少 target triple", proc)
    return texts


def build_and_run(compiler: Path, project: Path, opt: int, extra=()):
    """构建项目并运行默认二进制，返回 (构建结果, 运行结果)。"""
    build = run([compiler, f"-O{opt}", "build", *extra], project)
    binary = project / ".build" / PROJECT_NAME
    if build.returncode != 0 or not binary.exists():
        return build, None
    return build, run([binary], project)


def case_entries(compiler: Path, opt: int, work: Path, baseline=None, fixture=FIXTURE):
    """入口行为：单文件/项目/run、文本/汇编、失败发布与 oracle 摘要。"""
    project = copy_fixture(work / "入口 工作区" / "project", fixture)
    source = project / "cases" / "entry.yh"
    out = work / "entry.bin"
    proc = run([compiler, f"-O{opt}", "-o", out, source], project)
    require(proc.returncode == 0, "单文件入口编译失败", proc)
    ran = run([out], project)
    require(ran.returncode == 42, f"单文件入口返回 {ran.returncode}，期望 42", ran)

    entry_text = llvm_text_for_file(compiler, source, opt, project)
    asm = run([compiler, f"-O{opt}", "--emit-asm", source], project)
    require(asm.returncode == 0, "单文件汇编发射失败", asm)
    require(asm.stdout.strip() != "", "单文件汇编输出为空", asm)

    project_text = llvm_text_for_project(compiler, project, opt)
    require(len(project_text) >= 2,
            f"项目 LLVM 文本应覆盖 main 与 helper，实际 {sorted(project_text)}")
    # 现有项目 --emit-llvm 行为：文本是审阅附加产物，对象仍必须生成供链接。
    objects = [path for path in (project / ".build").rglob("*.o") if path.is_file()]
    require(len(objects) >= 2,
            f"项目 --emit-llvm 未保留对象产物：{[str(path) for path in objects]}")

    build, ran = build_and_run(compiler, project, opt)
    require(build.returncode == 0, "项目构建失败", build)
    require(ran is not None and ran.returncode == 42,
            f"项目可执行文件返回 {None if ran is None else ran.returncode}，期望 42", ran)
    run_cmd = run([compiler, f"-O{opt}", "run"], project)
    require(run_cmd.returncode == 42, f"yh run 返回 {run_cmd.returncode}，期望 42", run_cmd)

    # 失败发布回归：先记录成功产物，再让源码失败；旧程序与 manifest 必须不变。
    binary = project / ".build" / PROJECT_NAME
    before = {"binary": digest(binary), "manifests": manifest_state(project)}
    helper = project / "src" / "main" / "helper.yh"
    original = helper.read_text(encoding="utf-8")
    helper.write_text(original.replace("return 0;", "return missing_name;"),
                      encoding="utf-8")
    failed = run([compiler, f"-O{opt}", "build"], project)
    require(failed.returncode != 0, "引入源码错误后构建仍然成功", failed)
    after = {"binary": digest(binary), "manifests": manifest_state(project)}
    require(before == after, "失败构建改写了旧程序或成功 manifest", failed)
    leftovers = [name for name in file_manifest(project / ".build")
                 if ".tmp." in name]
    require(not leftovers, f"失败构建留下临时产物：{leftovers}", failed)
    helper.write_text(original, encoding="utf-8")
    build, ran = build_and_run(compiler, project, opt)
    require(build.returncode == 0 and ran is not None and ran.returncode == 42,
            "恢复源码后无法重新构建并运行", build)

    if baseline is not None:
        base_entry = llvm_text_for_file(baseline, source, opt, project)
        require(base_entry == entry_text, "单文件 LLVM 文本与基线不同")
        base_project = llvm_text_for_project(baseline, project, opt)
        require(base_project == project_text, "项目 LLVM 文本与基线不同")
    return {"entry_llvm_sha256": hashlib.sha256(entry_text.encode()).hexdigest(),
            "entry_asm_bytes": len(asm.stdout.encode()),
            "project_llvm_files": len(project_text)}


def case_check(compiler: Path, opt: int, work: Path, baseline=None):
    """check 行为：库文件无需 main、负例定位、无工具 PATH、无后端产物。"""
    project = copy_fixture(work / "检查 工作区" / "project")
    before = set(file_manifest(project))

    proc = run([compiler, f"-O{opt}", "check", project / "cases" / "library.yh"], project)
    require(proc.returncode == 0, "库文件 check 应成功", proc)
    require("检查通过" in proc.stdout, "库文件 check 缺少成功文案", proc)
    require(set(file_manifest(project)) == before,
            "单文件 check 生成了后端产物", proc)
    require(not (project / ".build").exists(),
            "单文件 check 创建了 .build 目录", proc)

    bad = run([compiler, f"-O{opt}", "check", project / "cases" / "invalid.yh"], project)
    require(bad.returncode != 0, "未声明名字的 check 应失败", bad)
    output = bad.stdout + bad.stderr
    require("错误:" in output, "负例 check 缺少错误诊断", bad)
    require(re.search(r"invalid\.yh:\d+:\d+", output) is not None,
            "负例诊断缺少路径/行/列", bad)

    # 前向调用：check 与编译都接受，运行返回 42。
    forward = project / "cases" / "forward.yh"
    forward_check = run([compiler, f"-O{opt}", "check", forward], project)
    require(forward_check.returncode == 0, "前向调用 check 失败", forward_check)
    forward_bin = work / "forward.bin"
    forward_build = run([compiler, f"-O{opt}", "-o", forward_bin, forward], project)
    require(forward_build.returncode == 0, "前向调用编译失败", forward_build)
    forward_run = run([forward_bin], project)
    require(forward_run.returncode == 42,
            f"前向调用返回 {forward_run.returncode}，期望 42", forward_run)

    # 错误 main：库 check 不要求入口，但存在时必须校验签名；编译同样失败。
    bad_main = project / "cases" / "badmain.yh"
    bad_main_check = run([compiler, f"-O{opt}", "check", bad_main], project)
    require(bad_main_check.returncode != 0, "错误 main 的 check 应失败", bad_main_check)
    require("main" in (bad_main_check.stdout + bad_main_check.stderr),
            "错误 main 的 check 缺少入口诊断", bad_main_check)
    bad_main_build = run([compiler, f"-O{opt}", "-o", work / "badmain.bin", bad_main],
                         project)
    require(bad_main_build.returncode != 0, "错误 main 的编译应失败", bad_main_build)

    empty_bin = work / "空 PATH"
    empty_bin.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PATH"] = str(empty_bin)
    isolated = run([compiler, f"-O{opt}", "check", project / "cases" / "library.yh"],
                   project, env=env)
    require(isolated.returncode == 0, "无工具 PATH 下库文件 check 失败", isolated)
    require(set(file_manifest(project)) == before,
            "无工具 PATH 的 check 生成了后端产物", isolated)

    # 项目 check 不要求 main 之外的后端产物，也不能覆盖已有正式缓存。
    project_check = run([compiler, f"-O{opt}", "check"], project)
    require(project_check.returncode == 0, "项目 check 失败", project_check)
    build_files = [path for path in (project / ".build").rglob("*")
                   if path.is_file()] if (project / ".build").exists() else []
    require(not build_files, f"项目 check 留下了 .build 文件：{build_files}",
            project_check)

    if baseline is not None:
        base_lib = run([baseline, f"-O{opt}", "check", project / "cases" / "library.yh"],
                       project)
        require(base_lib.returncode == proc.returncode,
                "库文件 check 退出码与基线不同")
        base_bad = run([baseline, f"-O{opt}", "check", project / "cases" / "invalid.yh"],
                       project)
        require(base_bad.returncode == bad.returncode,
                "负例 check 退出码与基线不同")
    return {"library_check": proc.returncode, "invalid_check": bad.returncode}


def case_lowering(compiler: Path, opt: int, work: Path, baseline=None):
    """lowering/semantics fixture：运行结果、LLVM 文本与基线对照。"""
    project = copy_fixture(work / "lowering 工作区" / "project")
    summary = {}
    for name in ("lowering", "semantics"):
        source = project / "cases" / f"{name}.yh"
        out = work / f"{name}.bin"
        proc = run([compiler, f"-O{opt}", "-o", out, source], project)
        require(proc.returncode == 0, f"{name} fixture 编译失败", proc)
        ran = run([out], project)
        require(ran.returncode == 0,
                f"{name} fixture 返回 {ran.returncode}，期望 0", ran)
        text = llvm_text_for_file(compiler, source, opt, project)
        if baseline is not None:
            base_text = llvm_text_for_file(baseline, source, opt, project)
            require(base_text == text, f"{name} LLVM 文本与基线不同")
        summary[f"{name}_llvm_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    return summary


def save_baseline(compiler: Path, opt: int, summary):
    """把首次可运行的输入/环境摘要与 LLVM 文本保存到 tmp 基线目录。"""
    target = BASELINE_ROOT / f"O{opt}"
    target.mkdir(parents=True, exist_ok=True)
    semantics = FIXTURE / "cases" / "semantics.yh"
    for name, source in (("entry.ll", ENTRY), ("lowering.ll", LOWERING),
                         ("semantics.ll", semantics)):
        proc = run([compiler, f"-O{opt}", "--emit-llvm", "--emit-asm", source], ROOT)
        if proc.returncode == 0:
            (target / name).write_text(proc.stdout, encoding="utf-8")
    record = {
        "compiler": str(compiler),
        "compiler_sha256": digest(compiler),
        "compiler_bytes": compiler.stat().st_size,
        "opt": opt,
        "fixture": {
            "entry_sha256": digest(ENTRY),
            "library_sha256": digest(LIBRARY),
            "invalid_sha256": digest(INVALID),
            "lowering_sha256": digest(LOWERING),
            "semantics_sha256": digest(FIXTURE / "cases" / "semantics.yh"),
        },
        "results": summary,
    }
    (target / "summary.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_cases(compiler: Path, opt: int, selected: str, baseline=None):
    """跑选中类别的全部用例，返回摘要；写文件一律在本临时工作区。"""
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="la0-", dir=WORK_ROOT) as temp:
        work = Path(temp) / "含 空格"
        work.mkdir(parents=True)
        summary = {"opt": opt}
        if selected in ("entries", "all"):
            summary.update(case_entries(compiler, opt, work, baseline))
        if selected in ("check", "all"):
            summary.update(case_check(compiler, opt, work, baseline))
        if selected in ("lowering", "all"):
            summary.update(case_lowering(compiler, opt, work, baseline))
        return summary


def self_test(compiler: Path, opt: int):
    """故意让入口 fixture 返回 41，harness 必须失败；恢复后必须通过。"""
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="oracle-", dir=WORK_ROOT) as temp:
        work = Path(temp)
        broken = work / "broken-fixture"
        copy_fixture(broken)
        entry = broken / "cases" / "entry.yh"
        text = entry.read_text(encoding="utf-8")
        entry.write_text(text.replace("return product(6, 7);", "return 41;"),
                         encoding="utf-8")
        try:
            case_entries(compiler, opt, work / "扰动", fixture=broken)
        except Failure:
            pass
        else:
            raise Failure("oracle 自检失败：入口返回 41 时 harness 仍然通过")
        case_entries(compiler, opt, work / "恢复")


def main() -> int:
    """解析命令行并执行 LA0 回归。"""
    parser = argparse.ArgumentParser(description="yh LLVM 架构 LA0 入口回归")
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--case", choices=("entries", "check", "lowering", "all"),
                        default="all")
    parser.add_argument("--opt-level", type=int, choices=(0, 2), default=None)
    parser.add_argument("--baseline-compiler", default=None)
    parser.add_argument("--save-baseline", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    baseline = Path(args.baseline_compiler).resolve() if args.baseline_compiler else None
    if not compiler.exists():
        print(f"编译器不存在：{compiler}")
        return 1
    levels = [args.opt_level] if args.opt_level is not None else [0, 2]
    try:
        if args.self_test:
            for opt in levels:
                self_test(compiler, opt)
            print("LA0 oracle 自检：返回 41 时失败，恢复后通过")
            return 0
        for opt in levels:
            summary = run_cases(compiler, opt, args.case, baseline)
            print(f"LA0 O{opt} 通过：{json.dumps(summary, sort_keys=True)}")
            if args.save_baseline:
                save_baseline(compiler, opt, summary)
    except Failure as error:
        print(f"FAIL {error}")
        return 1
    except subprocess.TimeoutExpired as error:
        print(f"FAIL 超时：{error}")
        return 1
    print("LA0：入口/check/lowering 外部行为通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
