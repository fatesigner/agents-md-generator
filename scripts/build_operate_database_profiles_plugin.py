from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "operate-database-profiles"
SKILL_SOURCE = PROJECT_ROOT / "skills" / SKILL_NAME
IGNORED_NAMES = {"__pycache__", ".DS_Store"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
PLUGIN_MANIFEST: dict[str, Any] = {
    "name": SKILL_NAME,
    "version": "0.1.0",
    "description": (
        "Safely inspect and query project-scoped SQL Server and PostgreSQL "
        "targets through local profiles."
    ),
    "author": {"name": "Local developer"},
    "skills": "./skills/",
    "mcpServers": "./.mcp.json",
    "interface": {
        "displayName": "Database Profile Operations",
        "shortDescription": "Safely inspect and query profiled databases",
        "longDescription": (
            "Use project-scoped profiles, a controlled local MCP server, and "
            "the shared dbctl safety core to diagnose connectivity and run "
            "reviewed read queries without exposing credentials."
        ),
        "developerName": "Local developer",
        "category": "Developer Tools",
        "capabilities": ["Interactive", "Read"],
        "defaultPrompt": [
            "Inspect the current project's declared database target before connecting",
            "Preflight and run a reviewed bounded read query",
        ],
    },
}
MCP_MANIFEST: dict[str, Any] = {
    "mcpServers": {
        "databaseProfiles": {
            "title": "Database Profiles",
            "description": (
                "Controlled local discovery, diagnosis, connectivity, and "
                "read-query tools for project-scoped database profiles."
            ),
            "cwd": ".",
            "command": "sh",
            "args": [
                "./skills/operate-database-profiles/scripts/dbctl-mcp.sh"
            ],
        }
    }
}


def ignored(path: Path) -> bool:
    return (
        any(part in IGNORED_NAMES for part in path.parts)
        or path.suffix.lower() in IGNORED_SUFFIXES
    )


def copy_skill(source: Path, target: Path) -> None:
    for source_path in sorted(source.rglob("*")):
        relative = source_path.relative_to(source)
        if ignored(relative):
            continue
        target_path = target / relative
        if source_path.is_symlink():
            raise ValueError(f"skill package cannot contain symlinks: {relative}")
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
        elif source_path.is_file():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_plugin(output: Path) -> Path:
    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    if not SKILL_SOURCE.is_dir():
        raise ValueError(f"canonical skill is missing: {SKILL_SOURCE}")

    output.mkdir(parents=True)
    copy_skill(SKILL_SOURCE, output / "skills" / SKILL_NAME)
    write_json(output / ".codex-plugin" / "plugin.json", PLUGIN_MANIFEST)
    write_json(output / ".mcp.json", MCP_MANIFEST)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the operate-database-profiles plugin from its canonical Skill."
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="New output directory; existing paths are rejected.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = build_plugin(args.output)
    except ValueError as error:
        print(f"build plugin: {error}")
        return 1
    print(f"Built plugin: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
