# Manifest Generator Usage

This document describes the helper that generates a suite manifest from shallow repository discovery.

Script path:

- `scripts/generate_suite_manifest.py`

## Scope

The manifest generator performs shallow discovery only.

- it scans the repository root and first-level child directories
- it infers child targets conservatively
- if no first-level child target is found but the repository root itself has project signals, it emits a single-project root config
- it does not deep-scan source code
- it does not overwrite any AGENTS files by itself
- it can optionally emit a review report for manual correction

## Discovery rules

- `backend-child`
  - discovered when a child directory contains `.sln` or `.csproj`
- `spring-boot-backend-child`
  - discovered when a child directory contains Spring Boot/Maven/Gradle signals
- `frontend-child`
  - discovered when a child directory contains `package.json` and either:
    - known front-end dependencies such as `react`, `vue`, `vite`, `next`, `nuxt`
    - or a `src/` directory
- other directories are ignored by default

## Single-project repositories

When the repository root itself matches a child project type and no first-level child target is discovered, the generated manifest uses the matching child template for root `AGENTS.md`.

Example root config:

```json
{
  "output": "AGENTS.md",
  "host": "codex",
  "template": "frontend-child",
  "target": ".",
  "detail_level": "rich",
  "single_project": true
}
```

This avoids producing an empty summary-style root file for repositories where the root is the actual app or service.

## Command

Use the project-approved Python environment for skill/template tooling:

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_suite_manifest.py `
  --root C:\path\to\repo `
  --persist-facts `
  --report-output C:\path\to\repo\.codex\agents-suite-report.md `
  --output C:\path\to\repo\.codex\agents-suite.json
```

## Arguments

- `--root`
  - repository root path
- `--detail-level`
  - default detail level for discovered child targets
  - omitted value defaults to `rich`
  - each discovered child target also receives this value explicitly as `detail_level`
  - edit individual child entries to `standard` or `basic` when selected subprojects should stay shorter
  - root `AGENTS.md` remains `standard` in generated manifests unless manually edited
- `--persist-facts`
  - include facts persistence in the generated manifest
- `--facts-dir`
  - relative facts directory written into the manifest
- `--no-claude`
  - omit root `CLAUDE.md` generation
- `--output`
  - manifest JSON output path
- `--report-output`
  - optional markdown report listing discovered and ignored directories with reasons and manual suggestions
  - the report includes suggestion levels such as `保持忽略`, `建议人工检查`, `建议纳入 manifest`
  - when manual action is recommended, the report also includes a copyable manifest snippet

## Typical workflow

1. Generate the manifest:

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_suite_manifest.py `
  --root C:\path\to\repo `
  --persist-facts `
  --report-output C:\path\to\repo\.codex\agents-suite-report.md `
  --output C:\path\to\repo\.codex\agents-suite.json
```

2. Generate the suite:

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_agents_suite.py `
  --manifest C:\path\to\repo\.codex\agents-suite.json
```

## Current limitations

- Discovery is first-level only.
- Child order is path-ascending only.
- Mixed or unusual project types still require manual manifest edits.
- The report explains shallow discovery results, but it does not replace manual review for ambiguous repositories.
- The report suggestions are intentionally conservative and should be treated as review hints, not authoritative decisions.
