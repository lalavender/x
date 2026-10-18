#!/usr/bin/env python3
"""滚动自举汇编与接口快照的发现、保存和固定点校验。"""

import argparse
import hashlib
import re
import shutil
import platform
import tempfile
from pathlib import Path


def default_seed(root: Path, system=None, machine=None) -> Path:
    """选择本机可执行的入库种子，Mac arm64 保留现有 bin/yh 名称。"""
    system = system or platform.system()
    machine = machine or platform.machine()
    if machine in ("aarch64", "arm64"):
        architecture = "arm64"
    elif machine in ("x86_64", "amd64"):
        architecture = "x64"
    else:
        architecture = machine.lower()

    if system == "Darwin" and architecture == "arm64":
        basename = "yh"
    else:
        basename = f"yh-{system.lower()}-{architecture}"
    return root / "bin" / basename


def expected_artifacts(project: Path):
    """按 project.toml 的本地项目边界与显式 path 依赖发现完整产物集。"""
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
        modules = set()
        for source in sorted(current.rglob("*.yh")):
            if any(parent in source.resolve().parents for parent in nested_projects):
                continue
            match = re.search(
                r"(?m)^\s*module\s+([A-Za-z_][A-Za-z0-9_]*)\s*;",
                source.read_text(),
            )
            if not match:
                raise ValueError(f"源码未声明 module：{source}")
            modules.add(match.group(1))
        if not modules:
            raise ValueError(f"项目没有 .yh 模块：{current}")

        artifacts = {
            f"{directory}/{name.group(1)}-{module}{suffix}"
            for module in modules
            for directory, suffix in (("asm", ".s"), ("iface", ".s.i"),
                                      ("iface", ".s.ct"))
        }
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
    """把同一项目模块集合映射为 LLVM 文本与接口快照路径。"""
    result = set()
    for path in expected_artifacts(project):
        if path.startswith("asm/") and path.endswith(".s"):
            result.add("llvm/" + path[len("asm/"):-len(".s")] + ".ll")
        else:
            result.add(path)
    return result


def seed_sha256(seed: Path) -> str:
    """计算平台种子的 SHA-256。"""
    return hashlib.sha256(seed.read_bytes()).hexdigest()


def verify_seed(seed: Path) -> str:
    """验证种子相邻的 SHA-256 文件，并返回实际摘要。"""
    if not seed.is_file():
        raise ValueError(f"种子不存在：{seed}")
    hash_file = Path(str(seed) + ".sha256")
    fields = hash_file.read_text().split()
    if not fields or fields[0].lower() != seed_sha256(seed):
        raise ValueError(f"种子 SHA-256 不匹配：{seed}（校验文件 {hash_file}）")
    return fields[0].lower()


def write_seed_hash(seed: Path) -> str:
    """为已验证滚动的种子写入同名 SHA-256 记录。"""
    if not seed.is_file():
        raise ValueError(f"种子不存在：{seed}")
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
        for source in sorted(source_dir.glob("*" + suffix)):
            if source.is_file():
                relative = f"{directory}/{source.name}"
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
        for path in sorted(actual):
            if not contents[path]:
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
    assert default_seed(root, "Darwin", "arm64") == root / "bin" / "yh"
    assert default_seed(root, "Linux", "aarch64") == root / "bin" / "yh-linux-arm64"
    assert default_seed(root, "Linux", "x86_64") == root / "bin" / "yh-linux-x64"
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
        (project / "project.toml").write_text('[project]\nname = "root"\n')
        (project / "main.yh").write_text("module main;\n")
        nested = project / "tools"
        nested.mkdir()
        (nested / "project.toml").write_text('[project]\nname = "nested"\n')
        (nested / "ir.yh").write_text("module ir;\n")
        assert expected_artifacts(project) == {
            "asm/root-main.s", "iface/root-main.s.i", "iface/root-main.s.ct"
        }
    with tempfile.TemporaryDirectory(dir=str(tmp_root)) as directory:
        project = Path(directory)
        (project / "project.toml").write_text(
            '[project]\nname = "root"\n\n[dependencies]\nir = { path = "tools/ir" }\n'
        )
        (project / "main.yh").write_text("module main;\n")
        dependency = project / "tools" / "ir"
        dependency.mkdir(parents=True)
        (dependency / "project.toml").write_text('[project]\nname = "nested"\n')
        (dependency / "ir.yh").write_text("module ir;\n")
        assert expected_artifacts(project) == {
            "asm/root-main.s", "iface/root-main.s.i",
            "iface/root-main.s.ct", "asm/nested-ir.s", "iface/nested-ir.s.i",
            "iface/nested-ir.s.ct",
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
