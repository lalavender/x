#!/usr/bin/env python3
"""LL7 ABI 门：核对 Linux/x86_64 C 调用约定的 LLVM 与双向运行。"""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp" / "llvm-migration" / "llvm-abi"
SOURCE = ROOT / "tests" / "selfhost" / "llvm-abi-probe.yh"
BRIDGE = ROOT / "tests" / "selfhost" / "llvm-abi-bridge.c"
PROJECT = ROOT / "tests" / "modules" / "projects" / "llvmabi"
BOOL_PROJECT = ROOT / "tests" / "modules" / "projects" / "llvmabibool"
TARGET = "x86_64-unknown-linux-gnu"


def run(command, cwd=None, env=None):
    """执行一条限时子进程命令，保留 stdout/stderr 供失败诊断使用。"""
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=300)


def locate(name):
    """解析开发期 LLVM 工具；该门只在测试中使用，不影响 yh 运行时依赖。"""
    fixed = Path("/usr/bin") / name
    return str(fixed) if fixed.is_file() else shutil.which(name)


def require(condition, message):
    """用同一错误格式中止本门，避免 assert 在优化模式下被裁掉。"""
    if not condition:
        raise RuntimeError(message)


def main():
    """编译探针为 LLVM IR，核对 C 窄型属性，再以 O0/O2 双向运行。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = str(Path(args.compiler_path).resolve())
    require(Path(compiler).is_file(), f"编译器不存在：{compiler}")
    clang, opt, cc = (locate(name) for name in ("clang", "opt", "gcc"))
    require(clang and opt and cc, "LL7 ABI 门缺少 clang/opt/gcc 开发工具")
    version = run([clang, "--version"])
    require(version.returncode == 0 and "21.1.8" in version.stdout,
            f"LL7 ABI oracle 需要 clang 21.1.8\n{version.stdout[-500:]}")
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)

    bare_varargs = ROOT / "tests" / "yh-run" / "fail" / "60-user-c-varargs.yh"
    rejected_varargs = run([compiler, "--emit-asm", "--backend", "llvm",
                            "--target", TARGET, str(bare_varargs)])
    require(rejected_varargs.returncode != 0
            and "用户源码不允许裸变参" in rejected_varargs.stdout + rejected_varargs.stderr,
            "LLVM 路径没有在源码层拒绝未支持的用户 C 裸变参")
    for name in ("28-cabi-callback-needs-extern.yh",
                 "34-cabi-to-yh-function.yh", "35-yh-to-cabi-function.yh",
                 "36-cabi-cast-convention.yh"):
        mismatch = ROOT / "tests" / "yh-run" / "fail" / name
        rejected = run([compiler, "--emit-asm", "--backend", "llvm", "--target", TARGET,
                        str(mismatch)])
        require(rejected.returncode != 0 and "错误:" in rejected.stdout + rejected.stderr,
                f"LLVM 路径没有在源码层拒绝函数值 ABI 错配：{name}")

    oracle = WORK / "clang-abi.ll"
    oracle_result = run([clang, "-S", "-emit-llvm", "-O0", str(BRIDGE), "-o", str(oracle)])
    require(oracle_result.returncode == 0,
            f"clang C ABI oracle 生成失败\n{oracle_result.stderr[-1600:]}")
    oracle_text = oracle.read_text(encoding="utf-8")
    for pattern in (r"define .*signext i8 @c_i8\(i8 noundef signext",
                    r"define .*zeroext i8 @c_u8\(i8 noundef zeroext",
                    r"define .*signext i16 @c_i16\(i16 noundef signext",
                    r"define .*zeroext i16 @c_u16\(i16 noundef zeroext",
                    r"define .*zeroext i1 @c_bool\(i1 noundef zeroext"):
        require(re.search(pattern, oracle_text) is not None,
                f"clang 21.1.8 oracle 缺少预期 ABI 属性：{pattern}")
    aggregate_oracle = WORK / "clang-aggregate-abi.ll"
    aggregate_result = run([clang, "-S", "-emit-llvm", "-O0",
                            str(PROJECT / "c" / "bridge.c"), "-o", str(aggregate_oracle)])
    require(aggregate_result.returncode == 0,
            f"clang C 聚合 ABI oracle 生成失败\n{aggregate_result.stderr[-1600:]}")
    aggregate_text = aggregate_oracle.read_text(encoding="utf-8")
    for pattern in (r"define .*i64 @c_pair\(i64 %",
                    r"define .*\{ double, i32 \} @c_mixed_struct\(double %\d+, i32 %\d+\)",
                    r"define .*void @c_wide_struct\(ptr .*sret\(%struct\.CWide\) align 8 %\d+, ptr .*byval\(%struct\.CWide\) align 8 %\d+\)"):
        require(re.search(pattern, aggregate_text) is not None,
                f"clang 21.1.8 聚合 oracle 缺少预期 SysV 分类：{pattern}")

    for level in (0, 2):
        emitted = run([compiler, "--emit-asm", "--backend", "llvm", "--target", TARGET,
                       f"-O{level}", "--emit-llvm", str(SOURCE)])
        require(emitted.returncode == 0,
                f"O{level} LLVM 发射失败\n{emitted.stderr[-2000:]}")
        text = emitted.stdout
        expected = (
            'declare signext i8 @"c_i8"(i8 signext)',
            'declare zeroext i8 @"c_u8"(i8 zeroext)',
            'declare signext i16 @"c_i16"(i16 signext)',
            'declare zeroext i16 @"c_u16"(i16 zeroext)',
            'declare zeroext i1 @"c_bool"(i1 zeroext)',
            'define signext i8 @"yh_i8"(i8 signext %p0)',
            'define zeroext i8 @"yh_u8"(i8 zeroext %p0)',
            'define signext i16 @"yh_i16"(i16 signext %p0)',
            'define zeroext i16 @"yh_u16"(i16 zeroext %p0)',
            'define zeroext i1 @"yh_bool"(i1 zeroext %p0)',
        )
        for fragment in expected:
            require(fragment in text or fragment.replace("define ", "define external ") in text,
                    f"O{level} 缺少 C ABI 签名属性：{fragment}")
        require(re.search(r'call signext i8 @"c_i8"\(i8 signext ', text) is not None,
                f"O{level} 调用点缺少 signext\n{text[-1800:]}")
        require(re.search(r'call zeroext i16 @"c_u16"\(i16 zeroext ', text) is not None,
                f"O{level} 调用点缺少 zeroext\n{text[-1800:]}")
        require(re.search(r'call zeroext i1 @"c_bool"\(i1 zeroext ', text) is not None,
                f"O{level} 调用点缺少 C bool zeroext\n{text[-1800:]}")
        require("zext i1 %p0 to i8" in text,
                f"O{level} C bool 形参未恢复为 YH bool 字节\n{text[-1800:]}")
        require(re.search(r'icmp ne i8 [^,]+, 0', text) is not None,
                f"O{level} C bool 调用参数未归一成 i1\n{text[-1800:]}")
        require(re.search(r'icmp ne i8 %v[0-9]+, 0\n  ret i1 %t[0-9]+', text) is not None,
                f"O{level} C bool 返回值未按非零字节归一成 i1\n{text[-1800:]}")
        require(re.search(r'call i64 @"c_many"\(i64 .*i64 .*i64 .*i64 .*i64 .*i64 .*i64 .*i64 ', text) is not None,
                f"O{level} 未发射 8 参数 C 调用\n{text[-1800:]}")
        irfile = WORK / f"abi-O{level}.ll"
        irfile.write_text(text, encoding="utf-8")
        verified = run([opt, "-passes=verify", "-S", str(irfile), "-o", "/dev/null"])
        require(verified.returncode == 0, f"O{level} LLVM verifier 失败\n{verified.stderr[-1600:]}")
        compile_ir = irfile
        if level == 2:
            optimized = WORK / "abi-O2-opt.ll"
            result = run([opt, "-S", "-passes=default<O2>", str(irfile), "-o", str(optimized)])
            require(result.returncode == 0, f"O2 优化失败\n{result.stderr[-1600:]}")
            compile_ir = optimized
        obj = WORK / f"abi-O{level}.o"
        compiled = run([clang, "-c", str(compile_ir), "-o", str(obj)])
        require(compiled.returncode == 0, f"O{level} LLVM 汇编失败\n{compiled.stderr[-1600:]}")
        executable = WORK / f"abi-O{level}"
        linked = run([cc, "-no-pie", str(obj), str(BRIDGE), "-o", str(executable)])
        require(linked.returncode == 0, f"O{level} C 桥接链接失败\n{linked.stderr[-1600:]}")
        executed = run([str(executable)])
        require(executed.returncode == 0,
                f"O{level} 双向 C ABI 运行失败 rc={executed.returncode}\n{executed.stderr[-800:]}")

        project = WORK / f"project-O{level}"
        shutil.copytree(PROJECT, project)
        project_env = dict(os.environ)
        project_env["PATH"] = "/usr/bin:" + project_env.get("PATH", "")
        built = run([compiler, "--backend", "llvm", "--target", TARGET,
                     f"-O{level}", "build", "--emit-llvm"], cwd=project, env=project_env)
        require(built.returncode == 0,
                f"O{level} 跨模块 LLVM C ABI 构建失败\n{built.stderr[-2000:]}")
        module_ir = list((project / ".build" / "llvm").glob("*.ll"))
        require(len(module_ir) == 2,
                f"O{level} 项目应为 main/bridge 各发一份 LLVM IR，实际 {len(module_ir)}")
        module_text = "\n".join(path.read_text(encoding="utf-8") for path in module_ir)
        require(re.search(r'yh_pair_sum.*\$yhllvmv1', module_text) is not None
                and re.search(r'yh_pair_make.*\$yhllvmv1', module_text) is not None,
                f"O{level} yh-llvm-v1 内部符号缺少 ABI 版本后缀")
        require(re.search(r'declare i32 @"c_apply_callback"\(ptr, i32\)', module_text) is not None
                and re.search(r'declare ptr @"c_choose_callback"\(\)', module_text) is not None
                and re.search(r'call i32 %v[0-9]+\(i32 %v[0-9]+, i32 %v[0-9]+\)', module_text) is not None
                and 'select i1 true, ptr @"yh_triple"' in module_text
                and re.search(r'call i32 %v[0-9]+\(i32 %v[0-9]+\)', module_text) is not None,
                f"O{level} 函数指针签名/间接调用/C callback 未发射")
        require('declare i64 @"c_apply_pair_callback"(ptr, i64)' in module_text
                and 'declare ptr @"c_choose_pair_callback"()' in module_text
                and 'select i1 true, ptr @"yh_cpair"' in module_text
                and re.search(r'call i64 %v[0-9]+\(i64 %[a-z]+[0-9]+\)', module_text) is not None,
                f"O{level} C 聚合 callback 参数/返回的间接 SysV ABI 未发射")
        require(re.search(r'define internal i32 @"yh_sum_pack[^\"]*"\(i32 %p0, ptr %p1\)',
                          module_text) is not None,
                f"O{level} YH 类型化变参没有保存 vararg=2 的切片 ABI 元数据")
        for fragment in (
            'declare i64 @"c_pair"(i64)',
            'declare {double, i32} @"c_mixed_struct"(double, i32)',
            'declare void @"c_wide_struct"(ptr sret([24 x i8]) align 8, ptr byval([24 x i8]) align 8)',
            'define i64 @"yh_cpair"(i64 %p0)',
            'define {double, i32} @"yh_cmixed"(double %p0, i32 %p1)',
            'define void @"yh_cwide"(ptr sret([24 x i8]) align 8 %p0, ptr byval([24 x i8]) align 8 %p1)',
        ):
            require(fragment in module_text, f"O{level} 跨模块接口缺少 SysV 聚合 ABI：{fragment}")
        program = project / ".build" / "llvmabi"
        executed = run([str(program)], cwd=project, env=project_env)
        require(executed.returncode == 0,
                f"O{level} 跨模块 C ABI 双向运行失败 rc={executed.returncode}\n"
                f"{executed.stderr[-800:]}")

        noreturn_project = WORK / f"noreturn-project-O{level}"
        shutil.copytree(PROJECT, noreturn_project)
        noreturn_main = noreturn_project / "main" / "main.yh"
        main_source = noreturn_main.read_text(encoding="utf-8")
        main_decl = "fn main() int {\n"
        require(main_decl in main_source, "noreturn 项目缺少 main 函数")
        noreturn_main.write_text(main_source.replace(
            main_decl, main_decl + "    bridge.c_returns();\n", 1), encoding="utf-8")
        bridge_source = noreturn_project / "bridge" / "bridge.yh"
        original_bridge = bridge_source.read_text(encoding="utf-8")
        noreturn_decl = "@[extern, noreturn]\npub fn c_returns() void;"
        normal_decl = "@[extern]\npub fn c_returns() void;"
        require(noreturn_decl in original_bridge, "noreturn 项目缺少跨模块声明")
        noreturn_build = run([compiler, "--backend", "llvm", "--target", TARGET,
                              f"-O{level}", "build", "--emit-llvm"],
                             cwd=noreturn_project, env=project_env)
        require(noreturn_build.returncode == 0,
                f"O{level} 跨模块 noreturn 构建失败\n{noreturn_build.stderr[-1600:]}")
        noreturn_ir_files = list((noreturn_project / ".build" / "llvm").glob("*.ll"))
        noreturn_text = "\n".join(path.read_text(encoding="utf-8")
                                   for path in noreturn_ir_files)
        iface_files = list(noreturn_project.rglob("*.s.i"))
        iface_text = "\n".join(path.read_text(encoding="utf-8") for path in iface_files)
        require("@[extern, noreturn]\npub fn c_returns" in iface_text
                and re.search(r'call void @"c_returns"\(\)\n  call void @llvm\.trap\(\)\n  unreachable',
                              noreturn_text) is not None,
                f"O{level} 接口未保留 noreturn 或调用点没有 trap")
        noreturn_program = noreturn_project / ".build" / "llvmabi"
        executed = run([str(noreturn_program)], cwd=noreturn_project, env=project_env)
        require(executed.returncode != 0,
                f"O{level} 跨模块 noreturn 违约返回后没有触发 trap")

        callback_decl = "pub fn yh_apply(callback fn(int, int) int, left int, right int) int {"
        callback_c_decl = "pub fn yh_apply(callback @[extern] fn(int, int) int, left int, right int) int {"
        require(callback_decl in original_bridge, "跨模块 callback ABI 错配探针缺少 yh_apply")
        bridge_source.write_text(original_bridge.replace(callback_decl, callback_c_decl, 1),
                                 encoding="utf-8")
        mismatch_build = run([compiler, "--backend", "llvm", "--target", TARGET,
                              f"-O{level}", "build", "--emit-llvm"],
                             cwd=noreturn_project, env=project_env)
        require(mismatch_build.returncode != 0
                and "错误:" in mismatch_build.stdout + mismatch_build.stderr,
                f"O{level} 函数接口 ABI 变化后未拒绝 YH callback 实参")
        bridge_source.write_text(original_bridge, encoding="utf-8")
        restored_build = run([compiler, "--backend", "llvm", "--target", TARGET,
                              f"-O{level}", "build", "--emit-llvm"],
                             cwd=noreturn_project, env=project_env)
        require(restored_build.returncode == 0,
                f"O{level} 恢复 callback ABI 接口后构建失败\n{restored_build.stderr[-1600:]}")
        restored_text = "\n".join(path.read_text(encoding="utf-8") for path in
                                   (noreturn_project / ".build" / "llvm").glob("*.ll"))
        require(re.search(r'call void @"c_returns"\(\)\n  call void @llvm\.trap\(\)\n  unreachable',
                          restored_text) is not None,
                f"O{level} 恢复 YH callback ABI 后没有正确重建调用方 IR")

        bridge_source.write_text(original_bridge.replace(noreturn_decl, normal_decl, 1),
                                 encoding="utf-8")
        normal_build = run([compiler, "--backend", "llvm", "--target", TARGET,
                            f"-O{level}", "build", "--emit-llvm"],
                           cwd=noreturn_project, env=project_env)
        require(normal_build.returncode == 0,
                f"O{level} 移除 noreturn 属性后增量构建失败\n{normal_build.stderr[-1600:]}")
        normal_text = "\n".join(path.read_text(encoding="utf-8") for path in
                                 (noreturn_project / ".build" / "llvm").glob("*.ll"))
        iface_text = "\n".join(path.read_text(encoding="utf-8")
                                for path in noreturn_project.rglob("*.s.i"))
        require("@[extern, noreturn]\npub fn c_returns" not in iface_text
                and "@[extern]\npub fn c_returns" in iface_text
                and re.search(r'call void @"c_returns"\(\)\n  call void @llvm\.trap\(\)',
                              normal_text) is None,
                f"O{level} noreturn 接口变更未使调用方缓存失效")
        executed = run([str(noreturn_program)], cwd=noreturn_project, env=project_env)
        require(executed.returncode == 0,
                f"O{level} 清除 noreturn 后调用方仍按违约 trap，rc={executed.returncode}")

        bridge_source.write_text(original_bridge, encoding="utf-8")
        restored_build = run([compiler, "--backend", "llvm", "--target", TARGET,
                              f"-O{level}", "build", "--emit-llvm"],
                             cwd=noreturn_project, env=project_env)
        require(restored_build.returncode == 0,
                f"O{level} 恢复 noreturn 属性后增量构建失败\n{restored_build.stderr[-1600:]}")
        restored_text = "\n".join(path.read_text(encoding="utf-8") for path in
                                   (noreturn_project / ".build" / "llvm").glob("*.ll"))
        require(re.search(r'call void @"c_returns"\(\)\n  call void @llvm\.trap\(\)\n  unreachable',
                          restored_text) is not None,
                f"O{level} 恢复 noreturn 后调用方没有重建 trap")
        executed = run([str(noreturn_program)], cwd=noreturn_project, env=project_env)
        require(executed.returncode != 0,
                f"O{level} 恢复 noreturn 后违约调用没有再次触发 trap")

        bool_project = WORK / f"bool-project-O{level}"
        shutil.copytree(BOOL_PROJECT, bool_project)
        built = run([compiler, "--backend", "llvm", "--target", TARGET,
                     f"-O{level}", "build", "--emit-llvm"], cwd=bool_project, env=project_env)
        require(built.returncode == 0,
                f"O{level} 跨模块 LLVM C bool 构建失败\n{built.stderr[-2000:]}")
        bool_ir = list((bool_project / ".build" / "llvm").glob("*.ll"))
        bool_text = "\n".join(path.read_text(encoding="utf-8") for path in bool_ir)
        require(len(bool_ir) == 2
                and 'define zeroext i1 @"yh_bool"(i1 zeroext %p0)' in bool_text
                and 'declare zeroext i1 @"c_bool"(i1 zeroext)' in bool_text,
                f"O{level} 跨模块接口未保留 C bool ABI 表示")
        bool_program = bool_project / ".build" / "llvmabibool"
        executed = run([str(bool_program)], cwd=bool_project, env=project_env)
        require(executed.returncode == 0,
                f"O{level} 跨模块 C bool 双向运行失败 rc={executed.returncode}\n"
                f"{executed.stderr[-800:]}")

        noreturn_source = ROOT / "tests" / "selfhost" / "llvm-noreturn-probe.yh"
        noreturn_bridge = ROOT / "tests" / "selfhost" / "llvm-noreturn-bridge.c"
        no_return = run([compiler, "--emit-asm", "--backend", "llvm", "--target", TARGET,
                         f"-O{level}", "--emit-llvm", str(noreturn_source)])
        require(no_return.returncode == 0,
                f"O{level} LLVM noreturn 发射失败\n{no_return.stderr[-1600:]}")
        noreturn_ir = WORK / f"noreturn-O{level}.ll"
        noreturn_ir.write_text(no_return.stdout, encoding="utf-8")
        require(re.search(r'call void @"c_returns"\(\)\n  call void @llvm\.trap\(\)\n  unreachable',
                          no_return.stdout) is not None
                and re.search(r'define(?: internal)? void @"yh_spin', no_return.stdout) is not None,
                f"O{level} noreturn 缺少违约 trap 或合法定义\n{no_return.stdout[-1600:]}")
        verified = run([opt, "-passes=verify", "-S", str(noreturn_ir), "-o", "/dev/null"])
        require(verified.returncode == 0,
                f"O{level} noreturn LLVM verifier 失败\n{verified.stderr[-1200:]}")
        compile_ir = noreturn_ir
        if level == 2:
            optimized = WORK / "noreturn-O2-opt.ll"
            result = run([opt, "-S", "-passes=default<O2>", str(noreturn_ir), "-o", str(optimized)])
            require(result.returncode == 0, f"O2 noreturn 优化失败\n{result.stderr[-1200:]}")
            compile_ir = optimized
            require("@llvm.trap" in optimized.read_text(encoding="utf-8"),
                    "O2 优化移除了 noreturn 违约 trap")
        obj = WORK / f"noreturn-O{level}.o"
        compiled = run([clang, "-c", str(compile_ir), "-o", str(obj)])
        require(compiled.returncode == 0,
                f"O{level} noreturn LLVM 汇编失败\n{compiled.stderr[-1200:]}")
        executable = WORK / f"noreturn-O{level}"
        linked = run([cc, "-no-pie", str(obj), str(noreturn_bridge), "-o", str(executable)])
        require(linked.returncode == 0,
                f"O{level} noreturn C 桥接链接失败\n{linked.stderr[-1200:]}")
        executed = run([str(executable)])
        require(executed.returncode != 0,
                f"O{level} noreturn 违约未触发 trap，退出码为 0")

    print("LL7 ABI 通过：clang oracle、C 标量/bool/聚合、YH 聚合/类型化变参、函数指针/C callback、noreturn trap，O0/O2 双向调用")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"LL7 ABI 门失败：{error}", file=sys.stderr)
        raise SystemExit(1)
