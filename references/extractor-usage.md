# Extractor Usage

This document describes the local helper script that performs shallow fact extraction before rendering.

Script path:

- `scripts/extract_facts.py`

## Scope

The script performs shallow local extraction only.

- it reads repository root and target first-level directories
- it reads `package.json`, `.sln`, `.csproj`, and common front-end config files when present
- it does not deep-scan source code
- it does not read sensitive config file contents
- it emits normalized JSON suitable for the renderer workflow

## Command

Use the project-approved Python environment for skill/template tooling:

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/extract_facts.py `
  --template frontend-child `
  --root C:\path\to\repo `
  --target C:\path\to\repo\web `
  --detail-level standard `
  --output .codex\web-facts.json
```

Supported template values:

- `root`
- `backend-child`
- `spring-boot-backend-child`
- `nestjs-backend-child`
- `frontend-child`
- `userscripts-child`
- `claude`

## Arguments

- `--root`
  - repository root path
- `--target`
  - child project path for backend/frontend extraction
- `--detail-level`
  - `basic`, `standard`, or `rich`
  - omitted value defaults to `rich` for child templates and `standard` for `root`/`claude`
  - `rich` adds verified project-specific fields such as structure extras, validation-by-change-type, config touchpoints, generated paths, and high-risk touchpoints within the shallow-scan boundary
- `--child-agent`
  - repeated relative path for generated child `AGENTS.md`
- `--host`
  - host profile for root/claude extraction: `codex` or `claude`
- `--database-project`
  - optional explicit database profile project identifier for `--template root`
  - never inferred from the repository directory, Git remote, solution, database name, or prior task
- `--database-production-read-target`
  - optional explicit default production-read target for `--template root`
  - requires `--database-project`; never inferred from the target list, a unique candidate, or prior task
- `--output`
  - output JSON path

## Typical workflow

1. Extract facts:

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/extract_facts.py `
  --template root `
  --root C:\path\to\repo `
  --child-agent backend/AGENTS.md `
  --child-agent web/AGENTS.md `
  --host codex `
  --output .codex\root-facts.json
```

2. Render the file:

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/render_agents_from_facts.py `
  --template root `
  --facts .codex\root-facts.json `
  --output AGENTS.md
```

## Current extraction coverage

### `root`

- repository shape
- top-level child directories
- child AGENTS references passed via CLI
- basic package manager and runtime hints

### `frontend-child`

- `package.json` scripts
- `engines.node`
- package manager and lockfile
- `src/` and `src/app/` first-level directories
- common front-end config files
- basic route/state/shared/api/theme/type path hints
- child `project_name` uses the target directory name rather than `package.json.name`

### `backend-child`

- `.sln`
- `.csproj`
- entry project heuristics
- contract/service/repository project name heuristics
- safe config file names such as `appsettings.example.json`
- `dotnet build`, `dotnet run`, `dotnet test` command candidates

### `claude`

- repository root path for relative include rewriting
- child AGENTS references passed via CLI
- optional host profile for `.claude` or other host-specific output conventions

## Limitations

- Extraction is intentionally shallow and conservative.
- The script favors verified file-system signals over smart inference.
- It does not read sensitive config contents; rich mode records config touchpoints by safe file name or directory existence only.
- It is designed to support the bundled templates first, not arbitrary custom templates.
