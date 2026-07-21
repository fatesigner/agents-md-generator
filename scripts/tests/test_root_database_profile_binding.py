from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from extract_facts import extract_root_facts  # noqa: E402
from generate_agents import generate_single  # noqa: E402
from render_agents_from_facts import render  # noqa: E402


class RootDatabaseProfileBindingTests(unittest.TestCase):
    def test_explicit_binding_renders_complete_subsection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            facts = extract_root_facts(
                root,
                [],
                database_project_identifier="p2mipc2i",
                database_default_production_read_target="backend-prod-ro",
            )

        rendered = render("root", facts)

        self.assertEqual(rendered.count("### 数据库 Profile 绑定"), 1)
        self.assertIn(
            "project identifier 为 `p2mipc2i`",
            rendered,
        )
        self.assertIn("`dbctl list p2mipc2i`", rendered)
        self.assertIn("默认生产只读 target 为 `backend-prod-ro`", rendered)
        self.assertIn("生产只读请求本身即构成该次操作授权", rendered)
        self.assertIn("自动传入 `--allow-production`", rendered)
        self.assertNotIn("__ROOT_DATABASE_PROFILE_BINDING__", rendered)

    def test_missing_binding_omits_complete_subsection(self) -> None:
        rendered_without_key = render("root", {})
        rendered_with_empty_binding = render(
            "root",
            {"database_profile_binding": {}},
        )

        for rendered in (rendered_without_key, rendered_with_empty_binding):
            self.assertNotIn("### 数据库 Profile 绑定", rendered)
            self.assertNotIn("__ROOT_DATABASE_PROFILE_BINDING__", rendered)
            self.assertNotIn("\n\n\n", rendered)

    def test_invalid_identifier_fails_closed(self) -> None:
        invalid_identifiers = [
            "bad project",
            "bad/project",
            "bad`project",
            "bad;project",
            "bad\nproject",
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for identifier in invalid_identifiers:
                with self.subTest(identifier=identifier):
                    with self.assertRaises(ValueError):
                        extract_root_facts(
                            root,
                            [],
                            database_project_identifier=identifier,
                        )
                    with self.assertRaises(ValueError):
                        render(
                            "root",
                            {
                                "database_profile_binding": {
                                    "project_identifier": identifier,
                                }
                            },
                        )

    def test_invalid_or_unbound_default_production_target_fails_closed(self) -> None:
        invalid_targets = ["bad target", "bad/target", "bad`target", "bad;target"]

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with self.assertRaises(ValueError):
                extract_root_facts(
                    root,
                    [],
                    database_default_production_read_target="backend-prod-ro",
                )
            for target in invalid_targets:
                with self.subTest(target=target):
                    with self.assertRaises(ValueError):
                        extract_root_facts(
                            root,
                            [],
                            database_project_identifier="p2mipc2i",
                            database_default_production_read_target=target,
                        )
                    with self.assertRaises(ValueError):
                        render(
                            "root",
                            {
                                "database_profile_binding": {
                                    "project_identifier": "p2mipc2i",
                                    "default_production_read_target": target,
                                }
                            },
                        )

    def test_generate_single_passes_binding_only_to_root_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "AGENTS.preview.md"
            generate_single(
                template="root",
                root=root,
                target=root,
                detail_level="standard",
                child_agents=[],
                output_path=output,
                database_project_identifier="p2mipc2i",
                database_default_production_read_target="backend-prod-ro",
            )
            self.assertIn("`dbctl list p2mipc2i`", output.read_text(encoding="utf-8"))
            self.assertIn(
                "默认生产只读 target 为 `backend-prod-ro`",
                output.read_text(encoding="utf-8"),
            )

            with self.assertRaises(ValueError):
                generate_single(
                    template="frontend-child",
                    root=root,
                    target=root,
                    detail_level="standard",
                    child_agents=[],
                    output_path=root / "child.preview.md",
                    database_project_identifier="p2mipc2i",
                )

    def test_suite_manifest_passes_explicit_root_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest = root / "agents-suite.json"
            manifest.write_text(
                json.dumps(
                    {
                        "root": str(root),
                        "root_agents": {
                            "output": "AGENTS.md",
                            "database_project": "p2mipc2i",
                            "database_production_read_target": "backend-prod-ro",
                        },
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "generate_agents_suite.py"),
                    "--manifest",
                    str(manifest),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            rendered = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("`dbctl list p2mipc2i`", rendered)
            self.assertIn("默认生产只读 target 为 `backend-prod-ro`", rendered)


if __name__ == "__main__":
    unittest.main()
