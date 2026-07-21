# Suite Generator Usage

This document describes the batch orchestrator for generating a root-and-children AGENTS.md suite in one fixed-order run.

Script path:

- `scripts/generate_agents_suite.py`

## Scope

The suite generator orchestrates multiple single-target generations.

Fixed order:

1. child `AGENTS.md` targets
2. root `AGENTS.md`
3. root `CLAUDE.md`

It keeps orchestration thin and delegates actual extraction and rendering to `generate_agents.py`.

## Manifest format

Use a JSON manifest.

```json
{
  "root": "C:/path/to/repo",
  "detail_level": "rich",
  "persist_facts": true,
  "facts_dir": ".codex/agents-facts",
  "children": [
    {
      "template": "backend-child",
      "target": "backend",
      "output": "backend/AGENTS.md"
    },
    {
      "template": "frontend-child",
      "target": "web",
      "output": "web/AGENTS.md",
      "detail_level": "rich"
    }
  ],
  "root_agents": {
    "output": "AGENTS.md",
    "host": "codex",
    "detail_level": "standard",
    "database_project": "example-project",
    "database_production_read_target": "backend-prod-ro"
  },
  "claude": {
    "output": "CLAUDE.md",
    "host": "claude"
  }
}
```

## Command

Use the project-approved Python environment for skill/template tooling:

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/generate_agents_suite.py `
  --manifest C:\path\to\repo\.codex\agents-suite.json
```

## Manifest fields

- `root`
  - repository root path
- `detail_level`
  - default detail level for child targets
  - omitted value defaults to `rich`
  - child targets can override this with `children[].detail_level`
  - root and Claude generation default to `standard` unless their own config sets `detail_level`
- `persist_facts`
  - whether to save intermediate facts JSON files
- `facts_dir`
  - relative directory for persisted facts
- `children`
  - ordered list of child targets
- `root_agents`
  - root `AGENTS.md` generation config
  - may set `template`, `target`, and `single_project: true` to render a child template directly as root rules for a single-project repository
  - may set `database_project` only when `template` is `root`; the value is explicit and is never inferred
  - may set `database_production_read_target` only with `database_project`; the default production-read target is explicit and is never inferred
- `claude`
  - Claude entry generation config; default output is repository-root `CLAUDE.md`

## Single-project root config

For a repository where the root is the actual app or service, use a child template as the root output:

```json
"root_agents": {
  "output": "AGENTS.md",
  "host": "codex",
  "template": "frontend-child",
  "target": ".",
  "detail_level": "rich",
  "single_project": true
}
```

When `single_project` is true, child-template intro text is rewritten so root `AGENTS.md` does not claim to inherit from itself.

## Notes

- Child targets should be declared in the desired stable order.
- The root file automatically receives generated child `AGENTS.md` paths.
- The `CLAUDE.md` file automatically receives generated child include paths rewritten relative to its output location.
- If you need to inspect or edit a single target manually, fall back to `generate_agents.py`.
