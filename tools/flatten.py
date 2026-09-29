#!/usr/bin/env python3
"""tools/flatten.py —— 自举过渡桥（ADR-0007 P3→P5）。

把活跃的四模块源码（含 module/import/限定名）扁平化为 stage0 可编译的
单文件：剥 module/import 行、剥 struct 字段 pub（stage0 二进制不含
U1 的字段 pub 支持）、去模块限定前缀（gen./lex./parse./cmd.）。

这是**一次性过渡产物**（旧 seed 编译器不支持 sizeof(m.T)，无法直接
build 项目）：过渡编译器 yh-trans 构建项目得到 yh-new-next，此后链上
全部用模块构建；扁平化正确性由 P5 的模块 .s/.s.i 固定点验证——若剥离
有误，固定点即断。不应作为长期种子维护（ADR-0007 的否决理由不变）。

用法：python3 tools/flatten.py > tmp/transition.yh
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 声明序（与编译器内 topo 依赖序一致：gen → lex → parse → cmd）
SOURCES = [
    "compiler/gen/model.yh", "compiler/gen/buffer.yh",
    "compiler/lex/lexer.yh",
    "compiler/gen/target.yh", "compiler/parse/parse_type.yh",
    "compiler/gen/symbols.yh",
    "compiler/gen/emit_arm64.yh",
    "compiler/gen/sem_value.yh", "compiler/gen/sem_expr.yh",
    "compiler/gen/sem_call_literal.yh", "compiler/gen/sem_flow.yh",
    "compiler/gen/sem_decl.yh",
    "compiler/parse/parse_expr.yh", "compiler/parse/parse_stmt.yh",
    "compiler/parse/parse_decl.yh", "compiler/parse/parse_global_init.yh",
    "compiler/parse/parse_module.yh", "compiler/parse/iface.yh",
    "compiler/cmd/toml.yh",
    "compiler/cmd/project_state.yh", "compiler/cmd/project_index.yh",
    "compiler/cmd/project_resolve.yh",
    "compiler/cmd/module_build.yh",
    "compiler/cmd/compile.yh",
    "compiler/cmd/driver.yh",
]

MODS = ("gen", "lex", "parse", "cmd")


def strip_module_lines(text: str) -> str:
    out = []
    for line in text.splitlines(True):
        if re.match(r'^(module|import) [a-z]+;\s*$', line):
            continue
        out.append(line)
    return ''.join(out)


def strip_field_pub(text: str) -> str:
    """struct 块内字段行剥掉 'pub '（顶层 pub fn/let/const/struct 保留）。"""
    out = []
    in_struct = False
    for line in text.splitlines(True):
        if re.match(r'^(pub )?struct [A-Za-z_]', line):
            in_struct = True
            out.append(line)
            continue
        if in_struct and line.rstrip('\n') == '}':
            in_struct = False
            out.append(line)
            continue
        if in_struct:
            line = re.sub(r'^(\s*)pub ', r'\1', line)
        out.append(line)
    return ''.join(out)


def dequalify(text: str) -> str:
    """代码态剥掉模块限定前缀（gen./lex./parse./cmd.）；注释与字符串不动。"""
    pat = re.compile(r'\b(%s)\.' % '|'.join(MODS))
    out = []
    i, n = 0, len(text)
    state = 'code'
    while i < n:
        c = text[i]
        if state == 'code':
            if c == '/' and i + 1 < n and text[i + 1] == '/':
                state = 'linecomment'
                out.append(c)
                i += 1
                continue
            if c == '"':
                state = 'string'
                out.append(c)
                i += 1
                continue
            if c == "'":
                state = 'char'
                out.append(c)
                i += 1
                continue
            m = pat.match(text, i)
            if m:
                # 标识符边界：前一字符不是 [.A-Za-z0-9_]
                if i == 0 or not re.match(r'[A-Za-z0-9_.]', text[i - 1]):
                    i = m.end()
                    continue
            out.append(c)
            i += 1
            continue
        if state == 'linecomment':
            out.append(c)
            if c == '\n':
                state = 'code'
            i += 1
            continue
        # string / char
        out.append(c)
        if c == '\\' and i + 1 < n:
            out.append(text[i + 1])
            i += 2
            continue
        if (state == 'string' and c == '"') or (state == 'char' and c == "'"):
            state = 'code'
        i += 1
    return ''.join(out)


def main() -> int:
    parts = []
    for src in SOURCES:
        text = (ROOT / src).read_text()
        text = strip_module_lines(text)
        text = strip_field_pub(text)
        text = dequalify(text)
        parts.append(text)
    sys.stdout.write(''.join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
