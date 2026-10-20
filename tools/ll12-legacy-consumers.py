#!/usr/bin/env python3
"""LL12-0 旧发射消费者普查：按文件/函数统计旧发射相关符号的引用。

用法：python3 tools/ll12-legacy-consumers.py [--json]
口径（2026-10-21 修订）：
  * 函数归属按 `fn <name>(` 切分行区间，命中归入最近的已定义函数；文件级记为 <file>。
  * `ast_ir_b_*` 是 LLVM 快照 lowering 共享的 IR 构造层，单列「共享IR构造」，
    不计入旧链；只有 `ast_ir_lower_*/cache_*/inline_*/template/call_*/hash_*/
    supported/file_shift/total_shift` 才算旧 SSA 链。
  * `bss_n`/`bss_symbols` 是 CheckedModule 快照字段（语义数据），不是发射缓冲，
    只统计 `bss_put*`/`bss_symbol` 发射入口。
  * `o_*` 缓冲只在 gen/ 与 cmd/ 统计，避免与普通变量名冲突。
  * 分类：发射器 / 混合(语义+发射) / 语义求值 / 入口 / LLVM共享 / 其他。
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "compiler"

EMIT_SYMBOLS = [r"\bem_[a-z_]+\b", r"\bdat_[a-z_]+\b", r"\bbss_put[a-z_]*\b", r"\bbss_symbol\b"]
BUFFER_SYMBOLS = [
    r"\bo_out\b", r"\bo_body\b", r"\bo_dat\b", r"\bo_bss\b",
    r"\bo_len\b", r"\bo_dlen\b", r"\bo_blen\b", r"\bo_body_len\b",
    r"\bflush_output[a-z_]*\b",
]
SWITCH_SYMBOLS = [
    r"\bc_backend\b", r"\bc_front_checked\b", r"\bc_em_suppress\b",
    r"\btarget_legacy_ready\b", r"--backend\b",
]
LEGACY_CHAIN_SYMBOLS = [
    r"\bast_ir_lower_[a-z_]+\b", r"\bast_ir_cache_[a-z_]+\b",
    r"\bast_ir_inline_[a-z_]+\b", r"\bast_ir_template[a-z_]*\b",
    r"\bast_ir_call_[a-z_]+\b", r"\bast_ir_hash_[a-z_]+\b",
    r"\bast_ir_expr_supported\b", r"\bast_ir_file_shift[a-z_]*\b",
    r"\bast_ir_total_shift\b", r"\barm64_[a-z_]+\b",
    r"\bemit_runtime_[a-z_]+\b",
]
SHARED_BUILDER_SYMBOLS = [r"\bast_ir_b_[a-z_]+\b"]
VALUE_STATE_SYMBOLS = [
    r"\bc_res_is_addr\b", r"\bc_spill_reg\b", r"\bc_in_body\b",
    r"\bc_lbl_n\b", r"\btn_lbl_[a-z_]+\b",
]

GROUPS = {
    "发射原语 em_/dat_/bss_put": EMIT_SYMBOLS,
    "四缓冲与 flush": BUFFER_SYMBOLS,
    "后端开关/闸门": SWITCH_SYMBOLS,
    "旧 SSA/ARM64 链": LEGACY_CHAIN_SYMBOLS,
    "共享 IR 构造 ast_ir_b_*": SHARED_BUILDER_SYMBOLS,
    "目标相关值状态": VALUE_STATE_SYMBOLS,
}

FN_RE = re.compile(r"^(?:pub )?fn ([a-z_][a-z0-9_]*)\s*\(")
BUFFER_FILES = ("compiler/gen/", "compiler/cmd/")


def iter_yh():
    for path in sorted(SRC.rglob("*.yh")):
        if ".build" in path.parts:
            continue
        yield path


def functions_of(text):
    result = []
    for i, line in enumerate(text.splitlines(), 1):
        m = FN_RE.match(line)
        if m:
            result.append((i, m.group(1)))
    return result


def owner_of(line_no, funcs):
    owner = "<file>"
    for start, name in funcs:
        if start <= line_no:
            owner = name
        else:
            break
    return owner


def classify(path):
    rel = path.relative_to(SRC).as_posix()
    if rel.startswith(("gen/emit_", "backend/arm64")) or rel in (
            "gen/buffer.yh", "gen/emit_runtime_memory.yh"):
        return "发射器"
    if rel.startswith("ast/ast_ir") or rel in ("ast/ast_ir.yh",):
        return "旧SSA链(含共享builder)"
    if rel.startswith("ast/module_snapshot") or rel.startswith("check/"):
        return "LLVM共享"
    if rel.startswith("gen/sem_") or rel == "gen/symbols.yh":
        return "混合(语义+发射)"
    if rel.startswith("parse/") or rel.startswith("comptime/"):
        return "语义/求值"
    if rel.startswith("cmd/"):
        return "入口"
    if rel.startswith(("backend/llvm", "ir/ssa_module")):
        return "LLVM共享"
    return "其他"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    per_file, per_func = {}, {}
    per_group = {name: 0 for name in GROUPS}
    total = 0
    for path in iter_yh():
        text = path.read_text(encoding="utf-8", errors="replace")
        funcs = functions_of(text)
        rel = path.relative_to(ROOT).as_posix()
        info = per_file.setdefault(rel, {"group": classify(path), "total": 0, "by": {}})
        for lineno, line in enumerate(text.splitlines(), 1):
            code = line.split("//", 1)[0]
            for group, patterns in GROUPS.items():
                if group == "四缓冲与 flush" and not rel.startswith(BUFFER_FILES):
                    continue
                hits = sum(len(re.findall(p, code)) for p in patterns)
                if not hits:
                    continue
                info["total"] += hits
                info["by"][group] = info["by"].get(group, 0) + hits
                per_group[group] += hits
                total += hits
                key = (rel, owner_of(lineno, funcs))
                per_func[key] = per_func.get(key, 0) + hits

    if args.json:
        print(json.dumps({"total": total, "per_group": per_group, "per_file": per_file,
                          "per_func": {f"{a}:{b}": c for (a, b), c in per_func.items()}},
                         ensure_ascii=False, indent=1))
        return 0

    print(f"总计 {total} 处引用（不含注释）\n")
    print("## 分组")
    for name, count in per_group.items():
        print(f"- {name}: {count}")
    print("\n## 按文件（前 40）")
    for rel, info in sorted(per_file.items(), key=lambda kv: -kv[1]["total"])[:40]:
        if not info["total"]:
            continue
        by = ", ".join(f"{k}={v}" for k, v in sorted(info["by"].items()))
        print(f"- {rel} [{info['group']}] {info['total']}（{by}）")
    print("\n## 按函数（前 60）")
    for (rel, fn), count in sorted(per_func.items(), key=lambda kv: -kv[1])[:60]:
        print(f"- {rel}:{fn} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
