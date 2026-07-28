from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "dbctl.py"
SPEC = importlib.util.spec_from_file_location("dbctl", MODULE_PATH)
assert SPEC and SPEC.loader
dbctl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dbctl)


class FakeProvider:
    def __init__(self) -> None:
        self.present = False
        self.set_refs: list[str] = []
        self.deleted_refs: list[str] = []

    def status(self, secret_ref: str) -> bool:
        return self.present

    def get(self, secret_ref: str) -> str:
        if not self.present:
            raise dbctl.DbctlError("credential is not configured")
        return "SYNTHETIC_SECRET"

    def set(self, secret_ref: str) -> None:
        self.set_refs.append(secret_ref)
        self.present = True

    def delete(self, secret_ref: str) -> None:
        self.deleted_refs.append(secret_ref)
        self.present = False


class DbctlTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.profile_root = self.root / "profiles-root"
        self.query_root = self.root / "repo" / ".codex" / "database" / "queries"
        self.query_root.mkdir(parents=True)
        self.project_dir = self.profile_root / "sample-project"
        self.profiles_dir = self.project_dir / "profiles"
        self.profiles_dir.mkdir(parents=True)
        self.profile_root.chmod(0o700)
        self.index_file = self.project_dir / "index.json"
        self.profile_file = self.profiles_dir / "backend-test.json"
        self.index = {
            "schemaVersion": 1,
            "project": "sample-project",
            "queryRoot": str(self.query_root),
            "targets": {
                "backend-test": {
                    "profile": "profiles/backend-test.json",
                    "engine": "sqlserver",
                    "environment": "testing",
                    "access": "read-write",
                }
            },
        }
        self.inline_profile = {
            "schemaVersion": 1,
            "project": "sample-project",
            "target": "backend-test",
            "environment": "testing",
            "engine": "sqlserver",
            "host": "EXAMPLE_HOST",
            "port": 1433,
            "database": "EXAMPLE_DATABASE",
            "username": "EXAMPLE_USERNAME",
            "password": "SYNTHETIC_SECRET",
            "access": "read-write",
            "encrypt": True,
            "trustServerCertificate": False,
        }
        self.write_secure(self.index_file, self.index)
        self.write_secure(self.profile_file, self.inline_profile)
        self.environment = mock.patch.dict(os.environ, {"DB_PROFILE_HOME": str(self.profile_root)})
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    @staticmethod
    def write_secure(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        path.chmod(0o600)

    def context(self) -> dict:
        index = dbctl.load_index("sample-project")
        return dbctl.load_target(index, "sample-project", "backend-test")

    def configure_production_target(self) -> None:
        production_index = dict(self.index)
        production_index["targets"] = {
            "backend-test": {
                "profile": "profiles/backend-test.json",
                "engine": "sqlserver",
                "environment": "production",
                "access": "read-only",
            }
        }
        production_profile = dict(self.inline_profile)
        production_profile["environment"] = "production"
        production_profile["access"] = "read-only"
        self.write_secure(self.index_file, production_index)
        self.write_secure(self.profile_file, production_profile)

    def configure_postgresql_production_target(self) -> None:
        production_index = dict(self.index)
        production_index["targets"] = {
            "backend-test": {
                "profile": "profiles/backend-test.json",
                "engine": "postgresql",
                "environment": "production",
                "access": "read-write",
            }
        }
        production_profile = dict(self.inline_profile)
        production_profile.update(
            {
                "engine": "postgresql",
                "environment": "production",
                "access": "read-write",
                "port": 5432,
            }
        )
        self.write_secure(self.index_file, production_index)
        self.write_secure(self.profile_file, production_profile)

    def test_inline_and_system_backed_profiles_are_exclusive(self) -> None:
        profile = dbctl.load_profile(self.context())
        self.assertEqual(profile["_secret_mode"], "inline")

        migrated = dict(self.inline_profile)
        migrated["schemaVersion"] = 2
        migrated.pop("password")
        migrated["secretProvider"] = "system"
        migrated["secretRef"] = "sample-project/backend-test"
        self.write_secure(self.profile_file, migrated)
        profile = dbctl.load_profile(self.context())
        self.assertEqual(profile["_secret_mode"], "system")

        migrated["password"] = "SYNTHETIC_SECRET"
        self.write_secure(self.profile_file, migrated)
        with self.assertRaisesRegex(dbctl.DbctlError, "ambiguous"):
            dbctl.load_profile(self.context())

    def test_secret_ref_cannot_target_another_credential(self) -> None:
        migrated = dict(self.inline_profile)
        migrated["schemaVersion"] = 2
        migrated.pop("password")
        migrated["secretProvider"] = "system"
        migrated["secretRef"] = "another-project/backend-prod-ro"
        self.write_secure(self.profile_file, migrated)
        with self.assertRaisesRegex(dbctl.DbctlError, "invalid secret reference"):
            dbctl.load_profile(self.context())

    def test_migration_writes_secret_then_removes_inline_password(self) -> None:
        provider = FakeProvider()
        with mock.patch.object(dbctl, "secret_provider", return_value=provider):
            result = dbctl.credential_command(
                ["set", "sample-project", "backend-test", "--migrate-profile"]
            )
        self.assertEqual(result, 0)
        self.assertEqual(provider.set_refs, ["sample-project/backend-test"])
        migrated = json.loads(self.profile_file.read_text(encoding="utf-8"))
        self.assertNotIn("password", migrated)
        self.assertEqual(migrated["schemaVersion"], 2)
        self.assertEqual(migrated["secretProvider"], "system")
        self.assertEqual(migrated["secretRef"], "sample-project/backend-test")

    def test_inline_credential_set_rotates_without_migrating(self) -> None:
        with mock.patch.object(dbctl.sys.stdin, "isatty", return_value=True), mock.patch.object(
            dbctl.getpass, "getpass", side_effect=["ROTATED_SECRET", "ROTATED_SECRET"]
        ), mock.patch("sys.stdout") as stdout:
            result = dbctl.credential_command(["set", "sample-project", "backend-test"])
        self.assertEqual(result, 0)
        rotated = json.loads(self.profile_file.read_text(encoding="utf-8"))
        self.assertEqual(rotated["schemaVersion"], 1)
        self.assertEqual(rotated["password"], "ROTATED_SECRET")
        self.assertNotIn("secretProvider", rotated)
        self.assertNotIn("secretRef", rotated)
        rendered = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        self.assertNotIn("ROTATED_SECRET", rendered)

    def test_inline_status_and_doctor_report_healthy(self) -> None:
        with mock.patch.object(dbctl, "find_sqlcmd", return_value=Path("/approved/sqlcmd")), mock.patch(
            "sys.stdout"
        ) as stdout:
            status_result = dbctl.credential_command(["status", "sample-project", "backend-test"])
            doctor_result = dbctl.doctor(["sample-project", "backend-test"])
        self.assertEqual(status_result, 0)
        self.assertEqual(doctor_result, 0)
        rendered = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        self.assertIn("Credential: INLINE", rendered)
        self.assertNotIn("SYNTHETIC_SECRET", rendered)

    def test_sqlcmd_arguments_never_include_password(self) -> None:
        args = dbctl.build_sqlcmd_args(
            Path("/approved/sqlcmd"), self.inline_profile, "ping", None
        )
        self.assertNotIn("SYNTHETIC_SECRET", args)
        self.assertNotIn("-P", args)
        self.assertIn("-Nm", args)
        self.assertIn("-x", args)
        self.assertFalse(any(value.startswith("-X") for value in args))
        self.assertNotIn("-C", args)

    def test_psql_arguments_never_include_password(self) -> None:
        profile = dict(self.inline_profile)
        profile.update({"engine": "postgresql", "port": 5432})
        args = dbctl.build_psql_args(Path("/approved/psql"), profile, "ping", None)
        self.assertNotIn("SYNTHETIC_SECRET", args)
        self.assertIn("-X", args)
        self.assertIn("-w", args)
        self.assertIn("ON_ERROR_STOP=1", args)
        self.assertNotIn("--password", args)

    def test_production_rejects_database_client_environment_overrides(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "DBCTL_SQLCMD": str(self.root / "untrusted-sqlcmd"),
                "DBCTL_PSQL": str(self.root / "untrusted-psql"),
            },
        ):
            with self.assertRaisesRegex(dbctl.DbctlError, "override is not allowed"):
                dbctl.find_sqlcmd(production=True)
            with self.assertRaisesRegex(dbctl.DbctlError, "override is not allowed"):
                dbctl.find_psql(production=True)

    @unittest.skipIf(os.name == "nt", "POSIX path trust policy")
    def test_production_rejects_database_client_outside_system_roots(self) -> None:
        client = self.root / "untrusted-sqlcmd"
        client.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        client.chmod(0o755)

        with self.assertRaisesRegex(dbctl.DbctlError, "under /usr or /opt"):
            dbctl.validate_production_client_path(client)

    def test_windows_production_client_requires_program_files_root(self) -> None:
        trusted_root = self.root / "Program Files"
        trusted_root.mkdir()
        trusted_client = trusted_root / "sqlcmd.exe"
        trusted_client.write_text("synthetic client", encoding="utf-8")
        trusted_client.chmod(0o755)
        untrusted_client = self.root / "Downloads" / "sqlcmd.exe"
        untrusted_client.parent.mkdir()
        untrusted_client.write_text("synthetic client", encoding="utf-8")
        untrusted_client.chmod(0o755)

        with mock.patch.object(dbctl.os, "name", "nt"), mock.patch.object(
            dbctl,
            "trusted_windows_program_roots",
            return_value=[trusted_root.resolve()],
        ):
            self.assertEqual(
                dbctl.validate_production_client_path(trusted_client),
                trusted_client.resolve(),
            )
            with self.assertRaisesRegex(dbctl.DbctlError, "under Program Files"):
                dbctl.validate_production_client_path(untrusted_client)

    def test_sql_file_must_stay_in_query_root_and_reject_meta_commands(self) -> None:
        valid = self.query_root / "valid.sql"
        valid.write_text("SELECT 1;\n", encoding="utf-8")
        self.assertEqual(dbctl.validate_sql_file(str(valid), self.query_root), valid.resolve())

        meta = self.query_root / "meta.sql"
        meta.write_text("  :r external.sql\n", encoding="utf-8")
        with self.assertRaisesRegex(dbctl.DbctlError, "meta-commands"):
            dbctl.validate_sql_file(str(meta), self.query_root)

        shell_escape = self.query_root / "shell-escape.sql"
        shell_escape.write_text("  !! unsafe-command\n", encoding="utf-8")
        with self.assertRaisesRegex(dbctl.DbctlError, "meta-commands"):
            dbctl.validate_sql_file(str(shell_escape), self.query_root)

        psql_meta = self.query_root / "psql-meta.sql"
        psql_meta.write_text("  \\! unsafe-command\n", encoding="utf-8")
        with self.assertRaisesRegex(dbctl.DbctlError, "meta-commands"):
            dbctl.validate_sql_file(str(psql_meta), self.query_root)

        inline_psql_meta = self.query_root / "inline-psql-meta.sql"
        inline_psql_meta.write_text("SELECT 1; \\! unsafe-command\n", encoding="utf-8")
        with self.assertRaisesRegex(dbctl.DbctlError, "meta-commands"):
            dbctl.validate_sql_file(str(inline_psql_meta), self.query_root)

        bom_meta = self.query_root / "bom-meta.sql"
        bom_meta.write_text("\ufeff:r external.sql\n", encoding="utf-8")
        with self.assertRaisesRegex(dbctl.DbctlError, "meta-commands"):
            dbctl.validate_sql_file(str(bom_meta), self.query_root)

        outside = self.root / "outside.sql"
        outside.write_text("SELECT 1;\n", encoding="utf-8")
        with self.assertRaisesRegex(dbctl.DbctlError, "configured query root"):
            dbctl.validate_sql_file(str(outside), self.query_root)

    @unittest.skipIf(os.name == "nt", "POSIX SQL file mode policy")
    def test_production_rejects_group_or_world_writable_sql_file(self) -> None:
        sql_file = self.query_root / "writable-production.sql"
        sql_file.write_text("SELECT 1;\n", encoding="utf-8")
        sql_file.chmod(0o666)

        with self.assertRaisesRegex(dbctl.DbctlError, "group- or world-writable"):
            dbctl.load_sql_snapshot(
                str(sql_file),
                self.query_root,
                production=True,
            )

    def test_query_rejects_write_keywords_outside_literals_and_comments(self) -> None:
        read_query = self.query_root / "read-query.sql"
        read_query.write_text(
            "-- UPDATE is documentation only\nWITH values_cte AS (SELECT 'DELETE' AS value) "
            "SELECT value FROM values_cte;\n",
            encoding="utf-8",
        )
        dbctl.validate_read_query(read_query)

        write_query = self.query_root / "write-query.sql"
        write_query.write_text("WITH rows AS (SELECT 1 AS id) UPDATE sample SET id = 2;\n")
        with self.assertRaisesRegex(dbctl.DbctlError, "contains a write"):
            dbctl.validate_read_query(write_query)

        implicit_exec = self.query_root / "implicit-exec.sql"
        implicit_exec.write_text("sp_executesql N'DELETE FROM sample';\n")
        with self.assertRaisesRegex(dbctl.DbctlError, "must begin with SELECT or WITH"):
            dbctl.validate_read_query(implicit_exec)

        production_unsafe = self.query_root / "production-unsafe.sql"
        production_unsafe.write_text(
            "SELECT NEXT VALUE FOR dbo.sequence_name;\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(dbctl.DbctlError, "unsafe production-read keyword"):
            dbctl.validate_read_query(production_unsafe, production=True)

        production_lock = self.query_root / "production-lock.sql"
        production_lock.write_text(
            "SELECT id FROM dbo.sample WITH (UPDLOCK);\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(dbctl.DbctlError, "unsafe production-read keyword"):
            dbctl.validate_read_query(production_lock, production=True)

    def test_production_rejects_quoted_dangerous_identifiers_and_cross_database_names(
        self,
    ) -> None:
        safe_quoted_column = self.query_root / "safe-quoted-column.sql"
        safe_quoted_column.write_text(
            'SELECT "update" FROM sample;\n',
            encoding="utf-8",
        )
        dbctl.validate_read_query(
            safe_quoted_column,
            production=True,
            engine="postgresql",
        )

        unsafe_cases = [
            (
                "quoted-terminate.sql",
                'SELECT pg_catalog."pg_terminate_backend"(1);\n',
                "postgresql",
                "unsafe production-read identifier",
            ),
            (
                "quoted-dblink.sql",
                'SELECT public."dblink_exec"(\'connection\', \'SELECT 1\');\n',
                "postgresql",
                "unsafe production-read identifier",
            ),
            (
                "cross-database.sql",
                "SELECT TOP (1) id FROM OtherDatabase.dbo.Sample;\n",
                "sqlserver",
                "cross-database or cross-server",
            ),
            (
                "cross-database-default-schema.sql",
                "SELECT TOP (1) id FROM OtherDatabase..Sample;\n",
                "sqlserver",
                "cross-database or cross-server",
            ),
            (
                "linked-server.sql",
                "SELECT TOP (1) id FROM LinkedServer.OtherDatabase.dbo.Sample;\n",
                "sqlserver",
                "cross-database or cross-server",
            ),
        ]
        for filename, sql, engine, message in unsafe_cases:
            with self.subTest(filename=filename):
                path = self.query_root / filename
                path.write_text(sql, encoding="utf-8")
                with self.assertRaisesRegex(dbctl.DbctlError, message):
                    dbctl.validate_read_query(path, production=True, engine=engine)

    def test_production_requires_exactly_one_statement_for_every_engine(self) -> None:
        multiple = self.query_root / "multiple-statements.sql"
        multiple.write_text("SELECT 1; SELECT 2;\n", encoding="utf-8")
        for engine in ("sqlserver", "postgresql"):
            with self.subTest(engine=engine):
                with self.assertRaisesRegex(dbctl.DbctlError, "exactly one statement"):
                    dbctl.validate_read_query(multiple, production=True, engine=engine)

        sqlserver_cte = self.query_root / "sqlserver-cte.sql"
        sqlserver_cte.write_text(
            ";WITH values_cte AS (SELECT 1 AS value) SELECT value FROM values_cte;\n",
            encoding="utf-8",
        )
        dbctl.validate_read_query(sqlserver_cte, production=True, engine="sqlserver")

    def test_runtime_sql_uses_the_validated_snapshot_after_source_changes(self) -> None:
        source = self.query_root / "snapshot.sql"
        source.write_text("SELECT 1 AS reviewed_value;\n", encoding="utf-8")
        snapshot = dbctl.load_sql_snapshot(str(source), self.query_root)
        dbctl.validate_read_query_text(
            snapshot.text,
            production=True,
            engine="sqlserver",
        )

        source.write_text("SELECT 2 AS changed_value;\n", encoding="utf-8")
        runtime = dbctl.create_runtime_sql_file(
            snapshot,
            engine="sqlserver",
            production_read=True,
        )
        try:
            runtime_text = runtime.read_text(encoding="utf-8")
        finally:
            runtime.unlink(missing_ok=True)

        self.assertIn("SELECT 1 AS reviewed_value", runtime_text)
        self.assertNotIn("SELECT 2 AS changed_value", runtime_text)

    def test_bounded_production_client_stops_at_output_and_timeout_limits(self) -> None:
        with self.assertRaisesRegex(dbctl.DbctlError, "output limit"):
            dbctl.run_bounded_production_client(
                [
                    sys.executable,
                    "-c",
                    (
                        "import sys; "
                        f"sys.stdout.write('X' * ({dbctl.PRODUCTION_MAX_OUTPUT_BYTES} + 8192))"
                    ),
                ],
                os.environ.copy(),
            )

        with mock.patch.object(dbctl, "PRODUCTION_QUERY_TIMEOUT_SECONDS", 0.05):
            with self.assertRaisesRegex(dbctl.DbctlError, "timed out"):
                dbctl.run_bounded_production_client(
                    [sys.executable, "-c", "import time; time.sleep(1)"],
                    os.environ.copy(),
                )

        returncode, output = dbctl.run_bounded_production_client(
            [sys.executable, "-c", "print('bounded-ok')"],
            os.environ.copy(),
        )
        self.assertEqual(returncode, 0)
        self.assertEqual(output, "bounded-ok\n")

    def test_project_access_requires_private_profile_root(self) -> None:
        self.profile_root.chmod(0o755)
        with self.assertRaisesRegex(dbctl.DbctlError, "profile root permissions are invalid"):
            dbctl.load_index("sample-project")

    def test_ping_error_categories_are_redacted(self) -> None:
        cases = {
            "server not found": "DNS",
            "Connection refused": "TCP_REFUSED",
            "connection timed out": "NETWORK_TIMEOUT",
            "Network is unreachable": "NETWORK_UNREACHABLE",
            "x509 certificate invalid": "TLS",
            "server does not support SSL, but SSL was required": "TLS",
            "Login failed": "AUTHENTICATION",
            "Cannot open database": "DATABASE_ACCESS",
            'FATAL: role "private_user" does not exist': "ROLE_NOT_FOUND",
            'FATAL: database "private_database" does not exist': "DATABASE_NOT_FOUND",
            "FATAL: no pg_hba.conf entry for host private_host": "PG_HBA_REJECTED",
            "server closed the connection unexpectedly": "CONNECTION_CLOSED",
            "could not receive data from server: Connection reset by peer": "CONNECTION_CLOSED",
            "Password:": "CLIENT_INTERACTIVE",
            "unclassified private endpoint text": "UNKNOWN",
        }
        for output, expected in cases.items():
            with self.subTest(output=output):
                self.assertEqual(dbctl.classify_ping_error(output), expected)

    def test_secret_backed_profile_rejects_any_password_field(self) -> None:
        migrated = dict(self.inline_profile)
        migrated["schemaVersion"] = 2
        migrated["password"] = ""
        migrated["secretProvider"] = "system"
        migrated["secretRef"] = "sample-project/backend-test"
        self.write_secure(self.profile_file, migrated)
        with self.assertRaisesRegex(dbctl.DbctlError, "ambiguous"):
            dbctl.load_profile(self.context())

    def test_postgresql_profile_rejects_database_connection_strings(self) -> None:
        self.configure_postgresql_production_target()
        unsafe = dict(self.inline_profile)
        unsafe.update(
            {
                "engine": "postgresql",
                "environment": "production",
                "access": "read-write",
                "database": "postgresql://user:secret@example.invalid/database",
                "port": 5432,
            }
        )
        self.write_secure(self.profile_file, unsafe)
        with self.assertRaisesRegex(dbctl.DbctlError, "invalid credential profile"):
            dbctl.load_profile(self.context())

    def test_missing_database_target_returns_redacted_cli_error(self) -> None:
        with mock.patch("sys.stderr") as stderr:
            result = dbctl.main(["ping", "sample-project"])
        self.assertEqual(result, 1)
        output = "".join(call.args[0] for call in stderr.write.call_args_list if call.args)
        self.assertIn("requires a project and target", output)
        self.assertNotIn("Traceback", output)

    def test_failed_query_suppresses_client_output_and_sqlcmd_environment(self) -> None:
        sql_file = self.query_root / "failed.sql"
        sql_file.write_text("SELECT 1;\n", encoding="utf-8")
        captured_arguments = []
        captured_environment = {}
        captured_stdin = None

        def fake_run(args, **kwargs):
            nonlocal captured_stdin
            captured_arguments.extend(args)
            captured_environment.update(kwargs["env"])
            captured_stdin = kwargs["stdin"]
            return SimpleNamespace(returncode=1, stdout="PRIVATE_ENDPOINT SYNTHETIC_SECRET")

        with mock.patch.dict(
            os.environ,
            {"SQLCMDINI": "/unsafe/startup.sql", "SQLCMDEDITOR": "/unsafe/editor"},
        ), mock.patch.object(dbctl, "find_sqlcmd", return_value=Path("/approved/sqlcmd")), mock.patch.object(
            dbctl, "resolve_password", return_value="SYNTHETIC_SECRET"
        ), mock.patch.object(dbctl.subprocess, "run", side_effect=fake_run), mock.patch(
            "sys.stdout"
        ) as stdout:
            with self.assertRaisesRegex(dbctl.DbctlError, "details were suppressed"):
                dbctl.run_database_command(
                    ["query", "sample-project", "backend-test", "--file", str(sql_file)]
                )
        self.assertNotIn("SQLCMDINI", captured_environment)
        self.assertNotIn("SQLCMDEDITOR", captured_environment)
        self.assertEqual(captured_environment.get("SQLCMDPASSWORD"), "SYNTHETIC_SECRET")
        self.assertNotIn("SYNTHETIC_SECRET", captured_arguments)
        self.assertNotIn("-P", captured_arguments)
        self.assertFalse(any(value.startswith("-X") for value in captured_arguments))
        self.assertIn("-x", captured_arguments)
        self.assertEqual(captured_stdin, dbctl.subprocess.DEVNULL)
        rendered = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        self.assertNotIn("PRIVATE_ENDPOINT", rendered)
        self.assertNotIn("SYNTHETIC_SECRET", rendered)

    def test_successful_ping_uses_sanitized_password_environment(self) -> None:
        captured_arguments = []
        captured_environment = {}
        captured_stdin = None

        def fake_run(args, **kwargs):
            nonlocal captured_stdin
            captured_arguments.extend(args)
            captured_environment.update(kwargs["env"])
            captured_stdin = kwargs["stdin"]
            return SimpleNamespace(returncode=0, stdout="ConnectionOk\n1\n")

        with mock.patch.dict(
            os.environ,
            {"SQLCMDINI": "/unsafe/startup.sql", "SQLCMDEDITOR": "/unsafe/editor"},
        ), mock.patch.object(dbctl, "find_sqlcmd", return_value=Path("/approved/sqlcmd")), mock.patch.object(
            dbctl, "resolve_password", return_value="SYNTHETIC_SECRET"
        ), mock.patch.object(dbctl.subprocess, "run", side_effect=fake_run), mock.patch(
            "sys.stdout"
        ) as stdout:
            result = dbctl.run_database_command(["ping", "sample-project", "backend-test"])

        self.assertEqual(result, 0)
        self.assertNotIn("SQLCMDINI", captured_environment)
        self.assertNotIn("SQLCMDEDITOR", captured_environment)
        self.assertEqual(captured_environment.get("SQLCMDPASSWORD"), "SYNTHETIC_SECRET")
        self.assertNotIn("SYNTHETIC_SECRET", captured_arguments)
        self.assertNotIn("-P", captured_arguments)
        self.assertFalse(any(value.startswith("-X") for value in captured_arguments))
        self.assertIn("-x", captured_arguments)
        self.assertEqual(captured_stdin, dbctl.subprocess.DEVNULL)
        rendered = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        self.assertIn("Connection: OK", rendered)
        self.assertNotIn("SYNTHETIC_SECRET", rendered)

    def test_profile_init_defaults_to_inline_password(self) -> None:
        answers = [
            "testing",
            "read-only",
            "sql.example.invalid",
            "1433",
            "EXAMPLE_DATABASE",
            "EXAMPLE_USERNAME",
            "yes",
            "no",
        ]
        with mock.patch.object(dbctl.sys.stdin, "isatty", return_value=True), mock.patch(
            "builtins.input", side_effect=answers
        ), mock.patch.object(
            dbctl.getpass, "getpass", side_effect=["SYNTHETIC_SECRET", "SYNTHETIC_SECRET"]
        ):
            result = dbctl.profile_command(["init", "sample-project", "backend-second"])
        self.assertEqual(result, 0)
        profile_path = self.profiles_dir / "backend-second.json"
        created = json.loads(profile_path.read_text(encoding="utf-8"))
        self.assertEqual(created["schemaVersion"], 1)
        self.assertEqual(created["password"], "SYNTHETIC_SECRET")
        self.assertNotIn("secretProvider", created)
        self.assertNotIn("secretRef", created)
        self.assertEqual(profile_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(profile_path.parent.stat().st_mode & 0o777, 0o700)
        updated_index = json.loads(self.index_file.read_text(encoding="utf-8"))
        self.assertIn("backend-second", updated_index["targets"])

    def test_profile_init_allows_inline_password_for_production_target(self) -> None:
        answers = [
            "production",
            "read-only",
            "sql.example.invalid",
            "1433",
            "EXAMPLE_DATABASE",
            "EXAMPLE_USERNAME",
            "yes",
            "no",
        ]
        with mock.patch.object(dbctl.sys.stdin, "isatty", return_value=True), mock.patch(
            "builtins.input", side_effect=answers
        ), mock.patch.object(
            dbctl.getpass, "getpass", side_effect=["SYNTHETIC_SECRET", "SYNTHETIC_SECRET"]
        ):
            result = dbctl.profile_command(
                [
                    "init",
                    "sample-project",
                    "backend-prod-new",
                    "--credential-mode",
                    "inline",
                ]
            )
        self.assertEqual(result, 0)
        created = json.loads(
            (self.profiles_dir / "backend-prod-new.json").read_text(encoding="utf-8")
        )
        self.assertEqual(created["schemaVersion"], 1)
        self.assertEqual(created["password"], "SYNTHETIC_SECRET")
        self.assertEqual(created["environment"], "production")
        self.assertEqual(created["access"], "read-only")
        updated_index = json.loads(self.index_file.read_text(encoding="utf-8"))
        self.assertEqual(updated_index["targets"]["backend-prod-new"]["access"], "read-only")

    def test_profile_init_supports_postgresql_production_read_write_metadata(self) -> None:
        answers = [
            "production",
            "read-write",
            "pg.example.invalid",
            "5432",
            "EXAMPLE_DATABASE",
            "EXAMPLE_USERNAME",
            "yes",
            "no",
        ]
        with mock.patch.object(dbctl.sys.stdin, "isatty", return_value=True), mock.patch(
            "builtins.input", side_effect=answers
        ), mock.patch.object(
            dbctl.getpass, "getpass", side_effect=["SYNTHETIC_SECRET", "SYNTHETIC_SECRET"]
        ):
            result = dbctl.profile_command(
                [
                    "init",
                    "sample-project",
                    "backend-postgres",
                    "--engine",
                    "postgresql",
                    "--credential-mode",
                    "inline",
                ]
            )
        self.assertEqual(result, 0)
        created = json.loads(
            (self.profiles_dir / "backend-postgres.json").read_text(encoding="utf-8")
        )
        self.assertEqual(created["engine"], "postgresql")
        self.assertEqual(created["environment"], "production")
        self.assertEqual(created["access"], "read-write")
        self.assertEqual(created["port"], 5432)
        updated_index = json.loads(self.index_file.read_text(encoding="utf-8"))
        self.assertEqual(updated_index["targets"]["backend-postgres"]["engine"], "postgresql")
        self.assertEqual(updated_index["targets"]["backend-postgres"]["access"], "read-write")

    def test_profile_init_requires_explicit_credential_mode_for_production(self) -> None:
        with mock.patch.object(dbctl.sys.stdin, "isatty", return_value=True), mock.patch(
            "builtins.input",
            side_effect=["production"],
        ), mock.patch.object(dbctl.getpass, "getpass") as getpass_prompt:
            with self.assertRaisesRegex(dbctl.DbctlError, "explicit --credential-mode"):
                dbctl.profile_command(["init", "sample-project", "backend-prod-implicit"])
        getpass_prompt.assert_not_called()
        self.assertFalse((self.profiles_dir / "backend-prod-implicit.json").exists())

    def test_profile_init_allows_explicit_system_mode(self) -> None:
        answers = [
            "testing",
            "read-only",
            "sql.example.invalid",
            "1433",
            "EXAMPLE_DATABASE",
            "EXAMPLE_USERNAME",
            "yes",
            "no",
        ]
        with mock.patch.object(dbctl.sys.stdin, "isatty", return_value=True), mock.patch.object(
            dbctl, "secret_provider", return_value=FakeProvider()
        ), mock.patch(
            "builtins.input", side_effect=answers
        ), mock.patch.object(dbctl.getpass, "getpass") as getpass_prompt:
            result = dbctl.profile_command(
                [
                    "init",
                    "sample-project",
                    "backend-system",
                    "--credential-mode",
                    "system",
                ]
            )
        self.assertEqual(result, 0)
        getpass_prompt.assert_not_called()
        created = json.loads(
            (self.profiles_dir / "backend-system.json").read_text(encoding="utf-8")
        )
        self.assertEqual(created["schemaVersion"], 2)
        self.assertNotIn("password", created)
        self.assertEqual(created["secretProvider"], "system")
        self.assertEqual(created["secretRef"], "sample-project/backend-system")

    def test_linux_inline_is_supported_but_system_init_fails_before_write(self) -> None:
        profile = dbctl.load_profile(self.context())
        with mock.patch.object(dbctl.sys, "platform", "linux"), mock.patch.object(
            dbctl.os, "name", "posix"
        ):
            self.assertEqual(dbctl.resolve_password(profile), "SYNTHETIC_SECRET")
            with mock.patch.object(dbctl.sys.stdin, "isatty", return_value=True):
                with self.assertRaisesRegex(dbctl.DbctlError, "unsupported on this platform"):
                    dbctl.profile_command(
                        [
                            "init",
                            "sample-project",
                            "backend-linux-system",
                            "--credential-mode",
                            "system",
                        ]
                    )
        self.assertFalse((self.profiles_dir / "backend-linux-system.json").exists())
        updated_index = json.loads(self.index_file.read_text(encoding="utf-8"))
        self.assertNotIn("backend-linux-system", updated_index["targets"])

    def test_production_inline_keeps_operation_gates_and_allows_guarded_reads(self) -> None:
        self.configure_production_target()

        with self.assertRaisesRegex(dbctl.DbctlError, "requires --allow-production"):
            dbctl.run_database_command(["ping", "sample-project", "backend-test"])

        sql_file = self.query_root / "production.sql"
        sql_file.write_text("SELECT 1 AS answer;\n", encoding="utf-8")
        with self.assertRaisesRegex(dbctl.DbctlError, "requires --allow-production"):
            dbctl.run_database_command(
                ["query", "sample-project", "backend-test", "--file", str(sql_file)]
            )

        with self.assertRaisesRegex(dbctl.DbctlError, "production writes are disabled"):
            dbctl.run_database_command(
                [
                    "exec",
                    "sample-project",
                    "backend-test",
                    "--file",
                    str(sql_file),
                    "--confirm-write",
                    "--allow-production",
                ]
            )

        calls = []
        runtime_sql = None

        def fake_bounded_run(args, env):
            nonlocal runtime_sql
            calls.append((args, {"env": dict(env)}))
            runtime_path = Path(args[args.index("-i") + 1])
            runtime_sql = runtime_path.read_text(encoding="utf-8")
            return 0, "answer\n------\n1\n"

        with mock.patch.object(
            dbctl, "find_sqlcmd", return_value=Path("/approved/sqlcmd")
        ), mock.patch.object(
            dbctl,
            "run_bounded_production_client",
            side_effect=fake_bounded_run,
        ), mock.patch("sys.stdout") as stdout:
            result = dbctl.run_database_command(
                [
                    "query",
                    "sample-project",
                    "backend-test",
                    "--file",
                    str(sql_file),
                    "--allow-production",
                ]
            )

        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn(f"SET ROWCOUNT {dbctl.PRODUCTION_MAX_ROWS}", runtime_sql)
        self.assertIn("SET LOCK_TIMEOUT", runtime_sql)
        self.assertIn("SELECT 1 AS answer", runtime_sql)
        query_args = calls[0][0]
        self.assertNotIn("-Q", query_args)
        self.assertIn("-y", query_args)
        self.assertIn(str(dbctl.PRODUCTION_MAX_FIELD_WIDTH), query_args)
        self.assertIn("-t", query_args)
        rendered = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        self.assertIn("ProductionReadControls: ENFORCED", rendered)
        self.assertIn("RowLimit: 200", rendered)
        self.assertIn("answer", rendered)
        self.assertEqual(
            list(self.query_root.glob(".dbctl-production-read-*.sql")),
            [],
        )

    def test_production_ping_uses_bounded_client_runner(self) -> None:
        self.configure_production_target()
        calls = []

        def fake_bounded_run(args, env, *, operation_name):
            calls.append((args, dict(env), operation_name))
            return 0, "ConnectionOk\n1\n"

        with mock.patch.object(
            dbctl, "find_sqlcmd", return_value=Path("/approved/sqlcmd")
        ), mock.patch.object(
            dbctl,
            "run_bounded_production_client",
            side_effect=fake_bounded_run,
        ), mock.patch("sys.stdout") as stdout:
            result = dbctl.run_database_command(
                [
                    "ping",
                    "sample-project",
                    "backend-test",
                    "--allow-production",
                ]
            )

        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], "ping")
        self.assertEqual(calls[0][1]["SQLCMDPASSWORD"], "SYNTHETIC_SECRET")
        rendered = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        self.assertIn("Connection: OK", rendered)
        self.assertNotIn("ConnectionOk", rendered)

    def test_production_query_does_not_probe_account_permissions(self) -> None:
        self.configure_production_target()
        sql_file = self.query_root / "production-no-permission-probe.sql"
        sql_file.write_text("SELECT 1;\n", encoding="utf-8")
        calls = []

        def fake_bounded_run(args, env):
            calls.append(args)
            return 0, "1\n"

        with mock.patch.object(
            dbctl, "find_sqlcmd", return_value=Path("/approved/sqlcmd")
        ), mock.patch.object(
            dbctl,
            "run_bounded_production_client",
            side_effect=fake_bounded_run,
        ):
            result = dbctl.run_database_command(
                [
                    "query",
                    "sample-project",
                    "backend-test",
                    "--file",
                    str(sql_file),
                    "--allow-production",
                ]
            )
        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("-Q", calls[0])
        self.assertNotIn("sys.fn_my_permissions", " ".join(map(str, calls[0])))

    def test_production_query_suppresses_oversized_output(self) -> None:
        self.configure_production_target()
        sql_file = self.query_root / "production-large.sql"
        sql_file.write_text("SELECT 1;\n", encoding="utf-8")
        with mock.patch.object(
            dbctl, "find_sqlcmd", return_value=Path("/approved/sqlcmd")
        ), mock.patch.object(
            dbctl,
            "run_bounded_production_client",
            side_effect=dbctl.DbctlError(
                "production query exceeded the output limit; results were suppressed"
            ),
        ), mock.patch("sys.stdout") as stdout:
            with self.assertRaisesRegex(dbctl.DbctlError, "output limit"):
                dbctl.run_database_command(
                    [
                        "query",
                        "sample-project",
                        "backend-test",
                        "--file",
                        str(sql_file),
                        "--allow-production",
                    ]
                )
        rendered = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        self.assertNotIn("X" * 100, rendered)

    def test_postgresql_production_read_write_profile_keeps_operation_read_only(self) -> None:
        self.configure_postgresql_production_target()
        sql_file = self.query_root / "postgres-production.sql"
        sql_file.write_text("SELECT 1 AS answer;\n", encoding="utf-8")

        with self.assertRaisesRegex(dbctl.DbctlError, "production writes are disabled"):
            dbctl.run_database_command(
                [
                    "exec",
                    "sample-project",
                    "backend-test",
                    "--file",
                    str(sql_file),
                    "--confirm-write",
                    "--allow-production",
                ]
            )

        calls = []
        runtime_sql = None

        def fake_bounded_run(args, env):
            nonlocal runtime_sql
            calls.append((args, {"env": dict(env)}))
            runtime_path = Path(args[args.index("-f") + 1])
            runtime_sql = runtime_path.read_text(encoding="utf-8")
            return 0, "answer,details\n1," + ("X" * 300) + "\n"

        with mock.patch.object(
            dbctl, "find_database_client", return_value=Path("/approved/psql")
        ), mock.patch.object(
            dbctl,
            "run_bounded_production_client",
            side_effect=fake_bounded_run,
        ), mock.patch("sys.stdout") as stdout:
            result = dbctl.run_database_command(
                [
                    "query",
                    "sample-project",
                    "backend-test",
                    "--file",
                    str(sql_file),
                    "--allow-production",
                ]
            )

        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertIn("-X", args)
        self.assertIn("-w", args)
        self.assertIn("--csv", args)
        self.assertIn("-q", args)
        self.assertNotIn("SYNTHETIC_SECRET", args)
        self.assertEqual(kwargs["env"].get("PGPASSWORD"), "SYNTHETIC_SECRET")
        self.assertEqual(kwargs["env"].get("PGSSLMODE"), "verify-full")
        self.assertNotIn("SQLCMDPASSWORD", kwargs["env"])
        self.assertIn("BEGIN TRANSACTION READ ONLY", runtime_sql)
        self.assertIn("SET LOCAL statement_timeout", runtime_sql)
        self.assertIn("SET LOCAL lock_timeout", runtime_sql)
        self.assertIn(f"LIMIT {dbctl.PRODUCTION_MAX_ROWS}", runtime_sql)
        self.assertIn("SELECT 1 AS answer", runtime_sql)
        rendered = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        self.assertIn("ProductionReadControls: ENFORCED", rendered)
        self.assertNotIn("X" * (dbctl.PRODUCTION_MAX_FIELD_WIDTH + 1), rendered)
        self.assertEqual(list(self.query_root.glob(".dbctl-production-read-*.sql")), [])

    def test_profile_init_rejects_invalid_mode_and_password_mismatch(self) -> None:
        with self.assertRaisesRegex(dbctl.DbctlError, "credential-mode"):
            dbctl.profile_command(
                ["init", "sample-project", "backend-invalid", "--credential-mode", "other"]
            )
        with self.assertRaisesRegex(dbctl.DbctlError, "engine"):
            dbctl.profile_command(
                ["init", "sample-project", "backend-invalid", "--engine", "mysql"]
            )

        answers = [
            "testing",
            "read-only",
            "sql.example.invalid",
            "1433",
            "EXAMPLE_DATABASE",
            "EXAMPLE_USERNAME",
            "yes",
            "no",
        ]
        with mock.patch.object(dbctl.sys.stdin, "isatty", return_value=True), mock.patch(
            "builtins.input", side_effect=answers
        ), mock.patch.object(dbctl.getpass, "getpass", side_effect=["first", "second"]):
            with self.assertRaisesRegex(dbctl.DbctlError, "confirmation does not match"):
                dbctl.profile_command(["init", "sample-project", "backend-mismatch"])
        self.assertFalse((self.profiles_dir / "backend-mismatch.json").exists())
        updated_index = json.loads(self.index_file.read_text(encoding="utf-8"))
        self.assertNotIn("backend-mismatch", updated_index["targets"])

        with mock.patch.object(dbctl.sys.stdin, "isatty", return_value=True), mock.patch(
            "builtins.input", side_effect=answers
        ), mock.patch.object(dbctl.getpass, "getpass", side_effect=["", ""]):
            with self.assertRaisesRegex(dbctl.DbctlError, "credential cannot be empty"):
                dbctl.profile_command(["init", "sample-project", "backend-empty"])
        self.assertFalse((self.profiles_dir / "backend-empty.json").exists())
        updated_index = json.loads(self.index_file.read_text(encoding="utf-8"))
        self.assertNotIn("backend-empty", updated_index["targets"])

    def test_macos_set_uses_interactive_security_prompt_without_secret_argument(self) -> None:
        provider = dbctl.MacOSKeychainProvider("/usr/bin/security")
        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0, stdout=b"")

        with mock.patch.object(dbctl.subprocess, "run", side_effect=fake_run), mock.patch.object(
            dbctl.sys.stdin, "isatty", return_value=True
        ):
            provider.set("sample-project/backend-test")
        self.assertEqual(calls[0][-1], "-w")
        self.assertNotIn("SYNTHETIC_SECRET", calls[0])
        self.assertNotIn("-g", calls[1])
        self.assertNotIn("-w", calls[1])

    def test_windows_provider_uses_injected_api_without_outputting_secret(self) -> None:
        class FakeApi:
            def __init__(self) -> None:
                self.value = None

            def status(self, secret_ref):
                return self.value is not None

            def read(self, secret_ref):
                return self.value

            def write(self, secret_ref, secret):
                self.value = secret

            def delete(self, secret_ref):
                existed = self.value is not None
                self.value = None
                return existed

        api = FakeApi()
        provider = dbctl.WindowsCredentialProvider(api)
        with mock.patch.object(dbctl.sys.stdin, "isatty", return_value=True), mock.patch.object(
            dbctl.getpass, "getpass", side_effect=["SYNTHETIC_SECRET", "SYNTHETIC_SECRET"]
        ):
            provider.set("sample-project/backend-test")
        self.assertTrue(provider.status("sample-project/backend-test"))
        self.assertEqual(provider.get("sample-project/backend-test"), "SYNTHETIC_SECRET")
        provider.delete("sample-project/backend-test")
        self.assertFalse(provider.status("sample-project/backend-test"))


if __name__ == "__main__":
    unittest.main()
