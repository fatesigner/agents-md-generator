from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_operate_database_profiles_plugin as plugin_builder  # noqa: E402
from sync_codex_assets import (  # noqa: E402
    ManagedPlugin,
    compare_tree,
    discover_managed_plugin,
    find_managed_plugin_drift,
    ignored_runtime_path,
    next_plugin_version,
    parse_mode,
    set_plugin_version,
    sync_managed_plugin,
)


class SyncCodexAssetsTests(unittest.TestCase):
    def test_parse_mode_requires_explicit_runtime_drift_override(self) -> None:
        self.assertEqual(parse_mode([]), "sync")
        self.assertEqual(parse_mode(["--check"]), "check")
        self.assertEqual(
            parse_mode(["--overwrite-runtime-drift"]),
            "overwrite",
        )
        with self.assertRaisesRegex(ValueError, "usage"):
            parse_mode(["--force"])

    def test_windows_entry_uses_dedicated_runtime_and_preserves_result(self) -> None:
        entry_script = (SCRIPTS.parent / "sync_codex_assets.cmd").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            r'set "PYTHON=%USERPROFILE%\Programs\1_develop\python-tools'
            r'\.runtime\.venv\Scripts\python.exe"',
            entry_script,
        )
        self.assertNotIn("where py.exe", entry_script)
        self.assertNotIn("where python.exe", entry_script)
        self.assertIn('set "SYNC_EXIT_CODE=%ERRORLEVEL%"', entry_script)
        self.assertIn(
            'if /i "%SYNC_CODEX_ASSETS_NO_PAUSE%"=="1" goto :exit',
            entry_script,
        )
        self.assertIn("pause", entry_script)
        self.assertEqual(entry_script.lower().count("exit /b"), 1)
        self.assertLess(entry_script.index("\n:finish\n"), entry_script.rindex("exit /b"))

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
