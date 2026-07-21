from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from extract_facts import infer_project_type, read_json, shallow_dirs, write_json


def detect_frontend_candidate(path: Path) -> bool:
    package_json = path / "package.json"
    if not package_json.exists():
        return False
    package = read_json(package_json)
    deps = {
        **package.get("dependencies", {}),
        **package.get("devDependencies", {}),
    }
    if any(name in deps for name in ("react", "vue", "vite", "next", "nuxt")):
        return True
    return (path / "src").exists()


def detect_backend_candidate(path: Path) -> bool:
    return any(path.glob("*.sln")) or any(path.glob("*.csproj"))


def detect_spring_boot_candidate(path: Path) -> bool:
    if not ((path / "pom.xml").exists() or (path / "build.gradle").exists() or (path / "build.gradle.kts").exists()):
        return False
    for marker_file in ("pom.xml", "build.gradle", "build.gradle.kts"):
        candidate = path / marker_file
        if candidate.exists() and "spring" in candidate.read_text(encoding="utf-8", errors="ignore").lower():
            return True
    return (path / "src" / "main" / "java").exists()


def analyze_child(path: Path) -> dict[str, str]:
    if detect_spring_boot_candidate(path):
        return {
            "template": "spring-boot-backend-child",
            "reason": "检测到 Spring Boot/Maven/Gradle 后端信号。",
            "suggestion_level": "保持当前识别",
            "suggestion": "保持当前识别，或在 manifest 中手工调整输出路径与 detail_level。",
        }
    if detect_backend_candidate(path):
        return {
            "template": "backend-child",
            "reason": "检测到 .sln 或 .csproj 文件。",
            "suggestion_level": "保持当前识别",
            "suggestion": "保持当前识别，或在 manifest 中手工调整输出路径与 detail_level。",
        }
    if detect_frontend_candidate(path):
        return {
            "template": "frontend-child",
            "reason": "检测到 package.json，且存在前端依赖或 src/ 目录。",
            "suggestion_level": "保持当前识别",
            "suggestion": "保持当前识别，或在 manifest 中手工调整输出路径与 detail_level。",
        }
    project_type = infer_project_type(path)
    if project_type == "后端":
        return {
            "template": "backend-child",
            "reason": "项目类型推断为后端。",
            "suggestion_level": "建议人工检查",
            "suggestion": "建议人工确认该目录是否确实应纳入 AGENTS 子项目。",
        }
    if project_type == "Java/Spring 后端":
        return {
            "template": "spring-boot-backend-child",
            "reason": "项目类型推断为 Java/Spring 后端。",
            "suggestion_level": "建议人工检查",
            "suggestion": "建议人工确认该目录是否确实应纳入 AGENTS 子项目。",
        }
    if project_type == "前端":
        return {
            "template": "frontend-child",
            "reason": "项目类型推断为前端。",
            "suggestion_level": "建议人工检查",
            "suggestion": "建议人工确认该目录是否确实应纳入 AGENTS 子项目。",
        }
    if (path / "package.json").exists():
        return {
            "template": "",
            "reason": "检测到 package.json，但缺少明确前端依赖和 src/ 目录，默认不纳入。",
            "suggestion_level": "建议人工检查",
            "suggestion": "建议检查该目录是否属于 Node 工具/脚本项目；若需要独立 AGENTS.md，请手工加入 manifest。",
        }
    if (path / "src").exists():
        return {
            "template": "",
            "reason": "检测到 src/ 目录，但缺少 package.json 或明确后端信号，默认不纳入。",
            "suggestion_level": "建议纳入 manifest",
            "suggestion": "建议检查是否为非标准前端目录布局；若需要纳入，请手工指定模板类型。",
        }
    return {
        "template": "",
        "reason": "未检测到前端或后端的浅层识别信号。",
        "suggestion_level": "保持忽略",
        "suggestion": "通常可保持忽略；若这是业务子项目，请手工检查并补充 manifest。",
    }


def output_path_for(template: str, child_relative: str) -> str:
    child_relative = child_relative.replace("\\", "/")
    return f"{child_relative}/AGENTS.md"


def suggested_template_for_item(item: dict[str, str]) -> str:
    if item.get("template"):
        return item["template"]
    if item.get("suggestion_level") == "建议纳入 manifest":
        return "frontend-child"
    return "frontend-child"


def suggested_manifest_snippet(item: dict[str, str]) -> str | None:
    if item.get("suggestion_level") in {"保持忽略", "保持当前识别"}:
        return None
    template = suggested_template_for_item(item)
    target = item["path"]
    output = output_path_for(template, target)
    return json.dumps(
        {
            "template": template,
            "target": target,
            "output": output,
            "detail_level": "rich",
        },
        ensure_ascii=False,
    )


def build_manifest(
    root: Path,
    detail_level: str,
    persist_facts: bool,
    facts_dir: str,
    include_claude: bool,
) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    children = []
    discovered: list[dict[str, str]] = []
    ignored: list[dict[str, str]] = []
    for child in shallow_dirs(root):
        analysis = analyze_child(child)
        template = analysis["template"]
        relative = str(child.relative_to(root)).replace("\\", "/")
        if not template:
            ignored.append(
                {
                    "path": relative,
                    "reason": analysis["reason"],
                    "suggestion_level": analysis["suggestion_level"],
                    "suggestion": analysis["suggestion"],
                }
            )
            continue
        children.append(
            {
                "template": template,
                "target": relative,
                "output": output_path_for(template, relative),
                "detail_level": detail_level,
            }
        )
        discovered.append(
            {
                "path": relative,
                "template": template,
                "reason": analysis["reason"],
                "suggestion_level": analysis["suggestion_level"],
                "suggestion": analysis["suggestion"],
            }
        )

    children.sort(key=lambda item: item["target"])
    discovered.sort(key=lambda item: item["path"])
    ignored.sort(key=lambda item: item["path"])
    root_analysis = analyze_child(root) if not children else {"template": ""}
    single_project = bool(root_analysis.get("template"))
    root_agents: dict[str, Any] = {
        "output": "AGENTS.md",
        "host": "codex",
        "detail_level": "standard",
    }
    if single_project:
        root_agents.update(
            {
                "template": root_analysis["template"],
                "target": ".",
                "detail_level": detail_level,
                "single_project": True,
            }
        )
        discovered.insert(
            0,
            {
                "path": ".",
                "template": root_analysis["template"],
                "reason": f"未发现第一层 child 目标；仓库根目录自身{root_analysis['reason']}",
                "suggestion_level": "单项目根目录",
                "suggestion": "root AGENTS.md 将使用匹配的 child 模板以 rich 细节生成，避免生成空泛 root 摘要。",
            },
        )

    manifest = {
        "root": str(root).replace("\\", "/"),
        "detail_level": detail_level,
        "persist_facts": persist_facts,
        "facts_dir": facts_dir,
        "children": children,
        "root_agents": root_agents,
    }
    if include_claude:
        manifest["claude"] = {
            "output": "CLAUDE.md",
            "host": "claude",
        }
    return manifest, discovered, ignored


def build_report(
    root: Path,
    discovered: list[dict[str, str]],
    ignored: list[dict[str, str]],
    manifest: dict[str, Any],
) -> str:
    lines = [
        "# Manifest Discovery Report",
        "",
        f"- 根目录：`{str(root).replace(chr(92), '/')}`",
        f"- 发现子项目数量：{len(discovered)}",
        f"- 忽略目录数量：{len(ignored)}",
        "",
        "## 已发现目标",
        "",
    ]
    if discovered:
        for item in discovered:
            lines.append(
                f"- `{item['path']}` -> `{item['template']}`：{item['reason']}"
            )
            lines.append(f"  建议级别：{item['suggestion_level']}")
            lines.append(f"  建议：{item['suggestion']}")
            snippet = suggested_manifest_snippet(item)
            if snippet:
                lines.append(f"  推荐片段：`{snippet}`")
    else:
        lines.append("- 未发现符合默认规则的 child 目标。")

    lines.extend(
        [
            "",
            "## 已忽略目录",
            "",
        ]
    )
    if ignored:
        for item in ignored:
            lines.append(f"- `{item['path']}`：{item['reason']}")
            lines.append(f"  建议级别：{item['suggestion_level']}")
            lines.append(f"  建议：{item['suggestion']}")
            snippet = suggested_manifest_snippet(item)
            if snippet:
                lines.append(f"  推荐片段：`{snippet}`")
    else:
        lines.append("- 无。")

    lines.extend(
        [
            "",
            "## 生成计划摘要",
            "",
            f"- root AGENTS 输出：`{manifest['root_agents']['output']}`",
            f"- root CLAUDE 输出：`{manifest.get('claude', {}).get('output', '已禁用')}`",
            "- 如发现遗漏或误判，请先修改 manifest，再运行 suite generator。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a suite manifest from shallow repository discovery."
    )
    parser.add_argument("--root", required=True, help="Repository root path.")
    parser.add_argument(
        "--detail-level",
        default="rich",
        choices=["basic", "standard", "rich"],
        help="Default detail level for discovered child targets. Root generation remains standard unless edited in the manifest.",
    )
    parser.add_argument(
        "--persist-facts",
        action="store_true",
        help="Persist intermediate facts in the generated suite manifest.",
    )
    parser.add_argument(
        "--facts-dir",
        default=".codex/agents-facts",
        help="Relative facts output directory for suite generation.",
    )
    parser.add_argument(
        "--no-claude",
        action="store_true",
        help="Do not include root CLAUDE.md generation in the manifest.",
    )
    parser.add_argument("--output", required=True, help="Output manifest JSON path.")
    parser.add_argument(
        "--report-output",
        help="Optional markdown report path describing discovered and ignored directories.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest, discovered, ignored = build_manifest(
        root=root,
        detail_level=args.detail_level,
        persist_facts=args.persist_facts,
        facts_dir=args.facts_dir,
        include_claude=not args.no_claude,
    )
    write_json(Path(args.output), manifest)
    if args.report_output:
        report_path = Path(args.report_output)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            build_report(root, discovered, ignored, manifest) + "\n",
            encoding="utf-8",
            newline="\n",
        )


if __name__ == "__main__":
    main()
