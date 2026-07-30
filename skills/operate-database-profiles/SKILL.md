---
name: operate-database-profiles
description: Operate or troubleshoot a real project database through project-scoped profiles and controlled database tools. Use for live SQL Server or PostgreSQL connectivity, queries, schema or permission inspection, authentication or TLS diagnosis, authorized development/test writes, DBeaver guidance, or a current-task production read against an explicitly named or project-bound target. Do not use for static review of repository SQL, migrations, schema definitions, or ORM code when no live database access is needed. Never read profile files directly.
---

# Operate Database Profiles

Keep profiles, credentials, connection metadata, raw client errors, and sensitive rows out of model context. Use only the bundled MCP tools or `dbctl`; never reconstruct a connection string or invoke a native database client directly.

## Load only the required contract

- Read [profile-contract.md](references/profile-contract.md) before resolving a project, target, profile, launcher, or query root.
- Read [safety-policy.md](references/safety-policy.md) before any connection, SQL execution, permission inspection, production operation, write, or TLS change.
- Read [secret-stores.md](references/secret-stores.md) before credential setup, status diagnosis, migration, or deletion.
- Read [credential-modes.md](references/credential-modes.md) before choosing or changing inline/system credential behavior.
- Read [architecture-and-responsibilities.md](references/architecture-and-responsibilities.md) before changing an execution boundary, adapter, client path, MCP tool, or UI workflow.

## Route the operation

1. Resolve the project identifier from the nearest applicable `AGENTS.md` or repository database declaration.
2. Resolve production only from the current request or an explicit project default production-read binding. Never infer it from history, uniqueness, or a similar name.
3. Classify the request as safe discovery, diagnosis, ping, read query, schema/permission inspection, test write, production read, credential maintenance, or unsupported production write.
4. Prefer the bundled `database_*` MCP tools when they are available. Otherwise use `scripts/dbctl.sh` on macOS/Linux or `scripts\dbctl.cmd` on Windows. Use `${HOME}/.local/bin/dbctl.sh` only as a compatibility entry when no nearer rule overrides it.
5. Stop if the controlled tool is missing or rejects the operation. Do not fall back to direct `sqlcmd`, `psql`, DBeaver, Docker, another driver, or another credential source.

## Use the narrowest controlled tool

- Safe metadata: `database_list_targets` or `dbctl list|describe`.
- Local target health without database contact: `database_inspect_target` or `dbctl doctor|preflight`.
- Connectivity: `database_ping` or `dbctl ping`.
- Reviewed read SQL: `database_query` or `dbctl query --file <sql-file>`.
- Development/test write: CLI only, after preview and explicit confirmation, with `dbctl exec --file <sql-file> --confirm-write`.
- Credential setup, migration, and deletion: interactive CLI only. The user enters secrets in a local terminal.

MCP intentionally exposes no write, profile-mutation, credential-mutation, raw-command, or credential-retrieval tool.

## Execute safely

- List and describe the target before database contact. Use `database_inspect_target` to combine safe target, client, credential-state, and preflight checks.
- Create SQL only under the declared project query root. Review the complete file before execution.
- Select only necessary columns, use deterministic filters and row bounds, and prefer counts or aggregates before details.
- For a current-task production ping/read/schema/permission request, resolve the target, review the SQL, and set `allowProduction: true` or `--allow-production` without asking for a second confirmation.
- Treat `access: read-only` as workflow metadata, not proof of database grants. Production writes remain unsupported.
- Never enable `trustServerCertificate` without explaining the identity-validation risk and obtaining explicit confirmation.
- Keep the selected native client fixed for the complete operation and permitted retries. ODBC `mssql-tools18` is preferred before Go `sqlcmd` during pre-execution discovery; never switch clients after database contact.
- Use idempotent retry only for reviewed non-production SQL that is safe to replay after an ambiguous connection close. Never retry production automatically or add an outer retry loop.

## Preserve diagnostic meaning

Use structured output and preserve `stage`, `category`, `databaseContacted`, `retryable`, `attempts`, and the selected client variant. Treat:

- `doctor` as local profile/client health only;
- `preflight` as execution-path validation without native-client startup;
- `ping` as connectivity only;
- successful query execution as neither proof of least privilege nor permission safety outside the reviewed operation.

Do not parse or repeat raw native-client output. After deterministic failure, run one matching preflight instead of retrying. Stop after the applicable retry ceiling.

## Keep write and credential boundaries explicit

For a development/test write, first run an equivalent bounded `SELECT`, verify the expected keys and row count, obtain explicit confirmation, execute one reviewed transactional SQL file through `dbctl exec`, then verify affected rows and post-state.

Never perform production writes, DDL, permission changes, imports, restores, or maintenance through this workflow. Never run unattended `credential set`, credential migration, or credential deletion. There is no credential `get` path.

Use DBeaver only when the user explicitly requests it. The user owns the connection and secret entry; DBeaver is not a fallback from a policy rejection.

## Report

Report the resolved project and target, environment, operation, whether database contact occurred, safe row or affected-row counts, verification performed, categorized failure when applicable, and residual permission/TLS/data-sensitivity/rollback risk. Never report profile contents, passwords, connection strings, production endpoints, account names, raw client errors, or unnecessary customer rows.
