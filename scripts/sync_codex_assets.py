from __future__ import annotations

import os
import re
import shutil
import stat
import sys
from collections.abc import Iterable
from typing import NamedTuple
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GLOBAL_REFERENCE_PATTERN = re.compile(r"references/([A-Za-z0-9_.-]+\.md)")
PROJECT_SKILL_ASSETS = (
    "SKILL.md",
    "agents",
    "references",
    "scripts",
    "skills",
    "subagents-main",
)
PROJECT_SKILL_ASSET_EXCLUDES: dict[str, tuple[str, ...]] = {}
RUNTIME_IGNORED_NAMES = {"__pycache__", ".DS_Store"}
RUNTIME_IGNORED_SUFFIXES = {".pyc", ".pyo"}


class DriftItem(NamedTuple):
    label: str
    target_exists: bool


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def ensure_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} does not exist: {resolved}")
    return resolved


def ensure_dir(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"{label} does not exist: {resolved}")
    return resolved


def write_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as target_file:
        target_file.write(content)
    print(f"[written] {target}")


def make_writable(path: Path) -> None:
    try:
        path.chmod(path.stat().st_mode | stat.S_IWRITE)
    except FileNotFoundError:
        return


def handle_rmtree_error(function, path: str, exc_info) -> None:
    exception = exc_info[1]
    if not isinstance(exception, PermissionError):
        raise exception

    make_writable(Path(path))
    function(path)


def remove_tree(path: Path) -> None:
    try:
        shutil.rmtree(path, onerror=handle_rmtree_error)
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot remove existing skill directory: {path}. "
            "Close any process using it and retry."
        ) from exc


def ignored_runtime_path(path: Path) -> bool:
    return any(part in RUNTIME_IGNORED_NAMES for part in path.parts) or (
        path.suffix.lower() in RUNTIME_IGNORED_SUFFIXES
    )


def managed_files(root: Path) -> dict[Path, Path]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root): path
        for path in root.rglob("*")
        if path.is_file() and not ignored_runtime_path(path.relative_to(root))
    }


def compare_file(source: Path, target: Path, label: str) -> list[DriftItem]:
    if not target.is_file():
        return [DriftItem(f"{label}: missing target", target.exists())]
    if source.read_bytes() != target.read_bytes():
        return [DriftItem(f"{label}: content differs", True)]
    return []


def compare_tree(source: Path, target: Path, label: str) -> list[DriftItem]:
    if not target.is_dir():
        return [DriftItem(f"{label}: missing target directory", target.exists())]
    source_files = managed_files(source)
    target_files = managed_files(target)
    drift: list[DriftItem] = []
    for relative in sorted(source_files.keys() | target_files.keys()):
        source_file = source_files.get(relative)
        target_file = target_files.get(relative)
        item_label = f"{label}/{relative.as_posix()}"
        if source_file is None:
            drift.append(DriftItem(f"{item_label}: unexpected target file", True))
        elif target_file is None:
            drift.append(DriftItem(f"{item_label}: missing target file", True))
        elif source_file.read_bytes() != target_file.read_bytes():
            drift.append(DriftItem(f"{item_label}: content differs", True))
    return drift


def compare_project_skill(source: Path, target: Path, label: str) -> list[DriftItem]:
    if not target.is_dir():
        return [DriftItem(f"{label}: missing target directory", target.exists())]
    drift: list[DriftItem] = []
    expected: set[Path] = set()
    for asset_name in PROJECT_SKILL_ASSETS:
        source_asset = source / asset_name
        if source_asset.is_dir():
            for relative, source_file in managed_files(source_asset).items():
                target_relative = Path(asset_name) / relative
                expected.add(target_relative)
                for item in compare_file(
                    source_file,
                    target / target_relative,
                    f"{label}/{target_relative.as_posix()}",
                ):
                    drift.append(DriftItem(item.label, True))
        else:
            expected.add(Path(asset_name))
            for item in compare_file(
                source_asset,
                target / asset_name,
                f"{label}/{asset_name}",
            ):
                drift.append(DriftItem(item.label, True))
    for relative in sorted(managed_files(target)):
        if relative not in expected:
            drift.append(
                DriftItem(
                    f"{label}/{relative.as_posix()}: unexpected target file",
                    True,
                )
            )
    return drift


def normalized_global_content(source: Path) -> bytes:
    content = source.read_text(encoding="utf-8")
    if not content.endswith("\n"):
        content += "\n"
    return content.encode("utf-8")


def compare_global_rule(source: Path, target: Path, label: str) -> list[DriftItem]:
    if not target.is_file():
        return [DriftItem(f"{label}: missing target", target.exists())]
    if normalized_global_content(source) != target.read_bytes():
        return [DriftItem(f"{label}: content differs", True)]
    return []


def find_managed_drift(
    *,
    global_source: Path,
    global_targets: Iterable[Path],
    references_source_dir: Path,
    references_target_dir: Path,
    subagents_source_dir: Path,
    subagents_target_dir: Path,
    skills_source_dir: Path,
    skills_target_dir: Path,
) -> list[DriftItem]:
    drift: list[DriftItem] = []
    for target in global_targets:
        drift.extend(compare_global_rule(global_source, target, str(target)))
    for source_file in discover_global_references(global_source, references_source_dir):
        target_file = references_target_dir / source_file.name
        drift.extend(compare_file(source_file, target_file, f"reference/{source_file.name}"))
    source_agents = sorted(subagents_source_dir.rglob("*.toml"))
    ensure_unique_agent_names(source_agents, subagents_source_dir)
    for source_file in source_agents:
        target_file = subagents_target_dir / source_file.name
        drift.extend(compare_file(source_file, target_file, f"agent/{source_file.name}"))
    for source_skill_dir in discover_skill_dirs(skills_source_dir):
        target_skill_dir = skills_target_dir / source_skill_dir.name
        label = f"skill/{source_skill_dir.name}"
        if same_path(source_skill_dir, target_skill_dir):
            continue
        if source_skill_dir == PROJECT_ROOT:
            drift.extend(
                compare_project_skill(source_skill_dir, target_skill_dir, label)
            )
        else:
            drift.extend(compare_tree(source_skill_dir, target_skill_dir, label))
    return drift


def sync_global_rules(source_file: Path, target_file: Path) -> int:
    content = source_file.read_text(encoding="utf-8")
    if not content.endswith("\n"):
        content += "\n"

    print(f"global_source: {source_file}")
    print(f"global_target: {target_file}")
    write_text(target_file, content)
    return 1


def discover_global_references(global_source_file: Path, references_source_dir: Path) -> list[Path]:
    content = global_source_file.read_text(encoding="utf-8")
    names = sorted(set(GLOBAL_REFERENCE_PATTERN.findall(content)))
    source_files: list[Path] = []

    for name in names:
        source_file = references_source_dir / name
        if not source_file.is_file():
            raise ValueError(f"Global reference is missing: {source_file}")
        source_files.append(source_file)

    return source_files


def sync_global_references(
    global_source_file: Path,
    references_source_dir: Path,
    references_target_dir: Path,
) -> int:
    source_files = discover_global_references(global_source_file, references_source_dir)

    print(f"references_source_dir: {references_source_dir}")
    print(f"references_target_dir: {references_target_dir}")

    references_target_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for source_file in source_files:
        target_file = references_target_dir / source_file.name
        shutil.copy2(source_file, target_file)
        print(f"[copied] reference {source_file.name} -> {target_file}")
        copied += 1

    return copied


def ensure_unique_agent_names(source_files: list[Path], source_dir: Path) -> None:
    seen: dict[str, Path] = {}
    duplicates: list[tuple[str, Path, Path]] = []

    for file_path in source_files:
        name = file_path.name
        if name in seen:
            duplicates.append((name, seen[name], file_path))
            continue
        seen[name] = file_path

    if duplicates:
        lines = ["Duplicate agent filenames detected in source tree:"]
        for name, first, second in duplicates:
            lines.append(f"- {name}: {first.relative_to(source_dir)} | {second.relative_to(source_dir)}")
        raise ValueError("\n".join(lines))


def sync_subagents(source_dir: Path, target_dir: Path) -> int:
    source_files = sorted(source_dir.rglob("*.toml"))
    if not source_files:
        raise ValueError(f"No .toml agent files found under: {source_dir}")

    ensure_unique_agent_names(source_files, source_dir)

    print(f"subagents_source_dir: {source_dir}")
    print(f"subagents_target_dir: {target_dir}")

    target_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for source_file in source_files:
        target_file = target_dir / source_file.name
        rel_source = source_file.relative_to(source_dir)
        shutil.copy2(source_file, target_file)
        print(f"[copied] {rel_source} -> {target_file}")
        copied += 1

    print(f"copied_agents: {copied}")
    return copied


def discover_nested_skill_dirs(source_dir: Path) -> list[Path]:
    return sorted(path for path in source_dir.iterdir() if path.is_dir() and (path / "SKILL.md").is_file())


def discover_skill_dirs(source_dir: Path) -> list[Path]:
    skill_dirs: list[Path] = []
    if (PROJECT_ROOT / "SKILL.md").is_file():
        skill_dirs.append(PROJECT_ROOT)
    skill_dirs.extend(discover_nested_skill_dirs(source_dir))

    seen: set[str] = set()
    duplicates: list[str] = []
    for skill_dir in skill_dirs:
        if skill_dir.name in seen:
            duplicates.append(skill_dir.name)
            continue
        seen.add(skill_dir.name)

    if duplicates:
        names = ", ".join(sorted(set(duplicates)))
        raise ValueError(f"Duplicate skill folder names detected: {names}")

    return skill_dirs


def copy_project_skill(source_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for asset_name in PROJECT_SKILL_ASSETS:
        source_asset = source_dir / asset_name
        if not source_asset.exists():
            raise ValueError(f"Project skill asset is missing: {source_asset}")

        target_asset = target_dir / asset_name
        if source_asset.is_dir():
            ignored_names = PROJECT_SKILL_ASSET_EXCLUDES.get(asset_name, ())
            shutil.copytree(
                source_asset,
                target_asset,
                ignore=shutil.ignore_patterns(
                    *ignored_names,
                    "__pycache__",
                    "*.pyc",
                    "*.pyo",
                    ".DS_Store",
                ),
            )
        else:
            shutil.copy2(source_asset, target_asset)


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except FileNotFoundError:
        return left.expanduser().absolute() == right.expanduser().absolute()


def sync_skills(source_dir: Path, target_dir: Path) -> int:
    skill_dirs = discover_skill_dirs(source_dir)
    if not skill_dirs:
        raise ValueError(f"No skill folders with SKILL.md found under: {source_dir}")

    print(f"skills_source_dir: {source_dir}")
    print(f"skills_target_dir: {target_dir}")

    target_dir.mkdir(parents=True, exist_ok=True)

    synced = 0
    for source_skill_dir in skill_dirs:
        target_skill_dir = target_dir / source_skill_dir.name
        if same_path(source_skill_dir, target_skill_dir):
            print(f"[skipped] skill already at target {target_skill_dir}")
            synced += 1
            continue

        if target_skill_dir.exists():
            remove_tree(target_skill_dir)
            print(f"[removed] {target_skill_dir}")
        if source_skill_dir == PROJECT_ROOT:
            copy_project_skill(source_skill_dir, target_skill_dir)
        else:
            shutil.copytree(
                source_skill_dir,
                target_skill_dir,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    "*.pyo",
                    ".DS_Store",
                ),
            )
        print(f"[copied] {source_skill_dir.name} -> {target_skill_dir}")
        synced += 1

    return synced


def parse_mode(argv: list[str]) -> str:
    if not argv:
        return "sync"
    if argv == ["--check"]:
        return "check"
    if argv == ["--overwrite-runtime-drift"]:
        return "overwrite"
    raise ValueError(
        "usage: sync_codex_assets.sh [--check|--overwrite-runtime-drift]"
    )


def main() -> int:
    mode = parse_mode(sys.argv[1:])

    codex_home = default_codex_home().resolve()
    print(f"codex_home: {codex_home}")

    global_source = ensure_file(PROJECT_ROOT / "references" / "global-template.md", "Global source file")
    global_target = (codex_home / "AGENTS.md").resolve()
    gemini_global_target = (Path.home() / ".gemini" / "GEMINI.md").resolve()
    references_source_dir = ensure_dir(PROJECT_ROOT / "references", "References source directory")
    references_target_dir = (codex_home / "references").resolve()
    subagents_source_dir = ensure_dir(PROJECT_ROOT / "subagents-main", "Subagents source directory")
    subagents_target_dir = (codex_home / "agents").resolve()
    skills_source_dir = ensure_dir(PROJECT_ROOT / "skills", "Skills source directory")
    skills_target_dir = (codex_home / "skills").resolve()

    drift_arguments = {
        "global_source": global_source,
        "global_targets": [global_target, gemini_global_target],
        "references_source_dir": references_source_dir,
        "references_target_dir": references_target_dir,
        "subagents_source_dir": subagents_source_dir,
        "subagents_target_dir": subagents_target_dir,
        "skills_source_dir": skills_source_dir,
        "skills_target_dir": skills_target_dir,
    }
    drift = find_managed_drift(**drift_arguments)
    for item in drift:
        print(f"[drift] {item.label}")
    if mode == "check":
        if drift:
            print(f"[DRIFT] Managed assets differ: {len(drift)}")
            return 1
        print("[OK] Managed assets are byte-identical.")
        return 0
    existing_drift = [item for item in drift if item.target_exists]
    if existing_drift and mode != "overwrite":
        raise ValueError(
            "managed runtime drift detected; run --check, review the differences, "
            "then use --overwrite-runtime-drift only when replacement is intended"
        )

    synced = {
        "global": sync_global_rules(global_source, global_target),
        "gemini_global": sync_global_rules(global_source, gemini_global_target),
        "global_references": sync_global_references(
            global_source,
            references_source_dir,
            references_target_dir,
        ),
        "subagents": sync_subagents(subagents_source_dir, subagents_target_dir),
        "skills": sync_skills(skills_source_dir, skills_target_dir),
    }

    remaining_drift = find_managed_drift(**drift_arguments)
    if remaining_drift:
        labels = "\n".join(f"- {item.label}" for item in remaining_drift[:20])
        raise ValueError(
            "post-sync verification failed; managed assets still differ:\n"
            f"{labels}"
        )
    for label, count in synced.items():
        print(f"synced_{label}: {count}")
    print("[OK] Sync completed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1) from None
