# Credential modes, rotation, and migration

## Decision

Support inline and system-backed credentials across the installation, but require exactly one credential mode per profile. Never fall back from a failed system credential lookup to an inline password.

| Profile mode | Schema | Secret fields | Intended use |
| --- | --- | --- | --- |
| Inline | 1 | Non-empty `password` only | Default for new testing profiles; explicit choice for new production profiles |
| System-backed | 2 | `secretProvider: system` and deterministic `secretRef` | Explicitly selected profiles and migrated profiles; preferred for production |

Different targets may use different modes while migration is in progress. A single target must not contain both modes.

## Invariants

- Create new testing profiles as schema version 1 inline by default; create schema version 2 only when `--credential-mode system` is explicitly selected.
- Require an explicit `--credential-mode inline|system` when creating a production profile. Prefer `system` where the platform provider is available.
- Do not add, preserve, or copy a `password` field into a schema-version-2 profile, including empty or null values.
- Do not add `secretProvider` or `secretRef` to a schema-version-1 profile.
- Derive `secretRef` exactly as `<project>/<target>`; do not accept an arbitrary credential identifier.
- Treat a mixed profile as invalid instead of choosing one credential source.
- Treat a missing, locked, unavailable, or corrupt system credential as an explicit failure. Do not consult an inline password, environment variable, connection string, DBeaver store, or another profile.
- Inline production profiles remain supported only when `--credential-mode inline` is explicitly selected, with `access: read-only` or `access: read-write` metadata. This metadata does not enable production writes; all production operation and confirmation gates remain unchanged, and production `exec` is always rejected.

## Resolution algorithm

1. Validate project, target, index mapping, file ownership, permissions, schema, and connection metadata.
2. For schema version 1, require a non-empty `password` and reject all system-secret fields. Report `INLINE` through safe status commands.
3. For schema version 2, reject the profile whenever a `password` key exists. Require `secretProvider: system` and the expected deterministic `secretRef`.
4. Ask the platform provider for presence or retrieval only inside the controlled launcher.
5. If the provider reports absent or unavailable, stop with a categorized error. Never retry through another credential mode.

## Resolution outcomes and status output

| State | Meaning | Allowed next step |
| --- | --- | --- |
| `INLINE` | Valid schema-version-1 inline profile | Authorized operation or interactive inline rotation; migration is optional |
| `ABSENT` | Provider is available, but a valid schema-version-2 profile has no stored credential | Interactive `credential set` |
| `PRESENT` | Valid schema-version-2 profile with a system credential | Authorized database operation |
| Invalid or ambiguous | Mixed fields, wrong reference, malformed schema, or unsafe file | Stop and repair the profile contract |
| Provider unavailable | Keychain or Credential Manager cannot serve the current user/session | Stop and repair the platform context |

`INLINE`, `ABSENT`, and `PRESENT` are credential-status states. `INITIALIZED`, `CONFIGURED`, and `DELETED` are command results, not additional status states. Provider unavailable, locked, or corrupt is an explicit categorized failure and must not be reported as `ABSENT`.

Status output must not reveal a password, password length, hash, host, username, database, production endpoint, or raw provider error. `INLINE` is a valid and target-scoped `doctor`-healthy credential state; it does not prove database connectivity or authorization.

## Rotation and optional migration workflow

Rotate an inline credential while retaining inline mode:

```text
dbctl credential status <project> <target>
dbctl credential set <project> <target>
dbctl credential status <project> <target>
dbctl doctor <project> <target>
```

Migrate one explicitly named inline target to system-backed mode only when requested:

```text
dbctl credential status <project> <target>
dbctl credential set <project> <target> --migrate-profile
dbctl credential status <project> <target>
dbctl doctor <project> <target>
```

The user runs the `credential set` command in a local interactive terminal and re-enters the password through the platform's hidden prompt. The launcher must:

1. validate that the source is a schema-version-1 inline profile;
2. store the newly entered password in the platform credential store;
3. verify credential presence;
4. atomically rewrite the profile as schema version 2;
5. remove the `password` field;
6. leave other targets unchanged.

If system credential setup or verification fails, do not rewrite the profile. If the system credential is stored but the atomic profile rewrite fails, report migration failure and leave the source profile unchanged; the deterministic system entry may remain and must be repaired by rerunning the explicit migration or explicitly deleting it. This is an incomplete migration, not permission to fall back. Do not copy or reuse the existing inline password automatically.

## New-machine workflow

The default testing new-machine path creates an inline profile and prompts twice for the password without placing it in argv or output:

```text
dbctl bootstrap
dbctl profile init <project> <target> [--engine sqlserver|postgresql]
dbctl credential status <project> <target>
dbctl doctor <project> <target>
```

Inline mode works on macOS, Windows, and Linux. To opt into a supported system store explicitly:

```text
dbctl bootstrap
dbctl profile init <project> <target> [--engine sqlserver|postgresql] --credential-mode system
dbctl credential set <project> <target>
dbctl credential status <project> <target>
dbctl doctor <project> <target>
```

For a new production profile, select the credential source explicitly:

```text
dbctl profile init <project> <target> --credential-mode system
```

Select `production` and the intended access metadata at the interactive prompts. Use `--credential-mode inline` instead only when that storage choice is intentional. Use `profile init` only for a target that does not already exist. If the selected platform has no supported system provider, explicit system initialization fails before the profile or index target is written; it never falls back to inline. System credentials do not travel with the Skill or profile metadata. For an existing schema-version-2 profile copied through an approved metadata workflow, skip initialization and run `credential set` locally. The same `secretRef` does not synchronize a secret across machines, OS users, or unavailable sessions; absolute query roots, index mappings, and file permissions also remain machine-local. Never copy an inline profile as a password-distribution mechanism.

## Rotation and recovery

- Rotate either credential mode with interactive `credential set`; inline remains schema version 1 and system-backed keeps its profile and `secretRef` unchanged.
- If a system credential is deleted or unavailable, report `ABSENT` or a provider error and stop.
- Do not retain the previous password in the profile as rollback material.
- Recover by repairing the platform credential provider or interactively setting the intended password again.
- Keep production migration, deletion, TLS changes, and database verification subject to their independent confirmation gates.

## Non-goals

- No `auto`, `prefer-system`, or `fallback-inline` mode.
- No schema-version-3 dual-mode profile or inline rollback copy.
- No public credential `get` command.
- No password synchronization through OneDrive, Git, repository files, SQL files, environment files, or chat.
- No claim that profile `access` metadata proves effective database permissions.
