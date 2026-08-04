from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_operate_database_profiles_plugin as plugin_builder  # noqa: E402
import sync_codex_assets as sync_module  # noqa: E402
from sync_codex_assets import (  # noqa: E402
    ManagedPlugin,
    compare_codex_config,
    compare_tree,
    config_source_paths,
    default_codex_config_target,
    default_config_platform,
    discover_managed_plugin,
    find_managed_plugin_drift,
    ignored_runtime_path,
    next_plugin_version,
    parse_mode,
    render_codex_config,
    set_plugin_version,
    sync_codex_config,
    sync_managed_plugin,
    validate_mcp_secret_fragment,
)


class SyncCodexAssetsTests(unittest.TestCase):
    def write_mcp_secret_fragment(
        self,
        root: Path,
        content: str = (
            "[mcp_servers.context7.env]\n"
            'CONTEXT7_API_KEY = "test-only-secret-value"\n'
        ),
    ) -> Path:
        source = root / ".codex" / "mcp-secrets.toml"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(content, encoding="utf-8")
        source.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return source

    def test_codex_config_baseline_is_valid_and_machine_neutral(
        self,
    ) -> None:
        source = SCRIPTS.parent / "references" / "codex-config-base.toml"
        config = tomllib.loads(source.read_text(encoding="utf-8"))

        forbidden_sections = {
            "desktop",
            "marketplaces",
            "mcp_servers",
            "notice",
            "notify",
            "plugins",
            "projects",
            "shell_environment_policy",
            "tui",
        }
        self.assertTrue(forbidden_sections.isdisjoint(config))
        self.assertEqual(
            config["sandbox_workspace_write"],
            {
                "network_access": True,
                "exclude_slash_tmp": False,
            },
        )
        self.assertTrue(config["disable_response_storage"])
        self.assertTrue(config["hide_rate_limit_model_nudge"])
        self.assertEqual(config["startup_timeout_sec"], 60)
        self.assertEqual(config["tool_timeout_sec"], 60)
        self.assertTrue(config["features"]["background_terminal"])
        self.assertFalse(config["features"]["js_repl"])
        self.assertTrue(config["features"]["unified_exec"])

        def strings(value):
            if isinstance(value, dict):
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strings(child)
            elif isinstance(value, str):
                yield value

        for value in strings(config):
            self.assertFalse(value.startswith(("/", "~/")))
            self.assertFalse(len(value) >= 3 and value[1:3] in {":/", ":\\"})

    def test_codex_config_platform_and_target_use_user_location(
        self,
    ) -> None:
        codex_home = Path("C:/Users/example/.codex")

        self.assertEqual(
            default_config_platform(
                os_name="nt",
                sys_platform_name="win32",
            ),
            "windows",
        )
        self.assertEqual(
            default_config_platform(
                os_name="posix",
                sys_platform_name="darwin",
            ),
            "macos",
        )
        self.assertEqual(
            default_codex_config_target(codex_home),
            (codex_home / "config.toml").resolve(),
        )
        with self.assertRaisesRegex(ValueError, "Unsupported operating system"):
            default_config_platform(
                os_name="posix",
                sys_platform_name="linux",
            )

    def test_rendered_codex_configs_share_the_same_mcp_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            secret_source = self.write_mcp_secret_fragment(
                Path(temporary_directory)
            )
            rendered = {
                platform_name: tomllib.loads(
                    render_codex_config(
                        config_source_paths(platform_name),
                        secret_source,
                        os_name="posix",
                    ).decode("utf-8")
                )
                for platform_name in ("macos", "windows")
            }

        expected_servers = {
            "cloudflare-api",
            "cloudflare-docs",
            "code-index",
            "context7",
            "deepwiki",
            "github",
            "openaiDeveloperDocs",
            "playwright",
            "serena",
        }
        self.assertEqual(set(rendered["macos"]["mcp_servers"]), expected_servers)
        self.assertEqual(set(rendered["windows"]["mcp_servers"]), expected_servers)
        self.assertNotIn("node_repl", expected_servers)
        self.assertNotIn("computer-use", expected_servers)

        for server_name in sorted(expected_servers):
            macos_config = dict(rendered["macos"]["mcp_servers"][server_name])
            windows_config = dict(rendered["windows"]["mcp_servers"][server_name])
            for platform_field in ("command", "args", "cwd"):
                macos_config.pop(platform_field, None)
                windows_config.pop(platform_field, None)
            self.assertEqual(
                macos_config,
                windows_config,
                msg=f"shared MCP contract differs for {server_name}",
            )

    def test_local_config_overlay_applies_last_and_preserves_nested_values(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            secret_source = self.write_mcp_secret_fragment(
                root,
                content=(
                    "[mcp_servers.context7.env]\n"
                    'CONTEXT7_API_KEY = "test-only-secret-value"\n'
                    "\n"
                    "[mcp_servers.machine-local.env]\n"
                    'MACHINE_LOCAL_TOKEN = "test-only-local-secret"\n'
                ),
            )
            local_source = root / ".codex" / "config.local.toml"
            local_source.write_text(
                'model = "machine-local-model"\n'
                "\n"
                "[mcp_servers.context7]\n"
                "enabled = false\n"
                "\n"
                "[mcp_servers.machine-local]\n"
                'command = "/machine/local/tool"\n'
                'args = ["serve"]\n'
                "enabled = true\n",
                encoding="utf-8",
            )
            local_source.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "permissions are too broad"):
                render_codex_config(
                    config_source_paths("macos"),
                    secret_source,
                    local_source=local_source,
                    os_name="posix",
                )
            local_source.chmod(0o600)

            rendered = tomllib.loads(
                render_codex_config(
                    config_source_paths("macos"),
                    secret_source,
                    local_source=local_source,
                    os_name="posix",
                ).decode("utf-8")
            )

        self.assertEqual(rendered["model"], "machine-local-model")
        self.assertFalse(rendered["mcp_servers"]["context7"]["enabled"])
        self.assertIn("command", rendered["mcp_servers"]["context7"])
        self.assertEqual(
            rendered["mcp_servers"]["context7"]["env"]["CONTEXT7_API_KEY"],
            "test-only-secret-value",
        )
        self.assertEqual(
            rendered["mcp_servers"]["machine-local"],
            {
                "command": "/machine/local/tool",
                "args": ["serve"],
                "enabled": True,
                "env": {"MACHINE_LOCAL_TOKEN": "test-only-local-secret"},
            },
        )

    def test_managed_plugin_enablement_is_included_before_local_overlay(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            secret_source = self.write_mcp_secret_fragment(root)
            local_source = root / ".codex" / "config.local.toml"
            local_source.write_text(
                '[plugins."operate-database-profiles@personal"]\n'
                "enabled = false\n",
                encoding="utf-8",
            )
            local_source.chmod(0o600)
            plugin = ManagedPlugin(
                "operate-database-profiles",
                "personal",
                root / "plugins" / "operate-database-profiles",
            )

            managed_default = tomllib.loads(
                render_codex_config(
                    config_source_paths("macos"),
                    secret_source,
                    managed_plugin=plugin,
                    os_name="posix",
                ).decode("utf-8")
            )
            rendered = tomllib.loads(
                render_codex_config(
                    config_source_paths("macos"),
                    secret_source,
                    local_source=local_source,
                    managed_plugin=plugin,
                    os_name="posix",
                ).decode("utf-8")
            )

        self.assertEqual(
            managed_default["plugins"],
            {"operate-database-profiles@personal": {"enabled": True}},
        )
        self.assertEqual(
            rendered["plugins"],
            {"operate-database-profiles@personal": {"enabled": False}},
        )

    def test_mcp_secret_fragment_is_private_and_secret_only(self) -> None:
        managed_server_names = {"context7"}
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "mcp-secrets.toml"
            source.write_text(
                "[mcp_servers.context7.env]\n"
                'CONTEXT7_API_KEY = "test-only-secret-value"\n',
                encoding="utf-8",
            )
            source.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "permissions are too broad"):
                validate_mcp_secret_fragment(
                    source,
                    managed_server_names,
                    os_name="posix",
                )
            source.chmod(0o600)
            parsed = validate_mcp_secret_fragment(
                source,
                managed_server_names,
                os_name="posix",
            )
            self.assertEqual(
                parsed["mcp_servers"]["context7"]["env"],
                {"CONTEXT7_API_KEY": "test-only-secret-value"},
            )

            invalid_fragments = {
                "placeholder": (
                    "[mcp_servers.context7.env]\n"
                    'CONTEXT7_API_KEY = "***REDACTED***"\n'
                ),
                "empty value": (
                    "[mcp_servers.context7.env]\n"
                    'CONTEXT7_API_KEY = ""\n'
                ),
                "unknown server": (
                    "[mcp_servers.unmanaged.env]\n"
                    'API_KEY = "test-only-secret-value"\n'
                ),
                "forbidden field": (
                    "[mcp_servers.context7]\n"
                    'command = "unexpected-command"\n'
                ),
            }
            for label, content in invalid_fragments.items():
                with self.subTest(label=label):
                    source.write_text(content, encoding="utf-8")
                    source.chmod(0o600)
                    with self.assertRaises(ValueError):
                        validate_mcp_secret_fragment(
                            source,
                            managed_server_names,
                            os_name="posix",
                        )

    def test_codex_config_sync_is_byte_exact_and_drift_protected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "codex-config.toml"
            target = root / ".codex" / "config.toml"
            source.write_bytes(b'web_search = "cached"\r\n')
            expected_content = source.read_bytes()

            missing = compare_codex_config(expected_content, target)
            self.assertEqual(len(missing), 1)
            self.assertIn("missing target", missing[0].label)
            self.assertFalse(missing[0].target_exists)

            self.assertEqual(sync_codex_config(expected_content, target), 1)
            self.assertEqual(target.read_bytes(), expected_content)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(compare_codex_config(expected_content, target), [])

            target.write_text('web_search = "disabled"\n', encoding="utf-8")
            drift = compare_codex_config(expected_content, target)
            self.assertEqual(len(drift), 1)
            self.assertIn("content differs", drift[0].label)
            self.assertTrue(drift[0].target_exists)

    def test_main_defaults_to_overwriting_codex_config_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            home = root / "home"
            codex_home = root / "codex"
            home.mkdir()
            codex_home.mkdir()
            target = codex_home / "config.toml"
            secret_source = self.write_mcp_secret_fragment(root)
            local_source = root / ".codex" / "config.local.toml"
            local_source.write_text(
                'personality = "friendly"\n',
                encoding="utf-8",
            )
            local_source.chmod(0o600)
            expected_content = render_codex_config(
                config_source_paths("macos"),
                secret_source,
                local_source=local_source,
                os_name="posix",
            )
            environment = {
                "HOME": str(home),
                "CODEX_HOME": str(codex_home),
            }

            with (
                patch.dict(os.environ, environment),
                patch.object(
                    sync_module,
                    "default_config_platform",
                    return_value="macos",
                ),
                patch.object(
                    sync_module,
                    "default_codex_config_target",
                    return_value=target,
                ),
                patch.object(
                    sync_module,
                    "default_mcp_secret_source",
                    return_value=secret_source,
                ),
                patch.object(
                    sync_module,
                    "default_local_config_source",
                    return_value=local_source,
                ),
                redirect_stdout(output := io.StringIO()),
            ):
                with patch.object(sys, "argv", ["sync_codex_assets.py"]):
                    self.assertEqual(sync_module.main(), 0)
                self.assertEqual(target.read_bytes(), expected_content)
                installed_references = (
                    codex_home
                    / "skills"
                    / "agents-md-generator"
                    / "references"
                )
                for source_name in (
                    "codex-config-base.toml",
                    "codex-config-local.example.toml",
                    "codex-mcp-servers.common.toml",
                    "codex-mcp-servers.macos.toml",
                    "codex-mcp-servers.windows.toml",
                    "codex-mcp-secrets.example.toml",
                ):
                    self.assertEqual(
                        (installed_references / source_name).read_bytes(),
                        (SCRIPTS.parent / "references" / source_name).read_bytes(),
                    )

                target.write_text("# local drift\n", encoding="utf-8")
                with patch.object(
                    sys,
                    "argv",
                    ["sync_codex_assets.py", "--check"],
                ):
                    self.assertEqual(sync_module.main(), 1)
                with patch.object(sys, "argv", ["sync_codex_assets.py"]):
                    self.assertEqual(sync_module.main(), 0)

                target.write_text("# local drift\n", encoding="utf-8")
                with patch.object(
                    sys,
                    "argv",
                    ["sync_codex_assets.py", "--overwrite-runtime-drift"],
                ):
                    self.assertEqual(sync_module.main(), 0)

            self.assertEqual(target.read_bytes(), expected_content)
            self.assertNotIn("test-only-secret-value", output.getvalue())
            self.assertFalse(
                (
                    codex_home
                    / "skills"
                    / "agents-md-generator"
                    / ".codex"
                    / "mcp-secrets.toml"
                ).exists()
            )

    def test_parse_mode_defaults_to_runtime_drift_overwrite(self) -> None:
        self.assertEqual(parse_mode([]), "overwrite")
        self.assertEqual(parse_mode(["--check"]), "check")
        self.assertEqual(
            parse_mode(["--overwrite-runtime-drift"]),
            "overwrite",
        )
        with self.assertRaisesRegex(ValueError, "usage"):
            parse_mode(["--force"])

    def test_windows_entry_discovers_compatible_runtime_and_preserves_result(
        self,
    ) -> None:
        entry_script = (SCRIPTS.parent / "sync_codex_assets.cmd").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            r'set "MANAGED_PYTHON=%USERPROFILE%\Programs\1_develop\python-tools'
            r'\.runtime\.venv\Scripts\python.exe"',
            entry_script,
        )
        self.assertIn(
            "if defined SYNC_CODEX_ASSETS_PYTHON goto :try_override",
            entry_script,
        )
        self.assertIn("where py.exe", entry_script)
        self.assertIn("py.exe -3", entry_script)
        self.assertIn("where python.exe", entry_script)
        self.assertGreaterEqual(
            entry_script.count("sys.version_info >= (3, 11)"),
            4,
        )
        self.assertIn('set "SYNC_EXIT_CODE=%ERRORLEVEL%"', entry_script)
        self.assertIn(
            'if /i "%SYNC_CODEX_ASSETS_NO_PAUSE%"=="1" goto :exit',
            entry_script,
        )
        self.assertIn("pause", entry_script)
        self.assertEqual(entry_script.lower().count("exit /b"), 1)
        self.assertLess(
            entry_script.index("\n:finish\n"),
            entry_script.rindex("exit /b"),
        )
        lines = [line.strip().lower() for line in entry_script.splitlines()]
        labels = {line[1:] for line in lines if line.startswith(":")}
        goto_targets = {
            line.rsplit("goto :", 1)[1]
            for line in lines
            if "goto :" in line
        }
        self.assertEqual(goto_targets - labels, set())

    def test_posix_entry_requires_python_3_11_for_toml_merging(self) -> None:
        entry_script = (SCRIPTS.parent / "sync_codex_assets.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("sys.version_info >= (3, 11)", entry_script)
        self.assertIn("Python 3.11 or later runtime not found", entry_script)

    def test_compare_tree_detects_managed_content_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "SKILL.md").write_text("source\n", encoding="utf-8")
            (target / "SKILL.md").write_text("source\n", encoding="utf-8")
            self.assertEqual(compare_tree(source, target, "skill/demo"), [])

            (target / "SKILL.md").write_text("runtime edit\n", encoding="utf-8")
            drift = compare_tree(source, target, "skill/demo")
            self.assertEqual(len(drift), 1)
            self.assertIn("content differs", drift[0].label)
            self.assertTrue(drift[0].target_exists)

    def test_runtime_caches_are_not_managed_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "SKILL.md").write_text("same\n", encoding="utf-8")
            (target / "SKILL.md").write_text("same\n", encoding="utf-8")
            cache = target / "__pycache__"
            cache.mkdir()
            (cache / "dbctl.cpython-312.pyc").write_bytes(b"runtime-cache")
            (target / ".DS_Store").write_bytes(b"metadata")

            self.assertTrue(ignored_runtime_path(Path("__pycache__/x.pyc")))
            self.assertTrue(ignored_runtime_path(Path(".DS_Store")))
            self.assertEqual(compare_tree(source, target, "skill/demo"), [])

    def test_discovers_local_plugin_from_personal_marketplace_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            marketplace = root / ".agents" / "plugins" / "marketplace.json"
            marketplace.parent.mkdir(parents=True)
            marketplace.write_text(
                json.dumps(
                    {
                        "name": "personal",
                        "plugins": [
                            {
                                "name": "operate-database-profiles",
                                "source": {
                                    "source": "local",
                                    "path": "./plugins/operate-database-profiles",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            plugin = discover_managed_plugin(marketplace)

            self.assertIsNotNone(plugin)
            assert plugin is not None
            self.assertEqual(plugin.marketplace, "personal")
            self.assertEqual(
                plugin.source_dir,
                (root / "plugins" / "operate-database-profiles").resolve(),
            )

    def test_rejects_managed_plugin_source_outside_marketplace_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            marketplace = root / ".agents" / "plugins" / "marketplace.json"
            marketplace.parent.mkdir(parents=True)
            marketplace.write_text(
                json.dumps(
                    {
                        "name": "personal",
                        "plugins": [
                            {
                                "name": "operate-database-profiles",
                                "source": {
                                    "source": "local",
                                    "path": "../../outside/operate-database-profiles",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "inside the marketplace root",
            ):
                discover_managed_plugin(marketplace)

    def test_managed_plugin_drift_ignores_only_cachebuster_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            plugin_root = (
                Path(temporary_directory) / "plugins" / plugin_builder.SKILL_NAME
            )
            plugin_builder.build_plugin(plugin_root)
            set_plugin_version(
                plugin_root,
                "0.1.0+codex.local-20260730-120000",
            )
            plugin = ManagedPlugin(
                plugin_builder.SKILL_NAME,
                "personal",
                plugin_root,
            )
            self.assertEqual(find_managed_plugin_drift(plugin), [])

            set_plugin_version(
                plugin_root,
                "0.2.0+codex.local-20260730-120000",
            )
            version_drift = find_managed_plugin_drift(plugin)
            self.assertEqual(len(version_drift), 1)
            self.assertIn("plugin.json: content differs", version_drift[0].label)

            set_plugin_version(
                plugin_root,
                "0.1.0+codex.local-20260730-120000",
            )
            packaged_core = (
                plugin_root
                / "skills"
                / plugin_builder.SKILL_NAME
                / "scripts"
                / "dbctl_core.py"
            )
            packaged_core.write_text("runtime edit\n", encoding="utf-8")
            drift = find_managed_plugin_drift(plugin)
            self.assertEqual(len(drift), 1)
            self.assertIn("dbctl_core.py: content differs", drift[0].label)

    def test_sync_managed_plugin_rebuilds_and_reinstalls_with_cachebuster(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            plugin_root = (
                Path(temporary_directory) / "plugins" / plugin_builder.SKILL_NAME
            )
            plugin = ManagedPlugin(
                plugin_builder.SKILL_NAME,
                "personal",
                plugin_root,
            )
            commands: list[list[str]] = []

            def fake_runner(command: list[str], **_: object):
                commands.append(command)
                return subprocess.CompletedProcess(command, 0, '{"installed":true}\n', "")

            count = sync_managed_plugin(
                plugin,
                codex_executable="/approved/codex",
                now=datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc),
                command_runner=fake_runner,
            )

            self.assertEqual(count, 1)
            self.assertEqual(
                commands,
                [
                    [
                        "/approved/codex",
                        "plugin",
                        "add",
                        "operate-database-profiles@personal",
                        "--json",
                    ]
                ],
            )
            manifest = json.loads(
                (
                    plugin_root / ".codex-plugin" / "plugin.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["version"],
                "0.1.0+codex.local-20260730-120000",
            )
            self.assertEqual(find_managed_plugin_drift(plugin), [])

            sync_managed_plugin(
                plugin,
                codex_executable="/approved/codex",
                now=datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc),
                command_runner=fake_runner,
            )
            repeated_manifest = json.loads(
                (
                    plugin_root / ".codex-plugin" / "plugin.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                repeated_manifest["version"],
                "0.1.0+codex.local-20260730-120001",
            )
            self.assertEqual(len(commands), 2)

    def test_sync_managed_plugin_stops_when_codex_install_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            plugin = ManagedPlugin(
                plugin_builder.SKILL_NAME,
                "personal",
                Path(temporary_directory) / plugin_builder.SKILL_NAME,
            )

            def failing_runner(command: list[str], **_: object):
                return subprocess.CompletedProcess(command, 7, "", "install failed")

            with self.assertRaisesRegex(
                ValueError,
                "Codex plugin reinstall failed",
            ):
                sync_managed_plugin(
                    plugin,
                    codex_executable="/approved/codex",
                    now=datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc),
                    command_runner=failing_runner,
                )

    def test_cachebuster_advances_if_repeated_in_the_same_second(self) -> None:
        now = datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(
            next_plugin_version(
                "0.1.0+codex.local-20260730-120000",
                now,
            ),
            "0.1.0+codex.local-20260730-120001",
        )


if __name__ == "__main__":
    unittest.main()
