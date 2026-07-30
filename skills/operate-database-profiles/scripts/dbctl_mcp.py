#!/usr/bin/env python3
"""Local STDIO MCP server for controlled database-profile operations."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import dbctl_core


SERVER_NAME = "operate-database-profiles"
SERVER_VERSION = "0.1.0"
LATEST_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = {
    LATEST_PROTOCOL_VERSION,
    "2025-06-18",
    "2024-11-05",
}
MAX_STRUCTURED_OUTPUT_BYTES = 64 * 1024
SERVER_INSTRUCTIONS = (
    "Use these tools only for project-scoped database profiles. Never provide "
    "credentials, connection strings, profile contents, or native-client arguments. "
    "Resolve production targets from the current request or explicit project rules, "
    "set allowProduction only for that authorized operation, and review SQL files "
    "before query calls. No write or credential-mutation tools are exposed."
)
SAFE_NAME_SCHEMA = {
    "type": "string",
    "pattern": "^[A-Za-z0-9_-]+$",
    "minLength": 1,
    "maxLength": 128,
}
SQL_FILE_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "description": "Absolute .sql path inside the target's declared query root.",
}
COMMON_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": True,
}


def object_schema(
    properties: dict[str, Any],
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "database_list_targets",
        "title": "List database targets",
        "description": (
            "List safe target aliases and routing metadata for one project "
            "without reading profiles or contacting a database."
        ),
        "inputSchema": object_schema({"project": SAFE_NAME_SCHEMA}, ("project",)),
        "outputSchema": COMMON_OUTPUT_SCHEMA,
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "database_inspect_target",
        "title": "Inspect and preflight a database target",
        "description": (
            "Combine target description, local health checks, and ping or query "
            "preflight without contacting a database."
        ),
        "inputSchema": object_schema(
            {
                "project": SAFE_NAME_SCHEMA,
                "target": SAFE_NAME_SCHEMA,
                "operation": {"type": "string", "enum": ["ping", "query"]},
                "sqlFile": SQL_FILE_SCHEMA,
                "allowProduction": {"type": "boolean", "default": False},
                "confirmIdempotentRetry": {"type": "boolean", "default": False},
            },
            ("project", "target", "operation"),
        ),
        "outputSchema": COMMON_OUTPUT_SCHEMA,
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "database_ping",
        "title": "Ping a database target",
        "description": (
            "Run the controlled connectivity check for an explicit target; "
            "this contacts the database but proves no query permission."
        ),
        "inputSchema": object_schema(
            {
                "project": SAFE_NAME_SCHEMA,
                "target": SAFE_NAME_SCHEMA,
                "allowProduction": {"type": "boolean", "default": False},
            },
            ("project", "target"),
        ),
        "outputSchema": COMMON_OUTPUT_SCHEMA,
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    },
    {
        "name": "database_query",
        "title": "Run a reviewed read query",
        "description": (
            "Run one reviewed query-root .sql file for an explicit target. "
            "Production requires current-task authorization and allowProduction."
        ),
        "inputSchema": object_schema(
            {
                "project": SAFE_NAME_SCHEMA,
                "target": SAFE_NAME_SCHEMA,
                "sqlFile": SQL_FILE_SCHEMA,
                "allowProduction": {"type": "boolean", "default": False},
                "confirmIdempotentRetry": {"type": "boolean", "default": False},
            },
            ("project", "target", "sqlFile"),
        ),
        "outputSchema": COMMON_OUTPUT_SCHEMA,
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
]
TOOL_BY_NAME = {tool["name"]: tool for tool in TOOLS}


class ToolInputError(Exception):
    pass


def require_arguments(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ToolInputError("tool arguments must be an object")
    return value


def validate_argument_names(
    arguments: dict[str, Any],
    allowed: set[str],
) -> None:
    unexpected = sorted(set(arguments) - allowed)
    if unexpected:
        raise ToolInputError("unsupported tool argument")


def required_text(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value:
        raise ToolInputError(f"{name} is required")
    return value


def optional_bool(
    arguments: dict[str, Any],
    name: str,
    *,
    default: bool = False,
) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise ToolInputError(f"{name} must be a boolean")
    return value


def core_result(argv: list[str]) -> dict[str, Any]:
    try:
        exit_code, payload = dbctl_core.invoke_json(argv)
    except Exception:
        return {
            "ok": False,
            "stage": "LOCAL",
            "category": "MCP_CORE_FAILURE",
            "retryable": False,
            "databaseContacted": False,
            "attempts": 1,
            "exitCode": 1,
            "message": "database core failed unexpectedly; details were suppressed",
        }
    result = dict(payload)
    result["exitCode"] = exit_code
    encoded = json.dumps(
        result,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > MAX_STRUCTURED_OUTPUT_BYTES:
        return {
            "ok": False,
            "stage": "OUTPUT",
            "category": "MCP_OUTPUT_LIMIT",
            "retryable": False,
            "databaseContacted": bool(result.get("databaseContacted")),
            "attempts": int(result.get("attempts", 1)),
            "exitCode": 50,
            "message": (
                "structured database result exceeded the MCP output limit; "
                "results were suppressed"
            ),
            "nextAction": "reduce selected columns or use a bounded aggregate",
        }
    return result


def database_args(
    command: str,
    arguments: dict[str, Any],
    *,
    include_sql_file: bool = False,
    include_operation: bool = False,
) -> list[str]:
    project = required_text(arguments, "project")
    target = required_text(arguments, "target")
    argv = [command, project, target]
    if include_operation:
        operation = required_text(arguments, "operation")
        if operation not in {"ping", "query"}:
            raise ToolInputError("operation must be ping or query")
        argv.extend(["--operation", operation])
        if operation == "query":
            sql_file = required_text(arguments, "sqlFile")
            argv.extend(["--file", sql_file])
        elif "sqlFile" in arguments:
            raise ToolInputError("sqlFile is only valid for query")
    elif include_sql_file:
        argv.extend(["--file", required_text(arguments, "sqlFile")])
    if optional_bool(arguments, "allowProduction"):
        argv.append("--allow-production")
    if optional_bool(arguments, "confirmIdempotentRetry"):
        argv.append("--confirm-idempotent-retry")
    return argv


def inspect_target(arguments: dict[str, Any]) -> dict[str, Any]:
    validate_argument_names(
        arguments,
        {
            "project",
            "target",
            "operation",
            "sqlFile",
            "allowProduction",
            "confirmIdempotentRetry",
        },
    )
    project = required_text(arguments, "project")
    target = required_text(arguments, "target")
    steps: dict[str, dict[str, Any]] = {}
    for step, argv in (
        ("describe", ["describe", project, target]),
        ("doctor", ["doctor", project, target]),
        (
            "preflight",
            database_args(
                "preflight",
                arguments,
                include_operation=True,
            ),
        ),
    ):
        steps[step] = core_result(argv)
        if not steps[step].get("ok"):
            return {
                "ok": False,
                "failedStep": step,
                "databaseContacted": False,
                "steps": steps,
            }
    return {
        "ok": True,
        "databaseContacted": False,
        "steps": steps,
    }


def call_tool(name: str, raw_arguments: Any) -> dict[str, Any]:
    if name not in TOOL_BY_NAME:
        raise ToolInputError("unknown database tool")
    arguments = require_arguments(raw_arguments)
    if name == "database_list_targets":
        validate_argument_names(arguments, {"project"})
        payload = core_result(["list", required_text(arguments, "project")])
    elif name == "database_inspect_target":
        payload = inspect_target(arguments)
    elif name == "database_ping":
        validate_argument_names(
            arguments,
            {"project", "target", "allowProduction"},
        )
        payload = core_result(database_args("ping", arguments))
    else:
        validate_argument_names(
            arguments,
            {
                "project",
                "target",
                "sqlFile",
                "allowProduction",
                "confirmIdempotentRetry",
            },
        )
        payload = core_result(
            database_args("query", arguments, include_sql_file=True)
        )

    ok = bool(payload.get("ok"))
    if ok:
        summary = f"{name}: OK; inspect structuredContent"
    else:
        summary = (
            f"{name}: {payload.get('category', 'FAILED')}; "
            f"databaseContacted={str(bool(payload.get('databaseContacted'))).lower()}"
        )
    return {
        "content": [{"type": "text", "text": summary}],
        "structuredContent": payload,
        "isError": not ok,
    }


def jsonrpc_error(
    request_id: Any,
    code: int,
    message: str,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def handle_request(message: Any) -> Optional[dict[str, Any]]:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return jsonrpc_error(None, -32600, "Invalid Request")
    request_id = message.get("id")
    method = message.get("method")
    if not isinstance(method, str):
        return jsonrpc_error(request_id, -32600, "Invalid Request")
    if request_id is None:
        return None
    params = message.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return jsonrpc_error(request_id, -32602, "Invalid params")
    if method == "initialize":
        requested = params.get("protocolVersion")
        protocol_version = (
            requested
            if isinstance(requested, str)
            and requested in SUPPORTED_PROTOCOL_VERSIONS
            else LATEST_PROTOCOL_VERSION
        )
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
                "instructions": SERVER_INSTRUCTIONS,
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS},
        }
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str):
            return jsonrpc_error(request_id, -32602, "Invalid params")
        try:
            result = call_tool(name, params.get("arguments"))
        except ToolInputError as error:
            result = {
                "content": [{"type": "text", "text": str(error)}],
                "structuredContent": {
                    "ok": False,
                    "stage": "ARGUMENT",
                    "category": "MCP_ARGUMENT_INVALID",
                    "retryable": False,
                    "databaseContacted": False,
                    "attempts": 1,
                },
                "isError": True,
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    return jsonrpc_error(request_id, -32601, "Method not found")


def write_message(message: dict[str, Any]) -> None:
    sys.stdout.write(
        json.dumps(
            message,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    sys.stdout.flush()


def serve() -> int:
    for raw_line in sys.stdin:
        if not raw_line.strip():
            continue
        try:
            message = json.loads(raw_line)
        except json.JSONDecodeError:
            write_message(jsonrpc_error(None, -32700, "Parse error"))
            continue
        try:
            response = handle_request(message)
        except Exception:
            request_id = message.get("id") if isinstance(message, dict) else None
            response = jsonrpc_error(
                request_id,
                -32603,
                "Internal error; details were suppressed",
            )
        if response is not None:
            write_message(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
