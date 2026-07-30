# Database profile and credential contract

Read [target-query-contract.md](target-query-contract.md) separately for project identifiers, target resolution, query roots, runtime semantics, and the controlled query-consumption boundary. This file covers profile storage, profile schemas, and credential-mode migration.

## Storage and ownership

- Resolve the macOS/Linux default root as `${HOME}/.local/share/database/<project>/`.
- Resolve the Windows default root as `%LOCALAPPDATA%\operate-database-profiles\<project>\`.
- Allow an absolute `DB_PROFILE_HOME` to override the platform default.
- Keep real profiles outside repositories and cloud-synced project directories.
- Require credential directories to be owner-only and credential files to be mode `600` on macOS/Linux.
- On Windows, disable inherited ACLs and grant the current user full control through the bundled bootstrap helper.
- Treat the project index as non-secret metadata, but keep it protected according to the launcher contract.
- Never copy a real profile into a Skill, repository, SQL file, example, report, or task artifact.

## Inline credential profile

New testing profiles default to schema version 1 and store one inline password in the protected local profile. Inline mode remains supported for production targets only when the initializer explicitly receives `--credential-mode inline`; production initialization must explicitly choose inline or system mode instead of silently defaulting. A production profile may declare `access: read-only` or `access: read-write`, but `dbctl` production operations remain read-only and retain all production gates.

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

For a new machine, run `dbctl profile init <project> <target> [--engine sqlserver|postgresql]` in a local interactive terminal after `bootstrap`. The engine defaults to `sqlserver`; pass `--engine postgresql` for PostgreSQL. Testing targets default to inline mode. Production targets must add either `--credential-mode system` or `--credential-mode inline`; prefer system mode on supported platforms. Inline initialization prompts for connection metadata and the password, creates a schema-version-1 profile, and adds the target to the index. System mode creates schema-version-2 metadata, then uses a separate `credential set` command. For the first target in a project, the query root must already exist and be supplied as an absolute local path.

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

## Profile validation boundary

- `secretProvider: system` maps to macOS Keychain or Windows Credential Manager according to the runtime platform.
- `secretRef` is safe lookup metadata, not a password or connection string.

Validate profile schema, target-context binding, connection-metadata shape, credential-mode exclusivity, and deterministic secret reference as separate fail-closed steps. Report only safe categories such as `PROFILE_SCHEMA_INVALID`, `PROFILE_CONTEXT_MISMATCH`, `PROFILE_CONNECTION_METADATA_INVALID`, `PROFILE_MODE_CONFLICT`, `PROFILE_INLINE_INVALID`, `PROFILE_SYSTEM_INVALID`, and `SECRET_REFERENCE_MISMATCH`; never report the rejected field value.
