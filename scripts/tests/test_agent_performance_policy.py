from __future__ import annotations

import io
import sys
import tempfile
import tomllib
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
        self.performance_policy = (
            PROJECT_ROOT / "references" / "performance-policy.md"
        ).read_text(encoding="utf-8")
        self.safety_policy = (
            PROJECT_ROOT / "references" / "safety-policy.md"
        ).read_text(encoding="utf-8")
        self.workflow_policy = (
            PROJECT_ROOT / "references" / "workflow-policy.md"
        ).read_text(encoding="utf-8")
        self.subagents_readme = (
            PROJECT_ROOT / "subagents-main" / "README.md"
        ).read_text(encoding="utf-8")

    def test_global_template_keeps_adaptive_parallelism_lazy(self) -> None:
        self.assertIn("端到端壁钟时间", self.global_template)
        self.assertIn("references/subagents-policy.md", self.global_template)
        self.assertIn("references/performance-policy.md", self.global_template)
        self.assertNotIn('fork_turns: "none"', self.global_template)
        self.assertNotIn("首批默认 1 个 subagent", self.global_template)
        self.assertIn('fork_turns: "none"', self.subagents_policy)
        self.assertIn("首批默认 1 个 subagent", self.subagents_policy)
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

    def test_subagent_assets_use_explicit_model_tiers(self) -> None:
        roles_by_model: dict[str, set[str]] = {}
        roles_by_model_effort: dict[tuple[str, str], set[str]] = {}
        configs_by_role: dict[str, dict[str, object]] = {}
        for path in (PROJECT_ROOT / "subagents-main").rglob("*.toml"):
            config = tomllib.loads(path.read_text(encoding="utf-8"))
            role = config["name"]
            model = config["model"]
            effort = config["model_reasoning_effort"]
            roles_by_model.setdefault(model, set()).add(role)
            roles_by_model_effort.setdefault((model, effort), set()).add(role)
            configs_by_role[role] = config

        self.assertEqual(
            {model: len(roles) for model, roles in roles_by_model.items()},
            {
                "gpt-5.6-sol": 49,
                "gpt-5.6-terra": 87,
                "gpt-5.6-luna": 2,
            },
        )
        self.assertEqual(
            {
                model_effort: len(roles)
                for model_effort, roles in roles_by_model_effort.items()
            },
            {
                ("gpt-5.6-luna", "medium"): 2,
                ("gpt-5.6-terra", "low"): 1,
                ("gpt-5.6-terra", "medium"): 63,
                ("gpt-5.6-terra", "high"): 23,
                ("gpt-5.6-sol", "high"): 48,
                ("gpt-5.6-sol", "xhigh"): 1,
            },
        )
        self.assertEqual(
            roles_by_model["gpt-5.6-luna"],
            {"refactoring-specialist", "test-automator"},
        )
        self.assertEqual(
            roles_by_model_effort[("gpt-5.6-sol", "xhigh")],
            {"decision-arbiter"},
        )
        self.assertEqual(
            configs_by_role["decision-arbiter"]["sandbox_mode"],
            "read-only",
        )
        for role in (
            "architect-reviewer",
            "deployment-engineer",
            "incident-responder",
            "it-ops-orchestrator",
            "payment-integration",
            "security-auditor",
        ):
            with self.subTest(model="sol", role=role):
                self.assertIn(role, roles_by_model["gpt-5.6-sol"])
        for role in (
            "backend-developer",
            "browser-debugger",
            "frontend-developer",
            "python-pro",
        ):
            with self.subTest(model="terra", role=role):
                self.assertIn(role, roles_by_model["gpt-5.6-terra"])

    def test_subagent_readme_describes_the_installed_model_ladder(self) -> None:
        self.assertIn(
            "The awesome collection of 138 Codex subagents",
            self.subagents_readme,
        )
        for marker in (
            "| Focused | `gpt-5.6-luna` + `medium`",
            "| Fast | `gpt-5.6-terra` + `medium`",
            "| Balanced | `gpt-5.6-terra` + `high`",
            "| Deep | `gpt-5.6-sol` + `high`",
            "| Arbiter | `gpt-5.6-sol` + `xhigh`",
            "Escalation happens at a new spawn boundary",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.subagents_readme)
        self.assertNotIn("| Balanced | `gpt-5.6` +", self.subagents_readme)
        self.assertNotIn("| Deep | `gpt-5.6` +", self.subagents_readme)

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
                "safety-policy.md",
                "search-policy.md",
                "session-policy.md",
                "subagents-policy.md",
                "workflow-policy.md",
            }.issubset(discovered)
        )

    def test_global_reference_paths_use_codex_home_not_project_cwd(self) -> None:
        self.assertIn(
            "用户级 Codex 目录 `${CODEX_HOME:-~/.codex}`",
            self.global_template,
        )
        self.assertIn(
            "不得相对当前仓库、目标项目或工作目录解析",
            self.global_template,
        )

    def test_global_template_stays_below_prompt_size_budget(self) -> None:
        self.assertLessEqual(
            len(self.global_template.encode("utf-8")),
            16_000,
        )

    def test_global_template_preserves_critical_gates(self) -> None:
        for marker in (
            "git push",
            "生产写入",
            "同类失败连续 3 次",
            "读取敏感原文",
            "$operate-database-profiles",
            "--allow-production",
            "改动文件、验证结果、已知风险",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.global_template)

        self.assertIn("references/safety-policy.md", self.global_template)
        self.assertNotIn("`.env.*`", self.global_template)
        self.assertNotIn("`.git-credentials`", self.global_template)

    def test_safety_policy_preserves_exact_sensitive_targets(self) -> None:
        for marker in (
            ".env.*",
            "appsettings.*.json",
            ".git-credentials",
            ".dockerconfigjson",
            ".ssh",
            "数据库备份",
            "客户数据",
            "git push",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.safety_policy)

    def test_workflow_policy_captures_long_running_contract(self) -> None:
        for marker in (
            "目标：",
            "完成标准：",
            "授权边界：",
            "durable thread",
            "Steer",
            "Queue",
            "New thread",
            "Automation",
            "Fast mode",
            "Artifact 审阅",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.workflow_policy)

    def test_performance_policy_uses_quality_gate_and_tiered_model_routing(
        self,
    ) -> None:
        self.assertIn(
            "先定义结果、正确性、安全性与验证覆盖的最低门槛",
            self.performance_policy,
        )
        self.assertIn("单位合格结果成本", self.performance_policy)
        self.assertIn("宿主已暴露相应模型", self.performance_policy)
        for model in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
            with self.subTest(model=model):
                self.assertIn(model, self.performance_policy)
        self.assertIn("Plan mode 使用 `xhigh`", self.performance_policy)
        self.assertIn("至少两个复杂度信号", self.performance_policy)
        self.assertIn("两次实质性错误路径", self.performance_policy)
        self.assertIn("等待时间不是推理复杂度信号", self.performance_policy)
        self.assertIn("Fast mode", self.performance_policy)
        self.assertIn("不代表更高智能或更高正确率", self.performance_policy)
        self.assertIn("不把 `xhigh`", self.performance_policy)
        self.assertIn(
            "不得声称同一运行中的 subagent 已被热切换",
            self.performance_policy,
        )
        self.assertIn("只读 `decision-arbiter`", self.performance_policy)
        self.assertIn("token/credit", self.performance_policy)
        self.assertIn("返工次数", self.performance_policy)

    def test_subagent_policy_uses_capability_gated_tiered_model_routing(
        self,
    ) -> None:
        self.assertIn("当前宿主和调用方式已暴露对应模型", self.subagents_policy)
        self.assertIn(
            "用户可选模型等同于 subagent 可覆盖模型",
            self.subagents_policy,
        )
        for model in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
            with self.subTest(model=model):
                self.assertIn(model, self.subagents_policy)
        self.assertIn(
            "不得通过增加更多低层级 subagents 补偿质量问题",
            self.subagents_policy,
        )
        self.assertIn(
            "动态路由必须发生在新建下一次 subagent 调用的边界",
            self.subagents_policy,
        )
        self.assertIn("Luna -> Terra、Terra -> Sol high", self.subagents_policy)
        self.assertIn("统一使用只读 `decision-arbiter`", self.subagents_policy)
        self.assertNotIn("默认允许运行时升级到 `xhigh`", self.subagents_policy)

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
            self.assertGreaterEqual(synced_count, 10)
            for name in (
                "performance-policy.md",
                "safety-policy.md",
                "search-policy.md",
                "session-policy.md",
                "subagents-policy.md",
                "workflow-policy.md",
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
            self.assertEqual(subagent_count, 138)
            self.assertEqual(
                (target_root / "agents" / "decision-arbiter.toml").read_text(
                    encoding="utf-8"
                ),
                (
                    PROJECT_ROOT
                    / "subagents-main"
                    / "09-meta-orchestration"
                    / "decision-arbiter.toml"
                ).read_text(encoding="utf-8"),
            )
            runtime_skill_target = target_root / "skills" / "agents-md-generator"
            self.assertTrue(
                (runtime_skill_target / "scripts" / "sync_codex_assets.py").is_file()
            )
            for entry_script in ("sync_codex_assets.cmd", "sync_codex_assets.sh"):
                with self.subTest(entry_script=entry_script):
                    self.assertFalse((runtime_skill_target / entry_script).exists())
            self.assertEqual(
                (
                    runtime_skill_target
                    / "references"
                    / "performance-policy.md"
                ).read_text(encoding="utf-8"),
                (PROJECT_ROOT / "references" / "performance-policy.md").read_text(
                    encoding="utf-8"
                ),
            )


if __name__ == "__main__":
    unittest.main()
