#!/usr/bin/env python3
"""LA3：函数级 IR 缓存的命中、失效、损坏与产物一致性回归。

用 llvmfunctioncache 项目的 4 个运行期函数验证 IR 缓存：
    cold       0 hit / 4 miss / 4 lowered
    注释/空行   4 hit / 0 miss / 0 lowered（模块对象键变化，worker 仍运行）
    改一个函数   3 hit / 1 miss / 1 lowered
    插入第 5 个  4 hit / 1 miss / 1 lowered
    损坏一条记录 3 hit / 1 miss，且只重建该记录
    改接口/布局  0 hit / 4 miss（环境键保守失效）
并比较冷编与命中构建的对象/LLVM 文本字节一致。

check 切片缓存自格式 v3（2026-10-26）起重新装载：记录携带本函数的字符串登记，
并在 capture 时守卫「本函数没有新建类型/静态数据」，因此命中后 lowering 仍能查到
受检字节，且类型编号不受跳过影响。下面的 check 期望即恢复为命中计数。

所有产物在 tmp/llvm-function-cache/；默认使用候选自身目标，不写死 x64。
usage: python3 tests/selfhost/llvm-function-cache.py --compiler-path ./yh
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "modules" / "projects" / "llvmfunctioncache"
WORK_ROOT = ROOT / "tmp" / "llvm-function-cache"
BINARY = "llvm_function_cache"


class Failure(Exception):
    """函数缓存行为不符合冻结预期。"""


def run(cmd, cwd, timeout=1800):
    """用 argv 调用命令并捕获输出。"""
    return subprocess.run([str(item) for item in cmd], cwd=cwd,
                          capture_output=True, text=True, timeout=timeout)


def require(condition, message, proc=None):
    """断言；失败时附带命令输出。"""
    if condition:
        return
    detail = ""
    if proc is not None:
        detail = (f"\n退出码: {proc.returncode}\nstdout:\n{proc.stdout[-2000:]}"
                  f"\nstderr:\n{proc.stderr[-2000:]}")
    raise Failure(message + detail)


def copy_fixture(work):
    """复制 fixture 到含空格/中文的工作目录。"""
    project = work / "函数 缓存" / "project"
    project.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE, project)
    return project


def parse_stats(proc):
    """解析主模块 worker 的 yh-stats 行，返回缓存计数。"""
    rows = []
    for line in (proc.stdout + proc.stderr).splitlines():
        if not line.startswith("yh-stats "):
            continue
        row = dict(item.split("=", 1) for item in line.split()[1:] if "=" in item)
        rows.append(row)
    workers = [row for row in rows if int(row.get("ir_functions", "0")) > 0]
    require(len(workers) == 1,
            f"应只有一个含函数计数的 worker，实际 {len(workers)}：{rows}", proc)
    row = workers[0]
    # PF2 阶段归因字段：存在性也是接口契约，缺字段直接判失败（-1 表示未输出）。
    stage_ns = {
        "front": int(row.get("time_front_ns", "-1")),
        "lower": int(row.get("time_lower_ns", "-1")),
        "irbuild": int(row.get("time_irbuild_ns", "-1")),
        "bridge": int(row.get("time_bridge_ns", "-1")),
    }
    require(all(value >= 0 for value in stage_ns.values()),
            f"stats 缺少阶段归因字段：{stage_ns}", proc)
    # PL1：lowering 细分字段；前四段之和必须 ≤ time_lower_ns（互斥子区间），
    # build 内四段之和也必须 ≤ time_lower_build_ns。
    lower_ns = {
        "prep": int(row.get("time_lower_prep_ns", "-1")),
        "decl": int(row.get("time_lower_decl_ns", "-1")),
        "build": int(row.get("time_lower_build_ns", "-1")),
        "verify": int(row.get("time_lower_verify_ns", "-1")),
        "lookup": int(row.get("time_lower_lookup_ns", "-1")),
        "cache": int(row.get("time_lower_cache_ns", "-1")),
        "fn": int(row.get("time_lower_fn_ns", "-1")),
        "capture": int(row.get("time_lower_capture_ns", "-1")),
    }
    require(all(value >= 0 for value in lower_ns.values()),
            f"stats 缺少 lowering 细分字段：{lower_ns}", proc)
    outer = lower_ns["prep"] + lower_ns["decl"] + lower_ns["build"] + lower_ns["verify"]
    require(outer <= stage_ns["lower"] * 1.02,
            f"lowering 四段之和 {outer} 超出 time_lower_ns {stage_ns['lower']}", proc)
    inner = (lower_ns["lookup"] + lower_ns["cache"] + lower_ns["fn"]
             + lower_ns["capture"])
    require(inner <= lower_ns["build"] * 1.02,
            f"build 内四段之和 {inner} 超出 time_lower_build_ns {lower_ns['build']}",
            proc)
    return {
        "hits": int(row.get("ir_cache_hits", "-1")),
        "misses": int(row.get("ir_cache_misses", "-1")),
        "lowered": int(row.get("ir_lowered", "-1")),
        "functions": int(row.get("ir_functions", "-1")),
        "check_hits": int(row.get("check_cache_hits", "-1")),
        "check_misses": int(row.get("check_cache_misses", "-1")),
        "check_skipped": int(row.get("check_skipped", "-1")),
        "stage_ns": stage_ns,
    }


def build(project, compiler, opt):
    """带 --emit-llvm 构建并运行；返回 (统计, 对象路径, LLVM 文本路径)。"""
    proc = run([compiler, f"-O{opt}", "--emit-llvm", "build", "--stats"], project)
    require(proc.returncode == 0, f"O{opt} 项目构建失败", proc)
    binary = project / ".build" / BINARY
    require(binary.exists(), "构建未生成默认程序", proc)
    ran = run([binary], project)
    require(ran.returncode == 0, f"程序返回 {ran.returncode}，期望 0", ran)
    stats = parse_stats(proc)
    objects = sorted(project.glob(".build/targets/*/llvm/*/obj/*-main.o"))
    texts = sorted(project.glob(".build/targets/*/llvm/*/llvm/*-main.ll"))
    require(len(objects) == 1 and len(texts) == 1,
            f"应有一个 main 对象/文本，实际 {objects} / {texts}", proc)
    return stats, objects[0], texts[0]


def digest(path):
    """文件内容 SHA-256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_dir(project, opt):
    """返回 main 模块的函数缓存目录。"""
    dirs = sorted(project.glob(f".build/targets/*/llvm/O{opt}/firc/*-main"))
    require(len(dirs) == 1, f"函数缓存目录数量异常：{dirs}")
    return dirs[0]


def records(project, opt):
    """返回 main 模块索引中实际登记的 键→摘要 映射（忽略旧版本残留记录）。"""
    directory = cache_dir(project, opt)
    index = directory / "index"
    require(index.exists(), f"函数缓存索引缺失：{index}")
    keys = [line.strip() for line in index.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    result = {}
    for key in keys:
        path = directory / f"{key}.fir"
        require(path.exists(), f"索引登记了缺失的记录：{path}")
        result[key] = digest(path)
    return result


def expect(stats, ir, check, label, proc=None):
    """断言 IR 与 check 两组缓存计数。"""
    actual_ir = (stats["hits"], stats["misses"], stats["lowered"])
    actual_check = (stats["check_hits"], stats["check_misses"],
                    stats["check_skipped"])
    require(actual_ir == ir,
            f"{label}：期望 IR hits/misses/lowered={ir}，实际 {actual_ir}", proc)
    require(actual_check == check,
            f"{label}：期望 check hits/misses/skipped={check}，实际 {actual_check}",
            proc)


def append(path, text):
    """在源码末尾追加文本。"""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def one_level(compiler, opt):
    """在一个 O 级别上跑完整失效矩阵。"""
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"O{opt}-", dir=WORK_ROOT) as temp:
        work = Path(temp)
        project = copy_fixture(work)
        main = project / "src" / "main" / "main.yh"

        cold, cold_object, cold_text = build(project, compiler, opt)
        expect(cold, (0, 4, 4), (0, 4, 0), "冷编")
        # PF2：冷编四段归因都应产生正时耗（前段/ lowering / IR 构造 / 内嵌桥）。
        require(min(cold["stage_ns"].values()) > 0,
                f"冷编阶段归因应全为正：{cold['stage_ns']}")
        cold_object_hash = digest(cold_object)
        cold_text_hash = digest(cold_text)
        # PC3：全冷构建（.build 刚清空）不写函数缓存，避免冷编付 capture 成本。
        # 先做一次等价重编把记录写出来，后面的失效矩阵从暖缓存开始。
        for pattern in ("manifest/*-main.manifest", "obj/*-main.o"):
            for path in (project / ".build").rglob(pattern):
                path.unlink()
        primed, _, _ = build(project, compiler, opt)
        expect(primed, (0, 4, 4), (4, 0, 4), "首轮重编（缓存写入）")

        # 注释/空行不进入 token 流：模块对象键变化，但 4 个函数应全部命中。
        # 插在函数之前会移动后续源码字节偏移，命中路径必须按当前符号重建 locs。
        main.write_text(main.read_text(encoding="utf-8").replace(
            "fn twice(value int) int {",
            "// 仅注释与空行变化\n\nfn twice(value int) int {", 1),
            encoding="utf-8")
        hot, hot_object, hot_text = build(project, compiler, opt)
        expect(hot, (4, 0, 0), (4, 0, 4), "注释变化")
        require(digest(hot_object) == cold_object_hash,
                "命中构建的对象与冷编不同")
        require(digest(hot_text) == cold_text_hash,
                "命中构建的 LLVM 文本与冷编不同")

        # 改一个函数体：只该函数 miss。
        main.write_text(main.read_text(encoding="utf-8").replace(
            "return value + 1;", "return value + 1 + 0;", 1), encoding="utf-8")
        changed, _, _ = build(project, compiler, opt)
        expect(changed, (3, 1, 1), (3, 1, 3), "单函数修改")

        # 插入第 5 个函数：签名事实进函数键（调用方 ABI 依赖被调方签名），
        # 声明集合变化按设计保守失效整模块——新函数可能被任何旧函数调用。
        # 新函数没有任何外部调用方：私有 + 无引用会被 UF1（未使用函数检查）
        # 判死，所以写成自递归形态（UF1 按名字判使用，自引用算已使用）。签名
        # () int 与既有 text_marker 相同，不新增类型/签名表项，其余 4 个函数的
        # check 键因此保持稳定（期望 4 命中 1 未命中）。
        append(main, "\nfn extra() int {\n    return extra();\n}\n")
        inserted, _, _ = build(project, compiler, opt)
        expect(inserted, (0, 5, 5), (4, 1, 4), "插入新函数")

        # 损坏一条记录：只重建该记录，其余仍命中。
        before = records(project, opt)
        require(len(before) == 5, f"应有 5 条记录，实际 {sorted(before)}")
        # 只有「可缓存的函数」才有 check 切片（v3 会跳过新建类型/静态数据的函数），
        # 所以选一个两份记录都在的键作受害者，否则 .fchk 的损坏对命中没有影响。
        directory = cache_dir(project, opt)
        victim = next((key for key in sorted(before)
                       if (directory / f"{key}.fchk").exists()), sorted(before)[0])
        for suffix in (".fir", ".fchk"):
            path = directory / f"{victim}{suffix}"
            if path.exists():
                path.write_bytes(b"corrupt")
        append(main, "\n// 触发 worker 以检查损坏记录\n")
        damaged, _, _ = build(project, compiler, opt)
        # v3 只为「不新建类型/静态数据」的函数写 check 切片，所以损坏的键是否被
        # 索引登记才决定 check 侧是 4/1 还是 5/0；IR 侧必须稳定地只重建该记录。
        check_index = directory / "index.check"
        indexed = (check_index.read_text(encoding="utf-8").split() if check_index.exists() else [])
        damaged_check = (4, 1, 4) if victim in indexed else (5, 0, 5)
        expect(damaged, (4, 1, 1), damaged_check, "损坏记录")
        after = records(project, opt)
        changed_keys = {key for key in before if before[key] != after.get(key)}
        # 重建后的记录可能与损坏前逐字节相同（缓存不再复制源码正文），
        # 关键是不能影响其他记录。
        require(changed_keys <= {victim},
                f"损坏恢复影响了非目标记录：{sorted(changed_keys - {victim})}")

        # 接口变化：环境键保守失效，全部 miss。
        append(main, "\npub const EXTRA_INTERFACE int = 0;\n")
        invalidated, _, _ = build(project, compiler, opt)
        expect(invalidated, (0, 5, 5), (0, 5, 0), "接口变化")

        # 恢复接口后的注释变化仍应全命中，证明失效记录已重新提交。
        append(main, "\n// 接口变化后的缓存已重建\n")
        rebuilt, _, _ = build(project, compiler, opt)
        expect(rebuilt, (5, 0, 0), (5, 0, 5), "接口重建后命中")


def main() -> int:
    """解析参数并跑 O0/O2 失效矩阵。"""
    parser = argparse.ArgumentParser(description="yh 函数级 IR 缓存回归")
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--opt-level", type=int, choices=(0, 2), default=None)
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    if not compiler.exists():
        print(f"编译器不存在：{compiler}")
        return 1
    levels = [args.opt_level] if args.opt_level is not None else [0, 2]
    try:
        for opt in levels:
            one_level(compiler, opt)
            print(f"LA3 O{opt}：冷编/命中/单函数/插入/损坏/接口失效全部通过")
    except Failure as error:
        print(f"FAIL {error}")
        return 1
    except subprocess.TimeoutExpired as error:
        print(f"FAIL 超时：{error}")
        return 1
    print("LA3：函数级 IR 缓存矩阵通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
