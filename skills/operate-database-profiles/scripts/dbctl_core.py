#!/usr/bin/env python3
"""Cross-platform controlled launcher for profile-based database access."""

from __future__ import annotations

import ctypes
import csv
import contextlib
import getpass
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, NamedTuple, Optional, Union


SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
MAC_KEYCHAIN_SERVICE = "com.openai.codex.dbctl.database-password.v1"
WINDOWS_CREDENTIAL_PREFIX = "OpenAI.Codex.dbctl.database-password.v1/"
PRODUCTION_MAX_ROWS = 200
PRODUCTION_MAX_FIELD_WIDTH = 256
PRODUCTION_MAX_OUTPUT_BYTES = 64 * 1024
PRODUCTION_QUERY_TIMEOUT_SECONDS = 30
PRODUCTION_LOCK_TIMEOUT_MS = 5000
MAX_SQL_FILE_BYTES = 1024 * 1024
SUPPORTED_ENGINES = {"postgresql", "sqlserver"}
DBCTL_VERSION = "2.2.0"
CLIENT_VERSION_TIMEOUT_SECONDS = 5
MACOS_SQLCMD_CANDIDATES = (
    Path("/opt/homebrew/opt/mssql-tools18/bin/sqlcmd"),
    Path("/usr/local/opt/mssql-tools18/bin/sqlcmd"),
    Path("/opt/homebrew/bin/sqlcmd"),
    Path("/usr/local/bin/sqlcmd"),
)
LINUX_SQLCMD_CANDIDATES = (
    Path("/opt/mssql-tools18/bin/sqlcmd"),
    Path("/opt/mssql-tools/bin/sqlcmd"),
)
TRANSIENT_RETRY_DELAYS_SECONDS = (0.5, 1.5)
NON_PRODUCTION_MAX_ATTEMPTS = len(TRANSIENT_RETRY_DELAYS_SECONDS) + 1
TRANSIENT_CLIENT_CATEGORIES = {
    "CONNECTION_CLOSED",
    "NETWORK_CONNECT",
    "NETWORK_TIMEOUT",
    "TCP_REFUSED",
}
PROGRAMMATIC_INVOKE_LOCK = threading.Lock()


class SqlSnapshot(NamedTuple):
    path: Path
    text: str


class SqlToken(NamedTuple):
    kind: str
    value: str
    start: int
    end: int

    @property
    def is_identifier(self) -> bool:
        return self.kind in {"word", "quoted-identifier", "unicode-quoted-identifier"}


class DatabasePlan(NamedTuple):
    command_name: str
    project: str
    target: str
    context: dict[str, Any]
    profile: dict[str, Any]
    client: Path
    sql_snapshot: Optional[SqlSnapshot]
    production_target: bool
    production_read: bool
    confirm_idempotent_retry: bool


class DbctlError(Exception):
    def __init__(
        self,
        message: str,
        *,
        stage: str = "LOCAL",
        category: str = "VALIDATION",
        retryable: bool = False,
        database_contacted: bool = False,
        attempts: int = 1,
        next_action: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.category = category
        self.retryable = retryable
        self.database_contacted = database_contacted
        self.attempts = attempts
        self.next_action = next_action


def die(
    message: str,
    *,
    stage: str = "LOCAL",
    category: str = "VALIDATION",
    retryable: bool = False,
    database_contacted: bool = False,
    attempts: int = 1,
    next_action: Optional[str] = None,
) -> "NoReturn":
    raise DbctlError(
        message,
        stage=stage,
        category=category,
        retryable=retryable,
        database_contacted=database_contacted,
        attempts=attempts,
        next_action=next_action,
    )


def launcher_build_id() -> str:
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        return "UNAVAILABLE"


def version_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "version": DBCTL_VERSION,
        "buildId": launcher_build_id(),
        "features": [
            "categorized-errors",
            "client-selection-diagnostics",
            "immutable-sql-snapshot",
            "json-diagnostics",
            "operation-preflight",
            "programmatic-json-api",
            "production-read-controls",
            "sqlcmd-odbc-first",
            "stdio-mcp",
        ],
    }


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def error_payload(error: DbctlError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "message": str(error),
        "stage": error.stage,
        "category": error.category,
        "retryable": error.retryable,
        "databaseContacted": error.database_contacted,
        "attempts": error.attempts,
    }
    if error.next_action:
        payload["nextAction"] = error.next_action
    return payload


def error_exit_code(error: DbctlError) -> int:
    if error.stage in {"INDEX", "TARGET", "PROFILE", "CREDENTIAL"}:
        return 20
    if error.stage in {"ARGUMENT", "POLICY", "SQL", "PREFLIGHT"}:
        return 30
    if error.stage in {"CLIENT", "CONNECT"}:
        return 40
    if error.stage in {"EXECUTE", "OUTPUT"}:
        return 50
    return 1


def usage() -> str:
    return """Usage:
  dbctl help
  dbctl version [--json]
  dbctl list <project>
  dbctl describe <project> <target>
  dbctl ping <project> <target> [--allow-production]
  dbctl query <project> <target> --file <sql-file> [--allow-production]
      [--confirm-idempotent-retry]
  dbctl exec <project> <target> --file <sql-file> --confirm-write
      [--confirm-idempotent-retry]
  dbctl preflight <project> <target> --operation ping|query|exec
      [--file <sql-file>] [--allow-production] [--confirm-write]
      [--confirm-idempotent-retry] [--json]
  dbctl credential status <project> <target>
  dbctl credential set <project> <target> [--migrate-profile]
  dbctl credential delete <project> <target> --confirm-delete
  dbctl profile init <project> <target> [--engine sqlserver|postgresql]
      [--credential-mode inline|system]
  dbctl bootstrap
  dbctl doctor [<project> [<target>]]

Global diagnostic flag:
  --json  Emit a machine-readable result for help, version, list, describe,
          doctor, credential status, preflight, ping, query, or exec."""


def safe_name(value: str) -> str:
    if not SAFE_NAME.fullmatch(value):
        die(
            "invalid project or target name",
            stage="ARGUMENT",
            category="INVALID_NAME",
        )
    return value


def credential_root() -> Path:
    configured = os.environ.get("DB_PROFILE_HOME")
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            die("DB_PROFILE_HOME must be an absolute path")
        return root
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            die("LOCALAPPDATA is not available")
        return Path(local_app_data) / "operate-database-profiles"
    return Path.home() / ".local" / "share" / "database"


def is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name != "nt" or not path.exists():
        return False
    try:
        return bool(getattr(os.lstat(path), "st_file_attributes", 0) & 0x400)
    except OSError:
        die("profile root could not be inspected")


def windows_acl_helper(root: Path, check_only: bool) -> bool:
    script = Path(__file__).with_name("set-profile-acl.ps1")
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not powershell or not script.is_file():
        return False
    command = [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script)]
    if check_only:
        command.append("-Check")
    command.append(str(root))
    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def profile_root_state(root: Path) -> str:
    if is_link_like(root):
        return "LINK_REJECTED"
    if not root.is_dir():
        return "MISSING"
    if os.name == "nt":
        return "OK" if windows_acl_helper(root, True) else "ACL_INVALID"
    info = root.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        return "PERMISSIONS_INVALID"
    return "OK"


def require_secure_file(
    path: Path,
    description: str,
    *,
    stage: str = "LOCAL",
    category: str = "FILE_INVALID",
) -> None:
    if not path.is_file():
        die(f"{description} not found", stage=stage, category=category)
    if path.is_symlink():
        die(f"{description} cannot be a symbolic link", stage=stage, category=category)
    if os.name != "nt":
        info = path.stat()
        if stat.S_IMODE(info.st_mode) != 0o600:
            die(f"{description} must have mode 600", stage=stage, category=category)
        if info.st_uid != os.getuid():
            die(f"{description} owner is invalid", stage=stage, category=category)


def read_json(
    path: Path,
    description: str,
    *,
    stage: str = "LOCAL",
    category: str = "JSON_INVALID",
) -> dict[str, Any]:
    require_secure_file(path, description, stage=stage, category=category)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        die(f"invalid {description}", stage=stage, category=category)
    if not isinstance(value, dict):
        die(f"invalid {description}", stage=stage, category=category)
    return value


def load_index(project: str) -> dict[str, Any]:
    root = credential_root()
    if profile_root_state(root) != "OK":
        die(
            "profile root permissions are invalid; run bootstrap",
            stage="INDEX",
            category="PROFILE_ROOT_INVALID",
            next_action="run dbctl bootstrap",
        )
    project_dir = root / project
    if is_link_like(project_dir):
        die("project profile directory cannot be a symbolic link or reparse point")
    index_file = project_dir / "index.json"
    index = read_json(
        index_file,
        "project index",
        stage="INDEX",
        category="INDEX_FILE_INVALID",
    )
    if (
        index.get("schemaVersion") != 1
        or index.get("project") != project
        or not isinstance(index.get("queryRoot"), str)
        or not Path(index["queryRoot"]).is_absolute()
        or not isinstance(index.get("targets"), dict)
    ):
        die(
            "invalid project index",
            stage="INDEX",
            category="INDEX_INVALID",
        )

    query_root = Path(index["queryRoot"])
    if not query_root.is_dir():
        die(
            "query root not found",
            stage="INDEX",
            category="QUERY_ROOT_NOT_FOUND",
        )
    if query_root.is_symlink():
        die(
            "query root cannot be a symbolic link",
            stage="INDEX",
            category="QUERY_ROOT_INVALID",
        )
    index["_file"] = index_file
    index["_query_root"] = query_root.resolve(strict=True)
    return index


def load_target(index: dict[str, Any], project: str, target: str) -> dict[str, Any]:
    safe_name(target)
    metadata = index["targets"].get(target)
    if not isinstance(metadata, dict):
        die(
            "unknown or invalid target; run dbctl list with the exact project name",
            stage="TARGET",
            category="TARGET_NOT_FOUND",
            next_action="run dbctl list <project>",
        )
    profile_rel = metadata.get("profile")
    engine = metadata.get("engine")
    environment = metadata.get("environment")
    access = metadata.get("access")
    if (
        not isinstance(profile_rel, str)
        or engine not in SUPPORTED_ENGINES
        or environment not in {"testing", "production"}
        or access not in {"read-write", "read-only"}
    ):
        die(
            "unknown or invalid target metadata",
            stage="TARGET",
            category="TARGET_INVALID",
        )
    rel = Path(profile_rel)
    if (
        len(rel.parts) != 2
        or rel.parts[0] != "profiles"
        or rel.suffix.lower() != ".json"
        or any(part in {"", ".", ".."} for part in rel.parts)
        or not all(re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in rel.parts)
    ):
        die(
            "invalid profile mapping",
            stage="TARGET",
            category="PROFILE_MAPPING_INVALID",
        )
    profile_file = credential_root() / project / rel
    if is_link_like(profile_file.parent):
        die("profile directory cannot be a symbolic link or reparse point")
    return {
        "project": project,
        "target": target,
        "engine": engine,
        "environment": environment,
        "access": access,
        "profile_file": profile_file,
        "query_root": index["_query_root"],
    }


def expected_secret_ref(project: str, target: str) -> str:
    return f"{safe_name(project)}/{safe_name(target)}"


def load_profile(context: dict[str, Any]) -> dict[str, Any]:
    profile = read_json(
        context["profile_file"],
        "credential profile",
        stage="PROFILE",
        category="PROFILE_FILE_INVALID",
    )
    if profile.get("schemaVersion") not in {1, 2}:
        die(
            "invalid credential profile schema",
            stage="PROFILE",
            category="PROFILE_SCHEMA_INVALID",
        )
    if any(
        profile.get(field) != context[field]
        for field in ("project", "target", "environment", "engine", "access")
    ):
        die(
            "credential profile does not match target metadata",
            stage="PROFILE",
            category="PROFILE_CONTEXT_MISMATCH",
        )
    if (
        not isinstance(profile.get("host"), str)
        or not profile.get("host")
        or not isinstance(profile.get("port"), int)
        or isinstance(profile.get("port"), bool)
        or not 1 <= profile["port"] <= 65535
        or not isinstance(profile.get("database"), str)
        or not profile.get("database")
        or (
            context["engine"] == "postgresql"
            and ("=" in profile["database"] or "://" in profile["database"])
        )
        or not isinstance(profile.get("username"), str)
        or not profile.get("username")
        or not isinstance(profile.get("encrypt"), bool)
        or not isinstance(profile.get("trustServerCertificate"), bool)
    ):
        die(
            "invalid credential profile connection metadata",
            stage="PROFILE",
            category="PROFILE_CONNECTION_METADATA_INVALID",
        )

    has_password_field = "password" in profile
    has_password = isinstance(profile.get("password"), str) and bool(profile.get("password"))
    has_provider = profile.get("secretProvider") == "system"
    has_ref = isinstance(profile.get("secretRef"), str) and bool(profile.get("secretRef"))
    if has_password_field and (has_provider or has_ref):
        die(
            "credential profile has ambiguous secret configuration",
            stage="PROFILE",
            category="PROFILE_MODE_CONFLICT",
        )
    if profile["schemaVersion"] == 1:
        if not has_password or has_provider or has_ref:
            die(
                "invalid inline credential profile",
                stage="PROFILE",
                category="PROFILE_INLINE_INVALID",
            )
        profile["_secret_mode"] = "inline"
    else:
        if has_password_field or not has_provider or not has_ref:
            die(
                "invalid secret-backed credential profile",
                stage="PROFILE",
                category="PROFILE_SYSTEM_INVALID",
            )
        if profile["secretRef"] != expected_secret_ref(context["project"], context["target"]):
            die(
                "invalid secret reference",
                stage="PROFILE",
                category="SECRET_REFERENCE_MISMATCH",
            )
        profile["_secret_mode"] = "system"
    return profile


class MacOSKeychainProvider:
    def __init__(self, security: str = "/usr/bin/security") -> None:
        self.security = security

    def _base(self, secret_ref: str) -> list[str]:
        return ["-a", secret_ref, "-s", MAC_KEYCHAIN_SERVICE]

    def status(self, secret_ref: str) -> bool:
        result = subprocess.run(
            [self.security, "find-generic-password", *self._base(secret_ref)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return True
        if result.returncode == 44:
            return False
        die(
            "keychain credential status failed; details were suppressed",
            stage="CREDENTIAL",
            category="CREDENTIAL_PROVIDER_UNAVAILABLE",
        )

    def get(self, secret_ref: str) -> str:
        result = subprocess.run(
            [self.security, "find-generic-password", *self._base(secret_ref), "-w"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 44:
            die(
                "credential is not configured",
                stage="CREDENTIAL",
                category="CREDENTIAL_ABSENT",
                next_action="run dbctl credential set in an interactive terminal",
            )
        if result.returncode != 0:
            die(
                "keychain credential lookup failed; details were suppressed",
                stage="CREDENTIAL",
                category="CREDENTIAL_PROVIDER_UNAVAILABLE",
            )
        secret = result.stdout
        if secret.endswith(b"\n"):
            secret = secret[:-1]
        if secret.endswith(b"\r"):
            secret = secret[:-1]
        try:
            value = secret.decode("utf-8")
        except UnicodeDecodeError:
            die(
                "keychain credential is invalid",
                stage="CREDENTIAL",
                category="CREDENTIAL_INVALID",
            )
        if not value:
            die(
                "keychain credential is empty",
                stage="CREDENTIAL",
                category="CREDENTIAL_INVALID",
            )
        return value

    def set(self, secret_ref: str) -> None:
        if not sys.stdin.isatty():
            die("credential setup requires an interactive terminal")
        result = subprocess.run(
            [
                self.security,
                "add-generic-password",
                "-U",
                *self._base(secret_ref),
                "-l",
                f"dbctl {secret_ref}",
                "-D",
                "dbctl database password",
                "-w",
            ],
            check=False,
        )
        if result.returncode != 0:
            die("keychain credential setup failed; details were suppressed")
        if not self.status(secret_ref):
            die("keychain credential verification failed")

    def delete(self, secret_ref: str) -> None:
        result = subprocess.run(
            [self.security, "delete-generic-password", *self._base(secret_ref)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 44:
            die("credential is not configured")
        if result.returncode != 0:
            die("keychain credential deletion failed; details were suppressed")


class WindowsCredentialApi:
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168
    ERROR_NO_SUCH_LOGON_SESSION = 1312

    def __init__(self) -> None:
        if os.name != "nt":
            die(
                "Windows Credential Manager is unavailable on this platform",
                stage="CREDENTIAL",
                category="CREDENTIAL_PROVIDER_UNAVAILABLE",
            )
        from ctypes import wintypes

        class CredentialW(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        self.CredentialW = CredentialW
        self.advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self.advapi32.CredWriteW.argtypes = [ctypes.POINTER(CredentialW), wintypes.DWORD]
        self.advapi32.CredWriteW.restype = wintypes.BOOL
        self.advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(CredentialW)),
        ]
        self.advapi32.CredReadW.restype = wintypes.BOOL
        self.advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.advapi32.CredDeleteW.restype = wintypes.BOOL
        self.advapi32.CredFree.argtypes = [ctypes.c_void_p]
        self.advapi32.CredFree.restype = None

    def _target(self, secret_ref: str) -> str:
        return WINDOWS_CREDENTIAL_PREFIX + secret_ref

    def write(self, secret_ref: str, secret: str) -> None:
        blob = bytearray(secret.encode("utf-16-le"))
        if len(blob) > 2560:
            die("credential is too large for Windows Credential Manager")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer(blob)
        credential = self.CredentialW()
        credential.Flags = 0
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = self._target(secret_ref)
        credential.Comment = "dbctl database password"
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        credential.AttributeCount = 0
        credential.Attributes = None
        credential.TargetAlias = None
        credential.UserName = None
        try:
            if not self.advapi32.CredWriteW(ctypes.byref(credential), 0):
                die("Windows credential setup failed; details were suppressed")
        finally:
            ctypes.memset(buffer, 0, len(blob))
            blob[:] = b"\x00" * len(blob)

    def _read(self, secret_ref: str, include_secret: bool) -> Optional[str]:
        pointer = ctypes.POINTER(self.CredentialW)()
        if not self.advapi32.CredReadW(
            self._target(secret_ref), self.CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)
        ):
            error = ctypes.get_last_error()
            if error == self.ERROR_NOT_FOUND:
                return None
            if error == self.ERROR_NO_SUCH_LOGON_SESSION:
                die(
                    "Windows credential store is unavailable for this logon session",
                    stage="CREDENTIAL",
                    category="CREDENTIAL_PROVIDER_UNAVAILABLE",
                )
            die(
                "Windows credential lookup failed; details were suppressed",
                stage="CREDENTIAL",
                category="CREDENTIAL_PROVIDER_UNAVAILABLE",
            )
        credential_blob = None
        credential_blob_size = 0
        try:
            credential = pointer.contents
            credential_blob = credential.CredentialBlob
            credential_blob_size = credential.CredentialBlobSize
            if credential_blob_size > 2560 or credential_blob_size % 2 != 0:
                die("Windows credential is invalid")
            if not include_secret:
                return "present"
            blob = ctypes.string_at(credential_blob, credential_blob_size)
            try:
                value = blob.decode("utf-16-le")
            except UnicodeDecodeError:
                die("Windows credential is invalid")
            if not value:
                die("Windows credential is empty")
            return value
        finally:
            if credential_blob and credential_blob_size:
                ctypes.memset(credential_blob, 0, credential_blob_size)
            self.advapi32.CredFree(pointer)

    def read(self, secret_ref: str) -> Optional[str]:
        return self._read(secret_ref, True)

    def status(self, secret_ref: str) -> bool:
        return self._read(secret_ref, False) is not None

    def delete(self, secret_ref: str) -> bool:
        if self.advapi32.CredDeleteW(self._target(secret_ref), self.CRED_TYPE_GENERIC, 0):
            return True
        error = ctypes.get_last_error()
        if error == self.ERROR_NOT_FOUND:
            return False
        if error == self.ERROR_NO_SUCH_LOGON_SESSION:
            die("Windows credential store is unavailable for this logon session")
        die("Windows credential deletion failed; details were suppressed")


class WindowsCredentialProvider:
    def __init__(self, api: Optional[Any] = None) -> None:
        self.api = api or WindowsCredentialApi()

    def status(self, secret_ref: str) -> bool:
        return bool(self.api.status(secret_ref))

    def get(self, secret_ref: str) -> str:
        value = self.api.read(secret_ref)
        if value is None:
            die(
                "credential is not configured",
                stage="CREDENTIAL",
                category="CREDENTIAL_ABSENT",
                next_action="run dbctl credential set in an interactive terminal",
            )
        return value

    def set(self, secret_ref: str) -> None:
        secret = prompt_confirmed_password()
        self.api.write(secret_ref, secret)
        secret = ""
        if not self.status(secret_ref):
            die("Windows credential verification failed")

    def delete(self, secret_ref: str) -> None:
        if not self.api.delete(secret_ref):
            die("credential is not configured")


def secret_provider() -> Union[MacOSKeychainProvider, WindowsCredentialProvider]:
    if sys.platform == "darwin":
        return MacOSKeychainProvider()
    if os.name == "nt":
        return WindowsCredentialProvider()
    die(
        "system credential provider is unsupported on this platform",
        stage="CREDENTIAL",
        category="CREDENTIAL_PROVIDER_UNAVAILABLE",
    )


def resolve_password(profile: dict[str, Any]) -> str:
    if profile["_secret_mode"] == "inline":
        return profile["password"]
    return secret_provider().get(profile["secretRef"])


def trusted_windows_program_roots() -> list[Path]:
    try:
        import winreg
    except ImportError:
        die("trusted Windows installation roots could not be resolved")

    roots: list[Path] = []
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion",
        ) as key:
            for value_name in (
                "ProgramFilesDir",
                "ProgramFilesDir (x86)",
                "ProgramFilesDir (Arm)",
            ):
                try:
                    value, _ = winreg.QueryValueEx(key, value_name)
                except OSError:
                    continue
                if isinstance(value, str) and value:
                    try:
                        root = Path(value).resolve(strict=True)
                    except OSError:
                        continue
                    if root not in roots:
                        roots.append(root)
    except OSError:
        die("trusted Windows installation roots could not be resolved")
    if not roots:
        die("trusted Windows installation roots could not be resolved")
    return roots


def validate_production_client_path(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        info = resolved.stat()
    except OSError:
        die("production database client path could not be validated")
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        die("production database client is not executable")
    if os.name == "nt":
        approved_roots = trusted_windows_program_roots()
        if not any(
            resolved == root or root in resolved.parents
            for root in approved_roots
        ):
            die("production database client must be installed under Program Files")
    else:
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            die("production database client cannot be group- or world-writable")
        approved_roots = [Path("/usr"), Path("/opt")]
        if not any(
            resolved == root or root in resolved.parents
            for root in approved_roots
        ):
            die("production database client must be installed under /usr or /opt")
    return resolved


def unique_paths(paths: list[Path]) -> list[Path]:
    return list(dict.fromkeys(paths))


def default_sqlcmd_candidates() -> list[Path]:
    candidates: list[Path] = []
    if sys.platform == "darwin":
        candidates.extend(MACOS_SQLCMD_CANDIDATES)
    elif os.name != "nt":
        candidates.extend(LINUX_SQLCMD_CANDIDATES)
    discovered = shutil.which("sqlcmd.exe" if os.name == "nt" else "sqlcmd")
    if discovered:
        candidates.append(Path(discovered))
    return unique_paths(candidates)


def find_sqlcmd(*, production: bool = False) -> Path:
    configured = os.environ.get("DBCTL_SQLCMD")
    candidates: list[Path] = []
    if configured:
        if production:
            die("DBCTL_SQLCMD override is not allowed for production targets")
        configured_path = Path(configured).expanduser()
        if not configured_path.is_absolute():
            die("DBCTL_SQLCMD must be an absolute path")
        candidates.append(configured_path)
    candidates.extend(default_sqlcmd_candidates())
    for candidate in unique_paths(candidates):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return validate_production_client_path(candidate) if production else candidate
    die("sqlcmd is not installed at an approved path")


def find_psql(*, production: bool = False) -> Path:
    configured = os.environ.get("DBCTL_PSQL")
    candidates: list[Path] = []
    if configured:
        if production:
            die("DBCTL_PSQL override is not allowed for production targets")
        configured_path = Path(configured).expanduser()
        if not configured_path.is_absolute():
            die("DBCTL_PSQL must be an absolute path")
        candidates.append(configured_path)
    if sys.platform == "darwin":
        candidates.extend(
            [
                Path("/opt/homebrew/bin/psql"),
                Path("/opt/homebrew/opt/libpq/bin/psql"),
                Path("/usr/local/bin/psql"),
                Path("/usr/local/opt/libpq/bin/psql"),
            ]
        )
    discovered = shutil.which("psql.exe" if os.name == "nt" else "psql")
    if discovered:
        candidates.append(Path(discovered))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return validate_production_client_path(candidate) if production else candidate
    die("psql is not installed at an approved path")


def find_database_client(engine: str, *, production: bool = False) -> Path:
    if engine == "sqlserver":
        return find_sqlcmd(production=production)
    if engine == "postgresql":
        return find_psql(production=production)
    die("database engine is not supported")


def sqlcmd_variant(path: Path) -> str:
    representations = [str(path).lower().replace("\\", "/")]
    try:
        representations.append(str(path.resolve(strict=True)).lower().replace("\\", "/"))
    except OSError:
        pass
    if any(
        marker in value
        for value in representations
        for marker in (
            "/mssql-tools/",
            "/mssql-tools18/",
            "/microsoft sql server/",
            "/client sdk/odbc/",
            "/tools/binn/",
        )
    ):
        return "ODBC"
    if any(
        marker in value
        for value in representations
        for marker in (
            "/cellar/sqlcmd/",
            "/program files/sqlcmd/",
        )
    ):
        return "GO"
    return "UNKNOWN"


def diagnostic_client_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("SQLCMD", "PG", "PSQL", "DBCTL_"))
    }


def parse_client_identity(
    engine: str,
    output: str,
    variant_hint: str,
) -> tuple[str, str]:
    if engine == "postgresql":
        match = re.search(r"(?i)psql\s+\(PostgreSQL\)\s+([^\s]+)", output)
        return "PSQL", match.group(1) if match else "UNAVAILABLE"
    go_match = re.search(r"(?im)^Version:\s*([^\s]+)", output)
    if go_match:
        return "GO", go_match.group(1)
    odbc_match = re.search(r"(?im)^Version\s+([^\s]+)", output)
    if odbc_match:
        return "ODBC", odbc_match.group(1)
    return variant_hint, "UNAVAILABLE"


def probe_client_identity(engine: str, path: Path) -> tuple[str, str]:
    variant = sqlcmd_variant(path) if engine == "sqlserver" else "PSQL"
    if engine == "sqlserver":
        probes = (
            [[str(path), "-?"]]
            if variant == "ODBC"
            else [[str(path), "--version"]]
            if variant == "GO"
            else [[str(path), "--version"], [str(path), "-?"]]
        )
    else:
        probes = [[str(path), "--version"]]
    for args in probes:
        try:
            result = subprocess.run(
                args,
                check=False,
                env=diagnostic_client_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=CLIENT_VERSION_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        detected_variant, version = parse_client_identity(
            engine,
            result.stdout or "",
            variant,
        )
        if version != "UNAVAILABLE":
            return detected_variant, version
    return variant, "UNAVAILABLE"


def client_path_class(path: Path, *, production: bool = False) -> str:
    if production:
        return "TRUSTED_SYSTEM"
    try:
        validate_production_client_path(path)
    except DbctlError:
        return "LOCAL_OR_CUSTOM"
    return "TRUSTED_SYSTEM"


def client_metadata(
    engine: str,
    path: Path,
    *,
    probe_version: bool,
    production: bool = False,
) -> dict[str, str]:
    variant = sqlcmd_variant(path) if engine == "sqlserver" else "PSQL"
    version = "NOT_PROBED"
    if probe_version:
        variant, version = probe_client_identity(engine, path)
    return {
        "state": "OK",
        "engine": engine,
        "variant": variant,
        "version": version,
        "pathClass": client_path_class(path, production=production),
    }


def load_sql_snapshot(
    sql_file: str,
    query_root: Path,
    *,
    production: bool = False,
) -> SqlSnapshot:
    path = Path(sql_file)
    if not path.is_absolute() or path.suffix.lower() != ".sql":
        die("SQL file must be an absolute .sql path")
    if not path.is_file():
        die("SQL file not found")
    if path.is_symlink():
        die("SQL file cannot be a symbolic link")
    resolved = path.resolve(strict=True)
    query_root = query_root.resolve(strict=True)
    try:
        resolved.relative_to(query_root)
    except ValueError:
        die("SQL file must be inside the configured query root")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: Optional[int] = None
    try:
        descriptor = os.open(resolved, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            die("SQL file must be a regular file")
        if before.st_size > MAX_SQL_FILE_BYTES:
            die("SQL file exceeds the size limit")
        if production and os.name != "nt" and before.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            die("production SQL file cannot be group- or world-writable")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, MAX_SQL_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_SQL_FILE_BYTES:
                die("SQL file exceeds the size limit")
        after = os.fstat(descriptor)
    except OSError:
        die("SQL file could not be validated")
    finally:
        if descriptor is not None:
            os.close(descriptor)

    try:
        current = resolved.lstat()
    except OSError:
        die("SQL file changed while it was being validated")
    if (
        current.st_dev != after.st_dev
        or current.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        die("SQL file changed while it was being validated")

    try:
        text = b"".join(chunks).decode("utf-8-sig")
    except UnicodeDecodeError:
        die("SQL file could not be validated")
    for line in text.splitlines():
        if re.match(r"^\s*(?::|!!|\\)", line):
            die("database client meta-commands are not allowed")
    if "\\" in visible_sql_text(text):
        die("database client meta-commands are not allowed")
    return SqlSnapshot(path=resolved, text=text)


def validate_sql_file(sql_file: str, query_root: Path) -> Path:
    return load_sql_snapshot(sql_file, query_root).path


def read_sql_text(sql_file: Path) -> str:
    try:
        return sql_file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        die("SQL file could not be validated")


def visible_sql_text(text: str) -> str:
    visible: list[str] = []
    position = 0
    block_depth = 0
    state = "normal"
    while position < len(text):
        character = text[position]
        following = text[position + 1] if position + 1 < len(text) else ""
        if state == "line-comment":
            if character in "\r\n":
                state = "normal"
                visible.append(character)
            else:
                visible.append(" ")
        elif state == "block-comment":
            if character == "/" and following == "*":
                block_depth += 1
                visible.extend((" ", " "))
                position += 1
            elif character == "*" and following == "/":
                block_depth -= 1
                visible.extend((" ", " "))
                position += 1
                if block_depth == 0:
                    state = "normal"
            else:
                visible.append(" ")
        elif state in {"string", "quoted-identifier", "bracket-identifier"}:
            terminator = {"string": "'", "quoted-identifier": '"', "bracket-identifier": "]"}[state]
            visible.append(" ")
            if character == terminator:
                if following == terminator:
                    visible.append(" ")
                    position += 1
                else:
                    state = "normal"
        elif character == "-" and following == "-":
            state = "line-comment"
            visible.extend((" ", " "))
            position += 1
        elif character == "/" and following == "*":
            state = "block-comment"
            block_depth = 1
            visible.extend((" ", " "))
            position += 1
        elif character == "'":
            state = "string"
            visible.append(" ")
        elif character == '"':
            state = "quoted-identifier"
            visible.append(" ")
        elif character == "[":
            state = "bracket-identifier"
            visible.append(" ")
        else:
            visible.append(character)
        position += 1
    if state in {"string", "quoted-identifier", "bracket-identifier", "block-comment"}:
        die("SQL file contains an unterminated literal, identifier, or comment")
    return "".join(visible)


def lex_sql(text: str) -> list[SqlToken]:
    tokens: list[SqlToken] = []
    position = 0

    def quoted_identifier(start: int, opener_length: int, terminator: str) -> tuple[str, int]:
        value: list[str] = []
        cursor = start + opener_length
        while cursor < len(text):
            character = text[cursor]
            following = text[cursor + 1] if cursor + 1 < len(text) else ""
            if character == terminator:
                if following == terminator:
                    value.append(terminator)
                    cursor += 2
                    continue
                return "".join(value), cursor + 1
            value.append(character)
            cursor += 1
        die("SQL file contains an unterminated quoted identifier")

    while position < len(text):
        character = text[position]
        following = text[position + 1] if position + 1 < len(text) else ""

        if character.isspace():
            position += 1
            continue
        if character == "-" and following == "-":
            newline = text.find("\n", position + 2)
            position = len(text) if newline < 0 else newline + 1
            continue
        if character == "/" and following == "*":
            depth = 1
            cursor = position + 2
            while cursor < len(text) and depth:
                pair = text[cursor : cursor + 2]
                if pair == "/*":
                    depth += 1
                    cursor += 2
                elif pair == "*/":
                    depth -= 1
                    cursor += 2
                else:
                    cursor += 1
            if depth:
                die("SQL file contains an unterminated comment")
            position = cursor
            continue
        if (
            character in {"E", "e"}
            and following == "'"
            and (position == 0 or not re.match(r"[A-Za-z0-9_$#@]", text[position - 1]))
        ):
            cursor = position + 2
            while cursor < len(text):
                if text[cursor] == "\\" and cursor + 1 < len(text):
                    cursor += 2
                elif text[cursor] == "'":
                    if cursor + 1 < len(text) and text[cursor + 1] == "'":
                        cursor += 2
                    else:
                        cursor += 1
                        break
                else:
                    cursor += 1
            else:
                die("SQL file contains an unterminated string literal")
            tokens.append(SqlToken("string", "", position, cursor))
            position = cursor
            continue
        if character == "'":
            cursor = position + 1
            while cursor < len(text):
                if text[cursor] == "'":
                    if cursor + 1 < len(text) and text[cursor + 1] == "'":
                        cursor += 2
                    else:
                        cursor += 1
                        break
                else:
                    cursor += 1
            else:
                die("SQL file contains an unterminated string literal")
            tokens.append(SqlToken("string", "", position, cursor))
            position = cursor
            continue
        if character == "$":
            delimiter_match = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", text[position:])
            if delimiter_match:
                delimiter = delimiter_match.group(0)
                end = text.find(delimiter, position + len(delimiter))
                if end < 0:
                    die("SQL file contains an unterminated dollar-quoted string")
                end += len(delimiter)
                tokens.append(SqlToken("dollar-string", "", position, end))
                position = end
                continue
        if (
            character in {"U", "u"}
            and text[position + 1 : position + 3] == '&"'
            and (position == 0 or not re.match(r"[A-Za-z0-9_$#@]", text[position - 1]))
        ):
            value, end = quoted_identifier(position, 3, '"')
            tokens.append(
                SqlToken("unicode-quoted-identifier", value.upper(), position, end)
            )
            position = end
            continue
        if character == '"':
            value, end = quoted_identifier(position, 1, '"')
            tokens.append(SqlToken("quoted-identifier", value.upper(), position, end))
            position = end
            continue
        if character == "[":
            value, end = quoted_identifier(position, 1, "]")
            tokens.append(SqlToken("quoted-identifier", value.upper(), position, end))
            position = end
            continue
        word = re.match(r"[A-Za-z_][A-Za-z0-9_$#@]*", text[position:])
        if word:
            end = position + len(word.group(0))
            tokens.append(SqlToken("word", word.group(0).upper(), position, end))
            position = end
            continue
        tokens.append(SqlToken("symbol", character, position, position + 1))
        position += 1
    return tokens


def executable_sql_tokens(sql_file: Path) -> list[str]:
    return [
        token.value
        for token in lex_sql(read_sql_text(sql_file))
        if token.kind == "word"
    ]


def single_statement_sql_text(text: str) -> str:
    semicolons = [
        token.start
        for token in lex_sql(text)
        if token.kind == "symbol" and token.value == ";"
    ]
    boundaries = [-1, *semicolons, len(text)]
    statements: list[str] = []
    for index in range(len(boundaries) - 1):
        statement = text[boundaries[index] + 1 : boundaries[index + 1]].strip()
        if statement and lex_sql(statement):
            statements.append(statement)
    if len(statements) != 1:
        die("production query must contain exactly one statement")
    return statements[0]


def has_cross_database_identifier(tokens: list[SqlToken]) -> bool:
    for position, token in enumerate(tokens):
        if not token.is_identifier:
            continue
        dot_count = 0
        cursor = position + 1
        last_was_identifier = True
        while cursor < len(tokens):
            current = tokens[cursor]
            if current.kind == "symbol" and current.value == ".":
                dot_count += 1
                last_was_identifier = False
                cursor += 1
                continue
            if current.is_identifier and not last_was_identifier:
                last_was_identifier = True
                cursor += 1
                continue
            break
        if dot_count >= 2 and last_was_identifier:
            return True
    return False


def validate_read_query_text(
    text: str,
    *,
    production: bool = False,
    engine: Optional[str] = None,
) -> None:
    forbidden = {
        "ALTER",
        "BACKUP",
        "BULK",
        "CREATE",
        "DBCC",
        "DELETE",
        "DENY",
        "DROP",
        "EXEC",
        "EXECUTE",
        "GRANT",
        "INSERT",
        "INTO",
        "KILL",
        "MERGE",
        "RECONFIGURE",
        "RESTORE",
        "REVOKE",
        "SHUTDOWN",
        "TRUNCATE",
        "UPDATE",
        "UPDATETEXT",
        "USE",
        "WRITETEXT",
    }
    lexical_tokens = lex_sql(text)
    word_tokens = [
        token.value
        for token in lexical_tokens
        if token.kind == "word"
    ]
    first_token = next(
        (token for token in lexical_tokens if token.kind != "symbol"),
        None,
    )
    if (
        first_token is None
        or first_token.kind != "word"
        or first_token.value not in {"SELECT", "WITH"}
    ):
        die("query SQL must begin with SELECT or WITH; use exec with review for other batches")
    blocked = forbidden.intersection(word_tokens)
    if blocked:
        die("query SQL contains a write, execution, or database-switching keyword; use exec with review")
    if production:
        if engine not in SUPPORTED_ENGINES:
            die("production query validation requires a supported database engine")
        single_statement_sql_text(text)
        if any(
            token.kind in {"unicode-quoted-identifier", "dollar-string"}
            for token in lexical_tokens
        ):
            die("production query contains an unsupported quoted form")
        production_forbidden_keywords = {
            "BEGIN",
            "CALL",
            "COMMIT",
            "COPY",
            "DECLARE",
            "DO",
            "GO",
            "HOLDLOCK",
            "LISTEN",
            "LOAD",
            "NEXT",
            "NOTIFY",
            "PREPARE",
            "RAISERROR",
            "RECEIVE",
            "RESET",
            "ROLLBACK",
            "SAVEPOINT",
            "SET",
            "TABLOCKX",
            "THROW",
            "UNLISTEN",
            "UPDLOCK",
            "VACUUM",
            "WAITFOR",
            "XLOCK",
        }
        if production_forbidden_keywords.intersection(word_tokens):
            die("query SQL contains an unsafe production-read keyword")
        production_forbidden_identifiers = {
            "DBLINK",
            "DBLINK_CONNECT",
            "DBLINK_CONNECT_U",
            "DBLINK_EXEC",
            "LO_EXPORT",
            "LO_IMPORT",
            "NEXTVAL",
            "OPENDATASOURCE",
            "OPENQUERY",
            "OPENROWSET",
            "PG_ADVISORY_LOCK",
            "PG_ADVISORY_LOCK_SHARED",
            "PG_ADVISORY_XACT_LOCK",
            "PG_ADVISORY_XACT_LOCK_SHARED",
            "PG_BACKUP_START",
            "PG_BACKUP_STOP",
            "PG_CANCEL_BACKEND",
            "PG_CREATE_RESTORE_POINT",
            "PG_LOG_BACKEND_MEMORY_CONTEXTS",
            "PG_LOGICAL_EMIT_MESSAGE",
            "PG_LS_DIR",
            "PG_PROMOTE",
            "PG_READ_BINARY_FILE",
            "PG_READ_FILE",
            "PG_RELOAD_CONF",
            "PG_ROTATE_LOGFILE",
            "PG_STAT_FILE",
            "PG_SWITCH_WAL",
            "PG_TERMINATE_BACKEND",
            "PG_TRY_ADVISORY_LOCK",
            "PG_TRY_ADVISORY_LOCK_SHARED",
            "PG_TRY_ADVISORY_XACT_LOCK",
            "PG_TRY_ADVISORY_XACT_LOCK_SHARED",
            "PG_WAL_REPLAY_PAUSE",
            "PG_WAL_REPLAY_RESUME",
            "PG_WRITE_FILE",
            "SETVAL",
            "SP_EXECUTESQL",
            "XP_CMDSHELL",
        }
        identifier_values = {
            token.value
            for token in lexical_tokens
            if token.is_identifier
        }
        if production_forbidden_identifiers.intersection(identifier_values):
            die("query SQL contains an unsafe production-read identifier")
        if engine == "sqlserver" and has_cross_database_identifier(lexical_tokens):
            die("production SQL Server query contains a cross-database or cross-server name")


def validate_read_query(
    sql_file: Path,
    *,
    production: bool = False,
    engine: Optional[str] = None,
) -> None:
    validate_read_query_text(
        read_sql_text(sql_file),
        production=production,
        engine=engine or ("sqlserver" if production else None),
    )


def classify_ping_error(output: str) -> str:
    lowered = output.lower()
    if not lowered.strip():
        return "CLIENT_SILENT_FAILURE"
    if any(
        value in lowered
        for value in (
            "could not translate host name",
            "name or service not known",
            "no such host",
            "server not found",
        )
    ):
        return "DNS"
    if "connection refused" in lowered:
        return "TCP_REFUSED"
    if "network is unreachable" in lowered:
        return "NETWORK_UNREACHABLE"
    if any(
        value in lowered
        for value in (
            "connection timed out",
            "context deadline exceeded",
            "i/o timeout",
            "operation timed out",
            "timeout expired",
        )
    ):
        return "NETWORK_TIMEOUT"
    if any(
        value in lowered
        for value in (
            "x509",
            "certificate",
            "tls",
            "server does not support ssl",
            "ssl was required",
        )
    ):
        return "TLS"
    if any(
        value in lowered
        for value in (
            "authentication failed",
            "login failed",
            "no password supplied",
            "password authentication failed",
        )
    ):
        return "AUTHENTICATION"
    if "no pg_hba.conf entry" in lowered:
        return "PG_HBA_REJECTED"
    if "role " in lowered and " does not exist" in lowered:
        return "ROLE_NOT_FOUND"
    if "database " in lowered and " does not exist" in lowered:
        return "DATABASE_NOT_FOUND"
    if any(
        value in lowered
        for value in (
            "server closed the connection unexpectedly",
            "connection reset by peer",
            "eof",
        )
    ):
        return "CONNECTION_CLOSED"
    if any(
        value in lowered
        for value in (
            "cannot open database",
            "database does not exist",
            "permission denied for database",
            "unknown database",
        )
    ):
        return "DATABASE_ACCESS"
    if any(value in lowered for value in ("liner: function not supported", "password:")):
        return "CLIENT_INTERACTIVE"
    if any(
        value in lowered
        for value in (
            "dial tcp",
            "unable to open tcp connection",
            "failed to connect",
        )
    ):
        return "NETWORK_CONNECT"
    return "UNKNOWN"


def classify_execution_error(output: str) -> str:
    lowered = output.lower()
    if any(
        value in lowered
        for value in (
            "permission was denied",
            "permission denied",
            "does not have permission",
            "insufficient privilege",
        )
    ):
        return "PERMISSION_DENIED"
    if any(value in lowered for value in ("lock request time out", "lock timeout")):
        return "LOCK_TIMEOUT"
    if any(value in lowered for value in ("deadlock victim", "was deadlocked")):
        return "DEADLOCK"
    if any(
        value in lowered
        for value in (
            "conflicted with the",
            "constraint",
            "duplicate key",
        )
    ):
        return "CONSTRAINT"
    if any(value in lowered for value in ("incorrect syntax", "syntax error")):
        return "SQL_SYNTAX"
    sql_server_error = re.search(r"\bmsg\s+(\d+)\b", lowered)
    if sql_server_error:
        return f"SQL_SERVER_{sql_server_error.group(1)}"
    connection_category = classify_ping_error(output)
    if connection_category != "UNKNOWN":
        return connection_category
    if "mssql:" in lowered:
        return "MSSQL_DRIVER"
    if "sqlcmd:" in lowered:
        return "SQLCMD_CLIENT"
    return "SQL_EXECUTION"


def client_error_signals(output: str) -> str:
    allowed = (
        "argument",
        "authentication",
        "cancelled",
        "certificate",
        "client",
        "connect",
        "connection",
        "context",
        "database",
        "deadline",
        "eof",
        "error",
        "failed",
        "file",
        "flag",
        "handshake",
        "instance",
        "invalid",
        "login",
        "lookup",
        "mssql",
        "network",
        "open",
        "protocol",
        "refused",
        "server",
        "socket",
        "sqlcmd",
        "tcp",
        "timeout",
        "tls",
        "unexpected",
    )
    words = set(re.findall(r"[a-z]+", output.lower()))
    matched = sorted(word for word in allowed if word in words)
    return ",".join(matched) if matched else "NONE"


def run_nonproduction_client(
    args: list[str],
    env: dict[str, str],
    command_name: str,
    *,
    confirm_idempotent_retry: bool = False,
) -> tuple[Any, int]:
    max_attempts = (
        NON_PRODUCTION_MAX_ATTEMPTS
        if command_name == "ping"
        or (command_name in {"query", "exec"} and confirm_idempotent_retry)
        else 1
    )
    result: Any = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = subprocess.run(
                args,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                check=False,
            )
        except OSError:
            die(
                f"{command_name} client could not be started; details were suppressed",
                stage="CLIENT",
                category="CLIENT_START_FAILED",
                attempts=attempt,
            )
        if result.returncode == 0:
            return result, attempt
        category = (
            classify_ping_error(result.stdout)
            if command_name == "ping"
            else classify_execution_error(result.stdout)
        )
        if category not in TRANSIENT_CLIENT_CATEGORIES or attempt == max_attempts:
            return result, attempt
        time.sleep(TRANSIENT_RETRY_DELAYS_SECONDS[attempt - 1])
    return result, max_attempts


def create_runtime_sql_file(
    snapshot: SqlSnapshot,
    *,
    engine: str,
    production_read: bool,
) -> Path:
    if engine not in SUPPORTED_ENGINES:
        die("database engine is not supported")
    prefix = ".dbctl-production-read-" if production_read else ".dbctl-runtime-"
    fd, temporary_name = tempfile.mkstemp(
        prefix=prefix,
        suffix=".sql",
        dir=snapshot.path.parent,
    )
    temporary = Path(temporary_name)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            if not production_read:
                handle.write(snapshot.text)
                if not snapshot.text.endswith("\n"):
                    handle.write("\n")
            elif engine == "sqlserver":
                query = single_statement_sql_text(snapshot.text)
                handle.write(f"SET LOCK_TIMEOUT {PRODUCTION_LOCK_TIMEOUT_MS};\n")
                handle.write("SET DEADLOCK_PRIORITY LOW;\n")
                handle.write("SET NOCOUNT ON;\n")
                handle.write(f"SET ROWCOUNT {PRODUCTION_MAX_ROWS};\n")
                handle.write(query)
                if not query.endswith("\n"):
                    handle.write("\n")
            elif engine == "postgresql":
                query = single_statement_sql_text(snapshot.text)
                handle.write("BEGIN TRANSACTION READ ONLY;\n")
                handle.write(
                    f"SET LOCAL statement_timeout = '{PRODUCTION_QUERY_TIMEOUT_SECONDS}s';\n"
                )
                handle.write(f"SET LOCAL lock_timeout = '{PRODUCTION_LOCK_TIMEOUT_MS}ms';\n")
                handle.write("COPY (\nSELECT * FROM (\n")
                handle.write(query)
                handle.write(f"\n) AS dbctl_bounded_query\nLIMIT {PRODUCTION_MAX_ROWS}\n")
                handle.write(") TO STDOUT WITH (FORMAT CSV, HEADER TRUE);\n")
                handle.write("ROLLBACK;\n")
        return temporary
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def build_sqlcmd_args(
    sqlcmd: Path,
    profile: dict[str, Any],
    command_name: str,
    sql_file: Optional[Path],
    *,
    production_read: bool = False,
) -> list[str]:
    args = [
        str(sqlcmd),
        "-S",
        f"{profile['host']},{profile['port']}",
        "-d",
        profile["database"],
        "-U",
        profile["username"],
        "-b",
        "-r",
        "1",
        "-x",
        "-l",
        "15",
        "-Nm" if profile["encrypt"] else "-No",
    ]
    if profile["trustServerCertificate"]:
        args.append("-C")
    if production_read:
        args.extend(
            [
                "-t",
                str(PRODUCTION_QUERY_TIMEOUT_SECONDS),
                "-y",
                str(PRODUCTION_MAX_FIELD_WIDTH),
                "-Y",
                str(PRODUCTION_MAX_FIELD_WIDTH),
                "-w",
                "4096",
                "-W",
                "-k",
                "2",
            ]
        )
    if command_name == "ping":
        args.extend(["-Q", "SET NOCOUNT ON; SELECT 1 AS ConnectionOk;"])
    else:
        args.extend(["-i", str(sql_file)])
    return args


def build_psql_args(
    psql: Path,
    profile: dict[str, Any],
    command_name: str,
    sql_file: Optional[Path],
    *,
    production_read: bool = False,
) -> list[str]:
    args = [
        str(psql),
        "-X",
        "-w",
        "-v",
        "ON_ERROR_STOP=1",
        "-h",
        profile["host"],
        "-p",
        str(profile["port"]),
        "-d",
        profile["database"],
        "-U",
        profile["username"],
    ]
    if production_read:
        args.extend(["--csv", "-q"])
    if command_name == "ping":
        args.extend(["-c", "SELECT 1 AS connection_ok;"])
    else:
        args.extend(["-f", str(sql_file)])
    return args


def build_database_client_args(
    client: Path,
    profile: dict[str, Any],
    command_name: str,
    sql_file: Optional[Path],
    *,
    production_read: bool = False,
) -> list[str]:
    if profile["engine"] == "sqlserver":
        return build_sqlcmd_args(
            client,
            profile,
            command_name,
            sql_file,
            production_read=production_read,
        )
    if profile["engine"] == "postgresql":
        return build_psql_args(
            client,
            profile,
            command_name,
            sql_file,
            production_read=production_read,
        )
    die("database engine is not supported")


def client_environment(profile: dict[str, Any], password: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("SQLCMD", "PG", "PSQL"))
    }
    if profile["engine"] == "sqlserver":
        env["SQLCMDPASSWORD"] = password
    elif profile["engine"] == "postgresql":
        env.update(
            {
                "PGPASSWORD": password,
                "PGCONNECT_TIMEOUT": "15",
                "PGCLIENTENCODING": "UTF8",
                "PGAPPNAME": "dbctl",
                "PGSSLMODE": (
                    "disable"
                    if not profile["encrypt"]
                    else "require" if profile["trustServerCertificate"] else "verify-full"
                ),
            }
        )
    else:
        die("database engine is not supported")
    return env


def clear_client_password(env: dict[str, str]) -> None:
    env.pop("SQLCMDPASSWORD", None)
    env.pop("PGPASSWORD", None)


def bound_postgresql_csv_output(output: str) -> str:
    try:
        rows = list(csv.reader(io.StringIO(output)))
    except csv.Error:
        die(
            "PostgreSQL production output could not be safely parsed; results were suppressed",
            stage="OUTPUT",
            category="OUTPUT_PARSE_FAILED",
            database_contacted=True,
        )
    bounded = rows[: PRODUCTION_MAX_ROWS + 1]
    bounded = [
        [field[:PRODUCTION_MAX_FIELD_WIDTH] for field in row]
        for row in bounded
    ]
    rendered = io.StringIO()
    csv.writer(rendered, lineterminator="\n").writerows(bounded)
    return rendered.getvalue()


def run_bounded_production_client(
    argv: list[str],
    env: dict[str, str],
    *,
    operation_name: str = "query",
) -> tuple[int, str]:
    try:
        process = subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError:
        die(
            f"production {operation_name} client could not be started; "
            "details were suppressed",
            stage="CLIENT",
            category="CLIENT_START_FAILED",
        )
    if process.stdout is None:
        process.kill()
        process.wait()
        die(
            f"production {operation_name} output could not be captured",
            stage="OUTPUT",
            category="OUTPUT_CAPTURE_FAILED",
        )

    captured = bytearray()
    output_limit_exceeded = threading.Event()
    reader_failures: list[BaseException] = []

    def read_output() -> None:
        try:
            while True:
                chunk = process.stdout.read(8192)
                if not chunk:
                    break
                remaining = PRODUCTION_MAX_OUTPUT_BYTES + 1 - len(captured)
                if remaining > 0:
                    captured.extend(chunk[:remaining])
                if (
                    len(captured) > PRODUCTION_MAX_OUTPUT_BYTES
                    and not output_limit_exceeded.is_set()
                ):
                    output_limit_exceeded.set()
                    try:
                        process.kill()
                    except OSError:
                        pass
        except BaseException as error:
            reader_failures.append(error)
            try:
                process.kill()
            except OSError:
                pass

    reader = threading.Thread(target=read_output, name="dbctl-output-reader", daemon=True)
    reader.start()
    timed_out = False
    try:
        returncode = process.wait(timeout=PRODUCTION_QUERY_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        returncode = process.wait()
    finally:
        reader.join(timeout=5)
        if reader.is_alive():
            try:
                process.kill()
            except OSError:
                pass
            process.wait()
            reader.join(timeout=1)
        process.stdout.close()

    if reader.is_alive() or reader_failures:
        die(
            f"production {operation_name} output could not be captured safely",
            stage="OUTPUT",
            category="OUTPUT_CAPTURE_FAILED",
            database_contacted=True,
        )
    if timed_out:
        captured.clear()
        die(
            f"production {operation_name} timed out; "
            "output and connection details were suppressed",
            stage="EXECUTE",
            category="QUERY_TIMEOUT",
            database_contacted=True,
        )
    if output_limit_exceeded.is_set():
        captured.clear()
        die(
            f"production {operation_name} exceeded the output limit; "
            "results were suppressed",
            stage="OUTPUT",
            category="OUTPUT_LIMIT",
            database_contacted=True,
            next_action="reduce selected columns or use a bounded aggregate",
        )
    return returncode, captured.decode("utf-8", errors="replace")


def credential_state(profile: dict[str, Any]) -> str:
    if profile["_secret_mode"] == "inline":
        return "INLINE"
    return "PRESENT" if secret_provider().status(profile["secretRef"]) else "ABSENT"


def prepare_database_command(argv: list[str]) -> DatabasePlan:
    if len(argv) < 3:
        die(
            "database command requires a project and target",
            stage="ARGUMENT",
            category="ARGUMENT_INVALID",
        )
    command_name, project, target, *rest = argv
    safe_name(project)
    index = load_index(project)
    context = load_target(index, project, target)
    allow_production = False
    confirm_write = False
    confirm_idempotent_retry = False
    sql_file_value: Optional[str] = None
    position = 0
    while position < len(rest):
        value = rest[position]
        if value == "--allow-production":
            allow_production = True
            position += 1
        elif value == "--confirm-write":
            confirm_write = True
            position += 1
        elif value == "--confirm-idempotent-retry":
            confirm_idempotent_retry = True
            position += 1
        elif value == "--file" and position + 1 < len(rest):
            sql_file_value = rest[position + 1]
            position += 2
        else:
            die(
                "unknown argument",
                stage="ARGUMENT",
                category="ARGUMENT_INVALID",
            )

    environment = context["environment"]
    access = context["access"]
    if environment == "production" and not allow_production:
        die(
            "production target requires --allow-production",
            stage="POLICY",
            category="PRODUCTION_GATE_REJECTED",
        )
    if command_name == "ping":
        if sql_file_value is not None:
            die(
                "ping does not accept --file",
                stage="ARGUMENT",
                category="ARGUMENT_INVALID",
            )
        if confirm_write:
            die(
                "ping does not accept --confirm-write",
                stage="ARGUMENT",
                category="ARGUMENT_INVALID",
            )
        if confirm_idempotent_retry:
            die(
                "ping does not accept --confirm-idempotent-retry",
                stage="ARGUMENT",
                category="ARGUMENT_INVALID",
            )
    elif command_name == "query":
        if sql_file_value is None:
            die(
                "query requires --file",
                stage="ARGUMENT",
                category="ARGUMENT_INVALID",
            )
        if confirm_write:
            die(
                "query does not accept --confirm-write",
                stage="ARGUMENT",
                category="ARGUMENT_INVALID",
            )
        if environment == "production" and confirm_idempotent_retry:
            die(
                "production query retries are disabled",
                stage="POLICY",
                category="PRODUCTION_RETRY_REJECTED",
            )
    elif command_name == "exec":
        if sql_file_value is None:
            die(
                "exec requires --file",
                stage="ARGUMENT",
                category="ARGUMENT_INVALID",
            )
        if not confirm_write:
            die(
                "exec requires --confirm-write",
                stage="POLICY",
                category="WRITE_CONFIRMATION_REQUIRED",
            )
        if environment == "production":
            die(
                "production writes are disabled",
                stage="POLICY",
                category="PRODUCTION_WRITE_REJECTED",
            )
        if access == "read-only":
            die(
                "writes are disabled for read-only targets",
                stage="POLICY",
                category="READ_ONLY_TARGET",
            )
    else:
        die(
            "unknown database command",
            stage="ARGUMENT",
            category="ARGUMENT_INVALID",
        )

    production_target = environment == "production"
    sql_snapshot: Optional[SqlSnapshot] = None
    if sql_file_value is not None:
        try:
            sql_snapshot = load_sql_snapshot(
                sql_file_value,
                context["query_root"],
                production=production_target,
            )
            if command_name == "query":
                validate_read_query_text(
                    sql_snapshot.text,
                    production=production_target,
                    engine=context["engine"],
                )
        except DbctlError as error:
            if error.stage == "LOCAL":
                error.stage = "SQL"
                error.category = "SQL_POLICY_REJECTED"
            raise
    profile = load_profile(context)
    try:
        client = find_database_client(profile["engine"], production=production_target)
    except DbctlError as error:
        if error.stage == "LOCAL":
            error.stage = "CLIENT"
            error.category = "CLIENT_MISSING"
            error.next_action = "install or repair the declared native database client"
        raise
    production_read = production_target and command_name == "query"
    return DatabasePlan(
        command_name,
        project,
        target,
        context,
        profile,
        client,
        sql_snapshot,
        production_target,
        production_read,
        confirm_idempotent_retry,
    )


def run_database_command(argv: list[str], *, json_output: bool = False) -> int:
    plan = prepare_database_command(argv)
    command_name = plan.command_name
    project = plan.project
    target = plan.target
    context = plan.context
    profile = plan.profile
    client = plan.client
    sql_snapshot = plan.sql_snapshot
    production_target = plan.production_target
    production_read = plan.production_read
    confirm_idempotent_retry = plan.confirm_idempotent_retry
    environment = context["environment"]
    access = context["access"]
    password = resolve_password(profile)
    metadata: dict[str, Any] = {
        "ok": True,
        "project": project,
        "target": target,
        "environment": environment,
        "access": access,
        "operation": command_name,
        "databaseContacted": False,
        "client": client_metadata(
            profile["engine"],
            client,
            probe_version=False,
            production=production_target,
        ),
    }
    if not json_output:
        print(
            f"Project: {project}\nTarget: {target}\nEnvironment: {environment}\n"
            f"Access: {access}\nOperation: {command_name}\n"
            f"ClientVariant: {metadata['client']['variant']}\n"
            f"ClientPathClass: {metadata['client']['pathClass']}"
        )
    if profile["_secret_mode"] == "inline":
        profile["password"] = ""
    env = client_environment(profile, password)
    password = ""
    runtime_sql_file: Optional[Path] = None
    attempts = 1
    try:
        if sql_snapshot is not None:
            runtime_sql_file = create_runtime_sql_file(
                sql_snapshot,
                engine=profile["engine"],
                production_read=production_read,
            )
        if production_read:
            metadata.update(
                {
                    "productionReadControls": "ENFORCED",
                    "rowLimit": PRODUCTION_MAX_ROWS,
                    "outputLimitBytes": PRODUCTION_MAX_OUTPUT_BYTES,
                }
            )
            if not json_output:
                print(
                    "ProductionReadControls: ENFORCED\n"
                    f"RowLimit: {PRODUCTION_MAX_ROWS}\n"
                    f"OutputLimitBytes: {PRODUCTION_MAX_OUTPUT_BYTES}"
                )
        elif command_name in {"query", "exec"} and confirm_idempotent_retry:
            metadata.update(
                {
                    "idempotentRetry": "ENABLED",
                    "maxAttempts": NON_PRODUCTION_MAX_ATTEMPTS,
                }
            )
            if not json_output:
                print(
                    "IdempotentRetry: ENABLED\n"
                    f"MaxAttempts: {NON_PRODUCTION_MAX_ATTEMPTS}"
                )
        args = build_database_client_args(
            client,
            profile,
            command_name,
            runtime_sql_file,
            production_read=production_read,
        )
        if command_name == "ping":
            metadata["databaseContacted"] = True
            if production_target:
                returncode, output = run_bounded_production_client(
                    args,
                    env,
                    operation_name="ping",
                )
            else:
                result, attempts = run_nonproduction_client(args, env, command_name)
                returncode = result.returncode
                output = result.stdout
                if attempts > 1 and not json_output:
                    print(f"TransientRetries: {attempts - 1}")
            clear_client_password(env)
            if returncode == 0:
                output = ""
                if not production_target:
                    result.stdout = ""
                metadata.update(
                    {
                        "connection": "OK",
                        "queryPolicy": "NOT_EVALUATED",
                        "databaseAuthorization": "NOT_PROVEN",
                        "attempts": attempts,
                    }
                )
                if json_output:
                    print_json(metadata)
                else:
                    print(
                        "Connection: OK\n"
                        "QueryPolicy: NOT_EVALUATED\n"
                        "DatabaseAuthorization: NOT_PROVEN"
                    )
                return 0
            category = classify_ping_error(output)
            signals = client_error_signals(output)
            output = ""
            if not production_target:
                result.stdout = ""
            die(
                f"{profile['engine']} client ping failed; category={category}; signals={signals}; "
                "connection details were suppressed",
                stage="CONNECT",
                category=category,
                database_contacted=True,
                attempts=attempts,
            )
        metadata["databaseContacted"] = True
        if production_read:
            returncode, output = run_bounded_production_client(args, env)
        else:
            result, attempts = run_nonproduction_client(
                args,
                env,
                command_name,
                confirm_idempotent_retry=confirm_idempotent_retry,
            )
            returncode = result.returncode
            output = result.stdout
            if attempts > 1 and not json_output:
                print(f"TransientRetries: {attempts - 1}")
        clear_client_password(env)
        if returncode != 0:
            category = classify_execution_error(output)
            signals = client_error_signals(output)
            output = ""
            if not production_read:
                result.stdout = ""
            die(
                f"{profile['engine']} client execution failed; category={category}; signals={signals}; "
                "connection details were suppressed",
                stage="EXECUTE",
                category=category,
                database_contacted=True,
                attempts=attempts,
            )
        if production_read and profile["engine"] == "postgresql":
            output = bound_postgresql_csv_output(output)
        metadata["attempts"] = attempts
        if json_output:
            metadata["output"] = output
            print_json(metadata)
        else:
            sys.stdout.write(output)
        output = ""
        if not production_read:
            result.stdout = ""
        return 0
    finally:
        clear_client_password(env)
        if runtime_sql_file is not None:
            runtime_sql_file.unlink(missing_ok=True)


def preflight_command(argv: list[str], *, json_output: bool = False) -> int:
    if len(argv) < 4:
        die(
            "preflight requires a project, target, and --operation",
            stage="ARGUMENT",
            category="ARGUMENT_INVALID",
        )
    project, target, *rest = argv
    operation: Optional[str] = None
    forwarded: list[str] = []
    position = 0
    while position < len(rest):
        value = rest[position]
        if value == "--operation" and position + 1 < len(rest):
            if operation is not None:
                die(
                    "preflight accepts one --operation",
                    stage="ARGUMENT",
                    category="ARGUMENT_INVALID",
                )
            operation = rest[position + 1]
            position += 2
            continue
        forwarded.append(value)
        position += 1
    if operation not in {"ping", "query", "exec"}:
        die(
            "preflight operation must be ping, query, or exec",
            stage="ARGUMENT",
            category="ARGUMENT_INVALID",
        )

    plan = prepare_database_command([operation, project, target, *forwarded])
    state = credential_state(plan.profile)
    if state == "ABSENT":
        die(
            "credential is not configured",
            stage="CREDENTIAL",
            category="CREDENTIAL_ABSENT",
            next_action="run dbctl credential set in an interactive terminal",
        )
    retry_policy = "SINGLE_ATTEMPT"
    if operation == "ping" and not plan.production_target:
        retry_policy = "AUTOMATIC_TRANSIENT"
    elif plan.confirm_idempotent_retry:
        retry_policy = "EXPLICIT_IDEMPOTENT"
    payload: dict[str, Any] = {
        "ok": True,
        "version": DBCTL_VERSION,
        "buildId": launcher_build_id(),
        "project": plan.project,
        "target": plan.target,
        "environment": plan.context["environment"],
        "access": plan.context["access"],
        "operation": operation,
        "profileState": "OK",
        "credentialState": state,
        "clientState": "OK",
        "client": client_metadata(
            plan.profile["engine"],
            plan.client,
            probe_version=False,
            production=plan.production_target,
        ),
        "sqlState": "OK" if plan.sql_snapshot is not None else "NOT_REQUIRED",
        "productionGate": "ENFORCED" if plan.production_target else "NOT_APPLICABLE",
        "retryPolicy": retry_policy,
        "databaseConnectivity": "NOT_CHECKED",
        "databaseAuthorization": "NOT_CHECKED",
        "databaseContacted": False,
    }
    if json_output:
        print_json(payload)
    else:
        print(
            f"Project: {plan.project}\nTarget: {plan.target}\n"
            f"Environment: {plan.context['environment']}\n"
            f"Access: {plan.context['access']}\nOperation: {operation}\n"
            "Profile: OK\n"
            f"Credential: {state}\nClient: OK\n"
            f"ClientVariant: {payload['client']['variant']}\n"
            f"ClientVersion: {payload['client']['version']}\n"
            f"ClientPathClass: {payload['client']['pathClass']}\n"
            f"SQL: {payload['sqlState']}\n"
            f"ProductionGate: {payload['productionGate']}\n"
            f"RetryPolicy: {retry_policy}\n"
            "DatabaseConnectivity: NOT_CHECKED\n"
            "DatabaseAuthorization: NOT_CHECKED\n"
            "DatabaseContacted: false"
        )
    return 0


def write_secure_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.parent.chmod(0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_profile(path: Path, profile: dict[str, Any]) -> None:
    clean_profile = {key: value for key, value in profile.items() if not key.startswith("_")}
    write_secure_json(path, clean_profile)


def prompt_choice(label: str, choices: set[str]) -> str:
    value = input(f"{label} ({'/'.join(sorted(choices))}): ").strip().lower()
    if value not in choices:
        die(f"invalid {label.lower()}")
    return value


def prompt_text(label: str) -> str:
    value = input(f"{label}: ").strip()
    if not value or len(value) > 512 or any(ord(character) < 32 for character in value):
        die(f"invalid {label.lower()}")
    return value


def prompt_boolean(label: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    value = input(f"{label} [{suffix}]: ").strip().lower()
    if not value:
        return default
    if value in {"y", "yes"}:
        return True
    if value in {"n", "no"}:
        return False
    die(f"invalid {label.lower()}")


def prompt_confirmed_password() -> str:
    if not sys.stdin.isatty():
        die("credential setup requires an interactive terminal")
    password = getpass.getpass("Database password: ")
    confirmation = getpass.getpass("Confirm database password: ")
    if not password:
        die("credential cannot be empty")
    if password != confirmation:
        die("credential confirmation does not match")
    confirmation = ""
    return password


def profile_command(argv: list[str]) -> int:
    if len(argv) < 3 or argv[0] != "init" or len(argv[3:]) % 2 != 0:
        die("profile init requires a project and target with optional engine and credential mode")
    credential_mode = "inline"
    engine = "sqlserver"
    seen_options: set[str] = set()
    for position in range(3, len(argv), 2):
        option = argv[position]
        value = argv[position + 1]
        if option in seen_options:
            die("profile init option was specified more than once")
        seen_options.add(option)
        if option == "--credential-mode":
            if value not in {"inline", "system"}:
                die("profile init accepts only --credential-mode inline|system")
            credential_mode = value
        elif option == "--engine":
            if value not in SUPPORTED_ENGINES:
                die("profile init accepts only --engine sqlserver|postgresql")
            engine = value
        else:
            die("unknown profile init option")
    if not sys.stdin.isatty():
        die("profile initialization requires an interactive terminal")
    if credential_mode == "system":
        secret_provider()
    project = safe_name(argv[1])
    target = safe_name(argv[2])
    root = credential_root()
    if profile_root_state(root) != "OK":
        die("profile root is not ready; run bootstrap first")

    project_dir = root / project
    index_file = project_dir / "index.json"
    profile_file = project_dir / "profiles" / f"{target}.json"
    if is_link_like(project_dir) or is_link_like(profile_file.parent):
        die("project profile directories cannot be symbolic links or reparse points")
    if profile_file.exists() or profile_file.is_symlink():
        die("target profile already exists")

    if index_file.exists() or index_file.is_symlink():
        index = load_index(project)
        if target in index["targets"]:
            die("target already exists")
        query_root = index["_query_root"]
        index = {key: value for key, value in index.items() if not key.startswith("_")}
    else:
        query_root_value = prompt_text("Absolute query root")
        query_root = Path(query_root_value).expanduser()
        if not query_root.is_absolute() or not query_root.is_dir() or query_root.is_symlink():
            die("query root must be an existing absolute directory without symlinks")
        index = {
            "schemaVersion": 1,
            "project": project,
            "queryRoot": str(query_root.resolve(strict=True)),
            "targets": {},
        }

    environment = prompt_choice("Environment", {"testing", "production"})
    if environment == "production" and "--credential-mode" not in seen_options:
        die(
            "production profile initialization requires explicit "
            "--credential-mode system|inline"
        )
    access = prompt_choice("Access", {"read-only", "read-write"})
    engine_label = "SQL Server" if engine == "sqlserver" else "PostgreSQL"
    host = prompt_text(f"{engine_label} host")
    if "," in host:
        die(f"invalid {engine_label} host")
    port_value = prompt_text(f"{engine_label} port")
    try:
        port = int(port_value)
    except ValueError:
        die(f"invalid {engine_label} port")
    if not 1 <= port <= 65535:
        die(f"invalid {engine_label} port")
    database = prompt_text("Database")
    username = prompt_text("Username")
    encrypt = prompt_boolean("Encrypt connection", True)
    trust_server_certificate = prompt_boolean("Trust server certificate", False)

    password = ""
    if credential_mode == "inline":
        password = prompt_confirmed_password()

    profile = {
        "schemaVersion": 1 if credential_mode == "inline" else 2,
        "project": project,
        "target": target,
        "environment": environment,
        "engine": engine,
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "access": access,
        "encrypt": encrypt,
        "trustServerCertificate": trust_server_certificate,
    }
    if credential_mode == "inline":
        profile["password"] = password
    else:
        profile["secretProvider"] = "system"
        profile["secretRef"] = expected_secret_ref(project, target)
    index["targets"][target] = {
        "profile": f"profiles/{target}.json",
        "engine": engine,
        "environment": environment,
        "access": access,
    }

    write_profile(profile_file, profile)
    if credential_mode == "inline":
        profile["password"] = ""
        password = ""
    try:
        write_secure_json(index_file, index)
    except BaseException:
        profile_file.unlink(missing_ok=True)
        raise
    credential_state = "INLINE" if credential_mode == "inline" else "ABSENT"
    print(
        f"Project: {project}\nTarget: {target}\nProfile: INITIALIZED\n"
        f"Credential: {credential_state}"
    )
    return 0


def credential_command(argv: list[str], *, json_output: bool = False) -> int:
    if len(argv) < 3:
        die("credential command requires an action, project, and target")
    action, project, target, *rest = argv
    safe_name(project)
    index = load_index(project)
    context = load_target(index, project, target)
    profile = load_profile(context)
    secret_ref = (
        profile["secretRef"]
        if profile["_secret_mode"] == "system"
        else expected_secret_ref(project, target)
    )
    if action == "status":
        if rest:
            die("credential status does not accept additional arguments")
        state = credential_state(profile)
        if json_output:
            print_json(
                {
                    "ok": state in {"INLINE", "PRESENT"},
                    "project": project,
                    "target": target,
                    "credentialState": state,
                    "databaseConnectivity": "NOT_CHECKED",
                    "databaseAuthorization": "NOT_CHECKED",
                    "databaseContacted": False,
                }
            )
        else:
            print(
                f"Project: {project}\nTarget: {target}\nCredential: {state}\n"
                "DatabaseConnectivity: NOT_CHECKED\n"
                "DatabaseAuthorization: NOT_CHECKED"
            )
        return 0
    if json_output:
        die(
            "--json is supported only for credential status",
            stage="ARGUMENT",
            category="ARGUMENT_INVALID",
        )
    if action == "set":
        migrate_profile = rest == ["--migrate-profile"]
        if rest and not migrate_profile:
            die("credential set accepts only --migrate-profile")
        if profile["_secret_mode"] == "inline" and not migrate_profile:
            password = prompt_confirmed_password()
            updated = dict(profile)
            updated["password"] = password
            write_profile(context["profile_file"], updated)
            updated["password"] = ""
            password = ""
            print(f"Project: {project}\nTarget: {target}\nCredential: CONFIGURED")
            return 0
        if profile["_secret_mode"] == "system" and migrate_profile:
            die("--migrate-profile requires an inline profile")
        secret_provider().set(secret_ref)
        if profile["_secret_mode"] == "inline":
            migrated = dict(profile)
            migrated["schemaVersion"] = 2
            migrated.pop("password", None)
            migrated["secretProvider"] = "system"
            migrated["secretRef"] = secret_ref
            write_profile(context["profile_file"], migrated)
        print(f"Project: {project}\nTarget: {target}\nCredential: CONFIGURED")
        return 0
    if action == "delete":
        if rest != ["--confirm-delete"]:
            die("credential delete requires --confirm-delete")
        if profile["_secret_mode"] != "system":
            die("inline credential cannot be deleted through the system credential provider")
        secret_provider().delete(secret_ref)
        print(f"Project: {project}\nTarget: {target}\nCredential: DELETED")
        return 0
    die("unknown credential command")


def bootstrap() -> int:
    root = credential_root()
    if is_link_like(root):
        die("profile root cannot be a symbolic link or reparse point")
    if root.exists() and not root.is_dir():
        die("profile root must be a directory")
    root.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        root.chmod(0o700)
    else:
        if not windows_acl_helper(root, False):
            die("Windows credential directory ACL setup failed")
    if profile_root_state(root) != "OK":
        die("profile root permission verification failed")
    sqlcmd_state = "OK"
    try:
        find_sqlcmd()
    except DbctlError:
        sqlcmd_state = "MISSING"
    psql_state = "OK"
    try:
        find_psql()
    except DbctlError:
        psql_state = "MISSING"
    print(
        f"Profile root: OK\nsqlcmd: {sqlcmd_state}\npsql: {psql_state}\n"
        "Credentials: NOT_MODIFIED"
    )
    return 0


def database_client_diagnostic(
    engine: str,
    *,
    production: bool = False,
) -> dict[str, str]:
    try:
        client = find_database_client(engine, production=production)
    except DbctlError:
        return {
            "state": "MISSING",
            "engine": engine,
            "variant": "UNKNOWN",
            "version": "UNAVAILABLE",
            "pathClass": "UNKNOWN",
        }
    return client_metadata(
        engine,
        client,
        probe_version=True,
        production=production,
    )


def database_client_state(engine: str, *, production: bool = False) -> str:
    return database_client_diagnostic(engine, production=production)["state"]


def format_client_diagnostic(engine: str, details: dict[str, str]) -> str:
    if details["state"] != "OK":
        return f"{engine}: {details['state']}"
    return (
        f"{engine}: OK "
        f"({details['variant']} {details['version']}, {details['pathClass']})"
    )


def doctor(argv: list[str], *, json_output: bool = False) -> int:
    if len(argv) > 2:
        die("doctor accepts at most a project and target")
    root = credential_root()
    root_state = profile_root_state(root)
    if not argv:
        client_details = {
            engine: database_client_diagnostic(engine)
            for engine in ("sqlserver", "postgresql")
        }
        sqlcmd_state = client_details["sqlserver"]["state"]
        psql_state = client_details["postgresql"]["state"]
        ok = root_state == "OK"
        payload = {
            "ok": ok,
            "profileRootState": root_state,
            "clients": {"sqlserver": sqlcmd_state, "postgresql": psql_state},
            "clientDetails": client_details,
            "databaseConnectivity": "NOT_CHECKED",
            "databaseAuthorization": "NOT_CHECKED",
            "databaseContacted": False,
        }
        if json_output:
            print_json(payload)
        else:
            print(
                f"Profile root: {root_state}\n"
                f"{format_client_diagnostic('sqlserver', client_details['sqlserver'])}\n"
                f"{format_client_diagnostic('postgresql', client_details['postgresql'])}\n"
                "DatabaseConnectivity: NOT_CHECKED\n"
                "DatabaseAuthorization: NOT_CHECKED"
            )
        return 0 if ok else 1
    project = safe_name(argv[0])
    index = load_index(project)
    contexts = [
        load_target(index, project, target)
        for target in index["targets"]
    ]
    if len(argv) == 2:
        target = safe_name(argv[1])
        contexts = [load_target(index, project, target)]
    required_engines = {context["engine"] for context in contexts}
    production_engines = {
        context["engine"]
        for context in contexts
        if context["environment"] == "production"
    }
    client_details = {
        engine: database_client_diagnostic(
            engine,
            production=engine in production_engines,
        )
        for engine in sorted(required_engines)
    }
    client_states = {
        engine: details["state"]
        for engine, details in client_details.items()
    }
    clients_ok = all(state == "OK" for state in client_states.values())
    payload: dict[str, Any] = {
        "ok": root_state == "OK" and clients_ok,
        "profileRootState": root_state,
        "project": project,
        "indexState": "OK",
        "clients": client_states,
        "clientDetails": client_details,
        "databaseConnectivity": "NOT_CHECKED",
        "databaseAuthorization": "NOT_CHECKED",
        "databaseContacted": False,
    }
    if len(argv) == 1:
        if json_output:
            print_json(payload)
        else:
            client_lines = "\n".join(
                format_client_diagnostic(engine, client_details[engine])
                for engine in client_states
            )
            print(f"Profile root: {root_state}\nProject: {project}\nIndex: OK")
            if client_lines:
                print(client_lines)
            print(
                "DatabaseConnectivity: NOT_CHECKED\n"
                "DatabaseAuthorization: NOT_CHECKED"
            )
        return 0 if root_state == "OK" and clients_ok else 1
    context = contexts[0]
    profile = load_profile(context)
    state = credential_state(profile)
    payload.update(
        {
            "target": context["target"],
            "profileState": "OK",
            "credentialState": state,
        }
    )
    payload["ok"] = (
        root_state == "OK"
        and clients_ok
        and state in {"INLINE", "PRESENT"}
    )
    if json_output:
        print_json(payload)
    else:
        client_lines = "\n".join(
            format_client_diagnostic(engine, client_details[engine])
            for engine in client_states
        )
        print(f"Profile root: {root_state}\nProject: {project}\nIndex: OK")
        if client_lines:
            print(client_lines)
        print(
            f"Target: {context['target']}\nProfile: OK\nCredential: {state}\n"
            "DatabaseConnectivity: NOT_CHECKED\n"
            "DatabaseAuthorization: NOT_CHECKED"
        )
    return 0 if payload["ok"] else 1


def list_or_describe(argv: list[str], *, json_output: bool = False) -> int:
    command_name = argv[0]
    if command_name == "list":
        if len(argv) != 2:
            die("list requires exactly one project")
        project = safe_name(argv[1])
        index = load_index(project)
        targets: list[dict[str, str]] = []
        for target, metadata in index["targets"].items():
            context = load_target(index, project, target)
            targets.append(
                {
                    "target": context["target"],
                    "environment": context["environment"],
                    "access": context["access"],
                }
            )
        if json_output:
            print_json({"ok": True, "project": project, "targets": targets})
        else:
            print("TARGET\tENVIRONMENT\tACCESS")
            for item in targets:
                print(f"{item['target']}\t{item['environment']}\t{item['access']}")
        return 0
    if len(argv) != 3:
        die("describe requires exactly one project and target")
    project = safe_name(argv[1])
    target = safe_name(argv[2])
    context = load_target(load_index(project), project, target)
    payload = {
        "ok": True,
        "project": project,
        "target": target,
        "engine": context["engine"],
        "environment": context["environment"],
        "access": context["access"],
    }
    if json_output:
        print_json(payload)
    else:
        print(
            f"Project: {project}\nTarget: {target}\nEngine: {context['engine']}\n"
            f"Environment: {context['environment']}\nAccess: {context['access']}"
        )
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in values
    try:
        if values.count("--json") > 1:
            die(
                "--json may be specified once",
                stage="ARGUMENT",
                category="ARGUMENT_INVALID",
            )
        values = [value for value in values if value != "--json"]
        if not values:
            die(
                "a command is required",
                stage="ARGUMENT",
                category="ARGUMENT_INVALID",
            )
        if values[0] in {"help", "-h", "--help"}:
            if len(values) != 1:
                die(
                    "help does not accept additional arguments",
                    stage="ARGUMENT",
                    category="ARGUMENT_INVALID",
                )
            if json_output:
                print_json({"ok": True, "usage": usage()})
            else:
                print(usage())
            return 0
        if values[0] == "version":
            if len(values) != 1:
                die(
                    "version does not accept additional arguments",
                    stage="ARGUMENT",
                    category="ARGUMENT_INVALID",
                )
            payload = version_payload()
            if json_output:
                print_json(payload)
            else:
                print(
                    f"dbctl {payload['version']}\n"
                    f"BuildId: {payload['buildId']}\n"
                    f"Features: {','.join(payload['features'])}"
                )
            return 0
        if values[0] in {"list", "describe"}:
            return list_or_describe(values, json_output=json_output)
        if values[0] in {"ping", "query", "exec"}:
            return run_database_command(values, json_output=json_output)
        if values[0] == "preflight":
            return preflight_command(values[1:], json_output=json_output)
        if values[0] == "credential":
            return credential_command(values[1:], json_output=json_output)
        if values[0] == "profile":
            if json_output:
                die(
                    "--json is not supported for profile mutation commands",
                    stage="ARGUMENT",
                    category="ARGUMENT_INVALID",
                )
            return profile_command(values[1:])
        if values[0] == "bootstrap":
            if json_output:
                die(
                    "--json is not supported for bootstrap",
                    stage="ARGUMENT",
                    category="ARGUMENT_INVALID",
                )
            if len(values) != 1:
                die("bootstrap does not accept arguments")
            return bootstrap()
        if values[0] == "doctor":
            return doctor(values[1:], json_output=json_output)
        die(
            "unknown command",
            stage="ARGUMENT",
            category="ARGUMENT_INVALID",
            next_action="run dbctl help",
        )
    except DbctlError as error:
        if json_output:
            print_json(error_payload(error))
        else:
            details = (
                f"stage={error.stage}; category={error.category}; "
                f"retryable={str(error.retryable).lower()}; "
                f"database_contacted={str(error.database_contacted).lower()}; "
                f"attempts={error.attempts}"
            )
            if error.next_action:
                details += f"; next_action={error.next_action}"
            print(f"dbctl: {error}; {details}", file=sys.stderr)
        return error_exit_code(error)


def invoke_json(argv: list[str]) -> tuple[int, dict[str, Any]]:
    """Invoke a JSON-capable command without exposing process-global streams."""

    values = [value for value in argv if value != "--json"]
    stdout = io.StringIO()
    stderr = io.StringIO()
    with PROGRAMMATIC_INVOKE_LOCK, contextlib.redirect_stdout(
        stdout
    ), contextlib.redirect_stderr(stderr):
        exit_code = main([*values, "--json"])

    lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
    if stderr.getvalue().strip() or len(lines) != 1:
        return 1, {
            "ok": False,
            "stage": "LOCAL",
            "category": "PROGRAMMATIC_OUTPUT_INVALID",
            "retryable": False,
            "databaseContacted": False,
            "attempts": 1,
            "message": "dbctl produced an invalid structured response; details were suppressed",
        }
    try:
        payload = json.loads(lines[0])
    except json.JSONDecodeError:
        return 1, {
            "ok": False,
            "stage": "LOCAL",
            "category": "PROGRAMMATIC_OUTPUT_INVALID",
            "retryable": False,
            "databaseContacted": False,
            "attempts": 1,
            "message": "dbctl produced an invalid structured response; details were suppressed",
        }
    if not isinstance(payload, dict):
        return 1, {
            "ok": False,
            "stage": "LOCAL",
            "category": "PROGRAMMATIC_OUTPUT_INVALID",
            "retryable": False,
            "databaseContacted": False,
            "attempts": 1,
            "message": "dbctl produced an invalid structured response; details were suppressed",
        }
    return exit_code, payload


if __name__ == "__main__":
    raise SystemExit(main())
