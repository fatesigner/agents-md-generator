---
name: operate-database-profiles
description: Operate or troubleshoot a real project database through project-scoped profiles and the controlled dbctl launcher. Use when the user wants to test connectivity; use SQL Server/sqlcmd, PostgreSQL/psql, or DBeaver against a real target; query live data; inspect schemas, tables, columns, indexes, views, stored procedures, or effective permissions; diagnose login, authentication, TLS, or database-access failures; perform an authorized development/test write; or run a current-task production read against an explicitly named or project-bound default target through operation-level SQL and bounded-output gates. Do not use for static review of repository SQL, migrations, schema definitions, or ORM code when no database connection or live data is required. Never read profile files directly.
---

# Operate Database Profiles

Use the controlled database launcher as the only agent-invoked credential-resolution and command-execution boundary. The OS provider, launcher process, and native client may touch the secret only as documented in the runtime chain. Keep profile contents out of model context, commands, logs, SQL files, and final responses.

## Load the contract

Read [references/profile-contract.md](references/profile-contract.md) before resolving a project, target, profile, launcher, or query root.

Read [references/safety-policy.md](references/safety-policy.md) before any connection attempt, SQL execution, permission inspection, production operation, write, or TLS-setting change.

Read [references/secret-stores.md](references/secret-stores.md) before bootstrap, credential status, secret setup, inline-profile migration, deletion, or credential-provider diagnosis.

Read [references/credential-modes.md](references/credential-modes.md) before choosing a credential mode, explaining coexistence, planning migration, handling a missing system credential, or considering fallback behavior.

Read [references/architecture-and-responsibilities.md](references/architecture-and-responsibilities.md) before explaining ownership or an end-to-end call chain, changing a launcher boundary, adding a database adapter, or selecting a UI/client path.

## Follow the workflow

1. Determine the project identifier from the nearest applicable `AGENTS.md` or repository database declaration. Resolve a production target only from the current request or an explicit default production-read target in the applicable project rules; never infer it from history, uniqueness, or naming similarity.
2. Locate the controlled launcher declared by project rules. Prefer the bundled `scripts/dbctl.sh` on macOS/Linux or `scripts/dbctl.cmd` on Windows. Use `${HOME}/.local/bin/dbctl.sh` only as a compatibility entry when no nearer rule overrides it. If the launcher is missing, stop instead of reading a profile directly.
3. List safe target metadata through the launcher, then describe the selected target. Never use `cat`, `sed`, `rg`, `jq`, an editor, or a generic script to expose profile contents.
4. Classify the operation as `ping`, `read-query`, `schema-inspection`, `permission-inspection`, `test-write`, `production-read`, or `production-write`.
5. Apply the environment and operation gates in the safety policy. Treat a current-task request for production `ping`, read query, schema inspection, or permission inspection as authorization for that operation after the target is resolved; do not request a second confirmation.
6. For SQL execution, create or update an auditable `.sql` file only in the project query root. Review the complete SQL before execution.
7. Execute only through the controlled launcher. Do not reconstruct a connection string or invoke a database client with credentials directly.
8. Verify the result in proportion to the operation: connectivity for `ping`, row/shape assertions for reads, and before/after plus affected-row checks for writes.
9. Report the project, target, environment, operation, result, verification, and residual risk without exposing credentials, production endpoints, customer data, or raw sensitive errors.

## Bootstrap a machine safely

Use the platform entry from the installed Skill directory:

```sh
scripts/bootstrap.sh
scripts/dbctl.sh doctor
```

```cmd
scripts\bootstrap.cmd
scripts\dbctl.cmd doctor
```

Bootstrap creates the platform-local profile root and applies owner-only permissions or ACLs. It does not install `sqlcmd` or `psql`, create profiles, migrate passwords, or modify credentials.

Prerequisites are Python 3, the native client required by each configured engine (`sqlcmd` for SQL Server or `psql` for PostgreSQL), and on Windows either Windows PowerShell or PowerShell 7. Bootstrap reports missing clients without installing them. Do not bypass an organization-managed PowerShell execution policy.

On a new machine with no project metadata, the user runs the interactive local initializer so internal connection metadata does not enter chat or agent logs:

```text
dbctl profile init <project> <target> [--engine sqlserver|postgresql] [--credential-mode inline|system]
```

The initializer defaults to SQL Server and an inline schema-version-1 profile, prompts for the password twice through hidden local input, and writes the protected profile with owner-only permissions. Pass `--engine postgresql` for PostgreSQL. Production profiles may describe either `read-only` or `read-write` account intent, but production operations remain read-only and retain every production authorization gate. Pass `--credential-mode system` to create a schema-version-2 profile with `Credential: ABSENT`, then run `dbctl credential set <project> <target>` locally to store the password in the platform credential store. The user, not the agent, supplies every password prompt. Then the agent may use `list`, `describe`, `credential status`, and `doctor` for safe verification.

## Use safe launcher commands

Resolve the launcher and project first, then use the narrowest command:

```sh
"$DBCTL" list "$PROJECT"
"$DBCTL" describe "$PROJECT" "$TARGET"
"$DBCTL" ping "$PROJECT" "$TARGET"
"$DBCTL" query "$PROJECT" "$TARGET" --file "$SQL_FILE"
"$DBCTL" exec "$PROJECT" "$TARGET" --file "$SQL_FILE" --confirm-write
"$DBCTL" credential status "$PROJECT" "$TARGET"
```

Add production flags only when the launcher, project rules, safety policy, and current-task production-read request allow them. The agent must add `--allow-production` itself without a second confirmation after resolving the target. Never bypass a launcher rejection by invoking `sqlcmd`, `psql`, `mysql`, DBeaver, Docker, or another path.

For a production read, resolve the target from the current request or the applicable project's explicit default production-read binding. The current-task request itself authorizes that read, so review the complete bounded SQL and use `query ... --allow-production` without asking for a second confirmation. The launcher intentionally does not inspect or prove the login's effective database permissions. It must enforce read-intent validation plus its row, field-width, timeout, lock-wait, and total-output limits, and it must reject every production `exec` operation.

When the user explicitly requests DBeaver, treat it as a separate user-owned UI workflow: the user configures the connection and handles the secret, while the same target, production-request authorization, SQL-review, and output controls remain applicable. It is never a fallback from a launcher rejection.

There is no public credential `get` command. Never invoke `credential set` or `credential delete` as an unattended agent action. The user must run interactive secret setup in a local terminal so the password is not captured in model context or tool output.

## Keep SQL bounded

- Select only required columns; avoid `SELECT *`.
- Add deterministic filters and an explicit row bound for exploratory reads.
- Prefer counts, aggregates, and existence checks before retrieving row data.
- Do not emit customer records or sensitive fields into the conversation.
- For production, keep the requested result below the launcher's fixed limits; use an aggregate when complete population coverage is required because row output is capped.
- For writes, run an equivalent `SELECT`, verify expected row count, use a transaction, and verify the result.
- Reject SQLCMD meta-commands, shell escapes, external file includes, credential literals, and connection strings.
- Do not treat command names such as `query` as the only security boundary; rely on the launcher's SQL validation and production-operation gates. A dedicated least-privilege database account is recommended as defense in depth, but the launcher does not require or verify it.

## Handle failures safely

- Preserve the launcher error category and suppress raw connection details.
- Do not read a profile to diagnose authentication, TLS, DNS, or database-access failures.
- Do not lower encryption or certificate validation to make a connection succeed without explicit user confirmation.
- Respect the applicable retry limit. After the limit, report attempts and request a strategy change.
- Do not fall back to DBeaver or browser/UI automation unless the user explicitly requests that path.

## Stop at the enforced boundary

Treat profile metadata such as `access: read-only` as descriptive of the permitted `dbctl` workflow, not proof of the login's database grants. The launcher intentionally does not inspect those grants and must not claim that the account itself is read-only.

Allow a production read only when the current task requests the operation, the target is explicitly named or resolved from the applicable project's explicit default production-read binding, the reviewed SQL passes the production-read validator, `--allow-production` is present, and the fixed production limits remain enabled. Do not ask for a second confirmation and do not reuse authorization from another task. An account with database write privileges may still be used through this workflow, but only read operations may be submitted through `dbctl`.

Do not implement production writes in this workflow. If a user requests one, stop and require a separately approved maintenance workflow with a temporary least-privilege credential, reviewed SQL, transaction controls, rollback plan, and commit-time confirmation.
