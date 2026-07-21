from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from generate_agents import generate_single

CHILD_TEMPLATES = {
    "dotnet-backend-child",
    "backend-child",
    "frontend-child",
    "userscripts-child",
    "nestjs-backend-child",
    "spring-boot-backend-child",
}


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def output_for(root: Path, relative_path: str) -> Path:
    return (root / relative_path).resolve()


def facts_output_for(root: Path, facts_dir: str | None, filename: str) -> Path | None:
    if not facts_dir:
        return None
    return (root / facts_dir / filename).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an AGENTS.md suite from a manifest in a fixed order."
    )
    parser.add_argument("--manifest", required=True, help="Path to the suite manifest JSON.")
    args = parser.parse_args()

    manifest = load_manifest(Path(args.manifest))
    root = Path(manifest["root"]).resolve()
    child_detail_level = manifest.get("detail_level", "rich")
    persist_facts = bool(manifest.get("persist_facts", False))
    facts_dir = manifest.get("facts_dir", ".codex/agents-facts") if persist_facts else None

    child_targets = manifest.get("children", [])
    child_agent_paths: list[str] = []

    for child in child_targets:
        template = child["template"]
        target = (root / child["target"]).resolve()
        output_relative = child["output"]
        output_path = output_for(root, output_relative)
        facts_output_path = facts_output_for(
            root,
            facts_dir,
            child.get("facts_output", f"{Path(output_relative).parent.name or 'root'}-{template}.json"),
        )
        generate_single(
            template=template,
            root=root,
            target=target,
            detail_level=child.get("detail_level", child_detail_level),
            child_agents=[],
            output_path=output_path,
            host=child.get("host", "codex"),
            facts_output_path=facts_output_path,
        )
        child_agent_paths.append(output_relative.replace("\\", "/"))

    root_config = manifest.get("root_agents")
    if root_config:
        root_template = root_config.get("template", "root")
        root_target = (root / root_config.get("target", ".")).resolve()
        single_project = bool(root_config.get("single_project", False))
        generate_single(
            template=root_template,
            root=root,
            target=root_target,
            detail_level=root_config.get("detail_level", "standard"),
            child_agents=[] if root_template in CHILD_TEMPLATES else child_agent_paths,
            output_path=output_for(root, root_config["output"]),
            host=root_config.get("host", "codex"),
            facts_output_path=facts_output_for(
                root,
                facts_dir,
                root_config.get("facts_output", "root-facts.json"),
            ),
            single_project=single_project,
            database_project_identifier=root_config.get("database_project"),
            database_default_production_read_target=root_config.get(
                "database_production_read_target"
            ),
        )

    claude_config = manifest.get("claude")
    if claude_config:
        generate_single(
            template="claude",
            root=root,
            target=root,
            detail_level=claude_config.get("detail_level", "standard"),
            child_agents=child_agent_paths,
            output_path=output_for(root, claude_config["output"]),
            host=claude_config.get("host", "claude"),
            facts_output_path=facts_output_for(
                root,
                facts_dir,
                claude_config.get("facts_output", "claude-facts.json"),
            ),
        )


if __name__ == "__main__":
    main()
