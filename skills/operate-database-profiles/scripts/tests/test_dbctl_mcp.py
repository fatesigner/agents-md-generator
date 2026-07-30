from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = SCRIPT_DIR / "dbctl_mcp.py"
SPEC = importlib.util.spec_from_file_location("dbctl_mcp", MODULE_PATH)
assert SPEC and SPEC.loader
dbctl_mcp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dbctl_mcp)


class DbctlMcpTests(unittest.TestCase):
    def test_tool_inventory_is_conservative_and_has_no_raw_escape_hatch(self) -> None:
        names = {tool["name"] for tool in dbctl_mcp.TOOLS}
        self.assertEqual(
            names,
            {
                "database_inspect_target",
                "database_list_targets",
                "database_ping",
                "database_query",
            },
        )
        self.assertFalse(any("exec" in name or "credential" in name for name in names))
        annotations = {
            tool["name"]: tool["annotations"]
            for tool in dbctl_mcp.TOOLS
        }
        self.assertFalse(annotations["database_query"]["readOnlyHint"])
        self.assertTrue(
            all(
                value["readOnlyHint"]
                for name, value in annotations.items()
                if name != "database_query"
            )
        )

    def test_query_maps_typed_arguments_to_fixed_core_argv(self) -> None:
        payload = {
            "ok": True,
            "databaseContacted": True,
            "attempts": 1,
            "output": "1\n",
        }
        with mock.patch.object(
            dbctl_mcp.dbctl_core,
            "invoke_json",
            return_value=(0, payload),
        ) as invoke:
            result = dbctl_mcp.call_tool(
                "database_query",
                {
                    "project": "sample-project",
                    "target": "backend-test",
                    "sqlFile": "/repo/.codex/database/queries/read.sql",
                    "allowProduction": True,
                },
            )
        invoke.assert_called_once_with(
            [
                "query",
                "sample-project",
                "backend-test",
                "--file",
                "/repo/.codex/database/queries/read.sql",
                "--allow-production",
            ]
        )
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["output"], "1\n")
        self.assertNotIn("1\n", result["content"][0]["text"])

    def test_inspect_target_combines_three_no_contact_checks(self) -> None:
        responses = [
            (0, {"ok": True, "databaseContacted": False, "environment": "testing"}),
            (0, {"ok": True, "databaseContacted": False, "profileState": "OK"}),
            (0, {"ok": True, "databaseContacted": False, "sqlState": "OK"}),
        ]
        with mock.patch.object(
            dbctl_mcp.dbctl_core,
            "invoke_json",
            side_effect=responses,
        ) as invoke:
            result = dbctl_mcp.call_tool(
                "database_inspect_target",
                {
                    "project": "sample-project",
                    "target": "backend-test",
                    "operation": "query",
                    "sqlFile": "/repo/.codex/database/queries/read.sql",
                },
            )
        self.assertEqual(invoke.call_count, 3)
        self.assertTrue(result["structuredContent"]["ok"])
        self.assertFalse(result["structuredContent"]["databaseContacted"])
        self.assertEqual(
            list(result["structuredContent"]["steps"]),
            ["describe", "doctor", "preflight"],
        )

    def test_unknown_or_secret_like_arguments_are_rejected_before_core(self) -> None:
        with mock.patch.object(dbctl_mcp.dbctl_core, "invoke_json") as invoke:
            response = dbctl_mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "database_ping",
                        "arguments": {
                            "project": "sample-project",
                            "target": "backend-test",
                            "password": "MUST_NOT_APPEAR",
                        },
                    },
                }
            )
        invoke.assert_not_called()
        assert response is not None
        rendered = json.dumps(response)
        self.assertIn("MCP_ARGUMENT_INVALID", rendered)
        self.assertNotIn("MUST_NOT_APPEAR", rendered)

    def test_inspect_requires_sql_file_for_query(self) -> None:
        with mock.patch.object(dbctl_mcp.dbctl_core, "invoke_json") as invoke:
            response = dbctl_mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tools/call",
                    "params": {
                        "name": "database_inspect_target",
                        "arguments": {
                            "project": "sample-project",
                            "target": "backend-test",
                            "operation": "query",
                        },
                    },
                }
            )
        invoke.assert_not_called()
        assert response is not None
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(
            response["result"]["structuredContent"]["category"],
            "MCP_ARGUMENT_INVALID",
        )

    def test_large_structured_result_is_suppressed(self) -> None:
        with mock.patch.object(
            dbctl_mcp.dbctl_core,
            "invoke_json",
            return_value=(
                0,
                {
                    "ok": True,
                    "databaseContacted": True,
                    "attempts": 1,
                    "output": "x" * dbctl_mcp.MAX_STRUCTURED_OUTPUT_BYTES,
                },
            ),
        ):
            result = dbctl_mcp.call_tool(
                "database_query",
                {
                    "project": "sample-project",
                    "target": "backend-test",
                    "sqlFile": "/repo/.codex/database/queries/read.sql",
                },
            )
        self.assertTrue(result["isError"])
        self.assertEqual(
            result["structuredContent"]["category"],
            "MCP_OUTPUT_LIMIT",
        )
        self.assertNotIn(
            "x" * 100,
            json.dumps(result),
        )

    def test_unexpected_core_failure_is_suppressed(self) -> None:
        with mock.patch.object(
            dbctl_mcp.dbctl_core,
            "invoke_json",
            side_effect=RuntimeError("SENSITIVE_INTERNAL_DETAIL"),
        ):
            result = dbctl_mcp.call_tool(
                "database_list_targets",
                {"project": "sample-project"},
            )
        rendered = json.dumps(result)
        self.assertTrue(result["isError"])
        self.assertIn("MCP_CORE_FAILURE", rendered)
        self.assertNotIn("SENSITIVE_INTERNAL_DETAIL", rendered)

    def test_stdio_protocol_initializes_and_lists_tools_without_logs(self) -> None:
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            },
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        ]
        completed = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input="\n".join(json.dumps(message) for message in messages) + "\n",
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        responses = [
            json.loads(line)
            for line in completed.stdout.splitlines()
            if line.strip()
        ]
        self.assertEqual([response["id"] for response in responses], [1, 2])
        self.assertEqual(
            responses[0]["result"]["serverInfo"]["name"],
            "operate-database-profiles",
        )
        self.assertEqual(len(responses[1]["result"]["tools"]), 4)


if __name__ == "__main__":
    unittest.main()
