# Generator Usage

This document describes the unified local entrypoint that combines shallow extraction and stable rendering.

Script path:

- `scripts/generate_agents.py`

## Scope

The generator orchestrates:

1. shallow fact extraction
2. normalized facts assembly
3. stable template rendering

It does not replace the lower-level tools. It wraps them for repeatable single-target generation.

## Command

Use the project-approved Python environment for skill/template tooling:

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_agents.py `
  --template frontend-child `
  --root C:\path\to\repo `
  --target C:\path\to\repo\web `
  --detail-level standard `
  --output C:\path\to\repo\web\AGENTS.md `
  --facts-output C:\path\to\repo\.codex\web-facts.json
```

Supported template values:

- `root`
- `dotnet-backend-child`
- `backend-child` (legacy alias)
- `nestjs-backend-child`
- `spring-boot-backend-child`
- `frontend-child`
- `userscripts-child`
- `claude`

## Arguments

- `--template`
  - target template type
- `--root`
  - repository root path
- `--target`
  - child project path for backend/frontend generation
- `--detail-level`
  - `basic`, `standard`, or `rich`
  - omitted value defaults to `rich` for child templates and `standard` for `root`/`claude`
  - pass `standard` or `basic` explicitly when a child target should stay shorter
- `--child-agent`
  - repeated relative path for generated child `AGENTS.md`
- `--host`
  - host profile for root/claude generation: `codex` or `claude`
- `--output`
  - final markdown output path
- `--facts-output`
  - optional path for persisting the intermediate facts JSON
- `--single-project`
  - render a child template as repository-root rules for a single-project repository
  - rewrites child-template intro text so root `AGENTS.md` does not inherit from itself
- `--database-project`
  - optional explicit database profile project identifier for `--template root`
  - invalid for child and Claude templates; never inferred from repository naming
- `--database-production-read-target`
  - optional explicit default production-read target for `--template root`
  - requires `--database-project`; never inferred from the target list or prior tasks

## Typical examples

### Generate root AGENTS.md

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_agents.py `
  --template root `
  --root C:\path\to\repo `
  --child-agent backend/AGENTS.md `
  --child-agent web/AGENTS.md `
  --host codex `
  --database-project example-project `
  --database-production-read-target backend-prod-ro `
  --output C:\path\to\repo\AGENTS.md `
  --facts-output C:\path\to\repo\.codex\root-facts.json
```

### Generate front-end child AGENTS.md

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_agents.py `
  --template frontend-child `
  --root C:\path\to\repo `
  --target C:\path\to\repo\web `
  --detail-level rich `
  --output C:\path\to\repo\web\AGENTS.md
```

To inspect the evidence before overwriting an existing target, also persist facts:

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_agents.py `
  --template frontend-child `
  --root C:\path\to\repo `
  --target C:\path\to\repo\web `
  --detail-level rich `
  --facts-output C:\path\to\repo\.codex\web-rich-facts.json `
  --output C:\path\to\repo\.codex\web-AGENTS.preview.md
```

### Generate userscripts child AGENTS.md

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_agents.py `
  --template userscripts-child `
  --root C:\path\to\repo `
  --target C:\path\to\repo\apps\userscripts `
  --detail-level rich `
  --output C:\path\to\repo\apps\userscripts\AGENTS.md
```

### Generate .NET back-end child AGENTS.md

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_agents.py `
  --template dotnet-backend-child `
  --root C:\path\to\repo `
  --target C:\path\to\repo\backend `
  --output C:\path\to\repo\backend\AGENTS.md
```

### Generate NestJS back-end child AGENTS.md

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_agents.py `
  --template nestjs-backend-child `
  --root C:\path\to\repo `
  --target C:\path\to\repo\apps\backend `
  --detail-level rich `
  --output C:\path\to\repo\apps\backend\AGENTS.md
```

### Generate root CLAUDE.md

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_agents.py `
  --template claude `
  --root C:\path\to\repo `
  --child-agent backend/AGENTS.md `
  --child-agent web/AGENTS.md `
  --host claude `
  --output C:\path\to\repo\CLAUDE.md
```

## Recommended use

- Use `generate_agents.py` when you want the most repeatable single-target generation path.
- Use `extract_facts.py` and `render_agents_from_facts.py` separately when you need to inspect or edit the intermediate facts.
- `claude` generation rewrites `@...` include paths relative to the final `--output` location, so root `CLAUDE.md` or other allowed output locations can safely point to root `AGENTS.md` and child files.
- Project-local traces remain repository-scoped. If the generated root rule set uses `.codex/` as the project-local trace directory, that directory should also be reused when Claude or Gemini operate inside the same repository.

## Current limitations

- The unified entrypoint currently focuses on one target file per invocation.
- It supports the bundled templates only.
- It relies on the current shallow extractor coverage.
