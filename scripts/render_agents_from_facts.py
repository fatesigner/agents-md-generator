from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "references"

TEMPLATE_MAP = {
    "root": REFERENCES / "root-template.md",
    "dotnet-backend-child": REFERENCES / "dotnet-backend-child-template.md",
    "backend-child": REFERENCES / "dotnet-backend-child-template.md",
    "frontend-child": REFERENCES / "frontend-child-template.md",
    "nestjs-backend-child": REFERENCES / "nestjs-backend-child-template.md",
    "spring-boot-backend-child": REFERENCES / "spring-boot-backend-child-template.md",
    "userscripts-child": REFERENCES / "userscripts-child-template.md",
    "claude": REFERENCES / "claude-template.md",
}

PROJECT_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def first_value(values: list[str], fallback: str) -> str:
    return values[0] if values else fallback


def sort_paths(items: list[dict[str, Any]] | list[str]) -> list[Any]:
    if not items:
        return []
    if isinstance(items[0], str):
        return sorted(items)
    return sorted(items, key=lambda item: str(item.get("path", "")))


def line_value(text: str) -> str | None:
    text = str(text).strip()
    return text or None


def package_script_invocation(package_manager: str, script_name: str) -> str:
    if package_manager == "pnpm":
        return f"pnpm {script_name}"
    if package_manager == "yarn":
        return f"yarn {script_name}"
    if package_manager == "bun":
        return f"bun run {script_name}"
    return f"npm run {script_name}"


def package_script_fix_invocation(package_manager: str, script_name: str) -> str:
    if package_manager == "pnpm":
        return f"pnpm {script_name} --fix"
    if package_manager == "yarn":
        return f"yarn {script_name} --fix"
    if package_manager == "bun":
        return f"bun run {script_name} -- --fix"
    return f"npm run {script_name} -- --fix"


def relative_include_path(output_path: Path, target_path: Path) -> str:
    include_path = Path(target_path)
    if not output_path.is_absolute():
        return str(include_path).replace("\\", "/")
    relative = Path(
        os.path.relpath(str(include_path), start=str(output_path.parent))
    )
    text = str(relative).replace("\\", "/")
    return text or "."


def item_label(item: dict[str, Any], primary_key: str = "path") -> str:
    value = item.get(primary_key) or item.get("name") or ""
    return str(value)


def detail_text(item: dict[str, Any]) -> str:
    for key in ("purpose", "reason", "mode"):
        value = str(item.get(key, "")).strip()
        if value:
            return value
    return ""


def bullet_block(
    items: list[dict[str, Any]],
    fallback: str,
    primary_key: str = "path",
) -> str:
    if not items:
        return f"- `[DEFAULT]` {fallback}"
    lines: list[str] = []
    for item in sort_paths(items):
        label = item_label(item, primary_key=primary_key)
        if not label:
            continue
        detail = detail_text(item)
        lines.append(f"- `{label}`" + (f"：{detail}" if detail else ""))
    return "\n".join(lines) if lines else f"- `[DEFAULT]` {fallback}"


def indented_bullet_block(
    items: list[dict[str, Any]],
    fallback: str,
    primary_key: str = "path",
) -> str:
    return "\n".join(f"  {line}" for line in bullet_block(items, fallback, primary_key).splitlines())


def tree_comment(text: str) -> str:
    return f" # {text}" if text else ""


def tree_block(root_label: str, entries: list[tuple[str, str]]) -> str:
    if len(entries) < 2:
        return ""
    lines = ["```text", root_label.rstrip("/") + "/"]
    for index, (path, purpose) in enumerate(entries[:12]):
        branch = "└──" if index == len(entries[:12]) - 1 else "├──"
        lines.append(f"{branch} {path}{tree_comment(purpose)}")
    lines.extend(["```"])
    return "\n".join(lines)


def strip_src_prefix(path: str) -> str:
    return path[4:] if path.startswith("src/") else path


def first_existing_item(items: list[dict[str, Any]], candidates: tuple[str, ...]) -> str:
    paths = {str(item.get("path", "")) for item in items}
    for candidate in candidates:
        if candidate in paths:
            return candidate
    return ""


def frontend_key_structure_tree(facts: dict[str, Any]) -> str:
    identity = facts.get("project_identity", {})
    structure = facts.get("structure", {})
    boundaries = facts.get("boundaries", {})
    source_dirs = list(structure.get("source_dirs", []))
    app_dirs = list(structure.get("app_dirs", []))
    known_dirs = {
        str(item.get("path", "")).rstrip("/")
        for group in ("source_dirs", "app_dirs", "feature_dirs", "shared_dirs")
        for item in structure.get(group, [])
    }
    entries: list[tuple[str, str]] = []
    for item in structure.get("entry_points", []):
        path = str(item.get("path", "")).strip()
        if path:
            entries.append((strip_src_prefix(path), str(item.get("purpose", "应用入口"))))
    route_dir = str(boundaries.get("route_dir", "")).strip()
    if route_dir.rstrip("/") in known_dirs and "未在本地" not in route_dir:
        entries.append((strip_src_prefix(route_dir.rstrip("/") + "/"), "路由定义、导航守卫与页面准入"))
    state_dir = str(boundaries.get("state_dir", "")).strip()
    if state_dir.rstrip("/") in known_dirs and "未在本地" not in state_dir:
        entries.append((strip_src_prefix(state_dir.rstrip("/") + "/"), "跨页面状态或核心上下文"))
    api_dir = str(boundaries.get("api_dir", "")).strip()
    if api_dir.rstrip("/") in known_dirs and "未在本地" not in api_dir:
        entries.append((strip_src_prefix(api_dir.rstrip("/") + "/"), "接口请求封装与服务访问"))
    for item in structure.get("feature_dirs", []):
        path = str(item.get("path", "")).strip()
        if path:
            entries.append((strip_src_prefix(path.rstrip("/") + "/"), str(item.get("purpose", "页面、功能或业务模块目录"))))
    for raw_path in str(boundaries.get("shared_dirs_text", "")).split("、"):
        path = raw_path.strip()
        if path.rstrip("/") in known_dirs and "未在本地" not in path:
            entries.append((strip_src_prefix(path.rstrip("/") + "/"), "可复用组件、共享工具或跨页面能力"))
    theme_dir = str(boundaries.get("theme_dir", "")).strip()
    if theme_dir.rstrip("/") in known_dirs and "未在本地" not in theme_dir:
        entries.append((strip_src_prefix(theme_dir.rstrip("/") + "/"), "全局样式、主题或设计令牌"))
    type_dir = str(boundaries.get("type_dir", "")).strip()
    if type_dir.rstrip("/") in known_dirs and "未在本地" not in type_dir:
        entries.append((strip_src_prefix(type_dir.rstrip("/") + "/"), "类型声明与共享类型"))
    deduped = list(dict.fromkeys(entries))
    return tree_block(f"{identity.get('path', '.')}/src", deduped)


def generic_key_structure_tree(facts: dict[str, Any]) -> str:
    identity = facts.get("project_identity", {})
    structure = facts.get("structure", {})
    entries: list[tuple[str, str]] = []
    for key in ("feature_dirs", "shared_dirs", "script_dirs", "docs_dirs"):
        for item in structure.get(key, []):
            path = str(item.get("path", "")).strip()
            purpose = str(item.get("purpose", "")).strip()
            if path and "未在本地" not in path:
                entries.append((path.rstrip("/") + "/", purpose))
    deduped = list(dict.fromkeys(entries))
    return tree_block(str(identity.get("path", ".")), deduped)


def key_structure_tree_block(facts: dict[str, Any]) -> str:
    project_type = str(facts.get("project_identity", {}).get("project_type", ""))
    if project_type in {"frontend", "userscripts"}:
        tree = frontend_key_structure_tree(facts)
        if tree:
            return tree
    return generic_key_structure_tree(facts)


def backend_structure_summary_block(facts: dict[str, Any], key_tree: str) -> str:
    structure = facts.get("structure", {})
    if key_tree:
        solution_file = str(structure.get("solution_file", "")).strip()
        lines = [key_tree]
        if solution_file and "未在本地" not in solution_file:
            lines.extend(["", f"- `[DEFAULT]` 解决方案文件：`{solution_file}`"])
        return "\n".join(lines)
    contracts = [str(item) for item in structure.get("contracts", []) if item]
    services = [str(item) for item in structure.get("services", []) if item]
    data_access = [str(item) for item in structure.get("data_access", []) if item]
    lines = [
        "- `[DEFAULT]` 入口项目：",
        f"  - `{structure.get('entry_project', '未在本地浅层扫描中确认入口项目')}`",
    ]
    if contracts or services:
        lines.append("- `[DEFAULT]` 业务契约与服务：")
        for item in contracts + services:
            lines.append(f"  - `{item}`")
    if data_access:
        lines.append("- `[DEFAULT]` 数据访问：")
        for item in data_access:
            lines.append(f"  - `{item}`")
    solution_file = str(structure.get("solution_file", "")).strip()
    if solution_file:
        lines.extend(["- `[DEFAULT]` 解决方案文件：", f"  - `{solution_file}`"])
    return "\n".join(lines)


def child_structure_overview_block(facts: dict[str, Any], key_tree: str, structure_extra: str) -> str:
    identity = facts.get("project_identity", {})
    project_type = str(identity.get("project_type", ""))
    structure = facts.get("structure", {})
    environment = facts.get("environment", {})
    if project_type == "backend":
        return backend_structure_summary_block(facts, key_tree)
    if key_tree:
        lines = [key_tree]
        meta_lines: list[str] = []
        if project_type in {"frontend", "userscripts"}:
            build_tool = str(environment.get("build_tool", "")).strip()
            test_tool = str(environment.get("test_tool", "")).strip()
            if build_tool and "未在本地" not in build_tool:
                meta_lines.append(f"- `[DEFAULT]` 构建工具：`{build_tool}`")
            if test_tool and "未在本地" not in test_tool:
                meta_lines.append(f"- `[DEFAULT]` 测试工具：`{test_tool}`")
        elif project_type == "nestjs-backend":
            prisma_dir = str(structure.get("prisma_dir", "")).strip()
            script_dir = str(structure.get("script_dir", "")).strip()
            if prisma_dir and "未在本地" not in prisma_dir:
                meta_lines.append(f"- `[DEFAULT]` Prisma 目录：`{prisma_dir}`")
            if script_dir and "未在本地" not in script_dir:
                meta_lines.append(f"- `[DEFAULT]` 脚本目录：`{script_dir}`")
        elif project_type == "spring-boot-backend":
            build_tool = str(environment.get("build_tool", "")).strip()
            build_descriptor = str(structure.get("build_descriptor", "")).strip()
            if build_tool and "未在本地" not in build_tool:
                suffix = f"（`{build_descriptor}`）" if build_descriptor and "未在本地" not in build_descriptor else ""
                meta_lines.append(f"- `[DEFAULT]` 构建工具：`{build_tool}`{suffix}")
        if meta_lines:
            lines.append("\n".join(meta_lines))
        return "\n\n".join(lines)
    if structure_extra:
        return structure_extra
    return "- `[DEFAULT]` 未在本地浅层扫描中确认足够稳定的关键结构；需要时再做局部确认。"


def validation_matrix_block(validation: dict[str, Any]) -> str:
    items = validation.get("by_change_type", [])
    if not items:
        return "- `[DEFAULT]` 未在本地浅层扫描中确认按改动类型区分的验证矩阵；执行前先查看项目测试配置。"
    lines: list[str] = []
    for item in items:
        change = str(item.get("change", "")).strip()
        command = str(item.get("command", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if not change or not command:
            continue
        suffix = f"；{reason}" if reason else ""
        lines.append(f"- `[DEFAULT]` {change}：`{command}`{suffix}")
    return "\n".join(lines) if lines else "- `[DEFAULT]` 未在本地浅层扫描中确认按改动类型区分的验证矩阵；执行前先查看项目测试配置。"


def config_touchpoints_block(config_touchpoints: dict[str, Any]) -> str:
    blocks: list[str] = []
    files = config_touchpoints.get("files", [])
    example_files = config_touchpoints.get("example_files", [])
    runtime_mode_files = config_touchpoints.get("runtime_mode_files", [])
    binding_files = config_touchpoints.get("binding_files", [])
    if files:
        blocks.append("- `[DEFAULT]` 已识别配置文件：")
        blocks.append(indented_bullet_block(files, "未在本地浅层扫描中确认配置文件。", primary_key="name"))
    if example_files:
        blocks.append("- `[MUST]` 新增配置项时优先同步示例配置：")
        blocks.append(indented_bullet_block(example_files, "未在本地浅层扫描中确认示例配置文件。", primary_key="name"))
    if runtime_mode_files:
        blocks.append("- `[DEFAULT]` 已识别运行模式配置文件；只按文件名确认，真实配置原文仍按敏感边界处理：")
        blocks.append(indented_bullet_block(runtime_mode_files, "未在本地浅层扫描中确认运行模式配置文件。", primary_key="name"))
    if binding_files:
        blocks.append("- `[DEFAULT]` 配置绑定或加载入口优先检查：")
        blocks.append(indented_bullet_block(binding_files, "未在本地浅层扫描中确认配置绑定入口。"))
    return "\n".join(blocks)


def structure_extra_block(structure: dict[str, Any], project_type: str = "") -> str:
    blocks: list[str] = []
    feature_title = (
        "业务模块与项目目录"
        if project_type in {"backend", "nestjs-backend", "spring-boot-backend"}
        else "功能、页面或业务模块目录"
    )
    for key, title, fallback in (
        ("feature_dirs", feature_title, "未在本地浅层扫描中确认额外功能目录。"),
        ("shared_dirs", "共享能力或公共基础设施目录", "未在本地浅层扫描中确认共享能力目录。"),
        ("script_dirs", "项目脚本或工具入口", "未在本地浅层扫描中确认项目脚本目录。"),
        ("docs_dirs", "项目文档目录", "未在本地浅层扫描中确认项目文档目录。"),
    ):
        items = structure.get(key, [])
        if items:
            blocks.append(f"- `[DEFAULT]` {title}：")
            blocks.append(indented_bullet_block(items, fallback))
    return "\n".join(blocks)


def generated_boundaries_block(boundaries: dict[str, Any]) -> str:
    blocks: list[str] = []
    generated_paths = boundaries.get("generated_paths", [])
    high_risk = boundaries.get("high_risk_touchpoints", [])
    if generated_paths:
        blocks.append("- `[MUST NOT]` 未经明确要求，不手工修改以下生成目录；需要更新时优先运行项目既有生成命令：")
        blocks.append(indented_bullet_block(generated_paths, "未在本地浅层扫描中确认生成目录。"))
    if high_risk:
        blocks.append("- `[MUST]` 以下路径属于高风险 touchpoint，改动时在交付中说明影响面、验证与回滚关注点：")
        blocks.append(indented_bullet_block(high_risk, "未在本地浅层扫描中确认高风险 touchpoint。"))
    return "\n".join(blocks)


def add_rich_block_replacements(replacements: dict[str, str], facts: dict[str, Any]) -> None:
    structure = facts.get("structure", {})
    validation = facts.get("validation", {})
    config_touchpoints = facts.get("config_touchpoints", {})
    boundaries = facts.get("boundaries", {})
    project_type = str(facts.get("project_identity", {}).get("project_type", ""))
    key_tree = key_structure_tree_block(facts)
    structure_extra = "" if key_tree else structure_extra_block(structure, project_type=project_type)
    child_overview = child_structure_overview_block(facts, key_tree, structure_extra)
    replacements["__CHILD_STRUCTURE_OVERVIEW__"] = child_overview
    replacements["__BACKEND_STRUCTURE_OVERVIEW__"] = child_overview
    replacements["__KEY_STRUCTURE_TREE__"] = key_tree
    replacements["__STRUCTURE_EXTRA__"] = structure_extra
    replacements["__VALIDATION_MATRIX__"] = validation_matrix_block(validation)
    replacements["__CONFIG_TOUCHPOINT_DETAILS__"] = config_touchpoints_block(config_touchpoints)
    replacements["__GENERATED_BOUNDARIES__"] = generated_boundaries_block(boundaries)


def root_top_level_line(entry: dict[str, Any]) -> str:
    path = str(entry.get("path", ""))
    project_type = str(entry.get("project_type", "")).strip()
    description = str(entry.get("description", "")).strip()
    if project_type and project_type != "目录":
        return f"- `{path}`：{project_type}，{description}"
    return f"- `{path}`：{description}"


def remove_empty_rich_sections(rendered: str) -> str:
    rich_headings = (
        "### 生成目录与高风险 touchpoint",
        "### 配置 touchpoint",
        "## 配置 touchpoint",
        "### 验证矩阵",
    )
    lines = rendered.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip() in rich_headings:
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            if next_index >= len(lines) or lines[next_index].startswith("#"):
                index = next_index
                continue
        output.append(line)
        index += 1
    return "\n".join(output).strip() + "\n"


def root_replacements(facts: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    host_profile = facts.get("host_profile", {})
    repository = facts.get("repository_profile", {})
    top_level_entries = sort_paths(facts.get("top_level_entries", []))
    child_paths = sort_paths(
        [
            item["path"] if isinstance(item, dict) else item
            for item in facts.get("child_agents_paths", [])
        ]
    )
    command_refs = sort_paths(facts.get("command_refs", []))
    database_profile_binding = facts.get("database_profile_binding", {})
    database_project = str(database_profile_binding.get("project_identifier", "")).strip()
    default_production_read_target = str(
        database_profile_binding.get("default_production_read_target", "")
    ).strip()

    replacements = {
        "[全局规则建议路径]": str(host_profile.get("global_rule_path", "~/.codex/AGENTS.md")),
        "[用户级工作目录]": str(host_profile.get("user_home_dir", "~/.codex")),
        "[仓库形态描述]": str(
            repository.get(
                "repo_shape",
                "按本地已验证目录结构组织的代码仓库",
            )
        ),
    }
    removable: set[str] = set()
    if database_project:
        if not PROJECT_IDENTIFIER_PATTERN.fullmatch(database_project):
            raise ValueError(
                "database profile project identifier must match "
                "[A-Za-z0-9][A-Za-z0-9._-]*"
            )
        if default_production_read_target and not PROJECT_IDENTIFIER_PATTERN.fullmatch(
            default_production_read_target
        ):
            raise ValueError(
                "default production read target must match "
                "[A-Za-z0-9][A-Za-z0-9._-]*"
            )
        binding_lines = [
            "### 数据库 Profile 绑定",
            "",
            f"- `[MUST]` 本仓库的 `$operate-database-profiles` project identifier 为 `{database_project}`。",
        ]
        if default_production_read_target:
            binding_lines.extend(
                [
                    f"- `[MUST]` 本仓库默认生产只读 target 为 `{default_production_read_target}`；仅在当前任务明确请求生产 `ping`、只读查询、schema 或权限检查且未点名 target 时使用。",
                    "- `[MUST]` 上述生产只读请求本身即构成该次操作授权，Agent 必须自动传入 `--allow-production`，不得要求额外确认；不得将该授权用于生产写入、TLS 降级或后续无关任务。",
                    f"- `[MUST]` 其他数据库 target 必须通过 `dbctl list {database_project}` 返回的安全元数据或用户在当前任务中的明确指定来确定，不得根据目录名、历史会话或相似名称猜测。",
                ]
            )
        else:
            binding_lines.extend(
                [
                    f"- `[MUST]` 数据库 target 必须通过 `dbctl list {database_project}` 返回的安全元数据或用户在当前任务中的明确指定来确定，不得根据目录名、历史会话或相似名称猜测。",
                    "- `[MUST]` 未声明默认生产只读 target 时，生产 target 必须由用户在当前任务中明确指定；明确的生产只读请求本身即构成该次操作授权，不再要求二次确认。",
                ]
            )
        replacements["__ROOT_DATABASE_PROFILE_BINDING__"] = "\n".join(binding_lines)
    else:
        if default_production_read_target:
            raise ValueError(
                "default production read target requires a database profile project identifier"
            )
        removable.add("__ROOT_DATABASE_PROFILE_BINDING__")
    if top_level_entries:
        replacements["__ROOT_TOP_LEVEL_ENTRIES__"] = "\n".join(
            root_top_level_line(entry)
            for entry in top_level_entries
        )
    else:
        replacements["__ROOT_TOP_LEVEL_ENTRIES__"] = "- `[DEFAULT]` 未在本地浅层扫描中确认核心目录。"

    for index in range(3):
        entry = top_level_entries[index] if index < len(top_level_entries) else None
        full_line_placeholder = f"- `[目录项{index + 1}]`：[项目类型]，[项目说明]"
        if entry:
            replacements[full_line_placeholder] = root_top_level_line(entry)
        else:
            removable.add(full_line_placeholder)

    for index in range(3):
        placeholder = f"[子目录 AGENTS 路径{index + 1}]"
        if index < len(child_paths):
            replacements[placeholder] = str(child_paths[index])
        else:
            removable.add(placeholder)

    for index in range(3):
        placeholder = f"[子目录 AGENTS 路径{index + 1}]"
        compact_placeholder = f"[子目录AGENTS路径{index + 1}]"
        if index < len(child_paths):
            replacements[compact_placeholder] = str(child_paths[index])
        else:
            removable.add(compact_placeholder)

    env = facts.get("environment", {})
    package_managers = env.get("package_managers", [])
    runtimes = env.get("runtimes", [])
    if package_managers or runtimes:
        env_lines: list[str] = []
        for item in package_managers:
            env_lines.append(
                f"- `[DEFAULT]` 包管理器：`{item.get('name', '')}`"
                + (f"（{item.get('version')}）" if item.get("version") else "")
            )
        for item in runtimes:
            env_lines.append(
                f"- `[DEFAULT]` 运行时：`{item.get('name', '')}`"
                + (f"（{item.get('version')}）" if item.get("version") else "")
            )
        replacements["__ROOT_ENV_EXTRA__"] = "\n".join(env_lines)
    else:
        removable.add("__ROOT_ENV_EXTRA__")

    if command_refs:
        command_lines = [f"  - `{item.get('path', '')}`" for item in command_refs]
        replacements["__ROOT_COMMAND_REFS__"] = "\n".join(command_lines)
    else:
        removable.add("__ROOT_COMMAND_REFS__")

    return replacements, removable


def backend_replacements(facts: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    identity = facts.get("project_identity", {})
    structure = facts.get("structure", {})
    boundaries = facts.get("boundaries", {})
    config_touchpoints = facts.get("config_touchpoints", {})
    validation = facts.get("validation", {})
    commands = facts.get("commands", {})

    contracts = structure.get("contracts", [])
    services = structure.get("services", [])
    data_access = structure.get("data_access", [])
    sql_script_dirs = sort_paths(structure.get("sql_script_dirs", []))
    command_items = [
        commands.get("build"),
        commands.get("test"),
        commands.get("lint"),
        commands.get("dev"),
        commands.get("codegen"),
    ]
    command_items = [item for item in command_items if item]
    key_configs = sort_paths(config_touchpoints.get("files", []))
    key_config_text = "、".join(str(item.get("name", "")) for item in key_configs if item.get("name"))
    sql_tooling = str(boundaries.get("sql_tooling", "")).strip()
    sql_dir_text = first_value(
        [str(item.get("path", "")) for item in sql_script_dirs if item.get("path")],
        "未在本地浅层扫描中确认现有 SQL 脚本目录；默认优先使用 db/migrations，其次考虑 database/migrations 或 sql/migrations。",
    )

    replacements = {
        "[后端项目名]": str(identity.get("project_name", identity.get("path", "后端项目"))),
        "[后端目录]": str(identity.get("path", "backend")),
        "[入口项目]": str(structure.get("entry_project", "未在本地浅层扫描中确认入口项目")),
        "[业务契约项目]": first_value(
            [str(item) for item in contracts if item],
            "未在本地浅层扫描中确认业务契约项目",
        ),
        "[业务服务项目]": first_value(
            [str(item) for item in services if item],
            "未在本地浅层扫描中确认业务服务项目",
        ),
        "[数据访问项目]": first_value(
            [str(item) for item in data_access if item],
            "未在本地浅层扫描中确认数据访问项目",
        ),
        "[解决方案文件]": str(structure.get("solution_file", "未在本地浅层扫描中确认解决方案文件")),
        "[后端分层描述]": str(
            boundaries.get("layering_description", "按现有项目分层与模块边界组织")
        ),
        "[后端模块示例]": str(boundaries.get("module_example", "业务模块目录")),
        "[关键配置目录与文件]": key_config_text or "已验证配置文件",
        "[入口项目路径]": str(validation.get("entry_project_path", identity.get("path", "."))),
        "[SQL工具链约束]": (
            f"项目已存在 `{sql_tooling}` 迁移主链路时，优先沿用该链路；仅在仓库已有 SQL 脚本体系或任务明确要求时，才新增裸 `.sql` 文件。"
            if sql_tooling
            else "未在本地浅层扫描中确认现有数据库迁移工具链；默认先复用仓库既有迁移方式，只有在已存在 SQL 脚本体系或任务明确要求时才新增裸 SQL 文件。"
        ),
        "[SQL脚本目录约束]": (
            f"若需新增或更新数据库 SQL 脚本，仅在 `{sql_dir_text}` 或其既有子目录中处理。"
            if "未在本地浅层扫描中确认现有 SQL 脚本目录" not in sql_dir_text
            else sql_dir_text
        ),
        "[SQL命名规范]": "新增 SQL 文件名默认使用 `YYYYMMDD_HHMM_description.sql` 或项目既有版本化命名规则；不得使用 `test.sql`、`temp.sql`、`fix.sql` 这类低语义名称。",
    }
    removable: set[str] = set()

    for index in range(5):
        placeholder = f"[后端命令 {index + 1}]"
        if index < len(command_items):
            replacements[placeholder] = str(command_items[index])
        else:
            removable.add(placeholder)

    add_rich_block_replacements(replacements, facts)
    return replacements, removable


def nestjs_backend_replacements(facts: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    identity = facts.get("project_identity", {})
    structure = facts.get("structure", {})
    boundaries = facts.get("boundaries", {})
    config_touchpoints = facts.get("config_touchpoints", {})
    validation = facts.get("validation", {})
    commands = facts.get("commands", {})
    environment = facts.get("environment", {})

    entry_files = list(structure.get("entry_files", []))
    generated_dirs = list(structure.get("generated_dirs", []))
    config_files = sort_paths(config_touchpoints.get("files", []))
    config_names = "、".join(str(item.get("name", "")) for item in config_files if item.get("name"))
    package_manager = str(environment.get("package_manager", "npm"))
    preferred_command_keys = commands.get("preferred_order", [])
    command_items = [
        package_script_invocation(package_manager, str(key))
        for key in preferred_command_keys
        if commands.get(str(key))
    ]
    format_command_items = [
        package_script_fix_invocation(package_manager, "lint")
        if commands.get("lint")
        else None,
        package_script_invocation(package_manager, "format")
        if commands.get("format")
        else None,
        "eslint . --fix 或针对改动文件的最小化 eslint --fix",
    ]
    format_command_items = [item for item in format_command_items if item]

    replacements = {
        "[NestJS后端项目名]": str(identity.get("project_name", identity.get("path", "nestjs-backend"))),
        "[NestJS后端目录]": str(identity.get("path", "backend")),
        "[NestJS业务目录]": str(structure.get("module_dir", "src/modules")),
        "[NestJS数据库目录]": str(structure.get("database_dir", "src/core/modules/database")),
        "[NestJS Prisma目录]": str(structure.get("prisma_dir", "prisma")),
        "[NestJS脚本目录]": str(structure.get("script_dir", "src/scripts")),
        "[NestJS分层描述]": str(boundaries.get("layering_description", "按 NestJS 分层与模块边界组织")),
        "[NestJS生成目录集合]": str(boundaries.get("generated_dir_text", "生成目录")),
        "[NestJS关键配置集合]": config_names or "已验证配置文件",
        "[NestJS锁文件]": str(environment.get("lockfile", "package-lock.json")),
        "[NestJS包管理器]": str(environment.get("package_manager", "npm")),
        "[NestJS Node 版本要求]": str(environment.get("node_version", "以本地配置文件为准")),
        "[NestJS快速验证命令]": str(validation.get("quick_command", "未在本地浅层扫描中确认快速验证命令")),
        "[NestJS验证命令 1]": str(validation.get("test_command", "未在本地浅层扫描中确认测试命令")),
        "[NestJS验证命令 2]": str(validation.get("e2e_command", "未在本地浅层扫描中确认端到端测试命令")),
        "[NestJS验证命令 3]": str(validation.get("build_command", "未在本地浅层扫描中确认构建命令")),
        "[NestJS验证命令 4]": str(validation.get("prisma_generate_command", "未在本地浅层扫描中确认 Prisma 生成命令")),
        "[NestJS验证命令 5]": str(validation.get("swagger_command", "未在本地浅层扫描中确认 Swagger 导出命令")),
    }
    removable: set[str] = set()

    for index in range(2):
        placeholder = f"[NestJS入口文件 {index + 1}]"
        if index < len(entry_files):
            item = entry_files[index]
            replacements[placeholder] = str(item.get("path", item))
        else:
            removable.add(placeholder)

    for index in range(2):
        placeholder = f"[NestJS生成目录 {index + 1}]"
        if index < len(generated_dirs):
            item = generated_dirs[index]
            replacements[placeholder] = str(item.get("path", item))
        else:
            removable.add(placeholder)

    for index in range(6):
        placeholder = f"[NestJS命令 {index + 1}]"
        if index < len(command_items):
            replacements[placeholder] = str(command_items[index])
        else:
            removable.add(placeholder)

    for index in range(3):
        placeholder = f"[NestJS格式化命令 {index + 1}]"
        if index < len(format_command_items):
            replacements[placeholder] = str(format_command_items[index])
        else:
            removable.add(placeholder)

    add_rich_block_replacements(replacements, facts)
    return replacements, removable


def spring_boot_backend_replacements(facts: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    identity = facts.get("project_identity", {})
    structure = facts.get("structure", {})
    boundaries = facts.get("boundaries", {})
    config_touchpoints = facts.get("config_touchpoints", {})
    validation = facts.get("validation", {})
    commands = facts.get("commands", {})
    environment = facts.get("environment", {})

    common_modules = list(structure.get("common_modules", []))
    service_modules = list(structure.get("service_modules", []))
    data_modules = list(structure.get("data_modules", []))
    service_module_text = first_value([str(item) for item in service_modules if item], "未在本地浅层扫描中确认业务模块")
    data_module_text = first_value([str(item) for item in data_modules if item], "未在本地浅层扫描中确认数据访问模块")
    if data_module_text == service_module_text:
        data_module_text = f"同 {service_module_text} 下 Mapper/Repository/DAO 目录"
    source_dirs = sort_paths(structure.get("source_dirs", []))
    config_files = sort_paths(config_touchpoints.get("files", []))
    config_names = "、".join(str(item.get("name", "")) for item in config_files if item.get("name"))
    command_items = [
        commands.get("build"),
        commands.get("test"),
        commands.get("dev"),
    ]
    command_items = [item for item in command_items if item]
    sql_tooling = str(boundaries.get("sql_tooling", "")).strip()
    sql_dir_text = str(
        boundaries.get(
            "sql_dir_text",
            "未在本地浅层扫描中确认现有 SQL 脚本目录",
        )
    )

    replacements = {
        "[SpringBoot后端项目名]": str(identity.get("project_name", identity.get("path", "spring-boot-backend"))),
        "[SpringBoot后端目录]": str(identity.get("path", ".")),
        "[SpringBoot构建工具]": str(environment.get("build_tool", "未在本地浅层扫描中确认")),
        "[SpringBoot构建文件]": str(structure.get("build_descriptor", "未在本地浅层扫描中确认构建文件")),
        "[SpringBoot入口模块]": str(structure.get("entry_module", "未在本地浅层扫描中确认入口模块")),
        "[SpringBoot公共模块]": first_value([str(item) for item in common_modules if item], "未在本地浅层扫描中确认公共模块"),
        "[SpringBoot业务模块]": service_module_text,
        "[SpringBoot数据模块]": data_module_text,
        "[SpringBoot模块集合]": str(boundaries.get("module_text", "未在本地浅层扫描中确认多模块结构")),
        "[SpringBoot分层描述]": str(boundaries.get("layering_description", "按 Spring Boot 分层与模块边界组织")),
        "[SpringBoot关键配置集合]": config_names or "已验证配置文件",
        "[SpringBoot数据访问主链路]": str(environment.get("data_access", "未在本地浅层扫描中确认数据访问主链路")),
        "[SpringBoot Java版本]": str(environment.get("java_version", "以本地构建配置为准")),
        "[SpringBoot快速验证命令]": str(validation.get("quick_command", "未在本地浅层扫描中确认快速验证命令")),
        "[SpringBoot构建验证命令]": str(validation.get("build_command", "未在本地浅层扫描中确认构建命令")),
        "[SpringBoot测试命令]": str(validation.get("test_command", "未在本地浅层扫描中确认测试命令")),
        "[SpringBoot启动命令]": str(validation.get("run_command", "未在本地浅层扫描中确认启动命令")),
        "[SpringBoot SQL工具链约束]": (
            f"项目已存在 `{sql_tooling}` 迁移主链路时，优先沿用该链路；仅在仓库已有 SQL 脚本体系或任务明确要求时，才新增裸 `.sql` 文件。"
            if sql_tooling
            else "未在本地浅层扫描中确认现有数据库迁移工具链；默认先复用仓库既有迁移方式，只有在已存在 SQL 脚本体系或任务明确要求时才新增裸 SQL 文件。"
        ),
        "[SpringBoot SQL脚本目录约束]": (
            f"若需新增或更新数据库 SQL 脚本，仅在 `{sql_dir_text}` 或其既有子目录中处理。"
            if "未在本地浅层扫描中确认现有 SQL 脚本目录" not in sql_dir_text
            else sql_dir_text
        ),
    }
    removable: set[str] = set()

    for index in range(4):
        placeholder = f"[SpringBoot源码目录 {index + 1}]"
        if index < len(source_dirs):
            item = source_dirs[index]
            replacements[placeholder] = str(item.get("path", item))
        else:
            removable.add(placeholder)

    for index in range(5):
        placeholder = f"[SpringBoot命令 {index + 1}]"
        if index < len(command_items):
            replacements[placeholder] = str(command_items[index])
        else:
            removable.add(placeholder)

    add_rich_block_replacements(replacements, facts)
    return replacements, removable


def frontend_replacements(facts: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    identity = facts.get("project_identity", {})
    structure = facts.get("structure", {})
    boundaries = facts.get("boundaries", {})
    config_touchpoints = facts.get("config_touchpoints", {})
    validation = facts.get("validation", {})
    commands = facts.get("commands", {})
    environment = facts.get("environment", {})

    src_dirs = list(structure.get("source_dirs", []))
    app_dirs = list(structure.get("app_dirs", []))
    feature_dirs = sort_paths(structure.get("feature_dirs", []))
    config_files = sort_paths(config_touchpoints.get("files", []))
    config_names = "、".join(str(item.get("name", "")) for item in config_files if item.get("name"))
    style_tools = environment.get("style_tools", [])
    package_manager = str(environment.get("package_manager", "npm"))
    preferred_command_keys = commands.get("preferred_order", [])
    if isinstance(preferred_command_keys, list) and preferred_command_keys:
        command_items = [
            package_script_invocation(package_manager, str(key))
            for key in preferred_command_keys
            if commands.get(str(key))
        ]
    else:
        command_items = [
            package_script_invocation(package_manager, "dev") if commands.get("dev") else None,
            package_script_invocation(package_manager, "build") if commands.get("build") else None,
            package_script_invocation(package_manager, "test") if commands.get("test") else None,
            package_script_invocation(package_manager, "lint") if commands.get("lint") else None,
        ]
    command_items = [item for item in command_items if item]

    replacements = {
        "[前端项目名]": str(identity.get("project_name", identity.get("path", "前端项目"))),
        "[前端目录]": str(identity.get("path", "web")),
        "[前端构建工具]": str(environment.get("build_tool", "未在本地浅层扫描中确认")),
        "[测试工具]": str(environment.get("test_tool", "未在本地浅层扫描中确认")),
        "[路由目录]": str(boundaries.get("route_dir", "src/router")),
        "[状态目录]": str(boundaries.get("state_dir", "未在本地浅层扫描中确认状态目录")),
        "[页面目录集合]": "、".join(str(item.get("path", "")) for item in feature_dirs if item.get("path")) or "未在本地浅层扫描中确认页面目录",
        "[共享目录集合]": str(boundaries.get("shared_dirs_text", "共享目录")),
        "[接口目录]": str(boundaries.get("api_dir", "src/api")),
        "[关键前端配置文件集合]": config_names or "已验证前端配置文件",
        "[样式与质量工具]": "、".join(style_tools) if style_tools else "项目本地样式与质量工具",
        "[样式主题目录]": str(boundaries.get("theme_dir", "src/styles")),
        "[类型目录]": str(boundaries.get("type_dir", "src/types")),
        "[锁文件]": str(environment.get("lockfile", "lock file")),
        "[包管理器]": str(environment.get("package_manager", "npm")),
        "[Node 版本要求]": str(environment.get("node_version", "以本地配置文件为准")),
        "[快速验证命令]": str(validation.get("quick_command", "未在本地浅层扫描中确认快速验证命令")),
        "[最小构建命令]": str(validation.get("minimal_build_command", "未在本地浅层扫描中确认最小构建命令")),
        "[单元测试命令]": str(validation.get("unit_test_command", "未在本地浅层扫描中确认单元测试命令")),
        "[端到端测试命令]": str(validation.get("e2e_test_command", "未在本地浅层扫描中确认端到端测试命令")),
    }
    removable: set[str] = set()

    for index in range(3):
        placeholder = f"[src 子目录 {index + 1}]"
        if index < len(src_dirs):
            item = src_dirs[index]
            replacements[placeholder] = str(item.get("path", item))
        else:
            removable.add(placeholder)

    for index in range(3):
        placeholder = f"[app 子目录 {index + 1}]"
        if index < len(app_dirs):
            item = app_dirs[index]
            replacements[placeholder] = str(item.get("path", item))
        else:
            removable.add(placeholder)

    for index in range(8):
        placeholder = f"[前端命令 {index + 1}]"
        if index < len(command_items):
            replacements[placeholder] = str(command_items[index])
        else:
            removable.add(placeholder)

    add_rich_block_replacements(replacements, facts)
    return replacements, removable


def userscripts_replacements(facts: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    identity = facts.get("project_identity", {})
    structure = facts.get("structure", {})
    config_touchpoints = facts.get("config_touchpoints", {})
    validation = facts.get("validation", {})
    commands = facts.get("commands", {})
    environment = facts.get("environment", {})

    source_dirs = list(structure.get("source_dirs", []))
    page_dirs = list(structure.get("page_dirs", []))
    config_files = sort_paths(config_touchpoints.get("files", []))
    config_names = "、".join(str(item.get("name", "")) for item in config_files if item.get("name"))
    style_tools = environment.get("style_tools", [])
    package_manager = str(environment.get("package_manager", "npm"))
    preferred_command_keys = commands.get("preferred_order", [])
    command_items = [
        package_script_invocation(package_manager, str(key))
        for key in preferred_command_keys
        if commands.get(str(key))
    ]

    replacements = {
        "[用户脚本项目名]": str(identity.get("project_name", identity.get("path", "userscripts"))),
        "[用户脚本目录]": str(identity.get("path", "apps/userscripts")),
        "[用户脚本页面目录]": str(structure.get("page_dir", "src/pages")),
        "[用户脚本服务目录]": str(structure.get("service_dir", "src/services")),
        "[用户脚本样式目录]": str(structure.get("style_dir", "src/styles")),
        "[用户脚本类型目录]": str(structure.get("type_dir", "src/types")),
        "[用户脚本工具目录]": str(structure.get("utils_dir", "src/utils")),
        "[用户脚本共享页面目录]": str(structure.get("shared_page_dir", "src/pages/shared")),
        "[用户脚本入口文件]": str(structure.get("entry_file", "src/entry.js")),
        "[用户脚本构建工具]": str(environment.get("build_tool", "未在本地浅层扫描中确认")),
        "[用户脚本测试工具]": str(environment.get("test_tool", "未在本地浅层扫描中确认")),
        "[用户脚本关键配置集合]": config_names or "已验证用户脚本配置文件",
        "[用户脚本样式与质量工具]": "、".join(style_tools) if style_tools else "项目本地样式与质量工具",
        "[用户脚本锁文件]": str(environment.get("lockfile", "lock file")),
        "[用户脚本包管理器]": str(environment.get("package_manager", "npm")),
        "[用户脚本 Node 版本要求]": str(environment.get("node_version", "以本地配置文件为准")),
        "[用户脚本快速验证命令]": str(validation.get("quick_command", "未在本地浅层扫描中确认快速验证命令")),
        "[用户脚本最小构建命令]": str(validation.get("minimal_build_command", "未在本地浅层扫描中确认最小构建命令")),
        "[用户脚本单元测试命令]": str(validation.get("unit_test_command", "未在本地浅层扫描中确认单元测试命令")),
        "[用户脚本端到端测试命令]": str(validation.get("e2e_test_command", "未在本地浅层扫描中确认端到端测试命令")),
    }
    removable: set[str] = set()

    for index in range(5):
        placeholder = f"[userscripts src 子目录 {index + 1}]"
        if index < len(source_dirs):
            item = source_dirs[index]
            replacements[placeholder] = str(item.get("path", item))
        else:
            removable.add(placeholder)

    for index in range(3):
        placeholder = f"[userscripts 页面子目录 {index + 1}]"
        if index < len(page_dirs):
            item = page_dirs[index]
            replacements[placeholder] = str(item.get("path", item))
        else:
            removable.add(placeholder)

    for index in range(4):
        placeholder = f"[用户脚本命令 {index + 1}]"
        if index < len(command_items):
            replacements[placeholder] = str(command_items[index])
        else:
            removable.add(placeholder)

    add_rich_block_replacements(replacements, facts)
    return replacements, removable


def claude_replacements(
    facts: dict[str, Any],
    output_path: Path | None = None,
) -> tuple[dict[str, str], set[str]]:
    root = Path(str(facts.get("repository_root", "."))).resolve()
    root_rule_path = Path("AGENTS.md")
    if output_path and output_path.is_absolute():
        root_rule = relative_include_path(output_path, root / root_rule_path)
    else:
        root_rule = str(root_rule_path).replace("\\", "/")

    paths = sort_paths(
        [
            item["path"] if isinstance(item, dict) else item
            for item in facts.get("child_agents_paths", [])
        ]
    )
    replacements: dict[str, str] = {
        "[根规则路径]": root_rule,
    }
    removable: set[str] = set()
    for index in range(3):
        placeholder = f"[子目录AGENTS路径{index + 1}]"
        if index < len(paths):
            child_path = Path(str(paths[index]))
            if output_path and output_path.is_absolute():
                replacements[placeholder] = relative_include_path(output_path, root / child_path)
            else:
                replacements[placeholder] = str(child_path).replace("\\", "/")
        else:
            removable.add(placeholder)
    return replacements, removable


def replace_line_placeholders(text: str, replacements: dict[str, str], removable: set[str]) -> str:
    rendered = text
    for placeholder, value in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        rendered = rendered.replace(placeholder, value)

    lines: list[str] = []
    for line in rendered.splitlines():
        if any(placeholder in line for placeholder in removable):
            continue
        if line.strip() == "__ROOT_ENV_EXTRA__":
            continue
        if line.strip() == "__ROOT_COMMAND_REFS__":
            continue
        if not line.strip() and lines and not lines[-1].strip():
            continue
        lines.append(line)
    rendered = "\n".join(lines).strip() + "\n"
    rendered = rendered.replace("__ROOT_ENV_EXTRA__", replacements.get("__ROOT_ENV_EXTRA__", ""))
    rendered = rendered.replace("__ROOT_COMMAND_REFS__", replacements.get("__ROOT_COMMAND_REFS__", ""))
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    rendered = remove_empty_rich_sections(rendered)
    unresolved = sorted(
        {
            match
            for match in re.findall(r"\[[^\]]+\]", rendered)
            if match not in {"[DEFAULT]", "[MUST]", "[MUST NOT]", "[STOP]"}
        }
    )
    if unresolved:
        raise ValueError(f"Template still contains unresolved placeholders: {', '.join(unresolved)}")
    return rendered


def apply_single_project_intro(rendered: str, facts: dict[str, Any]) -> str:
    if not facts.get("render_options", {}).get("single_project"):
        return rendered
    return re.sub(
        r"本文件作用于 `[^`]+` 及其子目录。未特别说明的事项，继承仓库根目录 `AGENTS\.md`。",
        "本文件作用于仓库根目录及其子目录。当前仓库本身就是主要项目，不再拆分 root/child 规则层。",
        rendered,
        count=1,
    )


def render(template_type: str, facts: dict[str, Any], output_path: Path | None = None) -> str:
    template_path = TEMPLATE_MAP[template_type]
    template_text = template_path.read_text(encoding="utf-8")
    if template_type == "root":
        replacements, removable = root_replacements(facts)
    elif template_type in {"dotnet-backend-child", "backend-child"}:
        replacements, removable = backend_replacements(facts)
    elif template_type == "nestjs-backend-child":
        replacements, removable = nestjs_backend_replacements(facts)
    elif template_type == "spring-boot-backend-child":
        replacements, removable = spring_boot_backend_replacements(facts)
    elif template_type == "userscripts-child":
        replacements, removable = userscripts_replacements(facts)
    elif template_type == "frontend-child":
        replacements, removable = frontend_replacements(facts)
    else:
        replacements, removable = claude_replacements(facts, output_path=output_path)
    rendered = replace_line_placeholders(template_text, replacements, removable)
    return apply_single_project_intro(rendered, facts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render AGENTS.md or CLAUDE.md from normalized facts JSON."
    )
    parser.add_argument(
        "--template",
        required=True,
        choices=sorted(TEMPLATE_MAP.keys()),
        help="Template type to render.",
    )
    parser.add_argument("--facts", required=True, help="Path to normalized facts JSON.")
    parser.add_argument("--output", required=True, help="Output markdown path.")
    args = parser.parse_args()

    facts = load_json(Path(args.facts))
    rendered = render(args.template, facts, output_path=Path(args.output))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
