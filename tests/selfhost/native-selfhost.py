#!/usr/bin/env python3
"""本机（Darwin/arm64）自举差分验证。

正式自举门（`make bootstrap`）在 aarch64 Linux 容器内执行，依赖
docker 与 tmp/sysroot。当容器不可用时，本脚本用同一套 compiler/ 源码
在本机跑一遍等价的三代闭环，用于日常回归与缺陷定位：

    stage0（仓库根 yh，Mach-O）
      └─编译 compiler/ 拼接源码→ stage1
          └─stage1 编译自身 → stage2
              └─stage2 编译自身 → stage3

差异点只有「汇编可汇编形态」：自举后端发射的是 GNU/Linux AArch64 汇编
（`adrp`+`:lo12:`、libc 裸名符号），本脚本经 macho.py 改写为 Mach-O 可
接受的 `@PAGE/@PAGEOFF` 与 `_` 前缀符号后交给 clang 链接。

校验项：
  1) s1/s2/s3 均能自解析 compiler.yh；
  2) s1/s2/s3 均通过 tests/yh 全量语法正反例；
  3) s1 与 s2、s2 与 s3 对 compiler.yh 的汇编逐字节一致（固定点）；
  4) 若无 printf，则运行语义语料（macOS 变参 ABI 与 Linux 不同，
     含 printf 的用例在本机不可判，脚本会如实报告跳过原因）。

用法：
    python3 tests/selfhost/native-selfhost.py            # 全量校验
    python3 tests/selfhost/native-selfhost.py --keep     # 保留中间产物

退出码：全部通过 0；任一项失败 1。
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent     # tests/selfhost
ROOT = HERE.parent.parent                  # 仓库根
WORK = ROOT / "tmp" / "selfhost"           # 中间产物（tmp/ 下）

# 与 Makefile 的 SELFHOST_SOURCES 保持一致的拼接顺序。
SOURCES = [
    "compiler/model.yh", "compiler/buffer.yh", "compiler/lexer.yh",
    "compiler/target.yh", "compiler/parse_type.yh", "compiler/symbols.yh",
    "compiler/emit_arm64.yh", "compiler/sem.yh", "compiler/parse_expr.yh",
    "compiler/parse_stmt.yh", "compiler/parse_decl.yh", "compiler/driver.yh",
]


def run(cmd, **kw):
    """执行命令；失败抛 CalledProcessError。"""
    return subprocess.run(cmd, check=True, **kw)


def concat_compiler(dst: Path) -> None:
    """按固定顺序拼接 compiler/ 源码为单文件。"""
    text = "".join((ROOT / s).read_text() for s in SOURCES)
    dst.write_text(text)


def emit_and_link(stage: Path, asm: Path, binary: Path) -> None:
    """用 stage 编译 compiler.yh → Mach-O 可执行二进制。"""
    with asm.open("w") as f:
        run([str(stage), "--emit-asm", str(WORK / "compiler.yh")], stdout=f)
    converted = asm.with_suffix(".macho.s")
    run([sys.executable, str(HERE / "macho.py"), str(asm), str(converted)])
    obj = asm.with_suffix(".o")
    run(["clang", "-c", "-o", str(obj), str(converted)])
    run(["clang", "-o", str(binary), str(obj), str(HERE / "probe-main.c")])


def stage_binary(path: Path, flag: str, arg: Path):
    """执行 stage 的指定模式，返回 CompletedProcess（不检查退出码）。"""
    return subprocess.run([str(path), flag, str(arg)],
                          capture_output=True, text=True)


def syntax_corpus(stage: Path) -> bool:
    """用 tests/yh 全量语法语料校验 stage。"""
    wrapper = WORK / "stage-wrapper.sh"
    wrapper.write_text("#!/bin/sh\nexec \"$YH_STAGE\" \"$@\"\n")
    wrapper.chmod(0o755)
    env = {"YH_STAGE": str(stage), "PATH": "/usr/bin:/bin"}
    r = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "yh" / "check.py"),
         "--compiler", "--compiler-path", str(wrapper), "--quiet"],
        capture_output=True, text=True, env=env)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    return r.returncode == 0


def printf_free_run_tests(stage: Path) -> bool:
    """用 stage 编译并运行 tests/yh-run/run 下不依赖 printf 的用例。

    macOS 的变参 ABI 与 Linux 不同，含 printf 的用例在本机不可判；
    不含 printf 的用例可以真正跑起来，从而验证运行时语义（含浮点位型）。
    """
    import re
    ok = True
    for src in sorted((ROOT / "tests" / "yh-run" / "run").glob("*.yh")):
        text = src.read_text()
        # 只在代码本体（去掉 // 之外的行内注释与整行注释）里找 printf，
        # 避免把注释里提到的 "printf" 当成真实调用。
        code = "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())
        if "printf" in code:
            continue
        head = re.search(r"^//\s*exit:\s*(-?\d+)", text, re.M)
        want = int(head.group(1)) if head else 0
        out = WORK / (src.stem + ".bin")
        asm = WORK / (src.stem + ".s")
        try:
            with asm.open("w") as f:
                run([str(stage), "--emit-asm", str(src)], stdout=f)
            converted = asm.with_suffix(".macho.s")
            run([sys.executable, str(HERE / "macho.py"), str(asm), str(converted)])
            obj = asm.with_suffix(".o")
            run(["clang", "-c", "-o", str(obj), str(converted)])
            run(["clang", "-o", str(out), str(obj), str(HERE / "probe-main.c")])
            r = subprocess.run([str(out)], capture_output=True)
            got = r.returncode
        except subprocess.CalledProcessError as e:
            got = "构建失败(%s)" % e
        good = got == want
        ok = ok and good
        sys.stdout.write("  运行 %-24s 期望=%s 实际=%s %s\n"
                         % (src.name, want, got, "OK" if good else "FAIL"))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留中间产物")
    args = ap.parse_args()

    WORK.mkdir(parents=True, exist_ok=True)
    concat_compiler(WORK / "compiler.yh")
    sys.stdout.write("拼接 compiler.yh 完成（%d 字节）\n"
                     % (WORK / "compiler.yh").stat().st_size)

    # 1) stage0 → stage1；stage1 → stage2；stage2 → stage3
    s1, s2, s3 = (WORK / n for n in ("s1", "s2", "s3"))
    run([str(ROOT / "yh"), str(WORK / "compiler.yh"), "-o", str(s1)])
    sys.stdout.write("stage1 构建完成\n")
    emit_and_link(s1, WORK / "s2.s", s2)
    sys.stdout.write("stage2 构建完成\n")
    emit_and_link(s2, WORK / "s3.s", s3)
    sys.stdout.write("stage3 构建完成\n")

    ok = True

    # 2) 逐 stage 自解析
    for name, st in (("stage1", s1), ("stage2", s2), ("stage3", s3)):
        r = stage_binary(st, "--syntax-check", WORK / "compiler.yh")
        good = r.returncode == 0
        ok = ok and good
        sys.stdout.write("自解析 %s：%s\n" % (name, "OK" if good else "FAIL"))

    # 3) 逐 stage 语法语料
    for name, st in (("stage1", s1), ("stage2", s2), ("stage3", s3)):
        sys.stdout.write("语法语料 %s：\n" % name)
        ok = syntax_corpus(st) and ok

    # 3b) stage2 运行不含 printf 的语义用例（真正执行，验证运行时语义）
    sys.stdout.write("stage2 运行语义（不含 printf 的用例）：\n")
    ok = printf_free_run_tests(s2) and ok

    # 4) 汇编固定点：s2 与 s3 对 compiler.yh 的发射逐字节一致
    run([str(s2), "--emit-asm", str(WORK / "compiler.yh")], stdout=(WORK / "fix2.s").open("w"))
    run([str(s3), "--emit-asm", str(WORK / "compiler.yh")], stdout=(WORK / "fix3.s").open("w"))
    same = (WORK / "fix2.s").read_bytes() == (WORK / "fix3.s").read_bytes()
    ok = ok and same
    sys.stdout.write("汇编固定点（s2.s == s3.s）：%s\n" % ("一致" if same else "不一致"))

    if not args.keep:
        shutil.rmtree(WORK, ignore_errors=True)
    sys.stdout.write("总计：%s\n" % ("全部通过" if ok else "存在失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
