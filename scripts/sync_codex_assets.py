from __future__ import annotations

import os
import re
import shutil
import stat
import sys
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
    "sync_codex_assets.cmd",
    "sync_codex_assets.sh",
)
PROJECT_SKILL_ASSET_EXCLUDES: dict[str, tuple[str, ...]] = {}


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
            shutil.copytree(source_asset, target_asset, ignore=shutil.ignore_patterns(*ignored_names))
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
            shutil.copytree(source_skill_dir, target_skill_dir)
        print(f"[copied] {source_skill_dir.name} -> {target_skill_dir}")
        synced += 1

    return synced


def main() -> int:
    if len(sys.argv) > 1:
        raise ValueError("sync_codex_assets no longer accepts arguments; run the script with no parameters.")

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
