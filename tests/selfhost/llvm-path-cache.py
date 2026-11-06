#!/usr/bin/env python3
"""C3：路径规范化与 --trimpath 回归。

验证三件事：
  1. 同源码复制到另一目录后，模块 worker 仍能用相对路径命中 check/IR 缓存；
  2. `--trimpath` 让不同目录的 LLVM 文本使用相同的相对来源路径；
  3. 不改变源码/参数的普通构建仍保留绝对来源路径（用于本地诊断）。

用法：python3 tests/selfhost/llvm-path-cache.py --compiler-path ./yh
退出码：全部通过 0，否则 1。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "modules" / "projects" / "llvmfunctioncache"
WORK_ROOT = ROOT / "tmp" / "llvm-path-cache"


def run(cmd, cwd, env=None):
    """执行命令并返回 CompletedProcess。"""
    complete = dict(os.environ)
    complete["YH_STDLIB"] = str(ROOT / "libs")
    complete.setdefault("YH_CACHE", "off")
    if env:
        complete.update(env)
    return subprocess.run([str(item) for item in cmd], cwd=cwd,
                          capture_output=True, text=True, env=complete,
                          timeout=1800)


def require(condition, message, proc=None):
    """断言；失败时附带命令输出。"""
    if condition:
        return
    detail = ""
    if proc is not None:
        detail = (f"\n退出码: {proc.returncode}\nstdout:\n{proc.stdout[-1600:]}"
                  f"\nstderr:\n{proc.stderr[-1600:]}")
    raise RuntimeError(message + detail)


def copy_fixture(project):
    """复制 fixture 到工作目录。"""
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(FIXTURE, project)


def build(compiler, project, extra=None, env=None):
    """在项目目录构建；返回 CompletedProcess。"""
    cmd = [compiler, "build"]
    if extra:
        cmd.extend(extra)
    return run(cmd, project, env)


def stats(proc):
    """取主模块 worker 的缓存计数（没有 worker 行时返回全 0）。"""
    rows = []
    for line in (proc.stdout + proc.stderr).splitlines():
        if not line.startswith("yh-stats "):
            continue
        row = dict(item.split("=", 1) for item in line.split()[1:] if "=" in item)
        if int(row.get("ir_functions", "0")) > 0:
            rows.append(row)
    if not rows:
        return {"check_hits": 0, "check_misses": 0,
                "ir_hits": 0, "ir_misses": 0}
    row = max(rows, key=lambda item: int(item.get("ir_functions", "0")))
    return {
        "check_hits": int(row.get("check_cache_hits", "0")),
        "check_misses": int(row.get("check_cache_misses", "0")),
        "ir_hits": int(row.get("ir_cache_hits", "0")),
        "ir_misses": int(row.get("ir_cache_misses", "0")),
    }


def force_worker(project):
    """删除 main 的模块 manifest/对象，强制 worker 重新进入缓存查询。"""
    for pattern in ("manifest/*-main.manifest", "obj/*-main.o"):
        for path in (project / ".build").rglob(pattern):
            path.unlink()


def link_count(proc):
    """取本轮最大 link 计数；没有 yh-stats 行返回 0。"""
    best = 0
    for line in (proc.stdout + proc.stderr).splitlines():
        if not line.startswith("yh-stats "):
            continue
        for item in line.split()[1:]:
            if item.startswith("link="):
                try:
                    best = max(best, int(item.split("=", 1)[1]))
                except ValueError:
                    pass
    return best


def llvm_texts(project):
    """返回项目当前目标的全部 .ll 文件。"""
    return sorted(project.glob(".build/targets/*/llvm/*/llvm/*.ll"))


def source_filename(path):
    """读取 LLVM 文本第一行 source_filename 的引号内容。"""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        marker = 'source_filename = "'
        if line.startswith(marker):
            return line[len(marker):].split('"', 1)[0]
    return ""


def one_level(compiler, opt):
    """跑一个优化级别下的路径缓存与 trimpath 检查。"""
    prefix = f"O{opt}-"
    with tempfile.TemporaryDirectory(prefix=prefix, dir=WORK_ROOT) as temp:
        work = Path(temp)
        a = work / "a" / "project"
        b = work / "b" / "project"
        copy_fixture(a)
        require(build(compiler, a, [f"-O{opt}"]).returncode == 0,
                "目录 A 冷编失败")
        force_worker(a)
        primed = build(compiler, a, [f"-O{opt}"])
        require(primed.returncode == 0, "目录 A 预热构建失败", primed)
        shutil.copytree(a, b)
        force_worker(b)
        moved = build(compiler, b, [f"-O{opt}", "--stats"])
        require(moved.returncode == 0, "目录 B 构建失败", moved)
        counts = stats(moved)
        require(counts["check_hits"] == 4 and counts["check_misses"] == 0,
                f"搬目录后 check 未全命中：{counts}", moved)
        require(counts["ir_hits"] == 4 and counts["ir_misses"] == 0,
                f"搬目录后 IR 未全命中：{counts}", moved)

        # trimpath：两个独立目录的 LLVM 文本必须逐字节一致，且来源路径是相对路径。
        c = work / "c" / "project"
        d = work / "d" / "project"
        copy_fixture(c)
        copy_fixture(d)
        trim_flags = [f"-O{opt}", "--trimpath", "--emit-llvm"]
        require(build(compiler, c, trim_flags).returncode == 0,
                "trimpath 目录 C 构建失败")
        require(build(compiler, d, trim_flags).returncode == 0,
                "trimpath 目录 D 构建失败")
        texts_c = llvm_texts(c)
        texts_d = [d / p.relative_to(c) for p in texts_c]
        require(len(texts_c) == 1 and texts_d[0].is_file(),
                f"trimpath 产物数量异常：{texts_c} / {texts_d}")
        require(texts_c[0].read_bytes() == texts_d[0].read_bytes(),
                "trimpath 下两个目录的 LLVM 文本不一致")
        relative = source_filename(texts_c[0])
        require(relative != "" and not relative.startswith("/")
                and not (len(relative) > 1 and relative[1] == ":"),
                f"trimpath source_filename 不是相对路径：{relative!r}")

        # 未开 trimpath 时必须保留绝对来源路径，确保本地诊断仍能定位。
        plain = work / "plain" / "project"
        copy_fixture(plain)
        require(build(compiler, plain,
                      [f"-O{opt}", "--emit-llvm"]).returncode == 0,
                "普通来源路径构建失败")
        absolute = source_filename(llvm_texts(plain)[0])
        require(absolute.startswith("/")
                or (len(absolute) > 1 and absolute[1] == ":"),
                f"未开 trimpath 时 source_filename 不是绝对路径：{absolute!r}")

        # 非白名单环境变化不应影响模块缓存：预热后换 YH_WORKERS 仍应命中模块缓存。
        workers = build(compiler, a, [f"-O{opt}"], env={"YH_WORKERS": "1"})
        require(workers.returncode == 0, "YH_WORKERS 构建失败", workers)
        require("[缓存] main" in workers.stdout + workers.stderr,
                "YH_WORKERS 变化不应让模块缓存失效", workers)

        # 白名单环境变化（Darwin 的 strip 开关）必须让链接键失效并重新链接。
        if sys.platform == "darwin":
            plain_link = build(compiler, a, [f"-O{opt}", "--stats"])
            require(plain_link.returncode == 0, "默认链接键构建失败", plain_link)
            require(link_count(plain_link) == 0,
                    "未改白名单环境时链接缓存未命中", plain_link)
            stripped = build(compiler, a, [f"-O{opt}", "--stats"],
                             env={"YH_LINK_STRIP": "1"})
            require(stripped.returncode == 0, "YH_LINK_STRIP 构建失败", stripped)
            require(link_count(stripped) >= 1,
                    "YH_LINK_STRIP 变化未让链接键失效", stripped)


def main():
    """解析参数并逐个优化级别跑检查。"""
    parser = argparse.ArgumentParser(description="C3 路径缓存与 trimpath 回归")
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--opt-level", type=int, choices=(0, 2), default=None)
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    if not compiler.is_file():
        print(f"编译器不存在：{compiler}")
        return 1
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    levels = [args.opt_level] if args.opt_level is not None else [0, 2]
    try:
        for opt in levels:
            one_level(compiler, opt)
            print(f"C3 O{opt}：搬目录命中、trimpath 与 YH_WORKERS 通过")
    except RuntimeError as error:
        print(f"FAIL {error}")
        return 1
    print("C3：路径规范化回归通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
