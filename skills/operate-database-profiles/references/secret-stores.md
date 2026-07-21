# System credential stores

## Provider mapping

`secretProvider: system` maps by runtime platform:

| Platform | Store | Local identifier |
| --- | --- | --- |
| macOS | Login Keychain generic password | service `com.openai.codex.dbctl.database-password.v1`, account `<project>/<target>` |
| Windows | Credential Manager generic credential | target `OpenAI.Codex.dbctl.database-password.v1/<project>/<target>` |

Linux has no system provider in this version. Explicit `--credential-mode system` initialization fails before writing a profile. Inline mode remains available as the selected/default mode; never fall back from a failed system lookup to inline or another source.

The identifier contains only validated project and target aliases. Do not include a host, database, username, customer name, production URL, or connection string.

Credential-source selection and migration semantics are defined in [credential-modes.md](credential-modes.md). A system-provider failure must never fall back to a profile password.

## Safe commands

These commands return metadata only:

```text
dbctl credential status <project> <target>
dbctl doctor [<project> [<target>]]
```

Secret setup is interactive:

```text
dbctl profile init <project> <target> [--engine sqlserver|postgresql] [--credential-mode inline|system]
dbctl credential set <project> <target>
dbctl credential set <project> <target> --migrate-profile
```

Use `profile init` only when the target does not exist. It defaults to schema-version-1 inline mode, collects connection metadata locally, prompts for the password twice through hidden input, and creates the protected profile with `Credential: INLINE`. Pass `--credential-mode system` to create a schema-version-2 profile with `Credential: ABSENT`; this mode never asks for or stores a password during initialization.

For an existing inline profile, `credential set <project> <target>` prompts twice and atomically rotates the inline password without changing modes. For an existing system profile, the same command writes the newly entered password to the system store.

Use `--migrate-profile` only for an existing schema version 1 profile. The command writes the newly entered password to the system store, verifies presence, atomically removes the inline password, and writes schema version 2. It never prints the password.

Deletion is explicit and irreversible:

```text
dbctl credential delete <project> <target> --confirm-delete
```

Do not expose or invent a credential `get` CLI. Password retrieval exists only inside `ping`, `query`, and `exec`.

## Agent boundary

- The agent may run `credential status`, `doctor`, `list`, and `describe` because they emit safe status metadata.
- The user must run `credential set` in a local interactive terminal. Do not send passwords through chat, tool stdin, command arguments, environment variables, redirected files, or SQL.
- Run `credential delete` only after explicit current-task confirmation.
- Never run `--migrate-profile` on behalf of the user without explicit authorization to migrate the inline profile and an interactive user handoff.
- Never enumerate unrelated Keychain or Credential Manager entries.

## macOS Keychain

The launcher uses `/usr/bin/security` with a fixed service and the derived account. For setup it passes a bare final `-w`, allowing the system command to prompt. It never passes the password as a `-w` argument.

Lookup output is captured inside the controlled launcher and passed only to the selected native client child process through `SQLCMDPASSWORD` for SQL Server or `PGPASSWORD` for PostgreSQL. It is never copied to normal output or error streams.

## Windows Credential Manager

The launcher uses the Unicode Advapi32 Credential API with `CRED_TYPE_GENERIC` and `CRED_PERSIST_LOCAL_MACHINE`. This persistence applies to later logon sessions for the same user on the same machine; it is not an all-users store and does not roam by default.

`CredReadW` results are cleared before `CredFree`. The launcher does not call `CredEnumerate`, use `cmdkey /pass`, require a third-party PowerShell module, or place the password in a command argument.

## Residual runtime exposure

System stores protect credentials at rest. Database authentication still requires the launcher to materialize the password briefly in process memory and in the environment of the single native-client child process. Do not claim hardware-backed isolation or protection from a malicious process already running as the same user.

Clear process-local references immediately after use, suppress raw client errors, and never enable shell or PowerShell tracing around credential operations.
