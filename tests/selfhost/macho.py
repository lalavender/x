#!/usr/bin/env python3
"""把 stage 发射的 AArch64 Linux 汇编转为可在本机（Darwin）汇编/链接的形态。

* `adrp/add :lo12:` → `@PAGE/@PAGEOFF`；
* libc 外部符号走 `@GOTPAGE` 并加 Darwin `_` 前缀；
* 入口 main → _yh_main（由 main.c 转发真实 argc/argv）。

仅供本机差分探针使用，不进入编译器产物。
用法：macho.py <in.s> <out.s>
"""
import re
import sys

LIBC = {'write', 'open', 'read', 'close', 'malloc', 'free',
        'memcpy', 'strlen', 'printf', 'exit'}


def convert(src: str, dst: str) -> None:
    lines = open(src).read().split('\n')
    out, i = [], 0
    while i < len(lines):
        l = lines[i]
        st = l.strip()
        if st.startswith('.globl') and st.split()[-1] == 'main':
            out.append('\t.globl\t_yh_main'); i += 1; continue
        if st == 'main:':
            out.append('_yh_main:'); i += 1; continue
        m = re.match(r'\tadrp\t(x\d+), (.+)$', l)
        if m and i + 1 < len(lines):
            reg, sym = m.group(1), m.group(2).strip()
            m2 = re.match(r'\tadd\t(' + reg + r'), ' + reg + r', :lo12:(.+)$', lines[i + 1])
            if m2 and m2.group(1) == reg:
                if sym in LIBC:
                    out.append('\tadrp\t%s, _%s@GOTPAGE' % (reg, sym))
                    out.append('\tldr\t%s, [%s, _%s@GOTPAGEOFF]' % (reg, reg, sym))
                else:
                    out.append('\tadrp\t%s, %s@PAGE' % (reg, sym))
                    out.append('\tadd\t%s, %s, %s@PAGEOFF' % (reg, reg, sym))
                i += 2; continue
        m3 = re.match(r'\tbl\t(\w+)$', l)
        if m3 and m3.group(1) in LIBC:
            out.append('\tbl\t_%s' % m3.group(1)); i += 1; continue
        out.append(l); i += 1
    open(dst, 'w').write('\n'.join(out))


if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2])
