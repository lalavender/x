#!/usr/bin/env python3
"""yh-codeflow：扫描当前编译器源码，生成自包含的 HTML 代码流程图。

用法：
    python3 tools/yh-codeflow.py                     # 生成 tmp/codeflow/index.html
    python3 tools/yh-codeflow.py --out /tmp/cf.html  # 指定输出
    python3 tools/yh-codeflow.py --check             # 只解析并打印统计（门禁用）
    python3 tools/yh-codeflow.py --max-functions 120 # 单模块函数图上限

设计要点（为什么这么做）：
1. **离线优先**：HTML 自包含（内联 CSS/JS/SVG），不引 CDN，断网也能打开。
2. **布局在 Python 里算**：SCC 缩点 + 最长路径分层 + 重心排序，输出确定坐标；
   JS 只负责平移/缩放/悬浮/下钻，刷新页面不会“跳图”。
3. **调用图是近似图**：yh 没有现成的跨模块调用图导出，这里按「函数声明名 +
   模块归属」启发式解析——同名函数优先同模块，其次仅当全仓唯一时才跨模块；
   解析不出的调用计数上报为 unresolved，不猜。

输出的三个视图：
- 模块依赖图：`import` 边（静态结构，17 个模块）。
- 模块调用图：函数级调用聚合到模块（动态耦合强度）。
- 函数调用图：选中模块内的函数节点 + 出/入调用边（跨模块调用显示为目标模块）。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "compiler"

MODULE_RE = re.compile(r"(?m)^module ([A-Za-z0-9_]+)")
IMPORT_RE = re.compile(r"(?m)^import ([A-Za-z0-9_.]+)(?:\s+as\s+([A-Za-z0-9_]+))?")
FN_RE = re.compile(
    r"(?m)^((?:@\[[^\]]*\]\s*)?)(pub )?fn ([A-Za-z_][A-Za-z0-9_]*)\s*\(")
QUAL_CALL_RE = re.compile(r"(?<![A-Za-z0-9_.])([A-Za-z_][A-Za-z0-9_]*)\."
                          r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
STRUCT_RE = re.compile(r"(?m)^(?:pub )?struct ([A-Za-z_][A-Za-z0-9_]*)")
CALL_RE = re.compile(r"(?<![A-Za-z0-9_.])([A-Za-z_][A-Za-z0-9_]*)\s*\(")
# 语言关键字/内建：即便与用户函数同名也不当作调用目标（减少噪声）。
CALL_IGNORE = {
    "if", "for", "while", "switch", "return", "sizeof", "cast", "typeof",
    "fn", "let", "const", "struct", "union", "enum", "test", "module", "import",
}

SKIP_DIRS = {".build", "tmp"}


def source_files(root: Path) -> list[Path]:
    """递归列出编译器源码（跳过构建缓存与临时目录）。"""
    files = []
    for path in sorted(root.rglob("*.yh")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return files


def parse_file(path: Path, root: Path) -> dict | None:
    """解析单个源文件：模块名、导入、函数声明、结构体名与行号。"""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    mod = MODULE_RE.search(text)
    if not mod:
        return None
    rel = path.relative_to(root).as_posix()
    lines = text.splitlines()
    fns = []
    for m in FN_RE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        fns.append({"name": m.group(3), "line": line,
                    "pub": 1 if m.group(2) else 0,
                    "extern": 1 if "extern" in m.group(1) else 0})
    structs = [m.group(1) for m in STRUCT_RE.finditer(text)]
    return {
        "path": rel,
        "module": mod.group(1),
        "loc": len(lines),
        "imports": [{"path": a, "alias": b or a.split(".")[-1]}
                    for a, b in IMPORT_RE.findall(text)],
        "fns": fns,
        "structs": structs,
        "text": text,
    }


def strip_noise(text: str) -> str:
    """把注释与字符串字面量替换为空格（保留换行），避免把 C 片段当调用。"""
    out = list(text)
    i, n = 0, len(text)
    state = None  # None / "line" / "block" / "str"
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state is None:
            if c == "/" and nxt == "/":
                state = "line"; out[i] = out[i + 1] = " "; i += 2; continue
            if c == "/" and nxt == "*":
                state = "block"; out[i] = out[i + 1] = " "; i += 2; continue
            if c == '"':
                state = "str"; out[i] = " "; i += 1; continue
        elif state == "line":
            if c == "\n":
                state = None
            else:
                out[i] = " "
        elif state == "block":
            if c == "*" and nxt == "/":
                out[i] = out[i + 1] = " "; i += 2; state = None; continue
            if c != "\n":
                out[i] = " "
        else:  # str
            if c == "\\" and i + 1 < n:
                out[i] = out[i + 1] = " "; i += 2; continue
            if c == '"':
                state = None
            if c != "\n":
                out[i] = " "
        i += 1
    return "".join(out)


def extract_calls(files: list[dict], mod_imports: dict[str, set[str]]
                  ) -> tuple[list[dict], int]:
    """抽取函数级调用边（启发式，见模块 docstring）。

    解析顺序：本文件别名表里的 `mod.fn(...)` → 同模块唯一声明 →
    文件 import 的模块里唯一声明 → 全仓唯一声明；其余记未解析。
    `@[extern]` 声明不进索引（它们是被调用的平台 API，不是内部流程）。
    """
    decl: dict[str, list[tuple[str, str]]] = defaultdict(list)
    by_module: set[tuple[str, str]] = set()
    for f in files:
        for fn in f["fns"]:
            if fn["extern"]:
                continue
            decl[fn["name"]].append((f["module"], fn["name"]))
            by_module.add((f["module"], fn["name"]))

    edges: Counter = Counter()
    unresolved = 0
    for f in files:
        mod = f["module"]
        fns = f["fns"]
        if not fns:
            continue
        alias: dict[str, str] = {x["alias"]: x["path"] for x in f["imports"]}
        alias[f["module"]] = f["module"]
        clean = strip_noise(f["text"]).splitlines()
        starts = [fn["line"] for fn in fns]
        for idx, fn in enumerate(fns):
            begin = fn["line"] - 1
            end = (starts[idx + 1] - 1) if idx + 1 < len(starts) else len(clean)
            body = "\n".join(clean[begin:end])
            # 1) 限定调用：别名 → 目标模块
            for m in QUAL_CALL_RE.finditer(body):
                target_mod = alias.get(m.group(1))
                if target_mod is None:
                    continue
                if (target_mod, m.group(2)) in by_module:
                    edges[(fn["name"], target_mod, m.group(2))] += 1
            # 2) 非限定调用
            for m in CALL_RE.finditer(body):
                name = m.group(1)
                if name in CALL_IGNORE or name == fn["name"]:
                    continue
                targets = decl.get(name)
                if not targets:
                    continue
                same = [t for t in targets if t[0] == mod]
                if len(same) == 1:
                    target = same[0]
                else:
                    imported = [t for t in targets
                                if t[0] in set(alias.values()) and t[0] != mod]
                    if len(imported) == 1:
                        target = imported[0]
                    elif len(targets) == 1:
                        target = targets[0]
                    else:
                        unresolved += 1
                        continue
                edges[(fn["name"], target[0], target[1])] += 1
    out = [{"from": a, "to": c, "to_module": b, "weight": w}
           for (a, b, c), w in edges.items()]
    return out, unresolved


def collect(root: Path) -> dict:
    """汇总一次扫描的数据（模块、文件、函数、调用边与统计）。"""
    files = [x for x in (parse_file(p, root) for p in source_files(root)) if x]
    modules: dict[str, dict] = {}
    for f in files:
        m = modules.setdefault(f["module"], {"name": f["module"], "files": [],
                                             "loc": 0, "imports": set(), "fns": 0})
        m["files"].append(f["path"])
        m["loc"] += f["loc"]
        m["fns"] += len(f["fns"])
        m["imports"].update(x["path"].split(".")[-1] for x in f["imports"]
                            if x["path"].split(".")[-1] != f["module"])
    for m in modules.values():
        m["imports"] = sorted(m["imports"])
    mod_imports = {name: set(m["imports"]) for name, m in modules.items()}
    edges, unresolved = extract_calls(files, mod_imports)
    # 标准库依赖（hash/libs）不是编译器模块：单独标为 external，让依赖图完整。
    known = set(modules)
    external = sorted({dep for m in modules.values() for dep in m["imports"]} - known)
    return {
        "files": [{"path": f["path"], "module": f["module"], "loc": f["loc"],
                   "fns": len(f["fns"]), "structs": f["structs"]} for f in files],
        "modules": sorted(modules.values(), key=lambda m: m["name"]),
        "functions": [{"name": fn["name"], "module": f["module"], "file": f["path"],
                       "line": fn["line"], "pub": fn["pub"]}
                      for f in files for fn in f["fns"]],
        "calls": edges,
        "unresolved": unresolved,
        "external": external,
    }


def strongly_connected(nodes: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Tarjan 强连通分量（节点用名字标识）。"""
    graph: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    result: list[list[str]] = []
    counter = [0]
    sys.setrecursionlimit(max(10000, len(nodes) * 4))

    def visit(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            result.append(comp)

    for n in nodes:
        if n not in index:
            visit(n)
    return result


def layered_layout(nodes: list[str], edges: list[tuple[str, str]]
                   ) -> tuple[dict[str, tuple[float, float]], float, float]:
    """SCC 缩点 → 缩点图拓扑分层 → 重心排序；返回 (坐标, 画布宽, 画布高)。

    分层用 Kahn 拓扑序做最长路径松弛（缩点图必然无环），所以不会出现
    「同一连通块里的节点被拉到第 33 层」这类假分层；画布尺寸按最宽一层自适应。
    自环（同文件内调用）不参与分层，但渲染时保留。
    """
    if not nodes:
        return {}, 1400.0, 900.0
    external = [(a, b) for a, b in edges if a != b]
    comps = strongly_connected(nodes, external)
    comp_of = {n: i for i, comp in enumerate(comps) for n in comp}
    nc = len(comps)
    children: dict[int, set[int]] = {i: set() for i in range(nc)}
    indeg = [0] * nc
    for a, b in external:
        ca, cb = comp_of[a], comp_of[b]
        if ca == cb:
            continue
        if cb not in children[ca]:
            children[ca].add(cb)
            indeg[cb] += 1
    queue = [i for i in range(nc) if indeg[i] == 0]
    topo: list[int] = []
    while queue:
        i = queue.pop()
        topo.append(i)
        for j in sorted(children[i]):
            indeg[j] -= 1
            if indeg[j] == 0:
                queue.append(j)
    layer = [0] * nc
    for i in topo:
        for j in children[i]:
            layer[j] = max(layer[j], layer[i] + 1)
    n_layers = max(layer) + 1

    by_layer: dict[int, list[str]] = defaultdict(list)
    for i, comp in enumerate(comps):
        for n in comp:
            by_layer[layer[i]].append(n)
    max_layer_nodes = max(len(v) for v in by_layer.values())
    width = max(1400.0, min(12000.0, max_layer_nodes * 155.0 + 200.0))
    height = max(900.0, min(9000.0, n_layers * 130.0 + 200.0))

    pos: dict[str, float] = {}
    succs: dict[str, list[str]] = defaultdict(list)
    preds: dict[str, list[str]] = defaultdict(list)
    for a, b in external:
        preds[b].append(a)
        succs[a].append(b)

    def place(layer_i: int, neighbors: dict[str, list[str]]) -> None:
        group = by_layer[layer_i]
        group.sort(key=lambda n: (sum(pos.get(p, 0.0) for p in neighbors[n]) /
                                  max(1, len(neighbors[n])), n))
        step = width / (len(group) + 1)
        for idx, n in enumerate(group):
            pos[n] = step * (idx + 1)

    for layer_i in range(n_layers):
        place(layer_i, preds)
    for _ in range(2):
        for layer_i in range(n_layers - 1, -1, -1):
            place(layer_i, succs)
        for layer_i in range(n_layers):
            place(layer_i, preds)
    coords = {n: (pos[n], height * (layer[comp_of[n]] + 1) / (n_layers + 1))
              for n in nodes}
    return coords, width, height


def aggregate_module_calls(data: dict) -> tuple[list[str], list[tuple[str, str, int]]]:
    """把函数级调用聚合到模块：模块内自调用不入边，跨模块保留计数。"""
    fn_module = {f["name"]: f["module"] for f in data["functions"]}
    weight: Counter = Counter()
    for e in data["calls"]:
        a = fn_module.get(e["from"])
        b = e["to_module"]
        if a and b and a != b:
            weight[(a, b)] += e["weight"]
    return [m["name"] for m in data["modules"]], \
        sorted((a, b, w) for (a, b), w in weight.items())


def module_layouts(data: dict) -> dict:
    """算好三个视图的布局：模块依赖、模块调用、模块内文件调用。

    文件视图按「调用者文件 → 被调用文件」聚合；跨模块调用落到 `@模块` 节点，
    避免单个模块的函数图把画面压成一团。
    """
    mods = [m["name"] for m in data["modules"]] + data.get("external", [])
    import_edges = [(m["name"], dep) for m in data["modules"] for dep in m["imports"]]
    fn_file = {(f["module"], f["name"]): f["file"] for f in data["functions"]}
    fn_module = {f["name"]: f["module"] for f in data["functions"]}
    call_nodes, call_edges = aggregate_module_calls(data)

    def layout(nodes, edges):
        pos, w, h = layered_layout(nodes, edges)
        return {"edges": [list(e) for e in edges], "pos": pos, "w": w, "h": h}

    layouts = {
        "imports": layout(mods, import_edges),
        "calls": layout(call_nodes, [(a, b) for a, b, _ in call_edges]),
        "calls_weights": {f"{a}\t{b}": w for a, b, w in call_edges},
        "files": {},
    }
    for m in data["modules"]:
        own = [f["path"] for f in data["files"] if f["module"] == m["name"]]
        if not own:
            continue
        own_set = set(own)
        weight: Counter = Counter()
        ext_mods = set()
        for e in data["calls"]:
            caller_mod = fn_module.get(e["from"])
            if caller_mod != m["name"]:
                continue
            src = fn_file.get((m["name"], e["from"]))
            if src is None:
                continue
            if e["to_module"] == m["name"]:
                dst = fn_file.get((m["name"], e["to"]))
                if dst is None:
                    continue
            else:
                dst = "@" + e["to_module"]
                ext_mods.add(e["to_module"])
            weight[(src, dst)] += e["weight"]
        nodes = sorted(own_set) + [f"@{x}" for x in sorted(ext_mods)]
        edges = sorted(weight)
        layouts["files"][m["name"]] = layout(nodes, edges)
        layouts["files"][m["name"]]["weights"] = {
            f"{a}\t{b}": w for (a, b), w in weight.items()}
    return layouts


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>yh 编译器代码流程图</title>
<style>
  :root { --bg:#0f1420; --panel:#161d2d; --fg:#dbe3f0; --dim:#8b97ad;
          --edge:#5b6b86; --hot:#68d391; --warn:#f6ad55; }
  * { box-sizing: border-box; }
  body { margin:0; font:13px/1.5 -apple-system,"Helvetica Neue",Arial,sans-serif;
         background:var(--bg); color:var(--fg); height:100vh; display:flex; }
  aside { width:260px; flex:0 0 260px; background:var(--panel); padding:14px;
          overflow:auto; border-right:1px solid #24304a; }
  h1 { font-size:14px; margin:0 0 8px; letter-spacing:.5px; }
  .stat { color:var(--dim); font-size:12px; margin-bottom:10px; white-space:pre-line; }
  .tabs button { width:100%; text-align:left; margin:2px 0; padding:6px 8px;
                 background:#1d2740; color:var(--fg); border:1px solid #2b3a5a;
                 border-radius:4px; cursor:pointer; font-size:12px; }
  .tabs button.on { border-color:var(--hot); color:var(--hot); }
  #mods { margin-top:10px; }
  #mods div { padding:3px 6px; border-radius:3px; cursor:pointer; color:var(--dim);
              font-size:12px; display:flex; justify-content:space-between; }
  #mods div:hover { background:#1d2740; color:var(--fg); }
  #mods div.on { background:#22304d; color:var(--hot); }
  main { flex:1; position:relative; overflow:hidden; }
  svg { width:100%; height:100%; display:block; cursor:grab; }
  svg.grabbing { cursor:grabbing; }
  .node rect { fill:#1d2740; stroke:#3a4b6d; stroke-width:1; rx:4; }
  .node text { fill:var(--fg); font-size:11px; pointer-events:none; }
  .node.pub rect { stroke:#68d391; }
  .node.ext rect { stroke-dasharray: 4 3; stroke:#6c7a94; }
  .node.ext text { fill: var(--dim); }
  .node:hover rect { fill:#27406b; stroke:var(--hot); }
  .node.sel rect { stroke:var(--warn); stroke-width:2; }
  .edge { stroke:var(--edge); fill:none; opacity:.38; }
  .edge.hi { opacity:.95; }
  .edge.cross { stroke:#8a6fb5; }
  .edge.hot { stroke:var(--hot); stroke-width:2; }
  .arrow { fill:var(--edge); }
  .arrow.cross { fill:#8a6fb5; }
  #tip { position:absolute; pointer-events:none; background:#0b1020; color:var(--fg);
         border:1px solid #3a4b6d; border-radius:4px; padding:6px 8px; font-size:12px;
         display:none; max-width:360px; white-space:pre-line; z-index:9; }
  #legend { position:absolute; right:12px; bottom:12px; color:var(--dim); font-size:11px;
            background:rgba(15,20,32,.85); padding:8px 10px; border-radius:4px;
            border:1px solid #24304a; white-space:pre-line; }
</style>
</head>
<body>
<aside>
  <h1>yh 代码流程图</h1>
  <div class="stat" id="stat"></div>
  <div class="tabs">
    <button data-view="imports" class="on">① 模块依赖（import）</button>
    <button data-view="calls">② 模块调用强度</button>
    <button data-view="files">③ 模块内文件调用</button>
  </div>
  <div id="mods"></div>
</aside>
<main>
  <svg id="graph" xmlns="http://www.w3.org/2000/svg"></svg>
  <div id="tip"></div>
  <div id="legend"></div>
</main>
<script>
const DATA = __DATA__;
const LAYOUT = __LAYOUT__;
const SVG_NS = "http://www.w3.org/2000/svg";
let view = "imports", selected = "", hoverNode = null, zoom = 1, panX = 0, panY = 0;

const svg = document.getElementById("graph");
const tip = document.getElementById("tip");
const stat = document.getElementById("stat");

function el(tag, attrs, parent) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}
function modInfo(name) { return DATA.modules.find(x => x.name === name); }
function currentLayout() {
  if (view === "files")
    return LAYOUT.files[selected] || { edges: [], pos: {}, w: 1400, h: 900, weights: {} };
  return LAYOUT[view];
}
function labelOf(node) {
  if (view !== "files") return node;
  if (node.startsWith("@")) return node.slice(1) + "（其他模块）";
  return node.split("/").pop().replace(/\\.yh$/, "");
}
function nodeSize(label, isModule) {
  return [Math.max(70, Math.min(260, label.length * 7 + 20)), isModule ? 26 : 30];
}
function weightOf(layout, a, b) {
  const w = layout.weights || {};
  return w[a + "\\t" + b] || 1;
}
function draw() {
  const layout = currentLayout();
  const W = layout.w || 1400, H = layout.h || 900;
  svg.innerHTML = "";
  const defs = el("defs", {}, svg);
  const marker = el("marker", { id: "arrow", viewBox: "0 0 10 10", refX: "9",
                                refY: "5", markerWidth: "6", markerHeight: "6",
                                orient: "auto-start-reverse" }, defs);
  el("path", { d: "M 0 0 L 10 5 L 0 10 z", class: "arrow" }, marker);
  const g = el("g", {}, svg);
  const pos = layout.pos || {};
  for (const [a, b] of layout.edges || []) {
    const pa = pos[a], pb = pos[b];
    if (!pa || !pb) continue;
    const [aw, ah] = nodeSize(labelOf(a), view !== "files");
    const [bw, bh] = nodeSize(labelOf(b), view !== "files");
    const cross = b.startsWith("@") || (view === "files" && a.startsWith("@"));
    const line = el("line", {
      x1: pa[0], y1: pa[1] + ah / 2, x2: pb[0], y2: pb[1] - bh / 2,
      class: "edge" + (cross ? " cross" : ""), "marker-end": "url(#arrow)",
    }, g);
    const w = weightOf(layout, a, b);
    if (view === "calls" || view === "files")
      line.setAttribute("stroke-width", Math.min(5, 0.8 + Math.log2(w + 1)));
    if (a === selected || b === selected) line.classList.add("hot");
    if (a === hoverNode || b === hoverNode) line.classList.add("hi");
  }
  for (const node of Object.keys(pos)) {
    const [x, y] = pos[node];
    const label = labelOf(node);
    const [w, h] = nodeSize(label, view !== "files");
    const isExternal = node.startsWith("@") ||
      (view !== "files" && !modInfo(node));
    const grp = el("g", { class: "node" + (node === selected ? " sel" : "") +
                          (isExternal ? " ext" : ""),
                          transform: `translate(${x - w / 2},${y - h / 2})` }, g);
    el("rect", { width: w, height: h }, grp);
    const txt = el("text", { x: w / 2, y: h / 2 + 4, "text-anchor": "middle" }, grp);
    txt.textContent = label;
    grp.addEventListener("mousemove", (ev) => {
      tip.style.display = "block";
      tip.style.left = (ev.clientX + 14) + "px";
      tip.style.top = (ev.clientY + 14) + "px";
      tip.textContent = describe(node);
    });
    grp.addEventListener("mouseenter", () => { hoverNode = node; draw(); });
    grp.addEventListener("mouseleave", () => {
      tip.style.display = "none"; hoverNode = null; draw();
    });
    grp.addEventListener("click", () => {
      if (view === "files" || node.startsWith("@")) return;
      selected = node; syncModules(); draw();
    });
  }
  applyTransform(W, H);
}
function describe(node) {
  if (view === "files") {
    if (node.startsWith("@")) {
      const m = modInfo(node.slice(1));
      return m ? `其他模块：${m.name}\\n文件 ${m.files.length} / 函数 ${m.fns}`
               : node;
    }
    const f = DATA.files.find(x => x.path === node);
    return f ? `${f.path}\\n模块 ${f.module} · ${f.loc} 行 · ${f.fns} 函数`
             : node;
  }
  const key = node.startsWith("@") ? node.slice(1) : node;
  const m = modInfo(key);
  if (!m) return key + "（外部依赖）";
  return `${m.name}\\n文件 ${m.files.length} / 行 ${m.loc} / 函数 ${m.fns}\\n` +
         `imports: ${m.imports.join(", ") || "无"}`;
}
function sizeNow() {
  const layout = currentLayout();
  return [layout.w || 1400, layout.h || 900];
}
function applyTransform(W, H) {
  const [w, h] = W ? [W, H] : sizeNow();
  svg.setAttribute("viewBox", `${-panX} ${-panY} ${w / zoom} ${h / zoom}`);
}
function syncModules() {
  for (const d of document.querySelectorAll("#mods div"))
    d.classList.toggle("on", d.dataset.name === selected);
}
function setView(next) {
  view = next;
  document.querySelectorAll(".tabs button").forEach(b =>
    b.classList.toggle("on", b.dataset.view === view));
  zoom = 1; panX = 0; panY = 0;
  syncModules(); draw();
}
function buildSidebar() {
  stat.textContent = `${DATA.modules.length} 模块 · ${DATA.files.length} 文件 · ` +
    `${DATA.functions.length} 函数\\n` +
    `${LAYOUT.imports.edges.length} 条 import 边 · ` +
    `${DATA.calls.length} 条调用边（未解析 ${DATA.unresolved}）`;
  const box = document.getElementById("mods");
  for (const m of DATA.modules) {
    const d = document.createElement("div");
    d.dataset.name = m.name;
    d.innerHTML = `<span>${m.name}</span><span>${m.fns}</span>`;
    d.onclick = () => { selected = m.name; setView("files"); };
    box.appendChild(d);
  }
  syncModules();
  document.getElementById("legend").textContent =
    "滚轮缩放 · 拖拽平移 · 双击复位\\n点击模块下钻到文件级调用图\\n绿框=pub · 紫边=跨模块";
}
for (const b of document.querySelectorAll(".tabs button"))
  b.onclick = () => setView(b.dataset.view);

let dragging = false, lx = 0, ly = 0;
svg.addEventListener("mousedown", (e) => {
  dragging = true; lx = e.clientX; ly = e.clientY; svg.classList.add("grabbing");
});
window.addEventListener("mouseup", () => {
  dragging = false; svg.classList.remove("grabbing");
});
window.addEventListener("mousemove", (e) => {
  if (!dragging) return;
  panX += (e.clientX - lx) / zoom;
  panY += (e.clientY - ly) / zoom;
  lx = e.clientX; ly = e.clientY;
  applyTransform();
});
svg.addEventListener("dblclick", () => { zoom = 1; panX = 0; panY = 0; applyTransform(); });
svg.addEventListener("wheel", (e) => {
  e.preventDefault();
  zoom = Math.max(0.2, Math.min(5, zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
  applyTransform();
}, { passive: false });

// 默认选中函数最多的模块；支持 #imports / #calls / #m=<模块> 深链。
selected = [...DATA.modules].sort((a, b) => b.fns - a.fns)[0].name;
const hash = decodeURIComponent(location.hash.replace(/^#/, ""));
if (hash === "calls" || hash === "imports") view = hash;
if (hash.startsWith("m=")) {
  const name = hash.slice(2);
  if (modInfo(name)) { selected = name; view = "files"; }
}
document.querySelectorAll(".tabs button").forEach(b =>
  b.classList.toggle("on", b.dataset.view === view));
buildSidebar();
draw();
</script>
</body>
</html>
"""


def write_html(data: dict, layouts: dict, out: Path) -> None:
    """把数据与布局烤进自包含 HTML。"""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    def pack(item: dict) -> dict:
        return {"edges": [list(e) for e in item.get("edges", [])],
                "pos": {k: list(v) for k, v in item.get("pos", {}).items()},
                "w": item.get("w", 1400), "h": item.get("h", 900),
                "weights": item.get("weights", {})}

    lay = {
        "imports": pack(layouts["imports"]),
        "calls": pack({**layouts["calls"], "weights": layouts["calls_weights"]}),
        "files": {name: pack(item) for name, item in layouts["files"].items()},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    html = HTML_TEMPLATE.replace("__DATA__", payload).replace(
        "__LAYOUT__", json.dumps(lay, ensure_ascii=False, separators=(",", ":")))
    out.write_text(html, encoding="utf-8")


def print_stats(data: dict, layouts: dict) -> None:
    """人类可读的统计（--check 与命令行都用它）。"""
    extra = data.get("external") or []
    print(f"模块 {len(data['modules'])} 个 / 文件 {len(data['files'])} 个 / "
          f"函数 {len(data['functions'])} 个"
          + (f"（外部依赖 {', '.join(extra)}）" if extra else ""))
    print(f"import 边 {len(layouts['imports']['edges'])} 条 / "
          f"模块调用边 {len(layouts['calls']['edges'])} 条 / "
          f"函数调用边 {len(data['calls'])} 条（未解析 {data['unresolved']}）")
    top = sorted(((k.split("\t")[0], k.split("\t")[1], w)
                  for k, w in layouts["calls_weights"].items()), key=lambda x: -x[2])[:5]
    if top:
        print("调用最密的模块对：" + "，".join(f"{a}→{b} ({w})" for a, b, w in top))


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 yh 编译器代码流程图（自包含 HTML）")
    ap.add_argument("--root", default=str(SRC), help="源码根（默认 compiler/）")
    ap.add_argument("--out", default=str(ROOT / "tmp" / "codeflow" / "index.html"))
    ap.add_argument("--check", action="store_true", help="只解析并打印统计")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"错误：源码根不存在：{root}", file=sys.stderr)
        return 1
    data = collect(root)
    if not data["modules"]:
        print(f"错误：{root} 下没有找到 module 声明", file=sys.stderr)
        return 1
    layouts = module_layouts(data)
    print_stats(data, layouts)
    if args.check:
        graphs = [layouts["imports"], layouts["calls"]] + list(layouts["files"].values())
        bad = [e for g in graphs for e in g["edges"]
               if e[0] not in g["pos"] or e[1] not in g["pos"]]
        if bad:
            print(f"错误：布局存在孤立端点 {len(bad)} 条（例：{bad[:3]}）", file=sys.stderr)
            return 1
        print("check: 布局端点自洽 ✓")
        return 0
    out = Path(args.out)
    write_html(data, layouts, out)
    print(f"已生成：{out}（自包含 HTML，双击打开）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
