# Database target and query contract

## Project index and query root

Use a protected project index to map safe target names to profile paths and execution metadata. Treat the project identifier, target name, engine, environment, access metadata, and query root as safe routing metadata, but never read or expose the referenced profile contents.

A minimal index shape is:

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

Keep real profiles outside repositories and cloud-synced project directories. Never copy a profile, password, complete connection string, or protected connection metadata into a Skill, repository, SQL file, report, or task artifact.

Create SQL only under the exact declared query root. Resolve the query root from an applicable repository declaration or safe controlled-tool metadata; never open the project index or profile directly to discover it.

## Resolve projects and targets

- Resolve the project identifier from the nearest applicable `AGENTS.md` or repository database declaration.
- Use safe target listing only for discovery, ambiguity, or exact-name confirmation when the current request and applicable project rules do not already resolve one target.
- Always describe the exact resolved target before database contact.
- Name targets as `<service>-<environment>` or `<service>-<environment>-<access>`, preferring explicit names such as `backend-test` and `backend-prod-ro`.
- Never infer production from history, uniqueness, directory names, or a similar target name.
- Never configure production as an implicit profile default. An applicable project rule may explicitly bind a default production-read target for the current task, but that never authorizes writes or unrelated tasks.

## Runtime semantics

- `engine` selects the launcher adapter. Supported values are `sqlserver` and `postgresql`; stop for any other value.
- `environment` controls production gates. A current-task production-read request does not require a second confirmation after exact target resolution.
- `access` describes intended target use; it neither grants nor proves effective database permissions.
- `encrypt: true` requests encrypted transport.
- `trustServerCertificate: true` preserves encryption but disables server-certificate identity validation. Never enable it without explicit confirmation.
- For PostgreSQL, `encrypt: true` with `trustServerCertificate: false` maps to `sslmode=verify-full`; `trustServerCertificate: true` maps to `sslmode=require`; and `encrypt: false` maps to `sslmode=disable`.
- Preserve production certificate validation unless an approved security exception explicitly overrides it.

## Controlled consumption

Allow only the shared `dbctl` core, reached through the controlled CLI or local STDIO MCP adapter, to parse a profile or retrieve a credential. Never reconstruct a connection string or invoke a native database client directly.

Use only safe `list`, `describe`, `doctor`, credential-status, preflight, and categorized result metadata. Never inspect or reproduce a profile body, credential value, protected connection field, native-client arguments, or raw driver output.

For a query:

1. Place the final SQL file under the declared query root.
2. Review the complete bounded file.
3. Run exact-target health and a preflight matching the final operation and file.
4. Execute through `database_query` or `dbctl query`.
5. Preserve the structured `stage`, `category`, `databaseContacted`, `retryable`, `attempts`, and selected-client meaning.

`preflight` may validate an inline profile and check system-credential presence, but it must not retrieve a system-backed credential value, pass credentials to a child process, start the native client, or contact the database. Report database connectivity and authorization as `NOT_CHECKED`.

For a credential-bearing operation, clear the inline password field from the in-memory profile immediately after resolving the child-process secret and clear selected-client environment values in `finally`. Treat this as reference minimization, not guaranteed memory erasure.
