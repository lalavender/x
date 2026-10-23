#!/usr/bin/env python3
"""tests/modules 的 yh test（YT1）项目验收。

覆盖测试发现、doctest 目标绑定、模块/文件选择、--list/--no-run、
测试专用导入不进入生产构建，以及测试体错误只在测试模式报错。

用法：
    python3 tests/modules/test-check.py [--compiler-path ./yh]
                                        [--workdir ../tmp/test-check]

退出码：全部通过 0；有失败 1。
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PROJ = HERE / "projects"
DEFAULT_WORK = ROOT / "tmp" / "test-check"


class Checker:
    def __init__(self, compiler: Path, work: Path):
        self.compiler = compiler
        self.work = work
        self.failed = 0
        self.darwin_arm64 = (
            sys.platform == "darwin" and platform.machine() in ("arm64", "aarch64"))
        self.expected_tests = 8 if self.darwin_arm64 else 7

    def prepare(self, fixture: str, case: str) -> Path:
        """复制 fixture 到独立工作目录，返回项目根。"""
        dst = self.work / case
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(PROJ / fixture, dst,
                        ignore=shutil.ignore_patterns(".build", "tmp"))
        return dst

    def run(self, project: Path, *args: str):
        # 编译器可能被暂存到临时目录（make test 的 FAST_STAGE），
        # 显式给出仓库标准库根，保证 import testing 等模块可解析。
        env = dict(os.environ)
        env.setdefault("YH_STDLIB", str(ROOT / "libs"))
        proc = subprocess.run(
            [str(self.compiler), "test", *args],
            cwd=project, capture_output=True, text=True, timeout=300, env=env)
        return proc

    def check(self, case: str, ok: bool, detail: str = ""):
        if ok:
            print(f"PASS {case}")
            return
        self.failed += 1
        print(f"FAIL {case}" + (f": {detail}" if detail else ""))

    def expect_ok(self, case: str, proc, *needles: str):
        ok = proc.returncode == 0
        missing = [n for n in needles if n not in proc.stdout + proc.stderr]
        self.check(case, ok and not missing,
                   f"退出码 {proc.returncode}，缺少 {missing}" if not ok or missing else "")

    def expect_fail(self, case: str, proc, needle: str):
        text = proc.stdout + proc.stderr
        self.check(case, proc.returncode != 0 and needle in text,
                   f"退出码 {proc.returncode}，诊断缺少 {needle!r}")

    def run_all(self) -> int:
        self.work.mkdir(parents=True, exist_ok=True)

        # 1. 全项目发现：跨文件私有目标、文档目标种类、平台文件筛选。
        p = self.prepare("ytest", "discover")
        proc = self.run(p, "--list")
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        text = "\n".join(lines)
        ok = (proc.returncode == 0
              and "app::src/app/lib.yh::decltest::secret" in text
              and "-> fn secret" in text
              and "app::src/app/more.yh::test::跨文件私有声明" in text
              and "app::src/app/more.yh::decltest::value" in text
              and "app::src/app/lib.yh::decltest::LIMIT" in text
              and "app::src/app/lib.yh::decltest::counter" in text
              and "app::src/app/lib.yh::decltest::Thing" in text
              and len(lines) == self.expected_tests)
        platform_line = "checks.darwin.arm64.yh" in text
        self.check("discover-project", ok and platform_line == self.darwin_arm64,
                   f"退出码 {proc.returncode}，行数 {len(lines)}，平台行 {platform_line}")

        # 2. 模块选择只列出该模块的测试。
        proc = self.run(p, "app", "--list")
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.check("select-module",
                   proc.returncode == 0 and len(lines) == self.expected_tests
                   and all(line.startswith("app::") for line in lines),
                   f"退出码 {proc.returncode}，行数 {len(lines)}")

        # 3. 文件选择仍用完整模块上下文绑定跨文件目标，但只列所选文件。
        proc = self.run(p, "src/app/more.yh", "--list")
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.check("select-file-cross-target",
                   proc.returncode == 0 and len(lines) == 2
                   and all("more.yh" in line for line in lines)
                   and any("-> fn value" in line for line in lines),
                   f"退出码 {proc.returncode}，输出 {lines}")

        # 4. --filter 只过滤列表。
        proc = self.run(p, "--list", "--filter", "跨文件")
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.check("list-filter", proc.returncode == 0 and len(lines) == 1,
                   f"退出码 {proc.returncode}，输出 {lines}")

        # 5. --no-run 检查全部测试体；默认无 --no-run 也走检查。
        proc = self.run(p, "--no-run")
        self.expect_ok("no-run", proc, "测试构建通过:",
                       f"{self.expected_tests} 个用例")
        proc = self.run(p)
        self.expect_ok("default-check", proc, "PASS ",
                       f"结果: {self.expected_tests} passed; 0 skipped; 0 failed")

        # 5b. 只选 app 模块时不要求入口 main；无 main 模块也能检查测试。
        proc = self.run(p, "app", "--no-run")
        self.expect_ok("module-without-main", proc, "测试构建通过:",
                       f"{self.expected_tests} 个用例")

        # 5c. YT2a：测试体降低为模块内函数，$assert 降为 __yh_test_assert 调用。
        lowered = self.prepare("ytest", "lowered")
        proc = self.run(lowered, "--no-run", "--emit-llvm")
        self.expect_ok("emit-llvm", proc, "测试构建通过:")
        test_dir = lowered / "tmp" / "yh-test" / "check"
        llvm_text = "".join(
            path.read_text(errors="replace")
            for path in sorted((test_dir / "llvm").glob("*.ll")))
        objects = sorted((test_dir / "obj").glob("*.o"))
        nm = subprocess.run(["nm", *map(str, objects)],
                            capture_output=True, text=True)
        self.check("test-bodies-lowered",
                   "__yh_test_" in nm.stdout
                   and "__yh_test_assert" in llvm_text
                   and "call void @\"__yh_test_assert\"" in llvm_text,
                   f"llvm 断言调用 {('__yh_test_assert' in llvm_text)}，"
                   f"nm 输出缺少测试符号")

        # 5d. YT2b：逐例执行、PASS 记录与汇总。
        run = self.prepare("ytest", "execute")
        proc = self.run(run)
        pass_lines = [line for line in proc.stdout.splitlines()
                      if line.startswith("PASS ")]
        self.check("execute-pass",
                   proc.returncode == 0
                   and len(pass_lines) == self.expected_tests
                   and f"结果: {self.expected_tests} passed; 0 skipped; 0 failed"
                   in proc.stdout,
                   f"退出码 {proc.returncode}，输出 {proc.stdout[-400:]!r}")

        # 5e. 失败路径：断言位置、提前退出、崩溃都算失败，后续用例继续。
        bad = self.prepare("ytestfail", "execute-fail")
        proc = self.run(bad)
        out = proc.stdout
        self.check("execute-fail",
                   proc.returncode == 1
                   and "断言位置: 12:5" in out
                   and "结果: 2 passed; 0 skipped; 3 failed" in out
                   and "PASS app::src/app/lib.yh::test::失败后继续执行" in out,
                   f"退出码 {proc.returncode}，输出 {out[-500:]!r}，"
                   f"stderr {proc.stderr[-300:]!r}")
        self.check("execute-fail-early-exit-and-crash",
                   "FAIL app::src/app/lib.yh::test::提前退出不算通过" in out
                   and "FAIL app::src/app/lib.yh::test::崩溃不算通过" in out,
                   "提前退出或崩溃被误判为通过")

        # 5g. --filter 作用于执行；无匹配时报错。
        proc = self.run(p, "--filter", "跨文件")
        pass_lines = [line for line in proc.stdout.splitlines()
                      if line.startswith("PASS ")]
        self.check("execute-filter",
                   proc.returncode == 0 and len(pass_lines) == 1
                   and "结果: 1 passed; 0 skipped; 0 failed" in proc.stdout,
                   f"退出码 {proc.returncode}，输出 {proc.stdout[-300:]!r}")
        proc = self.run(p, "--filter", "不存在的测试名")
        self.expect_fail("execute-filter-no-match", proc, "没有匹配的测试用例")

        # 5h. testing.fail / testing.skip 与断言消息。
        skip = self.prepare("ytestskip", "execute-skip")
        proc = self.run(skip)
        out = proc.stdout
        self.check("execute-skip-and-fail",
                   proc.returncode == 1
                   and "SKIP app::src/app/lib.yh::test::显式跳过" in out
                   and "断言消息: helper 拒绝继续" in out
                   and "断言消息: bump 结果不对" in out
                   and "结果: 2 passed; 1 skipped; 2 failed" in out,
                   f"退出码 {proc.returncode}，输出 {out[-500:]!r}，"
                   f"stderr {proc.stderr[-300:]!r}")

        # 5i. --timeout 终止死循环用例，后续用例继续。
        slow = self.prepare("ytesttimeout", "execute-timeout")
        proc = self.run(slow, "--timeout", "1")
        out = proc.stdout
        self.check("execute-timeout",
                   proc.returncode == 1
                   and "FAIL app::src/app/lib.yh::test::死循环用例" in out
                   and "用例超时" in out
                   and "PASS app::src/app/lib.yh::test::超时之后继续" in out
                   and "结果: 1 passed; 0 skipped; 1 failed" in out,
                   f"退出码 {proc.returncode}，输出 {out[-500:]!r}，"
                   f"stderr {proc.stderr[-300:]!r}")

        # 5f. --no-run 只构建，不执行。
        noexec = self.prepare("ytest", "no-exec")
        proc = self.run(noexec, "--no-run")
        self.check("no-run-does-not-execute",
                   proc.returncode == 0 and "PASS " not in proc.stdout
                   and "未执行" in proc.stdout,
                   f"退出码 {proc.returncode}，输出 {proc.stdout[-300:]!r}")

        # 6. 测试专用导入不进入生产构建；生产 build 跳过 helper。
        proc = subprocess.run([str(self.compiler), "build"], cwd=p,
                              capture_output=True, text=True, timeout=300)
        self.check("test-only-import-production",
                   proc.returncode == 0 and "[编译] helper" not in proc.stdout,
                   f"退出码 {proc.returncode}，stdout={proc.stdout!r}")
        prod_objects = sorted((p / ".build").rglob("obj/*.o"))
        prod_nm = subprocess.run(["nm", *map(str, prod_objects)],
                                 capture_output=True, text=True)
        self.check("production-has-no-test-symbols",
                   prod_objects and "__yh_test_" not in prod_nm.stdout,
                   f"对象数 {len(prod_objects)}")

        # 7. 空模块/空项目：--list 成功且为空；--no-run 对零用例报错。
        empty = self.prepare("ytestempty", "empty")
        proc = self.run(empty, "--list")
        self.check("zero-list", proc.returncode == 0 and not proc.stdout.strip(),
                   f"退出码 {proc.returncode}，stdout={proc.stdout!r}")
        proc = self.run(empty, "--no-run")
        self.expect_fail("zero-no-run", proc, "没有找到测试用例")

        # 8. 模块 selector 下零用例。
        proc = self.run(p, "helper", "--list")
        self.check("module-zero-list", proc.returncode == 0 and not proc.stdout.strip(),
                   f"退出码 {proc.returncode}，stdout={proc.stdout!r}")

        # 9. 无效文档目标、重复名称、导入别名目标。
        bad = self.prepare("ytestbad", "bad-target")
        self.expect_fail("bad-target", self.run(bad, "--list"), "文档测试目标")
        dup = self.prepare("ytestdup", "duplicate")
        self.expect_fail("duplicate", self.run(dup, "--list"), "重复")

        alias = self.prepare("ytest", "alias-target")
        with (alias / "src/app/lib.yh").open("a") as f:
            f.write("\ntest helper {\n}\n")
        self.expect_fail("import-alias-target", self.run(alias, "--list"),
                         "导入模块名")

        # 10. 测试体语义错误只进入 yh test；生产 build 仍然成功。
        sem = self.prepare("ytestsem", "body-error")
        build = subprocess.run([str(self.compiler), "build"], cwd=sem,
                               capture_output=True, text=True, timeout=300)
        self.check("body-error-production", build.returncode == 0,
                   f"退出码 {build.returncode}，stderr={build.stderr!r}")
        self.expect_fail("body-error-test", self.run(sem, "--no-run"),
                         "引用了未声明的名字")

        return 1 if self.failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="yh test（YT1）项目验收")
    ap.add_argument("--compiler-path", default=str(ROOT / "yh"))
    ap.add_argument("--workdir", default=str(DEFAULT_WORK))
    args = ap.parse_args()
    compiler = Path(args.compiler_path).resolve()
    if not compiler.exists():
        print(f"编译器不存在: {compiler}")
        return 1
    return Checker(compiler, Path(args.workdir).resolve()).run_all()


if __name__ == "__main__":
    sys.exit(main())
