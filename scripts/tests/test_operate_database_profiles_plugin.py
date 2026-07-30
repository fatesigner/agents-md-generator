from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import build_operate_database_profiles_plugin as builder


class OperateDatabaseProfilesPluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.plugin_root = Path(self.temporary.name) / "operate-database-profiles"
        builder.build_plugin(self.plugin_root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_manifest_packages_the_canonical_skill_and_local_mcp(self) -> None:
        manifest = json.loads(
            (self.plugin_root / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["name"], "operate-database-profiles")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        packaged_skill = (
            self.plugin_root / "skills" / "operate-database-profiles"
        )
        self.assertTrue((packaged_skill / "SKILL.md").is_file())
        self.assertEqual(
            (packaged_skill / "SKILL.md").read_bytes(),
            (
                PROJECT_ROOT
                / "skills"
                / "operate-database-profiles"
                / "SKILL.md"
            ).read_bytes(),
        )
        self.assertFalse(
            any(path.name == "__pycache__" for path in self.plugin_root.rglob("*"))
        )

    def test_fast_read_contract_is_packaged_from_canonical_source(self) -> None:
        source_skill = PROJECT_ROOT / "skills" / "operate-database-profiles"
        packaged_skill = (
            self.plugin_root / "skills" / "operate-database-profiles"
        )
        contract_path = Path("references/target-query-contract.md")

        self.assertEqual(
            (packaged_skill / contract_path).read_bytes(),
            (source_skill / contract_path).read_bytes(),
        )

        skill_text = (packaged_skill / "SKILL.md").read_text(
            encoding="utf-8"
        )
        safety_text = (
            packaged_skill / "references" / "safety-policy.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "completely review the final bounded SQL file before invoking query preflight",
            skill_text,
        )
        self.assertIn(
            "authorizes exactly one production read query",
            safety_text,
        )
        self.assertIn(
            "never reuse production authorization or preflight evidence across tasks",
            safety_text,
        )

    def test_mcp_manifest_starts_only_the_bundled_stdio_server(self) -> None:
        config = json.loads(
            (self.plugin_root / ".mcp.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(config["mcpServers"]), {"databaseProfiles"})
        server = config["mcpServers"]["databaseProfiles"]
        self.assertEqual(server["cwd"], ".")
        self.assertEqual(server["command"], "sh")
        self.assertEqual(
            server["args"],
            [
                "./skills/operate-database-profiles/scripts/dbctl-mcp.sh"
            ],
        )
        self.assertNotIn("url", server)
        self.assertNotIn("env", server)

    def test_existing_output_is_never_replaced(self) -> None:
        with self.assertRaisesRegex(ValueError, "already exists"):
            builder.build_plugin(self.plugin_root)


if __name__ == "__main__":
    unittest.main()
