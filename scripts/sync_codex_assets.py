from __future__ import annotations

import copy
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, NamedTuple

import tomllib

import build_operate_database_profiles_plugin as plugin_builder


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
CONFIG_PLATFORMS = {"macos", "windows"}
BARE_TOML_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
MCP_SECRET_PLACEHOLDERS = (
    "***redacted***",
    "changeme",
    "replace-me",
    "replace_me",
)


class DriftItem(NamedTuple):
    label: str
    target_exists: bool


class ManagedPlugin(NamedTuple):
    name: str
    marketplace: str
    source_dir: Path


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def default_config_platform(
    os_name: str | None = None,
    sys_platform_name: str | None = None,
) -> str:
    effective_os_name = os.name if os_name is None else os_name
    effective_sys_platform = (
        sys.platform if sys_platform_name is None else sys_platform_name
    )
    if effective_os_name == "nt" or effective_sys_platform.startswith("win"):
        return "windows"
    if effective_os_name == "posix" and effective_sys_platform == "darwin":
        return "macos"
    raise ValueError(
        "Unsupported operating system for Codex configuration: "
        f"os.name={effective_os_name}, sys.platform={effective_sys_platform}"
    )


def default_codex_config_target(codex_home: Path) -> Path:
    return (codex_home / "config.toml").resolve()


def default_mcp_secret_source(
    project_root: Path = PROJECT_ROOT,
) -> Path:
    return project_root / ".codex" / "mcp-secrets.toml"


def default_local_config_source(
    project_root: Path = PROJECT_ROOT,
) -> Path:
    return project_root / ".codex" / "config.local.toml"


def config_source_paths(
    platform_name: str,
    project_root: Path = PROJECT_ROOT,
) -> tuple[Path, Path, Path]:
    if platform_name not in CONFIG_PLATFORMS:
        raise ValueError(f"Unsupported config platform: {platform_name}")
    references_dir = project_root / "references"
    return (
        references_dir / "codex-config-base.toml",
        references_dir / "codex-mcp-servers.common.toml",
        references_dir / f"codex-mcp-servers.{platform_name}.toml",
    )


def default_personal_marketplace() -> Path:
    return (Path.home() / ".agents" / "plugins" / "marketplace.json").resolve()


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return payload


def discover_managed_plugin(
    marketplace_path: Path,
    plugin_name: str = plugin_builder.SKILL_NAME,
) -> ManagedPlugin | None:
    marketplace_path = marketplace_path.expanduser().resolve()
    if not marketplace_path.is_file():
        return None

    marketplace = read_json_object(marketplace_path, "Personal marketplace")
    marketplace_name = marketplace.get("name")
    if not isinstance(marketplace_name, str) or not marketplace_name:
        raise ValueError(
            f"Personal marketplace name is missing or invalid: {marketplace_path}"
        )
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        raise ValueError(
            f"Personal marketplace plugins must be a list: {marketplace_path}"
        )

    matching_entries = [
        entry
        for entry in plugins
        if isinstance(entry, dict) and entry.get("name") == plugin_name
    ]
    if not matching_entries:
        return None
    if len(matching_entries) != 1:
        raise ValueError(
            f"Personal marketplace contains duplicate plugin entries: {plugin_name}"
        )

    source = matching_entries[0].get("source")
    if not isinstance(source, dict) or source.get("source") != "local":
        raise ValueError(
            f"Managed plugin must use a local marketplace source: {plugin_name}"
        )
    source_path = source.get("path")
    if not isinstance(source_path, str) or not source_path:
        raise ValueError(f"Managed plugin source path is missing: {plugin_name}")

    if len(marketplace_path.parents) < 3:
        raise ValueError(
            f"Cannot resolve marketplace root for managed plugin: {marketplace_path}"
        )
    marketplace_root = marketplace_path.parents[2].resolve()
    plugin_source = Path(source_path).expanduser()
    if not plugin_source.is_absolute():
        plugin_source = marketplace_root / plugin_source
    plugin_source = plugin_source.resolve()
    if not plugin_source.is_relative_to(marketplace_root):
        raise ValueError(
            "Managed plugin source must stay inside the marketplace root: "
            f"{plugin_source}"
        )
    if plugin_source.name != plugin_name:
        raise ValueError(
            "Managed plugin source directory must match the plugin name: "
            f"{plugin_source}"
        )

    return ManagedPlugin(plugin_name, marketplace_name, plugin_source)


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


def plugin_manifest_path(plugin_dir: Path) -> Path:
    return plugin_dir / ".codex-plugin" / "plugin.json"


def set_plugin_version(plugin_dir: Path, version: str) -> None:
    manifest_path = plugin_manifest_path(plugin_dir)
    manifest = read_json_object(manifest_path, "Plugin manifest")
    manifest["version"] = version
    plugin_builder.write_json(manifest_path, manifest)


def plugin_version(plugin_dir: Path) -> str:
    manifest_path = plugin_manifest_path(plugin_dir)
    manifest = read_json_object(manifest_path, "Plugin manifest")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"Plugin version is missing or invalid: {manifest_path}")
    return version


def next_plugin_version(
    current_version: str,
    now: datetime | None = None,
) -> str:
    base_version = current_version.split("+", 1)[0]
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    candidate = (
        f"{base_version}+codex.local-{timestamp.strftime('%Y%m%d-%H%M%S')}"
    )
    if candidate == current_version:
        timestamp += timedelta(seconds=1)
        candidate = (
            f"{base_version}+codex.local-{timestamp.strftime('%Y%m%d-%H%M%S')}"
        )
    return candidate


def find_managed_plugin_drift(plugin: ManagedPlugin) -> list[DriftItem]:
    with tempfile.TemporaryDirectory() as temporary_directory:
        candidate = Path(temporary_directory) / plugin.name
        plugin_builder.build_plugin(candidate)
        target_manifest = plugin_manifest_path(plugin.source_dir)
        if target_manifest.is_file():
            candidate_version = plugin_version(candidate)
            target_version = plugin_version(plugin.source_dir)
            if candidate_version.split("+", 1)[0] == target_version.split("+", 1)[0]:
                set_plugin_version(candidate, target_version)
        return compare_tree(
            candidate,
            plugin.source_dir,
            f"plugin/{plugin.name}@{plugin.marketplace}",
        )


def find_codex_cli() -> str:
    executable = shutil.which("codex")
    if executable is None:
        raise ValueError(
            "Codex CLI is required to reinstall managed plugins but was not found"
        )
    return executable


def sync_managed_plugin(
    plugin: ManagedPlugin,
    *,
    codex_executable: str,
    now: datetime | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    print(f"plugin_source_dir: {plugin.source_dir}")
    print(f"plugin_marketplace: {plugin.marketplace}")

    previous_version = (
        plugin_version(plugin.source_dir)
        if plugin_manifest_path(plugin.source_dir).is_file()
        else None
    )
    if plugin.source_dir.exists() and not plugin.source_dir.is_dir():
        raise ValueError(
            f"Managed plugin source is not a directory: {plugin.source_dir}"
        )
    with tempfile.TemporaryDirectory() as temporary_directory:
        candidate = Path(temporary_directory) / plugin.name
        plugin_builder.build_plugin(candidate)
        version = next_plugin_version(plugin_version(candidate), now)
        if previous_version is not None and version == previous_version:
            version = next_plugin_version(previous_version, now)
        set_plugin_version(candidate, version)
        if plugin.source_dir.exists():
            remove_tree(plugin.source_dir)
            print(f"[removed] {plugin.source_dir}")
        shutil.copytree(candidate, plugin.source_dir)
    print(f"[built] {plugin.name} {version} -> {plugin.source_dir}")

    selector = f"{plugin.name}@{plugin.marketplace}"
    try:
        result = command_runner(
            [codex_executable, "plugin", "add", selector, "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(
            f"Codex plugin reinstall could not run for {selector}: {error}"
        ) from error
    output = (result.stdout or "").strip()
    error_output = (result.stderr or "").strip()
    if output:
        print(output)
    if result.returncode != 0:
        details = error_output or output or "no command output"
        raise ValueError(
            f"Codex plugin reinstall failed for {selector}: {details}"
        )
    print(f"[installed] {selector} {version}")
    return 1


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


def load_toml_object(source: Path, label: str) -> dict[str, Any]:
    source = ensure_file(source, label)
    try:
        parsed = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"{label} is not valid TOML: {source}: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must contain a TOML document: {source}")
    return parsed


def require_private_posix_file(
    source: Path,
    label: str,
    os_name: str | None = None,
) -> None:
    effective_os_name = os.name if os_name is None else os_name
    if effective_os_name != "posix":
        return
    mode = stat.S_IMODE(source.stat().st_mode)
    if mode & 0o077:
        raise ValueError(
            f"{label} permissions are too broad: {source}. "
            "Set mode 0600 before syncing."
        )


def secret_value_is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or any(
        placeholder in normalized for placeholder in MCP_SECRET_PLACEHOLDERS
    )


def validate_mcp_secret_fragment(
    source: Path,
    configured_server_names: set[str],
    os_name: str | None = None,
) -> dict[str, Any]:
    source = ensure_file(source, "Local MCP secret fragment")
    require_private_posix_file(
        source,
        "Local MCP secret fragment",
        os_name=os_name,
    )
    parsed = load_toml_object(source, "Local MCP secret fragment")
    if set(parsed) != {"mcp_servers"}:
        raise ValueError(
            "Local MCP secret fragment may contain only the mcp_servers table"
        )
    servers = parsed.get("mcp_servers")
    if not isinstance(servers, dict) or not servers:
        raise ValueError("Local MCP secret fragment has no MCP secret tables")
    for server_name, server_config in servers.items():
        if server_name not in configured_server_names:
            raise ValueError(
                "Local MCP secret fragment references an unconfigured MCP server: "
                f"{server_name}"
            )
        if not isinstance(server_config, dict) or not server_config:
            raise ValueError("Local MCP secret fragment has no MCP secret tables")
        unexpected_fields = set(server_config) - {"env", "http_headers"}
        if unexpected_fields:
            names = ", ".join(sorted(unexpected_fields))
            raise ValueError(
                f"MCP secret table {server_name} contains forbidden fields: {names}"
            )
        for field_name, values in server_config.items():
            if not isinstance(values, dict) or not values:
                raise ValueError(
                    f"MCP secret table {server_name}.{field_name} must be non-empty"
                )
            for key, value in values.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ValueError(
                        f"MCP secret value {server_name}.{field_name} must be a string"
                    )
                if secret_value_is_placeholder(value):
                    raise ValueError(
                        "MCP secret value is empty or still uses a placeholder: "
                        f"{server_name}.{field_name}.{key}"
                    )
    return parsed


def deep_merge_config(
    destination: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    for key, value in overlay.items():
        existing = destination.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            deep_merge_config(existing, value)
        else:
            destination[key] = copy.deepcopy(value)
    return destination


def toml_key(key: str) -> str:
    if BARE_TOML_KEY_PATTERN.fullmatch(key):
        return key
    return json.dumps(key, ensure_ascii=False)


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        entries = ", ".join(
            f"{toml_key(str(key))} = {toml_value(child)}"
            for key, child in value.items()
        )
        return "{ " + entries + " }"
    raise ValueError(f"Unsupported TOML value type: {type(value).__name__}")


def append_toml_table(
    lines: list[str],
    path: tuple[str, ...],
    table: dict[str, Any],
) -> None:
    if lines and lines[-1] != "":
        lines.append("")
    lines.append("[" + ".".join(toml_key(part) for part in path) + "]")
    for key, value in table.items():
        if not isinstance(value, dict):
            lines.append(f"{toml_key(str(key))} = {toml_value(value)}")
    for key, value in table.items():
        if isinstance(value, dict):
            append_toml_table(lines, path + (str(key),), value)


def serialize_toml_document(config: dict[str, Any]) -> str:
    lines = [
        "# Generated by sync_codex_assets. Edit the repository source fragments,",
        "# .codex/mcp-secrets.toml, or .codex/config.local.toml instead.",
        "",
    ]
    for key, value in config.items():
        if not isinstance(value, dict):
            lines.append(f"{toml_key(str(key))} = {toml_value(value)}")
    for key, value in config.items():
        if isinstance(value, dict):
            append_toml_table(lines, (str(key),), value)
    rendered = "\n".join(lines).rstrip() + "\n"
    try:
        reparsed = tomllib.loads(rendered)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"Rendered Codex config is not valid TOML: {error}") from error
    if reparsed != config:
        raise ValueError("Rendered Codex config does not round-trip to the merged values")
    return rendered


def render_codex_config(
    source_files: Iterable[Path],
    secret_source: Path,
    local_source: Path | None = None,
    managed_plugin: ManagedPlugin | None = None,
    os_name: str | None = None,
) -> bytes:
    merged: dict[str, Any] = {}
    configured_server_names: set[str] = set()
    for source_file in source_files:
        fragment = load_toml_object(source_file, "Codex config source fragment")
        servers = fragment.get("mcp_servers", {})
        if not isinstance(servers, dict):
            raise ValueError(f"mcp_servers must be a table: {source_file}")
        configured_server_names.update(str(name) for name in servers)
        deep_merge_config(merged, fragment)
    if not configured_server_names:
        raise ValueError("Codex config source fragments declare no MCP servers")

    local_overlay: dict[str, Any] | None = None
    if local_source is not None and local_source.is_file():
        require_private_posix_file(
            local_source,
            "Local Codex config overlay",
            os_name=os_name,
        )
        local_overlay = load_toml_object(
            local_source,
            "Local Codex config overlay",
        )
        local_servers = local_overlay.get("mcp_servers", {})
        if not isinstance(local_servers, dict):
            raise ValueError(f"mcp_servers must be a table: {local_source}")
        configured_server_names.update(str(name) for name in local_servers)

    deep_merge_config(
        merged,
        validate_mcp_secret_fragment(
            secret_source, configured_server_names, os_name=os_name
        )
    )
    if managed_plugin is not None:
        deep_merge_config(
            merged,
            {
                "plugins": {
                    f"{managed_plugin.name}@{managed_plugin.marketplace}": {
                        "enabled": True,
                    }
                }
            },
        )
    if local_overlay is not None:
        deep_merge_config(merged, local_overlay)
    return serialize_toml_document(merged).encode("utf-8")


def compare_global_rule(source: Path, target: Path, label: str) -> list[DriftItem]:
    if not target.is_file():
        return [DriftItem(f"{label}: missing target", target.exists())]
    if normalized_global_content(source) != target.read_bytes():
        return [DriftItem(f"{label}: content differs", True)]
    return []


def compare_codex_config(
    expected_content: bytes,
    target: Path,
) -> list[DriftItem]:
    if not target.is_file():
        return [
            DriftItem(
                "config/config.toml: missing target",
                target.exists(),
            )
        ]
    if expected_content != target.read_bytes():
        return [DriftItem("config/config.toml: content differs", True)]
    return []


def find_managed_drift(
    *,
    codex_config_content: bytes,
    codex_config_target: Path,
    global_source: Path,
    global_targets: Iterable[Path],
    references_source_dir: Path,
    references_target_dir: Path,
    subagents_source_dir: Path,
    subagents_target_dir: Path,
    skills_source_dir: Path,
    skills_target_dir: Path,
) -> list[DriftItem]:
    drift = compare_codex_config(codex_config_content, codex_config_target)
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


def sync_codex_config(
    content: bytes,
    target_file: Path,
) -> int:
    print(f"codex_config_target: {target_file}")
    temporary_path: Path | None = None
    try:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, raw_temporary_path = tempfile.mkstemp(
            prefix=f".{target_file.name}.",
            dir=target_file.parent,
        )
        temporary_path = Path(raw_temporary_path)
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(content)
        os.chmod(temporary_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary_path, target_file)
        temporary_path = None
        if os.name == "posix":
            os.chmod(target_file, stat.S_IRUSR | stat.S_IWUSR)
    except PermissionError as error:
        raise ValueError(
            f"Codex user config target is not writable: {target_file}."
        ) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    print(f"[copied] Codex user config -> {target_file}")
    return 1


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

    config_platform = default_config_platform()
    config_sources = tuple(
        ensure_file(path, "Codex config source fragment")
        for path in config_source_paths(config_platform)
    )
    mcp_secret_source = default_mcp_secret_source().resolve()
    if not mcp_secret_source.is_file():
        raise ValueError(
            "Local MCP secret fragment does not exist: "
            f"{mcp_secret_source}. Copy "
            "references/codex-mcp-secrets.example.toml to "
            ".codex/mcp-secrets.toml, replace every placeholder, and set mode 0600."
        )
    local_config_source = default_local_config_source().resolve()
    personal_marketplace = default_personal_marketplace()
    managed_plugin = discover_managed_plugin(personal_marketplace)
    codex_config_content = render_codex_config(
        config_sources,
        mcp_secret_source,
        local_source=local_config_source,
        managed_plugin=managed_plugin,
    )
    codex_config_target = default_codex_config_target(codex_home)
    print(f"codex_config_platform: {config_platform}")
    for config_source in config_sources:
        print(f"codex_config_source: {config_source}")
    print(f"mcp_secret_source: {mcp_secret_source}")
    if local_config_source.is_file():
        print(f"local_config_source: {local_config_source}")
    else:
        print(f"[skipped] optional local config overlay: {local_config_source}")
        if codex_config_target.is_file():
            print(
                "[warning] Existing user-only settings are not imported automatically. "
                "Move settings that must survive replacement into the optional local "
                "config overlay before syncing."
            )
    print(f"codex_config_target: {codex_config_target}")
    global_source = ensure_file(PROJECT_ROOT / "references" / "global-template.md", "Global source file")
    global_target = (codex_home / "AGENTS.md").resolve()
    gemini_global_target = (Path.home() / ".gemini" / "GEMINI.md").resolve()
    references_source_dir = ensure_dir(PROJECT_ROOT / "references", "References source directory")
    references_target_dir = (codex_home / "references").resolve()
    subagents_source_dir = ensure_dir(PROJECT_ROOT / "subagents-main", "Subagents source directory")
    subagents_target_dir = (codex_home / "agents").resolve()
    skills_source_dir = ensure_dir(PROJECT_ROOT / "skills", "Skills source directory")
    skills_target_dir = (codex_home / "skills").resolve()
    if managed_plugin is None:
        print(
            "[skipped] managed plugin is not configured in the personal marketplace: "
            f"{plugin_builder.SKILL_NAME}"
        )
    else:
        print(
            "managed_plugin: "
            f"{managed_plugin.name}@{managed_plugin.marketplace} "
            f"-> {managed_plugin.source_dir}"
        )

    drift_arguments = {
        "codex_config_content": codex_config_content,
        "codex_config_target": codex_config_target,
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
    if managed_plugin is not None:
        drift.extend(find_managed_plugin_drift(managed_plugin))
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

    codex_executable = find_codex_cli() if managed_plugin is not None else None
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
        "plugins": (
            sync_managed_plugin(
                managed_plugin,
                codex_executable=codex_executable,
            )
            if managed_plugin is not None and codex_executable is not None
            else 0
        ),
        "codex_config": sync_codex_config(
            codex_config_content,
            codex_config_target,
        ),
    }

    remaining_drift = find_managed_drift(**drift_arguments)
    if managed_plugin is not None:
        remaining_drift.extend(find_managed_plugin_drift(managed_plugin))
    if remaining_drift:
        labels = "\n".join(f"- {item.label}" for item in remaining_drift[:20])
        raise ValueError(
            "post-sync verification failed; managed assets still differ:\n"
            f"{labels}"
        )
    for label, count in synced.items():
        print(f"synced_{label}: {count}")
    print("[OK] Sync completed.")
    print("[ACTION] Restart Codex to load the refreshed user configuration.")
    if managed_plugin is not None:
        print(
            "[ACTION] Start a new Codex task to load the refreshed plugin MCP process."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1) from None
