#!/usr/bin/env python3
"""滚动自举汇编与接口快照的发现、保存和固定点校验。"""

import argparse
import hashlib
import re
import shutil
import platform
import sys
import tempfile
from pathlib import Path


def default_seed(root: Path, system=None, machine=None) -> Path:
    """选择本机可执行的入库种子，统一按 yh-<平台>-<架构> 命名。"""
    system = system or platform.system()
    machine = machine or platform.machine()
    if machine in ("aarch64", "arm64"):
        architecture = "arm64"
    elif machine in ("x86_64", "amd64"):
        architecture = "x64"
    else:
        architecture = machine.lower()

    return root / "bin" / f"yh-{system.lower()}-{architecture}"


def _clean_component(text: str) -> str:
    """与编译器 mb_mod_tag/mb_asm_stem 同一套清洗：非 [A-Za-z0-9_] → '_'。"""
    return re.sub(r"[^A-Za-z0-9_]", "_", text)


def _host_platform():
    """返回 (system, arch)，arch 与 default_seed 的命名一致（arm64/x64）。"""
    machine = platform.machine()
    if machine in ("aarch64", "arm64"):
        return platform.system().lower(), "arm64"
    if machine in ("x86_64", "amd64"):
        return platform.system().lower(), "x64"
    return platform.system().lower(), machine.lower()


_PLATFORM_WORDS = {"darwin", "linux", "arm64", "x64"}


def _matches_platform(stem: str, system: str, arch: str) -> bool:
    """源文件名尾部的平台限定（<base>.<system>[.<arch>].yh）是否匹配宿主。

    与编译器项目扫描一致：clock.darwin.yh 只在 darwin 编译，
    clock.linux.arm64.yh 只在 linux/arm64 编译；无平台限定的文件全平台编译。
    """
    parts = stem.split(".")
    i = len(parts)
    while i > 1 and parts[i - 1] in _PLATFORM_WORDS:
        i -= 1
    for word in parts[i:]:
        if word in ("darwin", "linux") and word != system:
            return False
        if word in ("arm64", "x64") and word != arch:
            return False
    return True


def expected_artifacts(project: Path):
    """按 project.toml 的本地项目边界与显式 path 依赖发现完整产物集。

    RS3b 按文件对象布局：每个源文件一个 asm/<tag>/<stem>.s（stem 为去 .yh
    基名清洗、重名加 _2/_3、避开保留名 <tag>.stub），外加运行时桩对象
    asm/<tag>/<tag>.stub.s；接口仍为扁平 iface/<tag>.s.i 与 iface/<tag>.s.ct。
    源文件顺序取 sorted(rglob)，与项目扫描序一致（stem 冲突时的去重序依赖
    该假设；仓库语料无冲突，仅为鲁棒性保留）。
    """
    def collect(current: Path, active: set[Path]):
        current = current.resolve()
        if current in active:
            raise ValueError(f"项目 path 依赖成环：{current}")
        active = active | {current}
        manifest_path = current / "project.toml"
        manifest = manifest_path.read_text()
        name = re.search(r'(?m)^name\s*=\s*"([^"]+)"\s*(?:#.*)?$', manifest)
        if not name:
            raise ValueError(f"project.toml 缺少项目名称：{current}")

        nested_projects = {
            nested.parent.resolve()
            for nested in current.rglob("project.toml")
            if nested.parent.resolve() != current
        }
        module_sources: dict[str, list[Path]] = {}
        host_system, host_arch = _host_platform()
        for source in sorted(current.rglob("*.yh")):
            # 跳过构建/测试产物（yh test 生成的入口模块落在项目 tmp/ 下）。
            if {"tmp", ".build"} & set(source.relative_to(current).parts):
                continue
            if any(parent in source.resolve().parents for parent in nested_projects):
                continue
            if not _matches_platform(source.stem, host_system, host_arch):
                continue
            match = re.search(
                r"(?m)^\s*module\s+([A-Za-z_][A-Za-z0-9_]*)\s*;?",
                source.read_text(),
            )
            if not match:
                raise ValueError(f"源码未声明 module：{source}")
            module_sources.setdefault(match.group(1), []).append(source)
        if not module_sources:
            raise ValueError(f"项目没有 .yh 模块：{current}")

        tag_prefix = _clean_component(name.group(1))
        artifacts = set()
        for module, sources in module_sources.items():
            tag = f"{tag_prefix}-{_clean_component(module)}"
            reserved = f"{tag}.stub"
            seen: set[str] = set()
            for source in sources:
                base = _clean_component(source.stem)[:120] or "_"
                k = 2
                cand = base
                while cand in seen or cand == reserved:
                    k += 1
                    cand = f"{base}_{k - 1}"
                seen.add(cand)
                artifacts.add(f"asm/{tag}/{cand}.s")
            artifacts.add(f"asm/{tag}/{reserved}.s")
            artifacts.add(f"iface/{tag}.s.i")
            artifacts.add(f"iface/{tag}.s.ct")
        dependencies = re.search(
            r"(?ms)^\[dependencies\]\s*(.*?)(?=^\[|\Z)", manifest
        )
        if dependencies:
            for dependency in re.finditer(
                r'^\s*[A-Za-z_][A-Za-z0-9_-]*\s*=\s*\{[^}]*?\bpath\s*=\s*"([^"]+)"[^}]*\}',
                dependencies.group(1), re.MULTILINE,
            ):
                child = (current / dependency.group(1)).resolve()
                artifacts.update(collect(child, active))
        return artifacts

    return collect(project, set())


def expected_llvm_artifacts(project: Path):
    """把同一项目模块集合映射为 LLVM 文本与接口快照路径（llvm/<tag>.ll）。"""
    result = set()
    for path in expected_artifacts(project):
        if path.startswith("asm/") and path.endswith(".stub.s"):
            tag = path[len("asm/"):-len(".stub.s")].split("/")[0]
            result.add(f"llvm/{tag}.ll")
        elif not path.startswith("asm/"):
            result.add(path)
    return result


def expected_seed_flat_artifacts(project: Path):
    """滚动种子（RS3b 之前）的扁平 asm 布局：asm/<tag>.s 每模块一个，
    无按文件对象与运行时桩对象。仅用于种子首代（cc2）的迁移兼容判定。"""
    result = set()
    for path in expected_artifacts(project):
        if path.startswith("asm/"):
            if path.endswith(".stub.s"):
                continue
            parts = path.split("/")
            result.add(f"asm/{parts[1]}.s")
        else:
            result.add(path)
    return result


def seed_sha256(seed: Path) -> str:
    """计算平台种子的 SHA-256。"""
    return hashlib.sha256(seed.read_bytes()).hexdigest()


def seed_path_warnings(seed: Path) -> list[str]:
    """检查种子是否携带构建机 $HOME 绝对路径（Zig 式：闭包配方属于构建环境）。

    滚动前入库的种子会把桥/LLVM 归档路径烘焙进 lld 配置；新流程改由
    YH_LLVM_SELFHOST_FLAGS 在链接时提供，因此新种子不应出现 $HOME 路径。
    旧种子只警告（否则上一版 Release 种子无法参与 CI 自举）。
    """
    home = str(Path.home())
    if len(home) < 5:
        return []
    needle = home.encode()
    overlap = len(needle) - 1
    tail = b""
    with seed.open("rb") as source:
        while True:
            chunk = source.read(8 * 1024 * 1024)
            if not chunk:
                return []
            block = tail + chunk
            if needle in block:
                return [f"种子包含构建机绝对路径 {home}："
                        "自举闭包必须由构建机在链接时提供（YH_LLVM_SELFHOST_FLAGS）"]
            tail = block[-overlap:] if overlap > 0 else b""


def verify_seed(seed: Path) -> str:
    """验证种子相邻的 SHA-256 文件，并返回实际摘要。"""
    if not seed.is_file():
        raise ValueError(f"种子不存在：{seed}")
    hash_file = Path(str(seed) + ".sha256")
    fields = hash_file.read_text().split()
    if not fields or fields[0].lower() != seed_sha256(seed):
        raise ValueError(f"种子 SHA-256 不匹配：{seed}（校验文件 {hash_file}）")
    for warning in seed_path_warnings(seed):
        print(f"警告：{warning}", file=sys.stderr)
    return fields[0].lower()


def write_seed_hash(seed: Path) -> str:
    """为已验证滚动的种子写入同名 SHA-256 记录。

    连同滚动一起拒绝携带构建机路径的种子，避免同类问题再次入库。
    """
    if not seed.is_file():
        raise ValueError(f"种子不存在：{seed}")
    warnings = seed_path_warnings(seed)
    if warnings:
        raise ValueError("；".join(warnings))
    digest = seed_sha256(seed)
    Path(str(seed) + ".sha256").write_text(f"{digest}  {seed.name}\n")
    return digest


def save_snapshot(build_dir: Path, snapshot_dir: Path):
    """立即将本代的汇编和接口复制到独立目录并返回内容快照。"""
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True)

    result = {}
    for directory, suffix in (("asm", ".s"), ("iface", ".s.i"),
                              ("iface", ".s.ct")):
        source_dir = build_dir / directory
        if not source_dir.is_dir():
            continue
        # RS3b：asm/<tag>/<stem>.s 按模块分子目录，rglob 递归收集。
        for source in sorted(source_dir.rglob("*" + suffix)):
            if source.is_file():
                relative = f"{directory}/{source.relative_to(source_dir)}"
                contents = source.read_bytes()
                destination = snapshot_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(contents)
                result[relative] = contents
    return result


def save_llvm_snapshot(build_dir: Path, snapshot_dir: Path):
    """保存 LLVM 项目的 .ll/.s.i/.s.ct，供候选世代固定点比较。"""
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True)
    result = {}
    for directory, suffix in (("llvm", ".ll"), ("iface", ".s.i"),
                              ("iface", ".s.ct")):
        source_dir = build_dir / directory
        if not source_dir.is_dir():
            continue
        for source in sorted(source_dir.glob("*" + suffix)):
            if source.is_file():
                relative = f"{directory}/{source.name}"
                contents = source.read_bytes()
                destination = snapshot_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(contents)
                result[relative] = contents
    return result


def llvm_snapshot_errors(snapshot, expected, triple: str):
    """除路径/固定点外，核对 LLVM target triple 与接口版本头。"""
    errors = snapshot_errors([("LLVM", snapshot)], expected)
    for path, contents in sorted(snapshot.items()):
        if path.endswith(".ll"):
            marker = f'target triple = "{triple}"'.encode()
            if marker not in contents:
                errors.append(f"LLVM target triple 缺失或错误：{path}")
        elif path.endswith(".s.i"):
            header = contents.splitlines()[0] if contents else b""
            if not re.fullmatch(
                    rb"// yh-iface v[123] arch=arm64 suffix=.*", header):
                errors.append(f"接口版本头不兼容：{path}")
        elif path.endswith(".s.ct"):
            header = contents.splitlines()[0] if contents else b""
            if not re.fullmatch(
                    rb"// yh-ctiface v1 arch=arm64 suffix=.*", header):
                errors.append(f"CT 接口版本头不兼容：{path}")
    return errors


def snapshot_errors(snapshots, expected):
    """拒绝空快照、缺失/多余产物及相邻代内容差异。"""
    errors = []
    if not expected:
        errors.append("预期产物集合为空")
    if not snapshots:
        errors.append("没有自举代际快照")

    for name, contents in snapshots:
        actual = set(contents)
        if not actual:
            errors.append(f"{name} 快照为空")
        # 汇编文件允许为空（纯类型/常量声明的源文件无任何发射内容）；
        # 接口文件承载绑定数据，必须非空。
        for path in sorted(actual):
            if not contents[path] and not path.startswith("asm/"):
                errors.append(f"{name} 产物为空：{path}")
        missing = expected - actual
        extra = actual - expected
        if missing:
            errors.append(f"{name} 缺少产物：{', '.join(sorted(missing))}")
        if extra:
            errors.append(f"{name} 有非预期产物：{', '.join(sorted(extra))}")

    for (left_name, left), (right_name, right) in zip(snapshots, snapshots[1:]):
        for path in sorted(expected & set(left) & set(right)):
            if left[path] != right[path]:
                errors.append(f"{left_name} 与 {right_name} 内容不一致：{path}")
    return errors


def self_test() -> bool:
    """验证快照门、平台种子路径与摘要检查的成功和失败分支。"""
    root = Path("/repo")
    assert default_seed(root, "Darwin", "arm64") == root / "bin" / "yh-darwin-arm64"
    assert default_seed(root, "Darwin", "x86_64") == root / "bin" / "yh-darwin-x64"
    assert default_seed(root, "Linux", "aarch64") == root / "bin" / "yh-linux-arm64"
    assert default_seed(root, "Linux", "x86_64") == root / "bin" / "yh-linux-x64"
    with tempfile.TemporaryDirectory() as directory:
        clean_seed = Path(directory) / "clean"
        clean_seed.write_bytes(b"clean seed")
        assert not seed_path_warnings(clean_seed)
        dirty_seed = Path(directory) / "dirty"
        dirty_seed.write_bytes(b"prefix " + str(Path.home()).encode() + b" suffix")
        assert seed_path_warnings(dirty_seed)
    expected = {"asm/demo-lib.s", "iface/demo-lib.s.i",
                "iface/demo-lib.s.ct"}
    good = {path: path.encode() for path in expected}
    assert not snapshot_errors([("cc2", good), ("cc3", good.copy())], expected)
    assert snapshot_errors([("cc2", {}), ("cc3", good)], expected)
    extra = good.copy()
    extra["asm/extra.s"] = b"x"
    assert snapshot_errors([("cc2", extra), ("cc3", good)], expected)
    assert snapshot_errors([("cc2", {"asm/demo-lib.s": b"x"}), ("cc3", good)], expected)
    empty_file = good.copy()
    empty_file["iface/demo-lib.s.i"] = b""
    assert snapshot_errors([("cc2", empty_file), ("cc3", good)], expected)
    changed = good.copy()
    changed["asm/demo-lib.s"] = b"changed"
    assert snapshot_errors([("cc2", good), ("cc3", changed)], expected)
    assert not snapshot_errors([("cc3", changed), ("cc4", changed.copy())], expected)
    assert snapshot_errors([("cc2", good)], set())
    llvm_expected = {"llvm/demo-lib.ll", "iface/demo-lib.s.i",
                     "iface/demo-lib.s.ct"}
    llvm_good = {
        "llvm/demo-lib.ll": b'target triple = "x86_64-unknown-linux-gnu"\n',
        "iface/demo-lib.s.i": b"// yh-iface v3 arch=arm64 suffix=demo\n",
        "iface/demo-lib.s.ct": b"// yh-ctiface v1 arch=arm64 suffix=demo\n",
    }
    assert not llvm_snapshot_errors(llvm_good, llvm_expected,
                                    "x86_64-unknown-linux-gnu")
    assert llvm_snapshot_errors({key: value for key, value in llvm_good.items()
                                 if not key.endswith(".ll")}, llvm_expected,
                                "x86_64-unknown-linux-gnu")
    bad_iface = llvm_good.copy()
    bad_iface["iface/demo-lib.s.i"] = b"// yh-iface v9 arch=arm64 suffix=demo\n"
    assert llvm_snapshot_errors(bad_iface, llvm_expected,
                                "x86_64-unknown-linux-gnu")
    bad_triple = llvm_good.copy()
    bad_triple["llvm/demo-lib.ll"] = b'target triple = "aarch64-unknown-linux-gnu"\n'
    assert llvm_snapshot_errors(bad_triple, llvm_expected,
                                "x86_64-unknown-linux-gnu")
    tmp_root = Path(__file__).resolve().parent.parent / "tmp"
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(tmp_root)) as directory:
        project = Path(directory)
        (project / "project.toml").write_text('[project]\nos = "host"\narch = "host"\nname = "root"\n')
        (project / "main.yh").write_text("module main;\n")
        nested = project / "tools"
        nested.mkdir()
        (nested / "project.toml").write_text('[project]\nos = "host"\narch = "host"\nname = "nested"\n')
        (nested / "ir.yh").write_text("module ir;\n")
        assert expected_artifacts(project) == {
            "asm/root-main/main.s", "asm/root-main/root-main.stub.s",
            "iface/root-main.s.i", "iface/root-main.s.ct",
        }
        assert expected_llvm_artifacts(project) == {
            "llvm/root-main.ll", "iface/root-main.s.i", "iface/root-main.s.ct",
        }
    with tempfile.TemporaryDirectory(dir=str(tmp_root)) as directory:
        project = Path(directory)
        (project / "project.toml").write_text(
            '[project]\nos = "host"\narch = "host"\nname = "root"\n\n[dependencies]\nir = { path = "tools/ir" }\n'
        )
        (project / "main.yh").write_text("module main;\n")
        dependency = project / "tools" / "ir"
        dependency.mkdir(parents=True)
        (dependency / "project.toml").write_text('[project]\nos = "host"\narch = "host"\nname = "nested"\n')
        (dependency / "ir.yh").write_text("module ir;\n")
        assert expected_artifacts(project) == {
            "asm/root-main/main.s", "asm/root-main/root-main.stub.s",
            "iface/root-main.s.i", "iface/root-main.s.ct",
            "asm/nested-ir/ir.s", "asm/nested-ir/nested-ir.stub.s",
            "iface/nested-ir.s.i", "iface/nested-ir.s.ct",
        }
        assert expected_llvm_artifacts(project) == {
            "llvm/root-main.ll", "iface/root-main.s.i", "iface/root-main.s.ct",
            "llvm/nested-ir.ll", "iface/nested-ir.s.i", "iface/nested-ir.s.ct",
        }
    with tempfile.TemporaryDirectory(dir=str(tmp_root)) as directory:
        seed = Path(directory) / "yh-test"
        seed.write_bytes(b"seed generation one")
        digest = write_seed_hash(seed)
        assert verify_seed(seed) == digest
        seed.write_bytes(b"seed generation two")
        try:
            verify_seed(seed)
        except ValueError:
            pass
        else:
            raise AssertionError("种子内容变化后应因 SHA-256 不匹配而被拒绝")
    return True


def main() -> int:
    """运行快照门自检，或读写本机平台种子的摘要记录。"""
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--verify-seed", type=Path)
    group.add_argument("--write-seed-hash", type=Path)
    args = ap.parse_args()
    try:
        if args.verify_seed:
            print(verify_seed(args.verify_seed))
            return 0
        if args.write_seed_hash:
            print(write_seed_hash(args.write_seed_hash))
            return 0
    except (OSError, ValueError) as error:
        print(f"FAIL {error}")
        return 1

    self_test()
    print("自举快照门自检：空集、缺失产物和内容差异均被拒绝")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
