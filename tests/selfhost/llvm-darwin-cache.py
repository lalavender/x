#!/usr/bin/env python3
"""Darwin/ARM64 LLVM 缓存身份门：SDK 内容闭包、minOS、原子发布与并发。

覆盖 F2-7 的输入变化矩阵：
- 相同输入两轮构建的 manifest 与对象字节确定；
- 有效无改动构建命中（对象/可执行文件都不重写）；
- 同路径源内容变化只影响实际缓存粒度（main 对象重编、helper 对象不动）；
- 部署版本变化同时失效对象与链接键，切回后键值复现；
- SDKROOT 切换区分链接键而对象键不变；
- SDK 重导出 stub 内容变化必须失效链接键（不能只哈希 SDKROOT/版本/mtime）；
- 链接失败保留旧可执行文件与旧成功 manifest；
- manifest/对象/接口损坏后重验重建，可执行文件损坏后重链；
- 两次并发构建都成功且最终 manifest 与串行结果一致。
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/darwin-cache"
FIXTURE = ROOT / "tests/modules/projects/llvmdarwincache"
SDK_PACKAGE = ROOT / "tmp/llvm-migration/darwin-sdk/sdk-darwin-aarch64"
HOST_RECORD = SDK_PACKAGE / "host.json"
TRIPLE = "aarch64-apple-darwin"
OPT = "O0"

# 与路径无关、且不含 LC_UUID/签名 blob 的确定性身份键：
# 两个 manifest 同理（链接键含输出路径，只在同路径内比较）。
IDENTITY_KEYS = ("llvmdarwincache-main.manifest", "llvmdarwincache-helper.manifest",
                 "llvmdarwincache-main.object", "llvmdarwincache-helper.object")


def link_input_key(state):
    """取链接 manifest 的前 16 字符：输入键（后半是输出文件摘要，含随机 UUID）。"""
    value = state["link.manifest"]
    return value[:16] if value else None


def require(condition, message):
    """报告稳定的门禁失败原因，不使用可能被 Python -O 移除的 assert。"""
    if not condition:
        raise RuntimeError(message)


def sdk_version(root):
    """读取 SDK 的规范化版本，用于选择合法的第二部署版本。"""
    data = json.loads((Path(root) / "SDKSettings.json").read_text(encoding="utf-8"))
    parts = [int(item) for item in str(data.get("Version", "")).split(".")]
    return tuple(parts + [0] * (3 - len(parts)))


def second_deployment(sdk_root, min_os="14.0.0"):
    """返回高于 min_os 且不高于 SDK 的部署版本；没有可用值返回 None。"""
    version = sdk_version(sdk_root)
    base = tuple(map(int, min_os.split("."))) + (0,)
    if version <= base:
        return None
    if version >= (15, 0, 0):
        return "15.0.0"
    return f"{version[0]}.{version[1]}.0"


def find_sdk_root(environment):
    """优先显式 SDKROOT，其次固定包记录，最后 xcrun 发现本机 SDK。"""
    if environment.get("SDKROOT"):
        return Path(environment["SDKROOT"]).resolve()
    if HOST_RECORD.is_file():
        record = json.loads(HOST_RECORD.read_text(encoding="utf-8"))
        if record.get("sdk_root"):
            return Path(record["sdk_root"])
    result = subprocess.run(["xcrun", "--sdk", "macosx", "--show-sdk-path"],
                            capture_output=True, text=True, check=False)
    require(result.returncode == 0 and result.stdout.strip(),
            "xcrun 未找到 macOS SDK")
    return Path(result.stdout.strip())


def make_min_sdk(source_root, dest):
    """复制链接最小闭包所需的 SDK 子集（SDKSettings + libSystem + 系统 stub）。

    完整 SDK 约 3 GiB，逐用例复制不可行；缓存身份只依赖这些输入，
    裁剪后仍能真实链接，且改动任一 stub 都能观察链接键变化。
    """
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "usr/lib/system").mkdir(parents=True)
    shutil.copy2(source_root / "SDKSettings.json", dest / "SDKSettings.json")
    for name in ("libSystem.B.tbd", "libSystem.tbd"):
        shutil.copy2(source_root / "usr/lib" / name, dest / "usr/lib" / name)
    for tbd in sorted((source_root / "usr/lib/system").glob("*.tbd")):
        shutil.copy2(tbd, dest / "usr/lib/system" / tbd.name)


def project_env(min_sdk, min_os="14.0.0"):
    """构造项目的构建环境：固定 SDK 与部署版本，缺省不继承 SDKROOT。"""
    env = dict(os.environ)
    env["SDKROOT"] = str(min_sdk)
    env["MACOSX_DEPLOYMENT_TARGET"] = min_os
    env.pop("YH_CC", None)
    return env


def digest(path):
    """返回文件内容的 SHA-256；不存在返回 None。"""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binary_digest(path):
    """返回剔除 LC_UUID 后的 Mach-O 摘要。

    lld 每次链接都会为 LC_UUID 生成新值，它是唯一允许变化的字节；
    确定性断言比较的是内容本身，因此先把 UUID 字段清零。
    """
    if not path.is_file():
        return None
    data = bytearray(path.read_bytes())
    if len(data) >= 32 and int.from_bytes(data[:4], "little") in (0xFEEDFACF, 0xFEEDFACE):
        count = int.from_bytes(data[16:20], "little")
        offset = 32
        for _ in range(count):
            if offset + 8 > len(data):
                break
            command = int.from_bytes(data[offset:offset + 4], "little")
            command_size = int.from_bytes(data[offset + 4:offset + 8], "little")
            if command_size <= 0:
                break
            if command == 0x1B and offset + 24 <= len(data):
                data[offset + 8:offset + 24] = bytes(16)
            offset += command_size
    return hashlib.sha256(bytes(data)).hexdigest()


class Project:
    """一个可重复构建的 llvmdarwincache 副本及其缓存状态读取。"""

    def __init__(self, name):
        self.root = WORK / name
        if self.root.exists():
            shutil.rmtree(self.root)
        shutil.copytree(FIXTURE, self.root)

    @property
    def artifacts(self):
        return self.root / ".build/targets" / TRIPLE / "llvm" / OPT

    @property
    def executable(self):
        return self.root / ".build/llvmdarwincache"

    def manifest(self, tag):
        return self.artifacts / "manifest" / f"{tag}.manifest"

    def object(self, tag):
        return self.artifacts / "obj" / f"{tag}.o"

    def iface(self, tag):
        return self.artifacts / "iface" / f"{tag}.s.i"

    def state(self):
        """收集本轮判断重建粒度所需的身份：manifest 内容 + 文件 mtime。"""
        snap = {}
        for tag in ("llvmdarwincache-main", "llvmdarwincache-helper", "link"):
            path = self.manifest(tag)
            snap[tag + ".manifest"] = path.read_text() if path.is_file() else None
        for tag in ("llvmdarwincache-main", "llvmdarwincache-helper"):
            path = self.object(tag)
            snap[tag + ".object"] = digest(path)
            snap[tag + ".mtime"] = path.stat().st_mtime_ns if path.is_file() else None
        snap["executable"] = binary_digest(self.executable)
        snap["executable.mtime"] = (self.executable.stat().st_mtime_ns
                                    if self.executable.is_file() else None)
        return snap


def build(compiler, project, env, args=("build",), stats=False, background=False):
    """执行一次项目构建；background 时返回 Popen 供并发用例使用。"""
    command = [str(compiler), "--backend", "llvm", "--target", TRIPLE, f"-{OPT}"]
    if stats:
        command.append("--stats")
    command += list(args)
    if background:
        return subprocess.Popen(command, cwd=project.root, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
    return subprocess.run(command, cwd=project.root, env=env,
                          capture_output=True, text=True, timeout=300)


def report(name, detail=""):
    """与既有 Darwin 门保持一致的 PASS 输出。"""
    print(f"PASS {name}" + (f"：{detail}" if detail else ""))


def run_suite(args, compiler, sdk_root, environment):
    """按输入矩阵逐项验证缓存键与原子发布。"""
    del environment  # 每个用例显式构造环境，避免继承宿主 SDKROOT。
    WORK.mkdir(parents=True, exist_ok=True)
    sdk_a = WORK / "sdk-a"
    sdk_b = WORK / "sdk-b"
    make_min_sdk(sdk_root, sdk_a)
    make_min_sdk(sdk_root, sdk_b)
    env_a = project_env(sdk_a)

    # —— 基线 + 热命中 + 确定复现 ——
    first = Project("first")
    built = build(compiler, first, env_a)
    require(built.returncode == 0, f"基线构建失败：{built.stderr[-2000:]}")
    base = first.state()
    require(base["executable.mtime"] is not None, "基线构建未产可执行文件")

    hot = build(compiler, first, env_a)
    require(hot.returncode == 0, f"热缓存构建失败：{hot.stderr[-1000:]}")
    again = first.state()
    require(again == base, "无改动构建改写了对象/产物，热缓存未命中")
    report("cache-hot-hit", "无改动构建对象、产物与 manifest 均未重写")

    second = Project("second")
    built = build(compiler, second, env_a)
    require(built.returncode == 0, f"复现构建失败：{built.stderr[-2000:]}")
    twin = second.state()
    # 链接键包含输出路径，可执行文件含每次链接都会重算的 LC_UUID 与
    # ad-hoc 签名 blob；因此跨目录只比较与路径无关的 manifest 与对象字节，
    # 产物只验证可运行。
    for key in IDENTITY_KEYS:
        require(twin[key] == base[key],
                f"相同输入两轮构建不確定：{key}\n{base[key]}\n{twin[key]}")
    for project in (first, second):
        executed = subprocess.run([str(project.executable)], capture_output=True,
                                  text=True, timeout=60)
        require(executed.returncode == 0,
                f"同一输入的产物运行失败：{project.root.name}")
    rebuilt = Project("rebuilt")
    built = build(compiler, rebuilt, env_a)
    require(built.returncode == 0, f"确定性基线失败：{built.stderr[-2000:]}")
    round_one = rebuilt.state()
    shutil.rmtree(rebuilt.root / ".build")
    built = build(compiler, rebuilt, env_a)
    require(built.returncode == 0, f"清空重建失败：{built.stderr[-2000:]}")
    round_two = rebuilt.state()
    for key in IDENTITY_KEYS:
        require(round_two[key] == round_one[key],
                f"同一路径清空重建的 {key} 不一致")
    require(link_input_key(round_two) == link_input_key(round_one),
            "同一路径清空重建的链接输入键不一致")
    report("cache-deterministic", "对象/产物可运行且确定，同路径清空重建全部键一致")

    # —— 同路径源内容变化：只影响实际缓存粒度 ——
    main_source = first.root / "main/main.yh"
    original_main = main_source.read_text(encoding="utf-8")
    main_source.write_text(original_main.replace("helper.add(40) != 42",
                                                 "helper.add(41) != 43", 1), encoding="utf-8")
    changed = build(compiler, first, env_a, stats=True)
    require(changed.returncode == 0, f"源变化构建失败：{changed.stderr[-2000:]}")
    after = first.state()
    require(after["llvmdarwincache-main.manifest"] != base["llvmdarwincache-main.manifest"],
            "main 源内容变化未失效 main 对象")
    require(after["llvmdarwincache-helper.manifest"] == base["llvmdarwincache-helper.manifest"],
            "main 源变化错误地失效了无关的 helper 对象")
    require(after["llvmdarwincache-helper.object"] == base["llvmdarwincache-helper.object"],
            "helper 对象被无关改动重编")
    require(after["link.manifest"] != base["link.manifest"], "源变化未触发重新链接")
    main_source.write_text(original_main, encoding="utf-8")
    restored = build(compiler, first, env_a)
    require(restored.returncode == 0, f"源恢复构建失败：{restored.stderr[-1000:]}")
    back = first.state()
    require(back["llvmdarwincache-main.manifest"] == base["llvmdarwincache-main.manifest"],
            "恢复源内容后对象键未回到原值")
    report("cache-source-content", "同路径内容变化只重编 main 并重链，helper 不动")

    # —— 部署版本变化：对象键与链接键同时失效，切回复现 ——
    os_project = Project("minos")
    built = build(compiler, os_project, project_env(sdk_a, "14.0.0"))
    require(built.returncode == 0, f"minOS 14 构建失败：{built.stderr[-2000:]}")
    min14 = os_project.state()
    second = second_deployment(sdk_a)
    if second is None:
        report("cache-deployment-version", "当前 SDK 没有可用的第二部署版本（跳过）")
    else:
        built = build(compiler, os_project, project_env(sdk_a, second))
        require(built.returncode == 0, f"minOS {second} 构建失败：{built.stderr[-2000:]}")
        min15 = os_project.state()
        for tag in ("llvmdarwincache-main.manifest", "llvmdarwincache-helper.manifest",
                    "link.manifest"):
            require(min15[tag] != min14[tag], f"部署版本变化未失效 {tag}")
        built = build(compiler, os_project, project_env(sdk_a, "14.0.0"))
        require(built.returncode == 0, f"minOS 切回失败：{built.stderr[-2000:]}")
        min14_again = os_project.state()
        for key in IDENTITY_KEYS:
            require(min14_again[key] == min14[key],
                    f"切回 14.0 后 {key} 未复现原值")
        require(link_input_key(min14_again) == link_input_key(min14),
                "切回 14.0 后链接输入键未复现原值")
        report("cache-deployment-version",
               f"minOS 14→{second}→14 对象与链接键均按值复现")

    # —— SDKROOT 切换：链接键区分路径，对象键与 SDK 无关 ——
    switched = Project("sdk-switch")
    built = build(compiler, switched, project_env(sdk_b))
    require(built.returncode == 0, f"SDK 切换构建失败：{built.stderr[-2000:]}")
    other = switched.state()
    for tag in ("llvmdarwincache-main.manifest", "llvmdarwincache-helper.manifest"):
        require(other[tag] == base[tag], f"SDKROOT 切换错误影响对象键 {tag}")
    require(other["link.manifest"] != base["link.manifest"],
            "SDKROOT 路径切换未区分链接键")
    report("cache-sdk-root-switch", "不同 SDK 路径对象键相同、链接键不同")

    # —— SDK 重导出 stub 内容变化：必须失效链接键 ——
    # 改一个不参与本程序解析的导出符号名：stub 仍是合法 TAPI 文件，但内容
    # 与原始 SDK 不同，链接键必须随之变化。
    dispatch = sdk_b / "usr/lib/system/libdispatch.tbd"
    original_dispatch = dispatch.read_text(encoding="utf-8")
    probed = original_dispatch.replace("__dispatch_bug", "__dispatch_bug_cache_probe", 1)
    require(probed != original_dispatch, "libdispatch.tbd 未包含预期探针符号")
    dispatch.write_text(probed, encoding="utf-8")
    stub_changed = build(compiler, switched, project_env(sdk_b))
    require(stub_changed.returncode == 0, f"stub 变化构建失败：{stub_changed.stderr[-2000:]}")
    stub_state = switched.state()
    require(stub_state["link.manifest"] != other["link.manifest"],
            "SDK 重导出 stub 内容变化未失效链接键")
    require(stub_state["llvmdarwincache-main.object"] == other["llvmdarwincache-main.object"],
            "SDK stub 变化错误地重编了对象")
    dispatch.write_text(original_dispatch, encoding="utf-8")
    restored_stub = build(compiler, switched, project_env(sdk_b))
    require(restored_stub.returncode == 0, f"stub 恢复失败：{restored_stub.stderr[-2000:]}")
    restored_state = switched.state()
    for key in IDENTITY_KEYS:
        require(restored_state[key] == other[key],
                f"stub 恢复后 {key} 未回到原值")
    require(link_input_key(restored_state) == link_input_key(other),
            "stub 恢复后链接输入键未回到原值")
    report("cache-sdk-stub-closure", "重导出 stub 内容变化只失效链接键并可复现")

    # —— 链接失败保留旧可执行文件与旧成功 manifest ——
    libsystem = sdk_b / "usr/lib/libSystem.tbd"
    original_libsystem = libsystem.read_bytes()
    libsystem.write_bytes(original_libsystem + b"\nnot-a-tapi-line\n")
    failed = build(compiler, switched, project_env(sdk_b))
    require(failed.returncode != 0, "损坏的 TAPI stub 未使链接失败")
    failed_state = switched.state()
    # 失败前最后一次成功构建是 stub 恢复后的 restored_state（输出摘要含随机
    # UUID，因此不能用更早的 other 作基线）。
    for key in IDENTITY_KEYS + ("link.manifest", "executable", "executable.mtime"):
        require(failed_state[key] == restored_state[key],
                f"链接失败改写了 {key}（原子发布被破坏）")
    libsystem.write_bytes(original_libsystem)
    recovered = build(compiler, switched, project_env(sdk_b))
    require(recovered.returncode == 0 and switched.state() == restored_state,
            f"修复 stub 后未能命中旧成功结果：{recovered.stderr[-1000:]}")
    report("cache-failure-preserves", "链接失败保留旧产物与旧 manifest，修复后命中")

    # —— 损坏重验：manifest / 对象 / 接口 / 可执行文件 ——
    damaged = Project("damaged")
    built = build(compiler, damaged, env_a)
    require(built.returncode == 0, f"损坏矩阵基线失败：{built.stderr[-2000:]}")
    good = damaged.state()
    damaged.manifest("llvmdarwincache-main").write_bytes(b"0" * 64)
    fixed = build(compiler, damaged, env_a)
    require(fixed.returncode == 0
            and damaged.manifest("llvmdarwincache-main").read_text() ==
            good["llvmdarwincache-main.manifest"],
            "manifest 损坏后未重新编译并恢复键值")
    damaged.object("llvmdarwincache-helper").write_bytes(b"not-an-object")
    fixed = build(compiler, damaged, env_a)
    require(fixed.returncode == 0
            and damaged.object("llvmdarwincache-helper").read_bytes()
            != b"not-an-object",
            "对象损坏后未重建")
    damaged.iface("llvmdarwincache-helper").write_bytes(b"// yh-iface v999\n")
    fixed = build(compiler, damaged, env_a)
    require(fixed.returncode == 0
            and damaged.iface("llvmdarwincache-helper").read_text()
            != "// yh-iface v999\n",
            "接口损坏后未重建")
    damaged.executable.write_bytes(b"")
    fixed = build(compiler, damaged, env_a)
    require(fixed.returncode == 0 and damaged.executable.stat().st_size > 0,
            "可执行文件损坏后未重新链接")
    require(damaged.state()["llvmdarwincache-main.manifest"]
            == good["llvmdarwincache-main.manifest"],
            "损坏恢复后 manifest 与基线不一致")
    report("cache-corruption-rebuild", "manifest/对象/接口/可执行文件损坏均重验重建")

    # —— 中断构建：终止构建进程后重建仍正确，残留临时文件不被误用 ——
    interrupted = Project("interrupted")
    victim = build(compiler, interrupted, env_a, background=True)
    # 立刻终止；即使构建已完成也无妨，关键是后续重建必须得到正确结果且
    # 不把任何残留 .tmp 文件当成有效缓存。
    victim.terminate()
    victim.communicate(timeout=300)
    residue = interrupted.artifacts / "manifest/link.manifest.tmp.99999"
    residue.parent.mkdir(parents=True, exist_ok=True)
    residue.write_bytes(b"garbage")
    resumed = build(compiler, interrupted, env_a)
    require(resumed.returncode == 0, f"中断后重建失败：{resumed.stderr[-2000:]}")
    resumed_state = interrupted.state()
    for key in IDENTITY_KEYS:
        require(resumed_state[key] == base[key],
                f"中断后重建的 {key} 与基线不一致")
    executed = subprocess.run([str(interrupted.executable)], capture_output=True,
                              text=True, timeout=60)
    require(executed.returncode == 0, "中断后重建的产物运行失败")
    stable = build(compiler, interrupted, env_a)
    require(stable.returncode == 0 and interrupted.state() == resumed_state,
            "中断后重建的结果不稳定（热构建再次改写）")
    report("cache-interrupted-build", "构建中断与临时残留不产生虚假命中")

    # —— 并发构建：两个进程同时发布同一项目 ——
    concurrent = Project("concurrent")
    procs = [build(compiler, concurrent, env_a, background=True) for _ in range(2)]
    results = [proc.communicate(timeout=300) + (proc.returncode,) for proc in procs]
    for stdout, stderr, code in results:
        require(code == 0, f"并发构建失败 rc={code}：\n{stdout}\n{stderr[-1500:]}")
    settle = build(compiler, concurrent, env_a, stats=True)
    require(settle.returncode == 0, f"并发后热构建失败：{settle.stderr[-1000:]}")
    settled = concurrent.state()
    # 跨目录只比较与路径无关的对象键；链接键含输出路径与输出摘要，
    # 这里改为验证并发结果稳定（再次热构建不重写任何文件）。
    for tag in IDENTITY_KEYS:
        require(settled[tag] == base[tag],
                f"并发构建的最终 {tag} 与串行基线不一致")
    require(settled["executable"] is not None, "并发构建未产出可执行文件")
    runs = subprocess.run([str(concurrent.executable)], capture_output=True,
                          text=True, timeout=60)
    require(runs.returncode == 0, f"并发产物运行失败 rc={runs.returncode}")
    settling = build(compiler, concurrent, env_a)
    require(settling.returncode == 0 and concurrent.state() == settled,
            "并发构建结果不稳定：热构建再次改写了产物")
    report("cache-concurrent-build", "两次并发构建都成功且最终键值与串行一致")


def main():
    """解析参数并执行 Darwin 缓存身份门。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    require(compiler.is_file(), f"编译器不存在：{compiler}")
    sdk_root = find_sdk_root(dict(os.environ))
    run_suite(args, compiler, sdk_root, dict(os.environ))
    print("PASS Darwin/ARM64 LLVM 缓存身份：SDK 闭包、minOS、原子发布与并发")


if __name__ == "__main__":
    main()
