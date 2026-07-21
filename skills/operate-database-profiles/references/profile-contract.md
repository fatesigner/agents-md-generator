# Database profile contract

## Storage and ownership

- Resolve the macOS/Linux default root as `${HOME}/.local/share/database/<project>/`.
- Resolve the Windows default root as `%LOCALAPPDATA%\operate-database-profiles\<project>\`.
- Allow an absolute `DB_PROFILE_HOME` to override the platform default.
- Keep real profiles outside repositories and cloud-synced project directories.
- Require credential directories to be owner-only and credential files to be mode `600` on macOS/Linux.
- On Windows, disable inherited ACLs and grant the current user full control through the bundled bootstrap helper.
- Treat the project index as non-secret metadata, but keep it protected according to the launcher contract.
- Never copy a real profile into a Skill, repository, SQL file, example, report, or task artifact.

## Project index

Use an index to map safe target names to profile paths and execution metadata. A minimal shape is:

```json
{
  "schemaVersion": 1,
  "project": "example-project",
  "queryRoot": "/absolute/project/path/.codex/database/queries",
  "targets": {
    "backend-test": {
      "profile": "profiles/backend-test.json",
      "engine": "sqlserver",
      "environment": "testing",
      "access": "read-write"
    }
  }
}
```

Keep project identifiers, target names, environment values, access metadata, relative profile mappings, and query roots in the index. Do not place passwords or complete connection strings in it.

## Inline credential profile

New profiles default to schema version 1 and store one inline password in the protected local profile. This mode is supported for testing and production targets. A production profile may declare `access: read-only` or `access: read-write`, but `dbctl` production operations remain read-only and retain all production gates.

```json
{
  "schemaVersion": 1,
  "project": "example-project",
  "target": "backend-test",
  "environment": "testing",
  "engine": "sqlserver",
  "host": "EXAMPLE_HOST",
  "port": 1433,
  "database": "EXAMPLE_DATABASE",
  "username": "EXAMPLE_USERNAME",
  "password": "***REDACTED***",
  "access": "read-write",
  "encrypt": true,
  "trustServerCertificate": false
}
```

This is a field-shape example only. The initializer obtains the password twice through hidden local input; never replace the placeholder in Skill, repository, command, log, or chat content.

- Require a non-empty `password` string and reject `secretProvider` or `secretRef` in schema version 1.
- Write the profile atomically with owner-only permissions or ACLs.
- Rotate an inline password through interactive `credential set <project> <target>` without changing modes.
- Never copy an inline profile into a repository, synchronized directory, report, SQL file, or another machine as a credential-distribution mechanism.

## System-backed credential profile

Pass `--credential-mode system` during initialization to create schema version 2 with connection metadata plus a deterministic system-secret reference:

```json
{
  "schemaVersion": 2,
  "project": "example-project",
  "target": "backend-test",
  "environment": "testing",
  "engine": "sqlserver",
  "host": "EXAMPLE_HOST",
  "port": 1433,
  "database": "EXAMPLE_DATABASE",
  "username": "EXAMPLE_USERNAME",
  "secretProvider": "system",
  "secretRef": "example-project/backend-test",
  "access": "read-write",
  "encrypt": true,
  "trustServerCertificate": false
}
```

This is a field-shape example only. Never replace the placeholders inside Skill or repository files.

For a new machine, run `dbctl profile init <project> <target> [--engine sqlserver|postgresql]` in a local interactive terminal after `bootstrap` for the default inline mode. The engine defaults to `sqlserver`; pass `--engine postgresql` for PostgreSQL. The initializer prompts for connection metadata and the password, creates a schema-version-1 profile, and adds the target to the index. For system mode, add `--credential-mode system`, then use a separate `credential set` command. For the first target in a project, the query root must already exist and be supplied as an absolute local path.

- Keep the database username in the protected local profile; in system mode, keep the password only in the platform credential store.
- Require `secretProvider` to equal `system`.
- Derive `secretRef` exactly as `<project>/<target>` after validating both names.
- Reject arbitrary secret references so a profile cannot request another project's credential.
- Reject a profile containing both `password` and `secretProvider`/`secretRef`.
- Reject schema-version-2 profiles whenever a `password` key exists, including empty or null values.

## Mode migration

Schema version 1 inline profiles and schema version 2 system profiles are both supported. Each profile must use exactly one mode; never fall back between them.

Optionally migrate inline to system only through `credential set <project> <target> --migrate-profile`. The user re-enters the password through the system's hidden prompt. After the credential store reports success, the launcher atomically writes schema version 2 and removes `password`. Do not automatically migrate, print, copy, or reuse the inline password.

See [credential-modes.md](credential-modes.md) for mode coexistence, strict per-profile exclusivity, status transitions, migration ordering, and the no-fallback rule.

## Naming

- Name targets as `<service>-<environment>` or `<service>-<environment>-<access>`.
- Prefer `backend-test` and `backend-prod-ro` over ambiguous names such as `test` and `prod`.
- Keep target names unique inside a project.
- Never configure a production target as an implicit default in the profile or index. An applicable project `AGENTS.md` may explicitly bind one default production-read target for current-task `ping`, read-query, schema-inspection, and permission-inspection requests; that binding never authorizes production writes or unrelated tasks.

## Runtime semantics

- `engine` selects the launcher adapter. Supported values are `sqlserver` (`sqlcmd`) and `postgresql` (`psql`). Stop for any other value.
- `environment` controls production gates; current-task production-read requests do not require a second confirmation after target resolution.
- `access` describes intended access; it does not grant or prove database permissions.
- `encrypt: true` requests encrypted transport.
- `trustServerCertificate: true` keeps transport encryption but disables server-certificate identity validation.
- For PostgreSQL, `encrypt: true` with `trustServerCertificate: false` maps to `sslmode=verify-full`; `trustServerCertificate: true` maps to `sslmode=require`; and `encrypt: false` maps to `sslmode=disable`.
- `secretProvider: system` maps to macOS Keychain or Windows Credential Manager according to the runtime platform.
- `secretRef` is safe lookup metadata, not a password or connection string.
- Require explicit confirmation before changing encryption or certificate-validation fields.
- Keep production certificate validation enabled unless an approved production security exception says otherwise.

## Consumption boundary

Allow only the controlled launcher to parse a real profile and retrieve a password. The agent may inspect safe `list`, `describe`, `credential status`, `doctor`, validation status, and categorized errors returned by the launcher. It must not inspect or reproduce the underlying credential values.
