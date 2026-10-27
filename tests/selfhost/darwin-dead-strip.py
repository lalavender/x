#!/usr/bin/env python3
"""Darwin 链接死代码回收门（J6-L1）：`-dead_strip` 缺省生效且可回退。

背景：yh 的链接粒度是「一个模块一个对象」。没有死代码回收时，任何用 fmt
打印的程序都会把整个 string/os/sys 闭包里未引用的函数与字符串字面量带进
产物（实测 hello 级程序 155,872 B → 89,632 B）。本门用当前编译器验证：

  1. 缺省（不设 YH_LINK_DEAD_STRIP）链接：未被引用的函数符号不进入产物；
  2. `YH_LINK_DEAD_STRIP=0` 链接：同一符号必须重新出现，产物可运行；
  3. 两种配置的产物行为一致（stdout 逐字节相同）；
  4. 先构建 0 再构建缺省，结果必须仍是「已回收」——证明开关进入链接缓存键，
     没有命中旧缓存。

usage: python3 tests/selfhost/darwin-dead-strip.py [--compiler-path ./yh]
                                                   [--workdir tmp/dead-strip]
退出码：全部通过 0；否则 1（非 Darwin/arm64 宿主直接拒绝，不做静默降级）。
"""

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "dead-strip"
# 探针同时覆盖「未引用的 public 函数」与正常输出：符号是否保留可直接用 nm 观察。
SOURCE_TEXT = """// dead-strip 探针：unused_probe 不被任何代码引用。
pub fn unused_probe() int {
    return 7
}

// main 只打印一行，不触碰 unused_probe。
fn main() int {
    printf("dead-strip probe\\n")
    return 0
}
"""
EXPECTED_STDOUT = "dead-strip probe\n"
PROBE_SYMBOL = "unused_probe"


def require(condition, message):
    """报告确定性的门禁失败，避免依赖可被 -O 移除的 assert。"""
    if not condition:
        print(f"FAIL {message}")
        raise SystemExit(1)


def run(cmd, env=None, timeout=120):
    """执行一条命令并返回 CompletedProcess；调用方负责判定返回码。"""
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, env=env)


def build(compiler, workdir, binary, dead_strip=None):
    """构建探针；dead_strip=None 表示不设环境变量（走缺省）。"""
    env = dict(os.environ)
    env.pop("YH_LINK_DEAD_STRIP", None)
    if dead_strip is not None:
        env["YH_LINK_DEAD_STRIP"] = dead_strip
    proc = run([str(compiler), str(workdir / "probe.yh"), "-o", str(binary)],
               env=env)
    require(proc.returncode == 0,
            f"构建失败（YH_LINK_DEAD_STRIP={dead_strip}）：{proc.stderr.strip()}")
    return binary


def symbols(binary):
    """返回 nm -a 输出；符号表缺失时判失败，避免「无输出=已回收」的假绿。"""
    proc = run(["nm", "-a", str(binary)])
    require(proc.returncode == 0, f"nm 读取失败：{proc.stderr.strip()}")
    return proc.stdout


def has_probe(binary):
    return PROBE_SYMBOL in symbols(binary)


def check_runs(binary, label):
    proc = run([str(binary)])
    require(proc.returncode == 0, f"{label}：退出码 {proc.returncode}")
    require(proc.stdout == EXPECTED_STDOUT,
            f"{label}：stdout 不符（{proc.stdout!r}）")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    parser.add_argument("--workdir", default=str(WORK))
    args = parser.parse_args()

    if sys.platform != "darwin" or platform.machine().lower() not in ("arm64", "aarch64"):
        print("FAIL 本门只支持 Darwin/arm64 宿主（其他平台不做静默降级）")
        return 1

    compiler = Path(args.compiler_path).resolve()
    require(compiler.is_file(), f"编译器不存在：{compiler}")
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "probe.yh").write_text(SOURCE_TEXT)

    stripped = build(compiler, workdir, workdir / "stripped")
    check_runs(stripped, "缺省链接")
    require(not has_probe(stripped),
            "缺省链接仍保留未引用函数符号：-dead_strip 未生效")
    print("PASS 缺省链接回收未引用符号")

    unstripped = build(compiler, workdir, workdir / "unstripped", "0")
    check_runs(unstripped, "YH_LINK_DEAD_STRIP=0 链接")
    require(has_probe(unstripped),
            "YH_LINK_DEAD_STRIP=0 未保留符号：回退开关失效")
    print("PASS YH_LINK_DEAD_STRIP=0 保留符号")

    # 关键顺序：先构建关闭态，再构建缺省态；后者必须重新链接。
    again = build(compiler, workdir, workdir / "again")
    check_runs(again, "关闭态之后重建缺省态")
    require(not has_probe(again),
            "缺省链接命中了关闭态的链接缓存：-dead_strip 未进入链接键")
    print("PASS 开关进入链接缓存键（0 → 缺省不会复用旧产物）")

    print("结果: 4 passed; 0 failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
