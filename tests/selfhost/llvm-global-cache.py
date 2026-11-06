#!/usr/bin/env python3
"""C4：全局内容寻址缓存（actions/outputs + 跨目录命中 + 损坏回退）。

覆盖：
  1. 显式 YH_CACHE 目录布局（v1/actions、outputs、tmp、lock）；
  2. 模块中间产物发布到全局 store，同内容只保留一份；
  3. 源目录搬到另一处、无 .build 时按 ActionID 全局命中并物化；
  4. 函数 check/IR action 的全局 fallback（本地记录缺失、iface 保留）；
  5. 损坏 OutputID 按 miss 重编并自愈；
  6. YH_CACHE=off 完全回退到项目缓存/完整构建。

用法：python3 tests/selfhost/llvm-global-cache.py --compiler-path ./yh
退出码：全部通过 0，否则 1。
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "modules" / "projects" / "llvmfunctioncache"
WORK_ROOT = ROOT / "tmp" / "llvm-global-cache"


def run(cmd, cwd, cache, env=None):
    """执行构建；cache 为 None 时设置 YH_CACHE=off。"""
    complete = dict(os.environ)
    complete["YH_STDLIB"] = str(ROOT / "libs")
    complete["YH_CACHE"] = "off" if cache is None else str(cache)
    if env:
        complete.update(env)
    return subprocess.run([str(item) for item in cmd], cwd=cwd,
                          capture_output=True, text=True, env=complete,
                          timeout=1800)


def build(compiler, project, cache, extra=None, env=None):
    """执行 yh build。"""
    cmd = [compiler, "build"]
    if extra:
        cmd.extend(extra)
    return run(cmd, project, cache, env)


def require(condition, message, proc=None):
    """断言；失败附带输出。"""
    if condition:
        return
    detail = ""
    if proc is not None:
        detail = (f"\n退出码: {proc.returncode}\nstdout:\n{proc.stdout[-1600:]}"
                  f"\nstderr:\n{proc.stderr[-1600:]}")
    raise RuntimeError(message + detail)


def copy_fixture(project):
    """复制 fixture，不带缓存目录。"""
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(FIXTURE, project,
                    ignore=shutil.ignore_patterns(".build", "tmp"))


def artifacts(project):
    """返回项目的 obj 目录与 manifest 目录。"""
    root = project / ".build" / "targets"
    dirs = list(root.glob("*/llvm/O*"))
    require(len(dirs) == 1, f"构建目录数量异常：{dirs}")
    return dirs[0]


def index_id(project):
    """读取 main 模块本地 index 的 ActionID（64 hex）。"""
    paths = list(artifacts(project).glob("index/*-main"))
    require(len(paths) == 1, f"本地 index 数量异常：{paths}")
    return paths[0].read_text(encoding="utf-8").strip()


def action_roles(cache):
    """返回 {ActionID: [role,...]}（只读 32 字节头 + 定长条目）。"""
    result = {}
    for path in (cache / "v1" / "actions").glob("*"):
        data = path.read_bytes()
        if len(data) < 24:
            continue
        magic, version, count = struct.unpack_from("<QQQ", data, 0)
        if magic != 0x3141435441485948 or version != 1 or count > 16:
            continue
        roles = []
        for i in range(count):
            off = 24 + i * 48
            if off + 48 > len(data):
                break
            roles.append(struct.unpack_from("<Q", data, off)[0])
        result[path.name] = roles
    return result


def find_action(cache, role):
    """找第一个含指定 role 的 action 文件。"""
    path = None
    for action, roles in action_roles(cache).items():
        if role in roles:
            path = cache / "v1" / "actions" / action
            break
    require(path is not None, f"全局缓存缺少 role={role} 的 action")
    return path


def outputs(cache):
    """全局输出文件列表。"""
    return sorted((cache / "v1" / "outputs").glob("*"))


def cache_cmd(compiler, cache, action, env=None):
    """执行 yh cache <action>；返回 CompletedProcess。"""
    complete = dict(os.environ)
    complete["YH_CACHE"] = str(cache)
    if env:
        complete.update(env)
    return subprocess.run([str(compiler), "cache", action], cwd=ROOT,
                          capture_output=True, text=True, env=complete,
                          timeout=600)


def stats(proc):
    """取 worker 的 check/IR 命中计数。"""
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


def force_module(project):
    """删除 main 的模块 manifest/obj，让 worker 进入缓存查询。"""
    for pattern in ("manifest/*-main.manifest", "obj/*-main.o"):
        for path in (project / ".build").rglob(pattern):
            path.unlink()


def one_run(compiler, work):
    """执行一轮 C4 验收。"""
    cache = work / "cache"
    shutil.rmtree(cache, ignore_errors=True)
    project = work / "a" / "project"
    copy_fixture(project)
    cold = build(compiler, project, cache)
    require(cold.returncode == 0, "冷编失败", cold)
    require((cache / "v1" / "actions").is_dir()
            and (cache / "v1" / "outputs").is_dir()
            and (cache / "v1" / "tmp").is_dir()
            and (cache / "v1" / "lock").is_file(),
            "YH_CACHE 目录布局不完整")
    module_action = find_action(cache, 1)
    modules = action_roles(cache)
    require(len(modules[module_action.name]) == 3, "模块 action 角色数不是 3")
    first_outputs = outputs(cache)
    require(len(first_outputs) >= 3, f"全局输出数量过少：{first_outputs}")
    manifest = list(artifacts(project).glob("manifest/*-main.manifest"))
    require(len(manifest) == 1 and manifest[0].stat().st_size == 128,
            "本地模块 manifest 不是 128 字节")
    require(len(index_id(project)) == 64, "本地 index 不是 64 hex ActionID")

    hot = build(compiler, project, cache)
    require(hot.returncode == 0 and "[缓存] main" in hot.stdout + hot.stderr,
            "同目录二次构建未命中模块缓存", hot)
    require(len(outputs(cache)) == len(first_outputs),
            "相同内容没有去重：输出数量变化")

    moved = work / "b" / "project"
    copy_fixture(moved)
    moved_build = build(compiler, moved, cache)
    require(moved_build.returncode == 0, "跨目录构建失败", moved_build)
    require("[缓存] main" in moved_build.stdout + moved_build.stderr,
            "跨目录未按 ActionID 全局命中", moved_build)
    require(list(artifacts(moved).glob("obj/*-main.o"))
            and list(artifacts(moved).glob("iface/*-main.s.i"))
            and list(artifacts(moved).glob("iface/*-main.s.ct")),
            "全局命中未物化 obj/iface")

    # 函数 action：保留 iface，删除 firc 记录与模块 action，强制 worker。
    prime = project
    force_module(prime)
    action_id = index_id(prime)
    (cache / "v1" / "actions" / action_id).unlink(missing_ok=True)
    primed = build(compiler, prime, cache)
    require(primed.returncode == 0, "函数缓存预热失败", primed)
    function_work = work / "c" / "project"
    shutil.copytree(prime, function_work)
    force_module(function_work)
    shutil.rmtree(artifacts(function_work) / "firc", ignore_errors=True)
    action_id = index_id(prime)
    (cache / "v1" / "actions" / action_id).unlink(missing_ok=True)
    function_build = build(compiler, function_work, cache, ["--stats"])
    require(function_build.returncode == 0, "函数全局缓存构建失败", function_build)
    counts = stats(function_build)
    require(counts["check_hits"] == 4 and counts["ir_hits"] == 4,
            f"函数 action 未全命中：{counts}", function_build)

    # 损坏输出：保留 action，破坏一个 output，下一次必须 miss 并自愈。
    module_action = cache / "v1" / "actions" / index_id(prime)
    require(module_action.is_file(), f"找不到 main 模块 action：{module_action}")
    target_output = None
    data = module_action.read_bytes()
    count = struct.unpack_from("<Q", data, 16)[0]
    for i in range(count):
        off = 24 + i * 48
        role, size = struct.unpack_from("<QQ", data, off)
        if role == 1:
            target_output = cache / "v1" / "outputs" / data[off + 16:off + 48].hex()
            break
    require(target_output is not None and target_output.is_file(),
            "找不到待损坏的模块输出")
    target_output.write_bytes(b"corrupt")
    damaged = work / "d" / "project"
    # 保留 iface/firc 让 worker 只需重建模块对象；删除 main manifest/obj
    # 迫使模块缓存查询走到被损坏的全局输出。
    shutil.copytree(prime, damaged)
    force_module(damaged)
    damaged_build = build(compiler, damaged, cache)
    require(damaged_build.returncode == 0, "损坏输出后构建失败", damaged_build)
    require(target_output.read_bytes() != b"corrupt"
            and len(target_output.read_bytes()) > 8,
            "损坏输出没有被重新发布")

    # off：无项目缓存时完整编译，不新增全局 action/output。
    off = work / "e" / "project"
    copy_fixture(off)
    actions_before = len(action_roles(cache))
    outputs_before = len(outputs(cache))
    off_build = build(compiler, off, None)
    require(off_build.returncode == 0 and "[编译] main" in off_build.stdout + off_build.stderr,
            "YH_CACHE=off 未回退到完整构建", off_build)
    require(len(action_roles(cache)) == actions_before
            and len(outputs(cache)) == outputs_before,
            "YH_CACHE=off 仍写入了全局缓存")

    # C6：debug / verify 损坏 / orphan trim / clean。
    debug_project = work / "f" / "project"
    copy_fixture(debug_project)
    debug = run([compiler, "build"], debug_project, cache,
                {"YH_CACHE_DEBUG": "1"})
    require(debug.returncode == 0
            and "[cache] module action" in debug.stdout + debug.stderr,
            "YH_CACHE_DEBUG 未输出 ActionID", debug)

    # 重新破坏一个当前被 action 引用的 output，verify 必须报 corrupt。
    corrupt_action = find_action(cache, 1)
    corrupt_data = corrupt_action.read_bytes()
    corrupt_count = struct.unpack_from("<Q", corrupt_data, 16)[0]
    corrupt_output = None
    for i in range(corrupt_count):
        off = 24 + i * 48
        role = struct.unpack_from("<Q", corrupt_data, off)[0]
        if role == 1:
            corrupt_output = cache / "v1" / "outputs" / corrupt_data[off + 16:off + 32].hex()
            # 上面的切片少了一半；用完整 32 字节构造路径。
            corrupt_output = cache / "v1" / "outputs" / corrupt_data[off + 16:off + 48].hex()
            break
    require(corrupt_output is not None and corrupt_output.is_file(),
            "找不到 verify 用的模块 output")
    corrupt_output.write_bytes(b"corrupt")
    bad_verify = cache_cmd(compiler, cache, "verify")
    require(bad_verify.returncode != 0 and "corrupt=1" in bad_verify.stdout,
            "verify 未发现损坏 OutputID", bad_verify)

    orphan = cache / "v1" / "outputs" / ("0" * 64)
    orphan.write_bytes(b"orphan" * 1024)
    orphan_verify = cache_cmd(compiler, cache, "verify")
    require(orphan_verify.returncode != 0 and "orphan=0" not in orphan_verify.stdout,
            "verify 未发现孤儿 output", orphan_verify)
    trimmed = cache_cmd(compiler, cache, "trim", {"YH_CACHE_MAX_SIZE": "1K"})
    require(trimmed.returncode in (0, 1), "trim 失败", trimmed)
    require(not orphan.exists(), "trim 未删除孤儿 output")
    clean_verify = cache_cmd(compiler, cache, "verify")
    require("orphan=0" in clean_verify.stdout, "trim 后仍报告 orphan", clean_verify)

    cleaned = cache_cmd(compiler, cache, "clean")
    require(cleaned.returncode == 0, "cache clean 失败", cleaned)
    info = cache_cmd(compiler, cache, "info")
    require(info.returncode == 0 and "actions: 0" in info.stdout
            and "outputs: 0" in info.stdout, "clean 后缓存非空", info)

    # C6：同项目并发构建由项目锁串行化，两边都必须成功。
    concurrent = work / "g" / "project"
    copy_fixture(concurrent)
    env = dict(os.environ)
    env["YH_STDLIB"] = str(ROOT / "libs")
    env["YH_CACHE"] = str(cache)
    cmd = [str(compiler), "build"]
    p1 = subprocess.Popen(cmd, cwd=concurrent, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True)
    p2 = subprocess.Popen(cmd, cwd=concurrent, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True)
    out1, err1 = p1.communicate(timeout=1800)
    out2, err2 = p2.communicate(timeout=1800)
    require(p1.returncode == 0 and p2.returncode == 0,
            f"同项目并发构建失败：{p1.returncode}/{p2.returncode}\n{err1[-400:]}\n{err2[-400:]}")


def main():
    """入口：清理工作目录并跑验收。"""
    parser = argparse.ArgumentParser(description="C4 全局缓存验收")
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    if not compiler.is_file():
        print(f"编译器不存在：{compiler}")
        return 1
    if WORK_ROOT.exists():
        shutil.rmtree(WORK_ROOT)
    WORK_ROOT.mkdir(parents=True)
    try:
        one_run(compiler, WORK_ROOT)
    except RuntimeError as error:
        print(f"FAIL {error}")
        return 1
    print("C4/C6：全局 content store、跨目录命中、函数 action、损坏回退、debug/verify/trim/clean 与 off 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
