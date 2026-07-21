from __future__ import annotations

import argparse
from pathlib import Path

from extract_facts import (
    extract_backend_facts,
    extract_claude_facts,
    extract_frontend_facts,
    extract_nestjs_backend_facts,
    extract_root_facts,
    extract_spring_boot_backend_facts,
    extract_userscripts_facts,
    write_json,
)
from render_agents_from_facts import render

CHILD_TEMPLATES = {
    "dotnet-backend-child",
    "backend-child",
    "frontend-child",
    "userscripts-child",
    "nestjs-backend-child",
    "spring-boot-backend-child",
}


def default_detail_level_for_template(template: str) -> str:
    return "rich" if template in CHILD_TEMPLATES else "standard"


def build_facts(
    template: str,
    root: Path,
    target: Path,
    detail_level: str,
    child_agents: list[str],
    host: str,
    database_project_identifier: str | None = None,
    database_default_production_read_target: str | None = None,
) -> dict:
    if template == "root":
        return extract_root_facts(
            root,
            child_agents,
            host=host,
            database_project_identifier=database_project_identifier,
            database_default_production_read_target=database_default_production_read_target,
        )
    if database_project_identifier or database_default_production_read_target:
        raise ValueError("database profile binding is valid only for the root template")
    if template == "frontend-child":
        return extract_frontend_facts(root, target, detail_level)
    if template == "userscripts-child":
        return extract_userscripts_facts(root, target, detail_level)
    if template == "nestjs-backend-child":
        return extract_nestjs_backend_facts(root, target, detail_level)
    if template == "spring-boot-backend-child":
        return extract_spring_boot_backend_facts(root, target, detail_level)
    if template in {"dotnet-backend-child", "backend-child"}:
        return extract_backend_facts(root, target, detail_level)
    return extract_claude_facts(root, child_agents, host=host)


def generate_single(
    template: str,
    root: Path,
    target: Path,
    detail_level: str,
    child_agents: list[str],
    output_path: Path,
    host: str = "codex",
    facts_output_path: Path | None = None,
    single_project: bool = False,
    database_project_identifier: str | None = None,
    database_default_production_read_target: str | None = None,
) -> dict:
    facts = build_facts(
        template=template,
        root=root,
        target=target,
        detail_level=detail_level,
        child_agents=child_agents,
        host=host,
        database_project_identifier=database_project_identifier,
        database_default_production_read_target=database_default_production_read_target,
    )
    if single_project:
        facts["render_options"] = {
            **facts.get("render_options", {}),
            "single_project": True,
        }

    if facts_output_path:
        write_json(facts_output_path, facts)

    rendered = render(template, facts, output_path=output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8", newline="\n")
    return facts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract facts and render AGENTS.md/CLAUDE.md in one command."
    )
    parser.add_argument(
        "--template",
        required=True,
        choices=["root", "dotnet-backend-child", "backend-child", "frontend-child", "userscripts-child", "nestjs-backend-child", "spring-boot-backend-child", "claude"],
        help="Template type to generate.",
    )
    parser.add_argument("--root", required=True, help="Repository root path.")
    parser.add_argument(
        "--target",
        help="Target project path for child generation. Defaults to --root for root/claude.",
    )
    parser.add_argument(
        "--detail-level",
        choices=["basic", "standard", "rich"],
        help="Fact extraction detail level. Defaults to rich for child templates and standard for root/claude.",
    )
    parser.add_argument(
        "--child-agent",
        action="append",
        default=[],
        help="Relative child AGENTS path. Can be repeated.",
    )
    parser.add_argument(
        "--host",
        default="codex",
        choices=["codex", "claude"],
        help="Host profile used for root/claude generation.",
    )
    parser.add_argument("--output", required=True, help="Rendered markdown output path.")
    parser.add_argument(
        "--facts-output",
        help="Optional path to persist the extracted facts JSON.",
    )
    parser.add_argument(
        "--single-project",
        action="store_true",
        help="Render a child template as repository-root rules for a single-project repository.",
    )
    parser.add_argument(
        "--database-project",
        help="Explicit database profile project identifier for the root template; never inferred.",
    )
    parser.add_argument(
        "--database-production-read-target",
        help="Explicit default production read target for the root template; requires --database-project.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    target = Path(args.target).resolve() if args.target else root
    detail_level = args.detail_level or default_detail_level_for_template(args.template)
    generate_single(
        template=args.template,
        root=root,
        target=target,
        detail_level=detail_level,
        child_agents=args.child_agent,
        output_path=Path(args.output),
        host=args.host,
        facts_output_path=Path(args.facts_output) if args.facts_output else None,
        single_project=args.single_project,
        database_project_identifier=args.database_project,
        database_default_production_read_target=args.database_production_read_target,
    )


if __name__ == "__main__":
    main()
