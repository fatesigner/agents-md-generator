# Architecture, responsibilities, and call chains

## Purpose

This document is the system map for database-profile operations. It explains ownership, trust boundaries, and how requests flow through the controlled launcher. It does not replace the field definitions, credential-mode rules, provider details, or operation gates in the other references.

## Contents

- [Responsibility matrix](#responsibility-matrix)
- [End-to-end control flow](#end-to-end-control-flow)
- [Operation-specific call chains](#operation-specific-call-chains)
- [Data and trust boundaries](#data-and-trust-boundaries)
- [Confirmation and authority gates](#confirmation-and-authority-gates)
- [Failure propagation and no-bypass rule](#failure-propagation-and-no-bypass-rule)
- [Adapter and UI extension boundary](#adapter-and-ui-extension-boundary)
- [Related contracts](#related-contracts)

## Responsibility matrix

| Component | Owns | Must not do |
| --- | --- | --- |
| User | Requests the database operation; names a non-default target when needed; explicitly authorizes write, TLS-trust, migration, and deletion decisions; enters secrets in a local interactive terminal | Paste a secret into chat or ask the agent to retain it |
| Applicable `AGENTS.md` | Declares project routing, an optional default production-read target, applicable safety rules, confirmation boundaries, and workspace constraints | Contain credentials, authorize production writes, or trigger production access without a current-task request |
| This Skill | Defines the repeatable workflow, contract-loading rules, safety gates, and reporting standard | Read a profile directly or retrieve a secret |
| Agent | Classifies intent, selects a declared target, reviews complete SQL, invokes `dbctl`, verifies outcomes, and reports sanitized evidence | Parse profile contents, invoke a client with credentials, infer production, or bypass a launcher rejection |
| Local STDIO MCP server | Exposes typed discovery, diagnosis, preflight, ping, and read-query tools backed by the shared `dbctl` core | Listen on a network socket, accept credentials or native-client arguments, expose writes, duplicate policy logic, or bypass a core rejection |
| Project index | Maps safe project/target names to profile and query-root locations plus safe environment/access metadata | Store passwords or act as database authorization |
| Protected profile | Stores connection metadata, username, TLS choices, and exactly one credential mode: schema-v1 inline `password` or schema-v2 `secretRef` | Expose its raw contents to the model; mix inline and system fields; distribute an inline profile as a secret-transfer mechanism |
| `dbctl` | Resolves index/profile data, validates paths and intent, obtains the secret, builds absolute client arguments, runs the client, and sanitizes failures | Print a secret, place it in argv or SQL, or fall back around a missing provider |
| OS credential store | Protects the secret for the current OS user and returns the referenced value only to the requesting `dbctl` process | Independently initiate a database operation, decide permissions, or decide operation safety |
| Database client adapter | Translates a validated request into a native client invocation; SQL Server prefers ODBC `sqlcmd` and falls back to Go `sqlcmd` only during pre-execution discovery, while PostgreSQL uses `psql` | Reinterpret user intent, weaken launcher checks, or switch implementations after an operation starts |
| SQL Server | Authenticates the login and enforces whatever effective grants the account has | Treat `dbctl` operation metadata as a database permission grant |
| PostgreSQL | Authenticates the role, enforces its effective grants, and enforces the launcher's production `READ ONLY` transaction | Treat profile access metadata as a PostgreSQL role grant |
| DBeaver or another UI | Optional user-owned path when explicitly requested; the user configures the connection and handles the secret, and the same intent, confirmation, production, SQL-review, and output controls apply | Serve as an automatic fallback, export credentials to the agent, or bypass a `dbctl` rejection |

## End-to-end control flow

```text
User intent and operation-specific authority
  -> applicable AGENTS.md rules
  -> operate-database-profiles workflow
  -> agent classification and complete SQL review
  -> typed local MCP tool or dbctl CLI
  -> shared dbctl core policy and input validation
  -> project index + protected profile metadata
  -> credential resolution inside dbctl: inline, macOS Keychain, or Windows Credential Manager
  -> sqlcmd or psql with an ephemeral child-process secret
  -> database authentication and effective grants
  -> captured result or categorized failure
  -> agent verification, redaction, and user report
```

Each layer has a separate job. `AGENTS.md` defines authority and scope; the Skill defines process; the agent interprets intent and reviews SQL; `dbctl` enforces client-side controls and consumes credentials; the protected profile or OS store protects secrets at rest; SQL Server or PostgreSQL remains the final authority for data access.

The MCP and CLI are peer adapters over one `dbctl_core.py` implementation. The MCP must call the core in-process through its structured JSON API instead of spawning the CLI, and the CLI remains the compatibility, interactive credential, profile-mutation, and authorized test-write entry. A policy rule must never be implemented only in one adapter.

## Operation-specific call chains

### Safe discovery and diagnosis

- `list` and `describe` resolve only safe index metadata. They do not read profile contents, retrieve a secret, or contact the database.
- `version` reports a semantic launcher version, a content-derived build ID, and a fixed feature list. Use it with the runtime-sync check to distinguish source from installed behavior.
- `credential status` reports a sanitized credential state through the launcher and never returns the value.
- Project-level `doctor` checks the protected root, index, and native clients required by configured target engines. It may run a client's local version/help command with database-related environment variables removed, but it never contacts a database. Target-level `doctor` also validates the profile and reports `INLINE` or checks system-credential presence; both forms explicitly report connectivity and authorization as `NOT_CHECKED`.
- `preflight` reuses the execution path's exact target, profile, selected client, SQL snapshot, read-intent, retry, and production-gate validation, then stops before native-client startup. It reports the selected client variant with `version: NOT_PROBED`; an inline profile is parsed only inside `dbctl`, and system-backed mode checks presence without retrieving the value. It reports `databaseContacted: false`.
- `database_inspect_target` combines safe describe, target-level doctor, and the selected operation's preflight in one MCP round trip. It stops at the first failed step and always reports `databaseContacted: false`.
- `ping` resolves the protected profile, obtains its single configured credential mode inside `dbctl`, runs a minimal connectivity query through `sqlcmd` or `psql`, and returns a sanitized success or categorized failure. A successful ping reports query policy as not evaluated and database authorization as not proven.

### Machine bootstrap and credential setup

```text
User terminal -> bootstrap -> protected root and ACL checks
  -> testing profile init -> schema-v1 inline profile by default
     or production profile init -> explicit inline or system choice
     or explicit --credential-mode system -> schema-v2 metadata with secretRef
  -> hidden password confirmation during inline init
     or interactive credential set for the system store
  -> credential status and doctor
```

`bootstrap` creates and protects the platform-local root; it does not install `sqlcmd` or `psql`, create a profile, or provision a credential. The user supplies protected connection metadata during local `profile init`; SQL Server is the default engine and PostgreSQL is selected with `--engine postgresql`. Testing profiles default to inline mode and prompt twice for the password. Production profile creation requires an explicit inline or system choice; prefer system mode where supported. Production access metadata may be read-only or read-write, while production operations remain read-only and retain all operation gates. The explicit system path creates only metadata and then accepts the secret during interactive `credential set`. The agent may guide the workflow and run safe validation commands, but it must not supply, capture, or repeat those values. A new machine receives scripts and non-secret structure through the approved asset flow; secrets are provisioned locally and inline profiles must never be synchronized as password-distribution files.

Inline mode is supported on macOS, Windows, and Linux. The current system credential providers support macOS Keychain and Windows Credential Manager only. On Linux, an explicit `--credential-mode system` request fails before any profile or index target is written; it never falls back to inline.

### Inline credential rotation and optional migration

```text
status -> interactive credential set -> atomically replace inline password
  -> status and doctor

or, when explicitly requested:
status -> explicit user approval -> interactive set --migrate-profile
  -> write and verify OS credential -> atomic profile rewrite
  -> status and doctor
```

The inline value is consumed only by `dbctl`; rotation preserves schema version 1, while optional migration removes the inline field after a verified system-store write. Different targets may use different modes, but one profile is always exactly one mode and there is no runtime fallback between inline and system modes. See [credential-modes.md](credential-modes.md) for state transitions and recovery behavior.

### Read query and schema inspection

```text
Agent writes SQL under the declared query root and reviews the whole file
  -> optional dbctl preflight validates the same execution plan without contacting the database
  -> select one absolute native-client path for the complete operation and every permitted retry
  -> dbctl opens one immutable snapshot and validates path, size, encoding, SQLCMD controls, and read intent
  -> for production: current-task request + explicit or project-bound target + --allow-production
     -> exactly one statement, quoted-identifier checks, and SQL Server cross-database rejection
     -> controlled temporary SQL adds lock, row, timeout, width, and output limits
  -> credential provider -> trusted sqlcmd or psql -> database grants
  -> streaming output cap -> agent verifies shape and reports a redacted summary
```

The launcher's SQL checks are an intent guard, not a complete SQL parser or database authorization system. For production, `dbctl` intentionally does not inspect roles, ownership, grant options, or effective grants, and it does not claim that the account is read-only. It instead opens and validates one immutable SQL snapshot, requires exactly one statement, rejects dangerous identifiers even when quoted, rejects SQL Server three- and four-part cross-database or linked-server names, permanently rejects production `exec`, and applies fixed row, field-width, query-timeout, lock-wait, and streaming-output limits. PostgreSQL receives an additional `READ ONLY` transaction wrapper. Static SQL cannot prove that an otherwise ordinary object is not a synonym, foreign table, view, or security-definer function, so database-side least privilege remains a necessary independent defense. Results may still be sensitive, so the agent must request only necessary columns and report a redacted summary.

Non-production ping may retry categorized transient connection failures with at most three total attempts and bounded backoff. Query and exec remain single-attempt unless the caller explicitly supplies `--confirm-idempotent-retry` after reviewing the complete SQL as repeat-safe. Production operations never retry automatically, and production query rejects the retry flag.

### Authorized development or test write

```text
Equivalent preview SELECT -> expected-row and unique-key review
  -> explicit user confirmation -> transactional SQL review
  -> dbctl exec --confirm-write -> database grants
  -> affected-row and post-state verification -> sanitized report
```

Writes require a non-production writable target, complete SQL review, a bounded predicate, and both human and launcher confirmation. The agent must report recovery limits.

### Production

- A current-task request for production connectivity, read query, schema inspection, or permission inspection authorizes that operation without a second confirmation. Resolve the target from the request or an explicit default production-read binding in the applicable project rules; never infer it from history, uniqueness, or naming similarity.
- The launcher accepts `ping ... --allow-production` and reviewed `query ... --file <sql-file> --allow-production` operations for production.
- The launcher does not inspect or require the login's actual read-only permissions. Profile access metadata describes the allowed launcher operation, not the account's effective grants.
- Production query SQL must contain exactly one statement and receives stricter quoted-identifier and engine-specific checks. SQL Server rejects three- and four-part names; both engines reject known database-escape or administrative identifiers.
- The launcher executes the already-validated immutable snapshot and applies fixed limits: 200 rows, 256 displayed characters per field, 30-second query timeout, 5-second lock wait, and 64 KiB total streamed output. It terminates the client when the time or output limit is exceeded.
- Production ignores `DBCTL_SQLCMD` and `DBCTL_PSQL` overrides. On POSIX systems it requires a resolved, non-group/world-writable client under `/usr` or `/opt`; on Windows it requires a resolved client under a Program Files root obtained from the system registry.
- On macOS and Linux, SQL Server discovery prefers the approved ODBC `mssql-tools18` path, then falls back to Go `sqlcmd` when ODBC is unavailable. Production performs this deterministic trusted-path selection before execution and never accepts an environment override.
- The launcher rejects production `exec` even when `--allow-production` and `--confirm-write` are present.
- Production writes, DDL, permission changes, imports, restores, and maintenance remain outside this Skill.

## Data and trust boundaries

| Data class | Allowed location and handling | Forbidden exposure |
| --- | --- | --- |
| Safe routing metadata | Project/target names, environment, access mode, engine, and sanitized status may appear in the index and reports | Must not be treated as proof of database authorization |
| Protected connection metadata | Host, database, username, TLS settings, profile path, and secret reference remain in protected files and launcher memory | Chat, logs, raw errors, SQL, and final responses |
| Secret material | For inline schema v1, the protected profile; for system-backed schema v2, the OS credential store; in both cases, the minimum transient launcher/client process memory | Model context, argv, parent or general-purpose environment variables, SQL files, synchronized assets, logs, and reports |
| SQL and results | SQL stays in the declared query root; results are bounded, verified, and redacted before reporting | Customer data dumps, unrestricted result sets, or retained sensitive output |

`SQLCMDPASSWORD` or `PGPASSWORD` may exist only in the selected native-client child environment created by `dbctl`. The launcher must clear inherited `SQLCMD*` and `PG*` values, inject only its controlled client settings, and never print the child environment.

## Confirmation and authority gates

| Action | Required authority |
| --- | --- |
| Safe `list`, `describe`, `credential status`, and `doctor` | Applicable project rules; no secret access |
| Credential creation or rotation | User enters the secret in a local interactive terminal |
| Credential migration or deletion | Explicit confirmation for the named target in the current task |
| Test/development write | Preview evidence, explicit user confirmation, and `--confirm-write` |
| Production connectivity | Current-task request, explicitly named or project-bound default target, and `--allow-production`; no second confirmation |
| Production read | Current-task request, explicitly named or project-bound default target, reviewed bounded SQL, `--allow-production`, and enabled production read/output controls; no second confirmation |
| TLS `trustServerCertificate=true` | Risk explanation and explicit confirmation |
| Production write | Unsupported by the current launcher; no bypass |

OS credential access proves that the current OS session can retrieve a secret; it does not prove user intent. Launcher flags prove that a required gate was acknowledged; they do not grant database permission. SQL Server or PostgreSQL grants remain decisive for what the account can do through any path, while `dbctl` independently limits production operations to reads.

## Failure propagation and no-bypass rule

- A missing launcher, undeclared target, invalid profile state, unavailable provider, unsafe SQL path, rejected SQL intent, or denied production operation stops the chain.
- A missing system credential does not trigger inline, environment-variable, connection-string, direct-client, or DBeaver fallback.
- Native client errors are captured and mapped to sanitized categories before they reach the agent or user.
- ODBC/Go fallback occurs only when discovering an available executable before database contact. Once `preflight` or execution selects a client, a connection or execution failure never triggers cross-client replay.
- Diagnostic errors expose only a stable stage, category, retryable flag, attempt count, database-contact flag, and optional safe next action. JSON output must not include raw profile values, endpoints, usernames, databases, passwords, or native-client errors.
- MCP tool input uses fixed JSON schemas and rejects additional fields. It accepts project/target aliases, operation flags, and reviewed SQL-file paths only; it never accepts a password, connection string, profile body, raw native-client argument, or arbitrary launcher argv. Structured MCP output is capped at 64 KiB and suppressed in full on overflow.
- A launcher rejection is a policy decision. Do not reconstruct the same operation with another script, client, driver, or UI.
- Internal retry attempts count toward the three-attempt failure ceiling. After the launcher exhausts that ceiling, do not wrap it in another retry loop; return to the user for a strategy decision.

## Adapter and UI extension boundary

A new database adapter must preserve the existing project-root, profile, secret-reference, SQL-path, confirmation, production, failure-sanitization, and output-control boundaries. It must pass credentials through a client-supported non-argv mechanism and receive dedicated tests before use.

The bundled MCP is a local STDIO adapter, not a remote service. Its first version exposes no write, profile-mutation, credential-mutation, credential-get, or raw-command tool. Add any future consequential tool separately with its own confirmation contract and tests; never turn the read-query tool into a mode-switching generic executor.

Use DBeaver only when the user explicitly requests interactive UI operation. It is a separate user-owned workflow, not an alternative credential resolver for profiles. The user creates or selects the connection, supplies protected connection metadata, and enters the password into the user's chosen secure store. The same target, production-request authorization, SQL-review, and output rules still apply. Do not scrape, export, or copy DBeaver credentials, and do not use its UI to retry an operation that `dbctl` rejected on policy grounds.

## Related contracts

- Profile and index fields: [profile-contract.md](profile-contract.md)
- Inline/system coexistence and migration: [credential-modes.md](credential-modes.md)
- Keychain and Credential Manager behavior: [secret-stores.md](secret-stores.md)
- Environment, SQL, TLS, write, and production gates: [safety-policy.md](safety-policy.md)
