---
name: agents-md-generator
description: Fill standardized AGENTS.md templates for a repository root or a specific subproject. Use when the user asks to generate, split, or update AGENTS.md files while keeping a fixed section structure and mostly fixed wording across projects, with only repository facts such as overview, structure, commands, validation, and config boundaries changing.
---

# AGENTS.md Template Filler

Fill AGENTS.md from fixed templates. Keep the section structure stable across repositories and change only verified local facts.

## Stability goal

This skill should behave like a constrained template renderer, not a freeform writer.

- For the same repository facts and the same target scope, the generated result should keep the same:
  - template selection
  - `##` section order
  - variable-field order inside each section
  - fallback wording for missing facts
- Wording outside the fact-filled areas should be treated as fixed template text.
- If a detail cannot be verified locally, do not improvise a new sentence shape. Use the predefined fallback wording or omit only the explicitly optional subsection.
- Prefer deterministic rendering behavior over stylistic variety.

## Default mode

Use strict template mode by default.

In strict template mode:

- Keep the second-level `##` section structure fixed.
- Reuse the bundled standard wording whenever possible.
- Only replace project-specific facts such as:
  - repository overview
  - project structure
  - commands
  - validation commands
  - config file names
  - package manager and runtime versions
- Extract facts into a stable intermediate structure before rendering prose.
- Do not freely rewrite stable sections unless the user explicitly asks to customize the template.
- Treat the global `编码行为四原则` block as fixed baseline text; do not rewrite, duplicate, or move it while filling repository-specific facts.
- Do not reorder sibling bullets in fact-filled sections unless the template or facts schema explicitly requires it.

## Stable generation model

Always use a two-stage generation flow:

1. Facts extraction
   - Collect verified local facts with shallow scanning.
   - Normalize them into a fixed schema.
   - Preserve stable key ordering from the schema definition.
2. Template rendering
   - Select the target template.
   - Fill only the allowed fact fields.
   - Keep section order and fact-field rendering order stable.
3. Validation
   - Check that the rendered file still matches the template structure.
   - Check that missing facts use predefined fallback wording.

Do not skip the facts-extraction stage for convenience when the task is AGENTS generation.

## Local renderer

When the task requires maximum output stability, prefer the local helper renderer after facts extraction:

- script: `scripts/render_agents_from_facts.py`
- usage: `references/renderer-usage.md`
- behavior:
  - reads normalized facts JSON
  - renders the selected bundled template
  - removes unused repeated placeholder lines
  - fails if unresolved placeholders remain

The helper renderer is narrow by design. It does not replace local fact extraction or template selection.

## Local extractor

When the task requires a repeatable `facts -> render` workflow, use the local extractor before rendering:

- script: `scripts/extract_facts.py`
- usage: `references/extractor-usage.md`
- behavior:
  - performs shallow repository scanning only
  - emits normalized facts JSON for bundled templates
  - avoids reading sensitive config file contents
  - keeps extraction conservative and repeatable

## Unified generator

When the task requires the simplest repeatable local path, prefer the unified generator:

- script: `scripts/generate_agents.py`
- usage: `references/generator-usage.md`
- behavior:
  - runs shallow extraction
  - optionally persists intermediate facts JSON
  - renders the final markdown output in one command

Use the unified generator for single-target generation. Use extractor + renderer separately when intermediate facts need inspection or manual adjustment.

## Suite generator

When the task requires generating a full AGENTS.md hierarchy in one run, prefer the suite generator:

- script: `scripts/generate_agents_suite.py`
- usage: `references/suite-generator-usage.md`
- behavior:
  - reads a manifest describing child targets, root output, and claude output
  - generates child files first
  - generates root `AGENTS.md` next
  - generates root `CLAUDE.md` last

Use the suite generator for stable multi-file orchestration. Keep template-specific extraction and rendering in the lower-level helpers.

## Manifest generator

When the task requires reducing manual suite setup, prefer the manifest generator first:

- script: `scripts/generate_suite_manifest.py`
- usage: `references/manifest-generator-usage.md`
- behavior:
  - scans the repository root and first-level child directories
  - discovers conservative backend/front-end targets
  - writes a manifest for `generate_agents_suite.py`
  - can also write a review report for manual correction

Use it when the repository follows common child-project layout and shallow discovery is sufficient.

## Codex and Gemini asset sync

When the task requires syncing this skill package's global assets to the user-level Codex and Gemini homes, use the unified sync script:

- script: `scripts/sync_codex_assets.py`
- shell entry: `sync_codex_assets.sh`
- Windows entry: `sync_codex_assets.cmd`
- behavior:
  - syncs `references/global-template.md` to `${CODEX_HOME:-~/.codex}/AGENTS.md`
  - syncs `references/global-template.md` to `~/.gemini/GEMINI.md`
  - syncs global policy references used by `references/global-template.md` into `${CODEX_HOME:-~/.codex}/references/`
  - flattens `subagents-main/**/*.toml` into `${CODEX_HOME:-~/.codex}/agents/`
  - syncs this top-level `agents-md-generator` skill runtime assets into `${CODEX_HOME:-~/.codex}/skills/agents-md-generator/`
  - includes the Python sync implementation and source subagents in the installed skill runtime package; keeps the macOS/Linux and Windows entry scripts in the source checkout only
  - syncs local nested `skills/*/` directories into `${CODEX_HOME:-~/.codex}/skills/`
  - when `operate-database-profiles` is configured as a local plugin in the default personal marketplace, rebuilds its plugin source from the canonical skill, assigns a fresh Codex cachebuster, and reinstalls it with `codex plugin add`
  - skips plugin installation when that personal marketplace entry is absent, rather than creating or rewriting marketplace configuration implicitly
  - accepts `--check` for read-only drift detection and `--overwrite-runtime-drift` for explicitly replacing reviewed managed runtime or plugin-source drift
  - requires a new Codex task after plugin refresh so the new MCP process and tool definitions are loaded

## Inheritance model

Use layered inheritance for generated files:

- Global baseline: `references/global-template.md`
- Global policy references: `references/safety-policy.md`, `references/workflow-policy.md`, `references/subagents-policy.md`, `references/performance-policy.md`, `references/search-policy.md`, `references/session-policy.md`, `references/web-task-policy.md`, `references/document-tools-policy.md`, `references/tool-report-policy.md`, `references/commit-policy.md`
- Skill-backed global workflows: `$web-task-routing`, `$document-tools-routing`, `$operate-database-profiles`
- Root template: `references/root-template.md`
- Child templates: `references/dotnet-backend-child-template.md`, `references/nestjs-backend-child-template.md`, `references/spring-boot-backend-child-template.md`, `references/frontend-child-template.md`, `references/userscripts-child-template.md`

Priority:

- Child `AGENTS.md` > Root `AGENTS.md` > Global baseline

Conflict resolution:

- Security and privacy constraints: stricter rule wins.
- Verified local facts (paths, commands, config names): nearest scope wins.
- If unresolved safely, keep stricter behavior and request confirmation on conflicting local facts.

## Overwrite rule

If the target path already contains an `AGENTS.md` file:

- Do not overwrite it immediately.
- First summarize what will be generated or updated.
- Ask the user whether to overwrite the existing file.
- If the user does not confirm, stop before writing and do not modify the file.
- If the user confirms, proceed with the template-filling workflow.

This applies to both repository-root and child-project `AGENTS.md` files.

When generating repository-root files, apply the same overwrite confirmation rule to `CLAUDE.md`:

- Do not overwrite existing `CLAUDE.md` without explicit confirmation.
- If the user confirms root overwrite, update `AGENTS.md` first, then update `CLAUDE.md`.

## Performance rules

Use a shallow, targeted collection strategy.

- Start from the repository root and scan root plus first-level child directories only.
- Do not start with full-repository recursive searches.
- Exclude large or irrelevant directories by default:
  - `.git`
  - `node_modules`
  - `dist`
  - `build`
  - `out`
  - `coverage`
  - `.vite`
  - `bin`
  - `obj`
- Read only the minimum files needed to fill the template:
  - `package.json`
  - `.csproj`
  - `.sln`
  - `tsconfig.*`
  - `vite.config.*`
  - `webpack.config.*`
  - `jest.config.*`
  - `playwright.config.*`
  - a shallow directory listing for the target project
- If multiple child `AGENTS.md` files are requested, process them in order rather than doing a deep scan of the whole repository first.
- If an `AGENTS.md` already exists at a target path, ask for overwrite confirmation before performing deeper project analysis for that target.

## Core workflow

1. Determine the target scope:
   - repository root `AGENTS.md`
   - .NET back-end child `AGENTS.md`
   - NestJS back-end child `AGENTS.md`
   - Spring Boot back-end child `AGENTS.md`
   - front-end child `AGENTS.md`
   - userscripts child `AGENTS.md`
   - other child project `AGENTS.md`
2. Select the fixed template:
   - global baseline: `references/global-template.md` (inheritance source)
   - global policy references: `references/safety-policy.md`, `references/workflow-policy.md`, `references/subagents-policy.md`, `references/performance-policy.md`, `references/search-policy.md`, `references/session-policy.md`, `references/web-task-policy.md`, `references/document-tools-policy.md`, `references/tool-report-policy.md`, `references/commit-policy.md`
   - skill-backed global workflows: `$web-task-routing`, `$document-tools-routing`, `$operate-database-profiles`
   - root: `references/root-template.md`
   - .NET back-end child: `references/dotnet-backend-child-template.md`
   - NestJS back-end child: `references/nestjs-backend-child-template.md`
   - Spring Boot back-end child: `references/spring-boot-backend-child-template.md`
   - front-end child: `references/frontend-child-template.md`
   - userscripts child: `references/userscripts-child-template.md`
   - claude root include file: `references/claude-template.md`
3. Collect target facts with shallow scanning first:
   - repository root entries
   - first-level child directories
   - only the minimum config and command files needed for the target
4. Normalize collected facts using the stable schema reference:
   - use `references/facts-schema.md`
   - keep field order stable
   - use predefined fallback wording for missing facts
5. If an `AGENTS.md` already exists at the target path, pause and request overwrite confirmation before deeper analysis.
6. Fill AGENTS templates with verified local facts.
   - Root output should inherit global baseline and avoid duplicating long global sections.
   - Child output should focus on local execution details and avoid restating root/global long-form rules.
   - render sections and bullets in the schema-defined order
   - do not introduce ad hoc summary sentences outside the template allowances
7. Generate requested `AGENTS.md` files first (root and/or child targets).
8. After `AGENTS.md` generation, generate the repository-level Claude entry only.
   - Do not generate `CLAUDE.md` in child directories.
   - Default Claude entry output is repository-root `CLAUDE.md` unless the user explicitly requests another allowed location.
   - `CLAUDE.md` should include root and generated child `AGENTS.md` paths via `@...` lines, rewritten relative to the final `CLAUDE.md` output path.
   - Project-local working notes, traces, and staged artifacts remain governed by the repository rule set; when the generated root `AGENTS.md` defines `.codex/` as the local trace directory, Claude and Gemini should follow that same project-local directory rather than introducing `.claude/` or `.gemini/` siblings.
9. Validate the result:
   - section structure remains intact
   - commands exist
   - paths exist
   - project names and module names match the target repository
  - repository Claude entry exists at the requested output path (default `CLAUDE.md`)
  - `CLAUDE.md` contains `@...` lines pointing to root `AGENTS.md` and generated child targets only
   - fact-filled bullets follow stable schema order
   - missing facts use predefined fallback wording rather than freeform paraphrase

## Completion rule

Once the requested `AGENTS.md` files (and root `CLAUDE.md` when root is in scope) have been generated or updated and validated, stop there.

- Do not proactively suggest further refinements such as:
  - compressing wording further
  - changing tone strength
  - rewriting into a more operational style
  - generating extra child AGENTS.md files not requested by the user
- Only propose follow-up changes if:
  - the user explicitly asks for refinement, or
  - required local facts are missing and block correct generation

## Final response rule

After successful generation, the final response should contain only:

- which `AGENTS.md` / `CLAUDE.md` files were created or updated
- whether overwrite confirmation was required
- what validation was performed

Do not include optional optimization suggestions unless the user explicitly asks for them.

## Preferred output heuristics

Apply these heuristics during the initial generation pass, not as post-generation refinement suggestions.

- Root AGENTS.md should stay at summary level and act as a repository-wide operating manual.
- Child AGENTS.md files should carry local execution detail such as boundaries, config touchpoints, commands, and validation.
- Prefer inheritance over duplication: if a detail belongs in a child file, point to the child file from the root instead of restating it.
- Prefer concise, directive bullets in fact-filled sections so the result is easy for an agent to execute.
- When shortening content, remove repetition first; do not remove executable facts such as real commands, paths, or config names.
- If multiple phrasings would be valid, prefer the wording already present in the template or schema reference.
- Project-local trace directories should remain repository-scoped. If the root rule set uses `.codex/` for local traces, do not add parallel `.claude/` or `.gemini/` project directories just because another host will consume the same project rules.

## Project-specific rich generation

When the user asks for more project-specific `AGENTS.md` output, keep strict template mode enabled and use richer verified facts instead of freer prose.

- Child-project targets default to `rich`; root and Claude targets default to `standard`.
- Pass `--detail-level standard` or `--detail-level basic` explicitly when a child target should stay shorter.
- Enrich output only through verified facts:
  - local architecture directories
  - real package, build, test, and wrapper scripts
  - validation commands by change type
  - config touchpoints by file name only
  - generated or high-risk paths
  - existing migration, code generation, and tooling boundaries
- Do not infer framework conventions unless confirmed by local files.
- Do not read sensitive config contents.
- Do not add freeform project advice outside template-defined rich blocks.
- For suite generation, treat the manifest-level `detail_level` as the child-target default; keep root generation `standard` unless explicitly overridden.

## Root generation rules

When generating a repository-root `AGENTS.md`:

- If the repository root itself is the actual project and no first-level child target is discovered, use the matching child template as root output with `single_project: true`.
- In single-project mode, render rich project details in root `AGENTS.md` and rewrite child-template intro text so the file does not inherit from itself.
- Preserve the fixed `##` section list from the root template.
- Keep global baseline content inherited by reference; do not duplicate long global sections in root.
- Only customize the repository overview, environment summary, child-project references, and appendix command references.
- If child-project `AGENTS.md` files exist or should exist, keep the root file at summary level and point detailed rules to child files.
- Generate the repository Claude entry after root/child `AGENTS.md` generation completes.
- Do not create `CLAUDE.md` in child directories.
- `CLAUDE.md` must include:
  - the root `AGENTS.md` include line
  - `@<child>/AGENTS.md` for each generated child target, rewritten relative to the final output path

## Child generation rules

When generating a child-project `AGENTS.md`:

- Preserve the fixed section list from the matching child template.
- State clearly that the file applies to that directory and inherits `Root > Global`.
- Only fill the local structure, local boundaries, local validation commands, local config names, and local command examples.
- Do not copy the root file's global sections into the child file.

## Template selection rules

- Use the root template for repository-level files.
- Use the .NET back-end child template for projects identified by markers such as `.csproj`, `.sln`, `pom.xml`, `build.gradle`, or server-side source trees.
- Use the NestJS back-end child template for Node back-end projects identified by `package.json` with `@nestjs/*` dependencies, `src/main.ts`, `src/app.module.ts`, or Prisma-driven NestJS structure.
- Use the front-end child template for projects identified by markers such as `package.json`, `src/`, `vite.config.*`, `webpack.config.*`, or front-end test configs.
- If a project type is unclear, infer the nearest matching template from local files and keep the same fixed-template philosophy.

## What to avoid

- Do not generate a new section layout unless the user explicitly asks for template evolution.
- Do not rewrite stable sections just because another wording is also reasonable.
- Do not reorder stable fact groups for stylistic reasons.
- Do not switch between omission and fallback text for the same missing field across runs.
- Do not invent commands not found in local files.
- Do not leave source-project names, paths, or module names in the generated file.
- Do not leave unresolved placeholders in generated files (for example `[字段]`, `[路径]`, `<value>`).
- Do not duplicate the entire root file into child directories.
- Do not overwrite an existing `AGENTS.md` without explicit user confirmation.
- Do not overwrite an existing `CLAUDE.md` without explicit user confirmation.
- Do not generate `CLAUDE.md` in child directories.
- Do not begin with broad recursive scanning of the full repository.

## Template evolution

If the user asks to add, remove, or rename a section:

1. Update the corresponding template file under `references/` first.
2. Then regenerate or update the target `AGENTS.md` files from that template.
3. Keep section ordering stable across repositories unless the user explicitly wants a new standard.

## References

Read as needed:

- Global baseline template: `references/global-template.md`
- Global policy references: `references/safety-policy.md`, `references/workflow-policy.md`, `references/subagents-policy.md`, `references/performance-policy.md`, `references/search-policy.md`, `references/session-policy.md`, `references/web-task-policy.md`, `references/document-tools-policy.md`, `references/tool-report-policy.md`, `references/commit-policy.md`
- Root template: `references/root-template.md`
- .NET back-end child template: `references/dotnet-backend-child-template.md`
- NestJS back-end child template: `references/nestjs-backend-child-template.md`
- Spring Boot back-end child template: `references/spring-boot-backend-child-template.md`
- Front-end child template: `references/frontend-child-template.md`
- Claude include template: `references/claude-template.md`
- Stable facts schema: `references/facts-schema.md`
- Facts catalog: `references/facts-catalog.md`
- Render policy: `references/render-policy.md`
- Extractor usage: `references/extractor-usage.md`
- Renderer usage: `references/renderer-usage.md`
- Generator usage: `references/generator-usage.md`
- Suite generator usage: `references/suite-generator-usage.md`
- Manifest generator usage: `references/manifest-generator-usage.md`
- Template filling rules: `references/template-sources.md`
- Merge strategy: `references/merge-strategy.md`
- Prompt examples: `references/prompt-examples.md`
