# Database operation safety policy

## Environment matrix

| Environment | Ping | Read query | Write | Default selection |
| --- | --- | --- | --- | --- |
| Development | Allowed by project rules | Allowed after SQL review | Allowed after impact review | Project-defined |
| Testing | Allowed by project rules | Allowed after SQL review | Allowed after preview and confirmation | May be project default |
| Production (operations read-only) | Current-task request with an explicitly named or project-bound target | Current-task request plus SQL review, operation-level read validation, and bounded-output controls | Prohibited regardless of profile access metadata | Explicit project binding for production reads only |
| Production maintenance | Separate approved workflow only | Separate approved workflow only | Separate approved workflow only | Never |

The stricter applicable global, repository, project, launcher, or database rule wins.

## Preflight

1. Resolve the project and selected target.
2. Run safe `list` and `describe` commands.
3. Confirm the environment, intended access, engine, and operation.
4. Verify that the query root and controlled launcher exist.
5. Confirm that no production target was inferred from prior context, uniqueness, or naming similarity.
6. For production, resolve the target from the current request or an explicit default production-read target in the applicable project rules. Treat the current-task production read request as authorization and do not ask for a second confirmation.
7. Use `preflight ... --json` when diagnosing routing, profile, credential, client, SQL-policy, or production-gate failures. It must reuse the execution validator and stop before database contact.
8. Confirm the selected native-client variant before execution. Treat `version: NOT_PROBED` in preflight as intentional; use `doctor` for a local version probe that does not contact the database.
9. Prefer the local `database_inspect_target` MCP tool when available to combine describe, doctor, and preflight without database contact. Treat every nested state literally and stop at the first failed step.

## Read queries

- Write SQL only in the configured query root.
- Select only required columns and add a deterministic row bound.
- Prefer `COUNT`, `EXISTS`, aggregates, and grouped summaries.
- Avoid customer records, credentials, tokens, identity fields, and unrestricted text columns.
- Verify expected columns, row bounds, and empty-result behavior.
- Summarize sensitive results; do not paste raw production rows.
- The launcher accepts `query` files only when the first executable token is `SELECT` or `WITH`, then rejects common write, execution, DDL, and database-switching tokens. Production additionally requires one statement, recognizes dangerous object/function names even when quoted, rejects Unicode-escaped identifiers and dollar-quoted bodies, and rejects SQL Server three-part or four-part names. Treat this as a fail-closed intent guard, not a complete SQL parser. The production workflow intentionally does not inspect or require database-side read-only permissions.

## Test writes

1. Run an equivalent `SELECT` using the same predicate.
2. Confirm the expected row count and identify the key or unique condition.
3. Reject unbounded `UPDATE` or `DELETE` statements.
4. Use engine-appropriate error handling and an explicit transaction when supported.
5. Keep commit behavior consistent with project and user confirmation rules.
6. Execute through the launcher write command and required confirmation flag.
7. Verify affected rows and post-write state.
8. Report rollback or recovery limits.

## Production

- Never infer production from history, uniqueness, or target naming, and never reuse a production authorization from another task. Use a default production-read target only when the applicable project rules declare it explicitly.
- Never bypass a production rejection from the launcher.
- Treat production writes, DDL, permission changes, imports, restores, and maintenance as outside this Skill.
- Treat a current-task request for production `ping`, read query, schema inspection, or permission inspection as authorization for that operation after resolving the target from the request or an explicit project binding. Pass `--allow-production` without asking for a second confirmation.
- Do not inspect server roles, database roles, ownership, grant options, or effective grants as a prerequisite for production reads. Do not claim that the login itself is read-only.
- Permit production reads through the operation-level controls even when the account's actual database permissions are broader or unknown. A dedicated least-privilege account remains strongly recommended as defense in depth, but it is not a launcher gate.
- Enforce the launcher limits for production reads: one statement, 200 result rows, 256 displayed characters per field, 30-second query timeout, 5-second lock wait, and 64 KiB captured output. SQL Server uses controlled session settings and client width limits. PostgreSQL wraps the reviewed statement in a `READ ONLY` transaction and a bounded CSV `COPY` query. Stream the native-client output through the bounded launcher reader; kill the client and suppress the entire result immediately when the timeout or total-output limit is exceeded.
- Reject production SQL that can reset launcher controls, cross statements, access external data sources, advance sequences, execute procedures or administrative functions, acquire advisory/update/exclusive locks, raise errors, wait deliberately, receive queue messages, or address another SQL Server database or server. Apply dangerous-identifier checks to quoted and unquoted names.
- Do not claim the SQL guard can identify every synonym, foreign table, view, or user-defined/security-definer function. Keep database-side object and execute grants least-privileged even after the dedicated read-only account is introduced.
- Treat profile `access` as descriptive account/target intent, not as operation authorization or proof of effective grants. Production operations remain read-only even when metadata says `read-write`.
- Do not return raw production data, endpoints, account names, or connection errors.
- Keep the MCP transport local over STDIO. Do not expose this profile-backed server over HTTP or another network listener without a separate authentication, tenancy, secret-handling, logging, and data-egress design review.

## SQL file controls

- Require an absolute `.sql` path inside the configured query root.
- Reject symbolic links, path traversal, external file includes, shell escapes, and SQLCMD meta-commands.
- Validate SQL as UTF-8 with an optional BOM and reject SQLCMD and psql meta-commands, external includes, and shell escapes before execution. For SQL Server, disable variable substitution with `-x`, remove inherited `SQLCMD*` settings, and inject only `SQLCMDPASSWORD`; do not combine `-X` or `-X1` with `SQLCMDPASSWORD`. For PostgreSQL, use `psql -X -w`, set `ON_ERROR_STOP`, remove inherited `PG*` settings, and inject only the controlled `PG*` values required for the selected profile. Disconnect stdin for both clients.
- Open each SQL file without following its final symlink, cap it at 1 MiB, read it once, verify that it did not change during the read, and validate that immutable snapshot. For production, reject group- or world-writable SQL files. Execute only an owner-only temporary file generated from the same validated snapshot, then delete it in `finally`; never reopen the user path after validation.
- For production, both engines must contain exactly one reviewed statement. Reject production native-client environment overrides. On POSIX, resolve the client under `/usr` or `/opt` and reject group- or world-writable binaries; on Windows, resolve it under a Program Files root read from the system registry. Prefer an approved ODBC `mssql-tools18` SQL Server client before Go `sqlcmd` during discovery, then keep the selected absolute path fixed for the operation.
- Do not place secrets, connection strings, profile paths, or passwords in SQL.
- MCP tools accept only typed project/target metadata, booleans, an operation enum, and an absolute reviewed SQL-file path. Reject additional fields and never accept credentials, profile bodies, raw client arguments, arbitrary command arrays, or inline SQL as a substitute for the audited query-root file.
- Mark discovery, local inspection, and ping tools read-only. Keep the query tool's `readOnlyHint` conservative because static SQL checks cannot prove that every view, synonym, foreign object, or user-defined/security-definer function is side-effect free; annotations never replace server-side gates or current-task authority.
- Review the entire file before execution.
- Keep generated SQL and sanitized execution summaries under the project `.codex/database/` area when project rules permit retention.

## Retry controls

- Permit automatic transient retries only for non-production ping, with at most three total attempts and bounded backoff.
- Keep query and exec single-attempt unless the caller explicitly supplies `--confirm-idempotent-retry` after reviewing the complete SQL as safe to execute again.
- Never automatically retry a production operation. Reject `--confirm-idempotent-retry` for production query, and continue to reject every production exec.
- Retry only `CONNECTION_CLOSED`, `NETWORK_CONNECT`, `NETWORK_TIMEOUT`, and `TCP_REFUSED`. Do not retry profile, credential, client-path, SQL-policy, permission, syntax, constraint, lock-timeout, deadlock, output-limit, or production-gate failures.
- Count launcher-internal attempts toward the three-attempt failure ceiling. Do not add an outer retry loop after the launcher exhausts its budget.
- Reuse the same selected native-client path for every permitted retry. Never switch between ODBC and Go `sqlcmd` after a connection or execution attempt, because the prior attempt might have reached or modified the database.
- Report the final category and total attempts. For ambiguous write failure, always verify post-state because an earlier attempt may have committed.

## TLS and authentication

- Do not expose authentication failures, usernames, hosts, or database names.
- Preserve encryption by default.
- Do not set `trustServerCertificate` to `true` without explaining that certificate identity validation is disabled and obtaining explicit confirmation.
- Prefer a trusted CA and a host name matching the certificate over disabling validation.
- Keep production certificate validation enabled unless an approved exception explicitly overrides it.
- Default new profiles to SQL Server and default testing profiles to the protected inline credential mode; accept `--engine postgresql` for PostgreSQL. Require a production initializer to explicitly choose `--credential-mode system` or `--credential-mode inline`, preferring the system store when supported instead of silently defaulting production to inline. Require hidden local password entry, owner-only profile permissions, and exact mode exclusivity. Production profile access metadata may be `read-only` or `read-write`, but production operations remain read-only and preserve every production authorization gate.
- Do not expose a credential-get command to users or agents.
- Require interactive user input for credential setup and explicit confirmation for profile migration or credential deletion.
- Do not use request-implied production-read authorization for credential migration or deletion; those operations still require the user to name the target and confirm explicitly in the current task.

## Failure handling

- Use stable stages such as `ARGUMENT`, `INDEX`, `TARGET`, `PROFILE`, `CREDENTIAL`, `POLICY`, `SQL`, `CLIENT`, `CONNECT`, `EXECUTE`, and `OUTPUT`.
- Use categorized failures such as `TARGET_NOT_FOUND`, `PROFILE_SCHEMA_INVALID`, `PROFILE_CONTEXT_MISMATCH`, `PROFILE_CONNECTION_METADATA_INVALID`, `PROFILE_MODE_CONFLICT`, `CREDENTIAL_ABSENT`, `CLIENT_MISSING`, `SQL_POLICY_REJECTED`, `PRODUCTION_GATE_REJECTED`, `DNS`, `TCP_REFUSED`, `NETWORK_UNREACHABLE`, `NETWORK_TIMEOUT`, `TLS`, `AUTHENTICATION`, `ROLE_NOT_FOUND`, `DATABASE_NOT_FOUND`, `DATABASE_ACCESS`, `PG_HBA_REJECTED`, `CONNECTION_CLOSED`, `CLIENT_INTERACTIVE`, `QUERY_TIMEOUT`, `OUTPUT_LIMIT`, and `UNKNOWN`. Treat `CLIENT_INTERACTIVE` as a client or launcher incompatibility, not proof of an invalid password; do not expose the prompt or request a password in chat.
- JSON errors and diagnostic-only commands may contain only the safe stage, category, retryable flag, attempt count, database-contact flag, fixed state labels, and an optional safe next action. Never include raw native-client output or protected profile values. A successful query requested with `--json` may wrap the same bounded result that plain output would return; it remains subject to every production row, width, total-output, data-minimization, and redaction rule.
- MCP returns the payload as machine-readable structured content and emits only a short textual summary. Cap the serialized structured result at 64 KiB for every environment and suppress the complete payload on overflow; do not return a partial query result.
- Do not emit raw driver errors when they can reveal endpoints or account information.
- Diagnose one category at a time and respect the applicable retry limit.
- After repeated failure, stop, report attempted paths, and request a strategy change.

## Delivery

Report:

- project and target;
- environment and operation;
- whether execution occurred;
- affected or returned row counts when safe;
- verification performed;
- redacted error category when applicable;
- remaining permission, TLS, data-sensitivity, or rollback risk.

Never report profile contents, passwords, complete connection strings, production endpoints, account names, or raw customer data.
