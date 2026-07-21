from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from sync_codex_assets import (  # noqa: E402
    discover_global_references,
    sync_global_references,
    sync_global_rules,
    sync_skills,
    sync_subagents,
)


class AgentPerformancePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.global_template = (
            PROJECT_ROOT / "references" / "global-template.md"
        ).read_text(encoding="utf-8")
        self.subagents_policy = (
            PROJECT_ROOT / "references" / "subagents-policy.md"
        ).read_text(encoding="utf-8")

    def test_global_template_uses_adaptive_parallelism(self) -> None:
        self.assertIn("端到端壁钟时间", self.global_template)
        self.assertIn('fork_turns: "none"', self.global_template)
        self.assertIn("首批默认 1 个 subagent", self.global_template)
        self.assertNotIn("速度优先的强触发分发", self.global_template)
        self.assertNotIn("多面任务默认 2-4 个 subagents", self.global_template)

    def test_subagent_policy_uses_current_context_parameter(self) -> None:
        self.assertIn("### 自适应触发矩阵", self.subagents_policy)
        self.assertIn('fork_turns: "none"', self.subagents_policy)
        self.assertIn('fork_turns: "all"', self.subagents_policy)
        self.assertNotIn("fork_context", self.subagents_policy)
        self.assertIn("subagent 不继续委派其他 subagent", self.subagents_policy)

    def test_core_hotset_has_installable_specialist_assets(self) -> None:
        specialist_roles = (
            "reviewer",
            "debugger",
            "test-automator",
            "frontend-developer",
            "backend-developer",
            "browser-debugger",
            "security-auditor",
        )

        for role in specialist_roles:
            with self.subTest(role=role):
                matches = list((PROJECT_ROOT / "subagents-main").rglob(f"{role}.toml"))
                self.assertEqual(len(matches), 1)

        self.assertIn("`explorer`、`worker`", self.subagents_policy)

    def test_global_template_discovers_lazy_performance_references(self) -> None:
        discovered = {
            path.name
            for path in discover_global_references(
                PROJECT_ROOT / "references" / "global-template.md",
                PROJECT_ROOT / "references",
            )
        }

        self.assertTrue(
            {
                "performance-policy.md",
                "search-policy.md",
                "session-policy.md",
                "subagents-policy.md",
            }.issubset(discovered)
        )

    def test_global_template_stays_below_prompt_size_budget(self) -> None:
        self.assertLessEqual(
            len(self.global_template.encode("utf-8")),
            24_500,
        )

    def test_global_rules_and_lazy_references_sync_in_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            target_root = Path(temporary_directory)
            global_target = target_root / "AGENTS.md"
            references_target = target_root / "references"

            with redirect_stdout(io.StringIO()):
                sync_global_rules(
                    PROJECT_ROOT / "references" / "global-template.md",
                    global_target,
                )
                synced_count = sync_global_references(
                    PROJECT_ROOT / "references" / "global-template.md",
                    PROJECT_ROOT / "references",
                    references_target,
                )

            self.assertEqual(global_target.read_text(encoding="utf-8"), self.global_template)
            self.assertGreaterEqual(synced_count, 8)
            for name in (
                "performance-policy.md",
                "search-policy.md",
                "session-policy.md",
                "subagents-policy.md",
            ):
                self.assertEqual(
                    (references_target / name).read_text(encoding="utf-8"),
                    (PROJECT_ROOT / "references" / name).read_text(encoding="utf-8"),
                )

    def test_runtime_skill_and_subagents_sync_in_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            target_root = Path(temporary_directory)
            with redirect_stdout(io.StringIO()):
                subagent_count = sync_subagents(
                    PROJECT_ROOT / "subagents-main",
                    target_root / "agents",
                )
                skill_count = sync_skills(
                    PROJECT_ROOT / "skills",
                    target_root / "skills",
                )

            self.assertGreater(subagent_count, 100)
            self.assertGreaterEqual(skill_count, 4)
            self.assertTrue((target_root / "agents" / "reviewer.toml").is_file())
            self.assertEqual(
                (
                    target_root
                    / "skills"
                    / "agents-md-generator"
                    / "references"
                    / "performance-policy.md"
                ).read_text(encoding="utf-8"),
                (PROJECT_ROOT / "references" / "performance-policy.md").read_text(
                    encoding="utf-8"
                ),
            )


if __name__ == "__main__":
    unittest.main()
