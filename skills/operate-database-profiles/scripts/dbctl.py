#!/usr/bin/env python3
"""Cross-platform controlled launcher for profile-based database access."""

from __future__ import annotations

import ctypes
import csv
import getpass
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, Union


SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
MAC_KEYCHAIN_SERVICE = "com.openai.codex.dbctl.database-password.v1"
WINDOWS_CREDENTIAL_PREFIX = "OpenAI.Codex.dbctl.database-password.v1/"
PRODUCTION_MAX_ROWS = 200
PRODUCTION_MAX_FIELD_WIDTH = 256
PRODUCTION_MAX_OUTPUT_BYTES = 64 * 1024
PRODUCTION_QUERY_TIMEOUT_SECONDS = 30
PRODUCTION_LOCK_TIMEOUT_MS = 5000
SUPPORTED_ENGINES = {"postgresql", "sqlserver"}


class DbctlError(Exception):
    pass


def die(message: str) -> "NoReturn":
    raise DbctlError(message)


def usage() -> str:
    return """Usage:
  dbctl list <project>
  dbctl describe <project> <target>
  dbctl ping <project> <target> [--allow-production]
  dbctl query <project> <target> --file <sql-file> [--allow-production]
  dbctl exec <project> <target> --file <sql-file> --confirm-write
  dbctl credential status <project> <target>
  dbctl credential set <project> <target> [--migrate-profile]
  dbctl credential delete <project> <target> --confirm-delete
  dbctl profile init <project> <target> [--engine sqlserver|postgresql]
      [--credential-mode inline|system]
  dbctl bootstrap
  dbctl doctor [<project> [<target>]]"""


def safe_name(value: str) -> str:
    if not SAFE_NAME.fullmatch(value):
        die("invalid project or target name")
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


def require_secure_file(path: Path, description: str) -> None:
    if not path.is_file():
        die(f"{description} not found")
    if path.is_symlink():
        die(f"{description} cannot be a symbolic link")
    if os.name != "nt":
        info = path.stat()
        if stat.S_IMODE(info.st_mode) != 0o600:
            die(f"{description} must have mode 600")
        if info.st_uid != os.getuid():
            die(f"{description} owner is invalid")


def read_json(path: Path, description: str) -> dict[str, Any]:
    require_secure_file(path, description)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        die(f"invalid {description}")
    if not isinstance(value, dict):
        die(f"invalid {description}")
    return value


def load_index(project: str) -> dict[str, Any]:
    root = credential_root()
    if profile_root_state(root) != "OK":
        die("profile root permissions are invalid; run bootstrap")
    project_dir = root / project
    if is_link_like(project_dir):
        die("project profile directory cannot be a symbolic link or reparse point")
    index_file = project_dir / "index.json"
    index = read_json(index_file, "project index")
    if (
        index.get("schemaVersion") != 1
        or index.get("project") != project
        or not isinstance(index.get("queryRoot"), str)
        or not Path(index["queryRoot"]).is_absolute()
        or not isinstance(index.get("targets"), dict)
    ):
        die("invalid project index")

    query_root = Path(index["queryRoot"])
    if not query_root.is_dir():
        die("query root not found")
    if query_root.is_symlink():
        die("query root cannot be a symbolic link")
    index["_file"] = index_file
    index["_query_root"] = query_root.resolve(strict=True)
    return index


def load_target(index: dict[str, Any], project: str, target: str) -> dict[str, Any]:
    safe_name(target)
    metadata = index["targets"].get(target)
    if not isinstance(metadata, dict):
        die("unknown or invalid target")
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
        die("unknown or invalid target")
    rel = Path(profile_rel)
    if (
        len(rel.parts) != 2
        or rel.parts[0] != "profiles"
        or rel.suffix.lower() != ".json"
        or any(part in {"", ".", ".."} for part in rel.parts)
        or not all(re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in rel.parts)
    ):
        die("invalid profile mapping")
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
    profile = read_json(context["profile_file"], "credential profile")
    common_valid = (
        profile.get("schemaVersion") in {1, 2}
        and profile.get("project") == context["project"]
        and profile.get("target") == context["target"]
        and profile.get("environment") == context["environment"]
        and profile.get("engine") == context["engine"]
        and profile.get("access") == context["access"]
        and isinstance(profile.get("host"), str)
        and bool(profile.get("host"))
        and isinstance(profile.get("port"), int)
        and not isinstance(profile.get("port"), bool)
        and 1 <= profile["port"] <= 65535
        and isinstance(profile.get("database"), str)
        and bool(profile.get("database"))
        and not (
            context["engine"] == "postgresql"
            and ("=" in profile["database"] or "://" in profile["database"])
        )
        and isinstance(profile.get("username"), str)
        and bool(profile.get("username"))
        and isinstance(profile.get("encrypt"), bool)
        and isinstance(profile.get("trustServerCertificate"), bool)
    )
    if not common_valid:
        die("invalid credential profile")

    has_password_field = "password" in profile
    has_password = isinstance(profile.get("password"), str) and bool(profile.get("password"))
    has_provider = profile.get("secretProvider") == "system"
    has_ref = isinstance(profile.get("secretRef"), str) and bool(profile.get("secretRef"))
    if has_password_field and (has_provider or has_ref):
        die("credential profile has ambiguous secret configuration")
    if profile["schemaVersion"] == 1:
        if not has_password or has_provider or has_ref:
            die("invalid inline credential profile")
        profile["_secret_mode"] = "inline"
    else:
        if has_password_field or not has_provider or not has_ref:
            die("invalid secret-backed credential profile")
        if profile["secretRef"] != expected_secret_ref(context["project"], context["target"]):
            die("invalid secret reference")
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
        die("keychain credential status failed; details were suppressed")

    def get(self, secret_ref: str) -> str:
        result = subprocess.run(
            [self.security, "find-generic-password", *self._base(secret_ref), "-w"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 44:
            die("credential is not configured")
        if result.returncode != 0:
            die("keychain credential lookup failed; details were suppressed")
        secret = result.stdout
        if secret.endswith(b"\n"):
            secret = secret[:-1]
        if secret.endswith(b"\r"):
            secret = secret[:-1]
        try:
            value = secret.decode("utf-8")
        except UnicodeDecodeError:
            die("keychain credential is invalid")
        if not value:
            die("keychain credential is empty")
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
            die("Windows Credential Manager is unavailable on this platform")
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
                die("Windows credential store is unavailable for this logon session")
            die("Windows credential lookup failed; details were suppressed")
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
            die("credential is not configured")
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
    die("system credential provider is unsupported on this platform")


def resolve_password(profile: dict[str, Any]) -> str:
    if profile["_secret_mode"] == "inline":
        return profile["password"]
    return secret_provider().get(profile["secretRef"])


def find_sqlcmd() -> Path:
    configured = os.environ.get("DBCTL_SQLCMD")
    candidates: list[Path] = []
    if configured:
        configured_path = Path(configured).expanduser()
        if not configured_path.is_absolute():
            die("DBCTL_SQLCMD must be an absolute path")
        candidates.append(configured_path)
    if sys.platform == "darwin":
        candidates.extend([Path("/opt/homebrew/bin/sqlcmd"), Path("/usr/local/bin/sqlcmd")])
    else:
        discovered = shutil.which("sqlcmd.exe" if os.name == "nt" else "sqlcmd")
        if discovered:
            candidates.append(Path(discovered))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    die("sqlcmd is not installed at an approved path")


def find_psql() -> Path:
    configured = os.environ.get("DBCTL_PSQL")
    candidates: list[Path] = []
    if configured:
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
            return candidate
    die("psql is not installed at an approved path")


def find_database_client(engine: str) -> Path:
    if engine == "sqlserver":
        return find_sqlcmd()
    if engine == "postgresql":
        return find_psql()
    die("database engine is not supported")


def validate_sql_file(sql_file: str, query_root: Path) -> Path:
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
    try:
        with resolved.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                if re.match(r"^\s*(?::|!!|\\)", line):
                    die("database client meta-commands are not allowed")
    except (OSError, UnicodeError):
        die("SQL file could not be validated")
    if "\\" in visible_sql_text(read_sql_text(resolved)):
        die("database client meta-commands are not allowed")
    return resolved


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


def executable_sql_tokens(sql_file: Path) -> list[str]:
    visible = visible_sql_text(read_sql_text(sql_file))
    return re.findall(r"[A-Za-z_][A-Za-z0-9_$#@]*", visible.upper())


def validate_read_query(sql_file: Path, *, production: bool = False) -> None:
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
    tokens = executable_sql_tokens(sql_file)
    if not tokens or tokens[0] not in {"SELECT", "WITH"}:
        die("query SQL must begin with SELECT or WITH; use exec with review for other batches")
    blocked = forbidden.intersection(tokens)
    if blocked:
        die("query SQL contains a write, execution, or database-switching keyword; use exec with review")
    if production:
        production_forbidden = {
            "BEGIN",
            "CALL",
            "COMMIT",
            "COPY",
            "DECLARE",
            "DBLINK_EXEC",
            "DO",
            "GO",
            "HOLDLOCK",
            "LISTEN",
            "LOAD",
            "LO_EXPORT",
            "NEXT",
            "NEXTVAL",
            "NOTIFY",
            "OPENDATASOURCE",
            "OPENQUERY",
            "OPENROWSET",
            "PG_CANCEL_BACKEND",
            "PG_CREATE_RESTORE_POINT",
            "PG_LOGICAL_EMIT_MESSAGE",
            "PG_LS_DIR",
            "PG_READ_BINARY_FILE",
            "PG_READ_FILE",
            "PG_RELOAD_CONF",
            "PG_ROTATE_LOGFILE",
            "PG_STAT_FILE",
            "PG_SWITCH_WAL",
            "PG_TERMINATE_BACKEND",
            "PG_WRITE_FILE",
            "PREPARE",
            "RAISERROR",
            "RECEIVE",
            "RESET",
            "ROLLBACK",
            "SAVEPOINT",
            "SET",
            "SETVAL",
            "SP_EXECUTESQL",
            "TABLOCKX",
            "THROW",
            "UNLISTEN",
            "UPDLOCK",
            "VACUUM",
            "WAITFOR",
            "XLOCK",
            "XP_CMDSHELL",
        }
        if production_forbidden.intersection(tokens):
            die("query SQL contains an unsafe production-read keyword")


def classify_ping_error(output: str) -> str:
    lowered = output.lower()
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
    return "UNKNOWN"


def single_statement_sql(sql_file: Path) -> str:
    sql_text = read_sql_text(sql_file)
    visible = visible_sql_text(sql_text)
    semicolons = [position for position, character in enumerate(visible) if character == ";"]
    if len(semicolons) > 1:
        die("production PostgreSQL query must contain exactly one statement")
    if semicolons:
        position = semicolons[0]
        if visible[position + 1 :].strip():
            die("production PostgreSQL query must contain exactly one statement")
        sql_text = sql_text[:position] + sql_text[position + 1 :]
    sql_text = sql_text.strip()
    if not sql_text:
        die("production PostgreSQL query is empty")
    return sql_text


def create_production_query_file(sql_file: Path, engine: str) -> Path:
    sql_text = read_sql_text(sql_file)
    fd, temporary_name = tempfile.mkstemp(
        prefix=".dbctl-production-read-",
        suffix=".sql",
        dir=sql_file.parent,
    )
    temporary = Path(temporary_name)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            if engine == "sqlserver":
                handle.write(f"SET LOCK_TIMEOUT {PRODUCTION_LOCK_TIMEOUT_MS};\n")
                handle.write("SET DEADLOCK_PRIORITY LOW;\n")
                handle.write(f"SET ROWCOUNT {PRODUCTION_MAX_ROWS};\n")
                handle.write(sql_text)
                if not sql_text.endswith("\n"):
                    handle.write("\n")
            elif engine == "postgresql":
                query = single_statement_sql(sql_file)
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
            else:
                die("database engine is not supported")
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
        die("PostgreSQL production output could not be safely parsed; results were suppressed")
    bounded = rows[: PRODUCTION_MAX_ROWS + 1]
    bounded = [
        [field[:PRODUCTION_MAX_FIELD_WIDTH] for field in row]
        for row in bounded
    ]
    rendered = io.StringIO()
    csv.writer(rendered, lineterminator="\n").writerows(bounded)
    return rendered.getvalue()


def run_database_command(argv: list[str]) -> int:
    if len(argv) < 3:
        die("database command requires a project and target")
    command_name, project, target, *rest = argv
    safe_name(project)
    index = load_index(project)
    context = load_target(index, project, target)
    allow_production = False
    confirm_write = False
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
        elif value == "--file" and position + 1 < len(rest):
            sql_file_value = rest[position + 1]
            position += 2
        else:
            die("unknown argument")

    environment = context["environment"]
    access = context["access"]
    if environment == "production" and not allow_production:
        die("production target requires --allow-production")
    if command_name == "ping":
        if sql_file_value is not None:
            die("ping does not accept --file")
        if confirm_write:
            die("ping does not accept --confirm-write")
    elif command_name == "query":
        if sql_file_value is None:
            die("query requires --file")
        if confirm_write:
            die("query does not accept --confirm-write")
    elif command_name == "exec":
        if sql_file_value is None:
            die("exec requires --file")
        if not confirm_write:
            die("exec requires --confirm-write")
        if environment == "production":
            die("production writes are disabled")
        if access == "read-only":
            die("writes are disabled for read-only targets")
    else:
        die("unknown database command")

    sql_file = None
    if sql_file_value is not None:
        sql_file = validate_sql_file(sql_file_value, context["query_root"])
        if command_name == "query":
            validate_read_query(sql_file, production=environment == "production")
    profile = load_profile(context)
    client = find_database_client(profile["engine"])
    password = resolve_password(profile)
    production_read = environment == "production" and command_name == "query"
    print(
        f"Project: {project}\nTarget: {target}\nEnvironment: {environment}\n"
        f"Access: {access}\nOperation: {command_name}"
    )
    env = client_environment(profile, password)
    password = ""
    runtime_sql_file: Optional[Path] = None
    try:
        if production_read:
            runtime_sql_file = create_production_query_file(sql_file, profile["engine"])
            print(
                "ProductionReadControls: ENFORCED\n"
                f"RowLimit: {PRODUCTION_MAX_ROWS}\n"
                f"OutputLimitBytes: {PRODUCTION_MAX_OUTPUT_BYTES}"
            )
        args = build_database_client_args(
            client,
            profile,
            command_name,
            runtime_sql_file or sql_file,
            production_read=production_read,
        )
        if command_name == "ping":
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
            clear_client_password(env)
            if result.returncode == 0:
                print("Connection: OK")
                return 0
            category = classify_ping_error(result.stdout)
            result.stdout = ""
            die(
                f"{profile['engine']} client ping failed; category={category}; "
                "connection details were suppressed"
            )
        try:
            result = subprocess.run(
                args,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                timeout=PRODUCTION_QUERY_TIMEOUT_SECONDS if production_read else None,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            error.output = None
            die("production query timed out; output and connection details were suppressed")
        clear_client_password(env)
        if result.returncode != 0:
            result.stdout = ""
            die(f"{profile['engine']} client execution failed; connection details were suppressed")
        output = result.stdout
        if production_read and profile["engine"] == "postgresql":
            output = bound_postgresql_csv_output(output)
            result.stdout = ""
        if production_read and len(output.encode("utf-8")) > PRODUCTION_MAX_OUTPUT_BYTES:
            result.stdout = ""
            output = ""
            die("production query exceeded the output limit; results were suppressed")
        sys.stdout.write(output)
        output = ""
        result.stdout = ""
        return 0
    finally:
        clear_client_password(env)
        if runtime_sql_file is not None:
            runtime_sql_file.unlink(missing_ok=True)


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


def credential_command(argv: list[str]) -> int:
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
        if profile["_secret_mode"] == "inline":
            state = "INLINE"
        else:
            state = "PRESENT" if secret_provider().status(secret_ref) else "ABSENT"
        print(f"Project: {project}\nTarget: {target}\nCredential: {state}")
        return 0
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


def database_client_state(engine: str) -> str:
    try:
        find_database_client(engine)
        return "OK"
    except DbctlError:
        return "MISSING"


def doctor(argv: list[str]) -> int:
    if len(argv) > 2:
        die("doctor accepts at most a project and target")
    root = credential_root()
    root_state = profile_root_state(root)
    if not argv:
        sqlcmd_state = database_client_state("sqlserver")
        psql_state = database_client_state("postgresql")
        print(f"Profile root: {root_state}\nsqlcmd: {sqlcmd_state}\npsql: {psql_state}")
        return 0 if root_state == "OK" else 1
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
    client_states = {
        engine: database_client_state(engine)
        for engine in sorted(required_engines)
    }
    client_lines = "\n".join(
        f"{engine}: {state}" for engine, state in client_states.items()
    )
    print(f"Profile root: {root_state}\nProject: {project}\nIndex: OK")
    if client_lines:
        print(client_lines)
    clients_ok = all(state == "OK" for state in client_states.values())
    if len(argv) == 1:
        return 0 if root_state == "OK" and clients_ok else 1
    context = contexts[0]
    profile = load_profile(context)
    if profile["_secret_mode"] == "inline":
        credential_state = "INLINE"
    else:
        credential_state = "PRESENT" if secret_provider().status(profile["secretRef"]) else "ABSENT"
    print(f"Target: {context['target']}\nProfile: OK\nCredential: {credential_state}")
    return (
        0
        if root_state == "OK"
        and clients_ok
        and credential_state in {"INLINE", "PRESENT"}
        else 1
    )


def list_or_describe(argv: list[str]) -> int:
    command_name = argv[0]
    if command_name == "list":
        if len(argv) != 2:
            die("list requires exactly one project")
        project = safe_name(argv[1])
        index = load_index(project)
        print("TARGET\tENVIRONMENT\tACCESS")
        for target, metadata in index["targets"].items():
            context = load_target(index, project, target)
            print(f"{context['target']}\t{context['environment']}\t{context['access']}")
        return 0
    if len(argv) != 3:
        die("describe requires exactly one project and target")
    project = safe_name(argv[1])
    target = safe_name(argv[2])
    context = load_target(load_index(project), project, target)
    print(
        f"Project: {project}\nTarget: {target}\nEngine: {context['engine']}\n"
        f"Environment: {context['environment']}\nAccess: {context['access']}"
    )
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        print(usage(), file=sys.stderr)
        return 1
    try:
        if values[0] in {"list", "describe"}:
            return list_or_describe(values)
        if values[0] in {"ping", "query", "exec"}:
            return run_database_command(values)
        if values[0] == "credential":
            return credential_command(values[1:])
        if values[0] == "profile":
            return profile_command(values[1:])
        if values[0] == "bootstrap":
            if len(values) != 1:
                die("bootstrap does not accept arguments")
            return bootstrap()
        if values[0] == "doctor":
            return doctor(values[1:])
        print(usage(), file=sys.stderr)
        die("unknown command")
    except DbctlError as error:
        print(f"dbctl: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
