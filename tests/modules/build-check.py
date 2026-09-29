#!/usr/bin/env python3
"""tests/modules 项目级验收（MOD-U2..U5）。

用 tests/modules/projects/ 下的真实 mod.toml 项目 fixture，把自举编译器
的「发现 → 索引 → 三层解析 → 模块语义 → 独立对象/接口 → 链接运行 →
对象缓存」整条管线过一遍。每个用例复制到 tmp/modcheck/ 后执行：

    run     用例       yh run   退出码 == 期望值（程序退出码）
    fail    用例       yh build 非零退出且 stderr 含期望诊断子串
    ok      用例       yh build 退出 0
    iface   用例+方法  构建成功后破坏依赖接口，再构建必须拒绝
    rebind  用例+方法  构建后新增本地同名模块，必须重绑定并重编译

usage: python3 tests/modules/build-check.py [--compiler-path ./yh-new]
退出码：全部通过 0；有失败 1。
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PROJ = HERE / "projects"
WORK = ROOT / "tmp" / "modcheck"


def sh(cmd, cwd, env=None):
    e = dict(__import__("os").environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          env=e, timeout=300)


CASES = []


def case(name, kind, fixture, sub, expect=None, msg=None):
    CASES.append(dict(name=name, kind=kind, fixture=fixture, sub=sub,
                      expect=expect, msg=msg))


# —— MOD-U4：两项目真实链接运行（含跨模块聚合/浮点/间接调用/限定字面量） ——
case("u4-basic-run", "run", "basic", "app", 255)
case("u4-iso-run", "run", "iso", "host", 15)
case("u4-aggfloat-run", "run", "aggfloat", "host", 29)
# —— MOD-U2：清单与三层解析 ——
case("u2-toml-syntax", "fail", "tomlbad", ".", msg="mod.toml")
case("u2-toml-unknown-field", "fail", "tomlunknown", ".", msg="未知字段")
case("u2-transitive-rejected", "fail", "transitive", "host", msg="模块不存在")
case("u2-ambiguous-deps", "fail", "ambiguity", "host", msg="歧义")
# —— MOD-U3：模块语义 ——
case("u3-import-cycle", "fail", "cycle", "a", msg="环")
case("u3-entry-not-importable", "fail", "cycleentry", "host", msg="入口模块不可")
case("u3-private-field", "fail", "pubpriv", "host", msg="私有字段")
case("u3-private-fn", "fail", "pubpriv", "host2", msg="导出")
case("u3-positional-private", "fail", "pubpriv", "host3", msg="私有")
case("u3-duplicate-decl", "fail", "dupdecl", "host", msg="重定义")
case("u3-unused-import", "fail", "unusedimp", "host", msg="导入未使用")
case("u3-import-clash", "fail", "clashname", "host", msg="导入名冲突")


def copy_proj(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler-path", default=str(ROOT / "yh-new"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    WORK.mkdir(parents=True, exist_ok=True)
    failed = 0

    def report(ok, name, detail=""):
        nonlocal failed
        if not ok:
            failed += 1
            print(f"FAIL {name}: {detail}")
        elif not args.quiet:
            print(f"OK   {name}")

    for c in CASES:
        dst = WORK / c["fixture"].replace("/", "_")
        copy_proj(PROJ / c["fixture"], dst)
        r = sh([compiler, "run"] if c["kind"] == "run" else [compiler, "build"],
               cwd=dst / c["sub"])
        if c["kind"] == "run":
            report(r.returncode == c["expect"], c["name"],
                   f"退出码 {r.returncode} 期望 {c['expect']}\n{r.stderr[-400:]}")
        else:
            ok = r.returncode != 0 and c["msg"] in (r.stderr + r.stdout)
            report(ok, c["name"],
                   f"退出码 {r.returncode}，期望诊断含「{c['msg']}」\n{(r.stderr + r.stdout)[-400:]}")

    # —— stdlib 三层（YH_STDLIB） ——
    std = (WORK / "stdlib")
    copy_proj(PROJ / "stdlib", std)
    r = sh([compiler, "run"], cwd=std / "host-only", env={"YH_STDLIB": str(std)})
    report(r.returncode == 101, "u2-stdlib-fallback",
           f"退出码 {r.returncode} 期望 101（标准库层）\n{r.stderr[-300:]}")
    r = sh([compiler, "run"], cwd=std / "host-shadow", env={"YH_STDLIB": str(std)})
    report(r.returncode == 201, "u2-stdlib-shadowed",
           f"退出码 {r.returncode} 期望 201（本地遮蔽标准库）\n{r.stderr[-300:]}")

    # —— MOD-U4：接口不兼容拒绝（破坏依赖接口后必须拒绝重建） ——
    dst = WORK / "ifacebad"
    copy_proj(PROJ / "ifacebad", dst)
    r = sh([compiler, "build"], cwd=dst / "host")
    if r.returncode != 0:
        report(False, "u4-iface-corrupt", f"首次构建失败: {r.stderr[-300:]}")
    else:
        # 找到 geom 的接口文件并破坏头行
        bad = None
        for p in dst.rglob("geom.s.i"):
            bad = p
        if bad is None:
            report(False, "u4-iface-corrupt", "未找到 geom.s.i")
        else:
            bad.write_text("// yh-iface v999 arch=x99 suffix=x\n")
            r2 = sh([compiler, "build"], cwd=dst / "host")
            report(r2.returncode != 0 and "接口不兼容" in (r2.stderr + r2.stdout),
                   "u4-iface-corrupt",
                   f"破坏接口后未被拒绝: {r2.returncode} {(r2.stderr + r2.stdout)[-300:]}")

    # —— MOD-U5：重绑定与冷热一致 ——
    dst = WORK / "u5_rebind"
    copy_proj(PROJ / "basic", dst)
    r1 = sh([compiler, "build"], cwd=dst / "app")
    report(r1.returncode == 0 and "[编译] main" in r1.stdout,
           "u5-cold-builds", f"{r1.returncode} {r1.stdout[-200:]}")
    r2 = sh([compiler, "build"], cwd=dst / "app")
    report(r2.returncode == 0 and "[缓存]" in r2.stdout and "[编译]" not in r2.stdout,
           "u5-hot-cache-hits", f"二次构建未全部命中缓存: {r2.stdout[-200:]}")
    # 新增本地 json（与第三方同源码、不带 mod.toml）→ json/main 必须重编译
    (dst / "app" / "src" / "json").mkdir(parents=True, exist_ok=True)
    shutil.copy(dst / "json" / "src" / "codec.yh", dst / "app" / "src" / "json" / "codec.yh")
    r3 = sh([compiler, "build"], cwd=dst / "app")
    recompiled = r3.returncode == 0 and "[编译] main" in r3.stdout and "[编译] json" in r3.stdout
    report(recompiled, "u5-rebind-local-json",
           f"新增本地 json 未触发重编译: {r3.stdout[-200:]} {r3.stderr[-200:]}")
    # 重绑定后产物与原第三方版本一致（同源码，冷热一致）
    r4 = sh([compiler, "run"], cwd=dst / "app")
    report(r4.returncode == 255, "u5-rebind-run-same",
           f"重绑定后运行退出码 {r4.returncode} 期望 255")

    total = len(CASES) + 6
    print(f"project cases: 通过 {total - failed}/{total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
