# Render Policy

This document defines how normalized facts are rendered into fixed templates.

Use this file together with:

- `facts-catalog.md`: what to extract
- `facts-schema.md`: how extracted facts are normalized

## Goal

Render more detailed project facts without making the output noisier or less stable.

- Templates define structure.
- Facts define detail.
- Render policy defines what is shown, where it is shown, and when it is omitted.

## Section mapping

### Root template mapping

- `## 仓库概览`
  - render: `repository_profile`, `top_level_entries`
  - do not render: commands, validation, config file details
- `## 技术栈与环境`
  - render: package managers, runtimes, high-level framework markers
  - do not render: path boundaries
- `## 代码改动约束`
  - render: only repository-scope boundaries and routing hints
- `## 测试与验证`
  - render: high-level command references or child-rule references only
- `## 附录：常用命令与示例`
  - render: command references and child AGENTS references

### Child template mapping

- project identity section
  - render: target path, type, inheritance line
- structure section
  - render: source dirs, test dirs, sql script dirs, shared dirs, feature dirs, generated dirs when high-value
- commands section
  - render: command facts in fixed order
- validation section
  - render: minimal validation command first, then supplementary commands
- config section
  - render: safe config touchpoints only
- boundaries section
  - render: allowed paths, generated paths, avoid paths, high-risk touchpoints

Do not move a fact group into another section just because it "reads better" there.

Child title naming rule:

- For front-end child templates, `[前端项目名]` should map to the child directory name, not `package.json.name`.
- The child directory name is more stable for repository navigation and better matches the generated file scope.
- Only switch to package-name-based display if the user explicitly asks for that behavior.

## Display priority

When there are many verified facts, display them in this priority order:

1. Minimal executable facts
   - primary commands
   - minimal validation
   - target scope and inheritance
2. Main structure facts
   - source dirs
   - test dirs
   - config touchpoints
3. High-value enrichment facts
   - shared dirs
   - feature dirs
   - typecheck
   - preview
   - codegen
   - migrate
   - generated paths
4. Nice-to-have detail
   - supplementary commands
   - environment modes
   - optional script entrypoints

If a section becomes crowded, drop lower-priority enrichment first, not core executable facts.

## Command rendering rules

- Use fixed key order:
  - `install`
  - `dev`
  - `build`
  - `test`
  - `lint`
  - `format`
  - `typecheck`
  - `preview`
  - `codegen`
  - `migrate`
  - `seed`
- Render a command only when locally verified.
- If the template expects a command area but the field is missing, use the command fallback from `facts-schema.md`.
- Do not rewrite multiple commands into one summary sentence if the command keys are available.

## Structure rendering rules

- Prefer short bullets in path-ascending order.
- Merge repetitive sibling directories only when their purpose is the same and the merge does not lose actionable detail.
- For front-end projects:
  - shared reusable UI goes under shared directories
  - page-local UI stays near the page
  - avoid presenting page-local directories as if they were shared infrastructure
- For back-end projects:
  - preserve layer distinctions such as API, service, repository, contract, domain when locally verified
  - when a fixed SQL script directory is locally verified, render that directory as the canonical location instead of describing SQL placement in prose

## Config rendering rules

- Prefer file names over prose descriptions.
- Sensitive config files may be mentioned by path or name only.
- Example config files have higher display value than secret-bearing real config files.
- If only one safe config touchpoint is known, render that single verified entry rather than inventing a larger config summary.

## Omission and fallback rules

- Omit a subsection only when the corresponding template and `facts-schema.md` allow omission.
- Omit the complete root `### 数据库 Profile 绑定` subsection when no explicit `database_profile_binding.project_identifier` fact is supplied; never synthesize a fallback identifier or default production-read target.
- Otherwise use the fixed fallback sentence from `facts-schema.md`.
- For the same missing field class, use the same fallback sentence across runs.
- Do not alternate between:
  - omission
  - a generic sentence
  - a custom explanation

## Detail-level behavior

### `basic`

- Render only the minimum executable facts and the minimum structure needed for safe operation.

### `standard`

- Render the default fact set from `facts-catalog.md`.
- Include high-value enrichment when verified and concise.

### `rich`

- Render richer detail only within the same template slots.
- Add more bullets, not more section types.
- Keep the same section order and command order.
- Prefer extra structure and command bullets over long explanatory paragraphs.

## Quality gates

Before finalizing a render, check:

- Are all displayed facts locally verified?
- Are facts rendered in the correct section?
- Does bullet order follow the fixed policy?
- Are core executable facts present before enrichment facts?
- Are missing facts handled by omission rules or fixed fallbacks?
- Is the result more informative without becoming repetitive?
