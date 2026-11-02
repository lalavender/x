#!/usr/bin/env python3
"""运行侧：在真实 Windows 上执行交叉编译产物并核对 stdout/退出码（W1-7）。

编译侧（WSL/Linux/macOS）先跑：

    python3 tests/selfhost/llvm-windows-target.py --manifest-out tmp/windows-target/manifest.json

产物与清单都在仓库 `tmp/` 下，Windows 侧同一工作树直接可见（`\\\\wsl$\\...` 或挂载盘符），
然后：

    python3 tests/windows/run-exe.py --manifest tmp/windows-target/manifest.json

清单是相对仓库根的路径 + 期望值，不含宿主相关的绝对路径，所以跨机器拷目录也能用。
退出码：0 全部符合；1 有不符/缺失；2 用法错误。
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Windows 控制台默认 GBK：统一成 UTF-8 + 可替换，避免中文诊断变成乱码或抛异常。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")



def main() -> int:
    parser = argparse.ArgumentParser(description="执行 Windows 交叉产物并核对结果")
    parser.add_argument("--manifest", required=True, help="编译侧写出的 manifest.json")
    parser.add_argument("--timeout", type=float, default=60.0, help="单例超时（秒）")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"错误：找不到清单 {manifest_path}", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for case in manifest.get("cases", []):
        exe = ROOT / case["exe"]
        if not exe.is_file():
            failures.append(f"{case['name']}：缺少产物 {exe}")
            continue
        argv = [str(exe)] + list(case.get("argv") or [])
        stdin_bytes = bytes.fromhex(case["stdin_hex"]) if case.get("stdin_hex") else None
        try:
            result = subprocess.run(argv, capture_output=True, text=True,
                                    input=None if stdin_bytes is None else
                                    stdin_bytes.decode("utf-8", "replace"),
                                    timeout=args.timeout)
        except (OSError, subprocess.SubprocessError) as error:
            failures.append(f"{case['name']}：无法执行（{error}）")
            continue
        # 与 tests/yh-run/check.py 的 diff_output 同一口径：按行比对，忽略尾部空行。
        want = case["expected_stdout"].rstrip("\n").split("\n") if case["expected_stdout"] else []
        got = result.stdout.rstrip("\n").split("\n") if result.stdout else []
        if want != got:
            failures.append(f"{case['name']}：stdout 不符\n    期望 {want}\n    实际 {got}")
        if result.returncode != case["expected_exit"]:
            failures.append(f"{case['name']}：退出码 {result.returncode} 期望 "
                            f"{case['expected_exit']}")

    if failures:
        for failure in failures:
            print(f"失败：{failure}", file=sys.stderr)
        return 1
    print(f"Windows 运行侧通过：{len(manifest.get('cases', []))} 例 stdout 与退出码均符合")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
