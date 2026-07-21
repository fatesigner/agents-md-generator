# Template Filling Rules

This skill is a standard template filler, not an open-ended AGENTS generator.

## Core principle

Keep section structure and wording stable across repositories. Only fill verified local facts.

## Stable rendering principle

Treat AGENTS generation as a deterministic rendering task constrained by templates and facts schema.

- First normalize local facts using `facts-schema.md`.
- Then render the selected template with those normalized facts.
- For the same normalized facts, keep the same section order, bullet order, and fallback wording across runs.
- Do not use stylistic variation to "improve" the result.

## Section structure source

- The section structure is defined directly by the selected template file.
- Global baseline template -> `global-template.md` (for inherited stable rules)
- Global policy references -> `subagents-policy.md`, `web-task-policy.md`, `document-tools-policy.md`, `tool-report-policy.md`, `commit-policy.md`
- Root file -> `root-template.md`
- .NET back-end child file -> `dotnet-backend-child-template.md`
- NestJS back-end child file -> `nestjs-backend-child-template.md`
- Spring Boot back-end child file -> `spring-boot-backend-child-template.md`
- Front-end child file -> `frontend-child-template.md`
- Claude root include file -> `claude-template.md`
- Keep the selected template's section list fixed unless the user explicitly requests template evolution.
- Prefer inheritance over duplication.
- Use concise bullets.
- Keep local-fact sections concrete and executable.
- Keep fact-field rendering order consistent with `facts-schema.md`.

## Inheritance and merge

- Priority: Child `AGENTS.md` > Root `AGENTS.md` > Global baseline.
- Security and privacy rules use stricter-wins merge.
- Local facts use nearest-scope-wins merge.
- Root should reference global baseline rather than duplicating long global text blocks.
- Child files should not restate root/global long-form sections.
- Low-frequency global procedures should remain in policy reference files and be loaded only when the task matches that procedure.
- Web/browser and document-tool procedures may be implemented as user-level skills (`$web-task-routing`, `$document-tools-routing`) while the policy files remain the template-maintenance source.

## Built-in quality heuristics

Apply these heuristics during the first draft instead of offering them later as optional refinements:

- 根级 AGENTS.md 保持摘要层级，承担跨项目总则和分流职责。
- 子级 AGENTS.md 聚焦局部边界、配置触点、常用命令和最小验证要求。
- 根级文件引用子级文件，不重复展开子级细节。
- 可变事实区使用简洁、直接、可执行的条目式表达。
- 压缩内容时优先删除重复说明，不删除真实路径、命令、配置文件名和验证要求。
- 对前端项目，组件目录归属应显式区分“共享能力”和“页面局部实现”：具备明确复用价值的组件进入共享目录，页面私有组件可留在页面目录，但页面目录内避免使用 `shared` 作为局部目录名，优先使用 `components`、`parts`。
- 缺失事实时优先使用固定回退文案，不为同类缺失事实生成不同表述。

## What can change

These areas may change per repository:

- 仓库概览
- 根级文件中的子项目引用方式
- 技术栈与环境中的本地版本和项目路径
- 子项目结构
- 配置文件名
- 本地命令
- 本地验证方式
- 子级文件中的局部边界与配置触点

These areas should change only through normalized facts, not ad hoc prose:

- 仓库概览的事实条目顺序
- 子项目清单顺序
- 命令字段值
- 验证命令值
- 配置文件名清单
- 运行时和包管理器版本

## What should stay stable

These areas must remain verbatim or near-verbatim to the standard templates unless the user explicitly asks for customization:

- 基本协作规则
- 编码行为四原则（Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution），来源锚点：https://github.com/multica-ai/andrej-karpathy-skills
- 代码改动约束的总则
- 编码风格与命名规范的大部分正文
- 提交与交付
- 角色定位与职责边界
- 高风险操作
- 配置与密钥边界
- 工具与降级
- 文档处理工具约定摘要及专项引用
- 文档与留痕
- 工作流程
- 缺失事实的回退文案
- 事实字段的渲染顺序

## Facts normalization

Before rendering:

1. Extract only verified local facts.
2. Expand fact coverage according to `facts-catalog.md` and the requested detail level.
3. Map them into the fixed schema from `facts-schema.md`.
4. Sort list-like fields according to the schema rules.
5. Render fields according to `render-policy.md`.

Do not directly transform raw scan notes into prose paragraphs.

## Detail enrichment policy

When the user wants richer project detail:

- increase fact coverage, not prose freedom
- prefer additional verified bullets over longer summary paragraphs
- stay within the template's existing section boundaries
- use `facts-catalog.md` to decide which extra facts are worth extracting
- use `render-policy.md` to decide which verified facts should actually appear in the rendered file

## Local renderer policy

When a task explicitly aims for maximum repeatability:

- prefer `scripts/render_agents_from_facts.py` after facts normalization
- use `renderer-usage.md` as the invocation contract
- keep the renderer narrow and template-specific rather than making it a general prose generator
- if the renderer cannot express a new field cleanly, evolve the schema and template references first

## Local extractor policy

When a task explicitly aims for a repeatable end-to-end workflow:

- prefer `scripts/extract_facts.py` for shallow, conservative fact extraction
- use `extractor-usage.md` as the invocation contract
- keep extraction aligned with `facts-catalog.md` but allow partial coverage when only a subset is locally verifiable
- expand extraction coverage gradually instead of adding speculative inference

## Unified generator policy

When a task is a straightforward generation request for one target file:

- prefer `scripts/generate_agents.py`
- use `generator-usage.md` as the invocation contract
- keep orchestration logic thin and delegate extraction/rendering to the lower-level helpers
- if a task needs review of intermediate facts, fall back to separate extractor and renderer calls

## Suite generator policy

When a task explicitly asks for a root-plus-children AGENTS suite:

- prefer `scripts/generate_agents_suite.py`
- use `suite-generator-usage.md` as the invocation contract
- keep execution order stable: child targets -> root AGENTS -> root CLAUDE
- keep the manifest explicit rather than inferring a large multi-target plan from prose at runtime

## Manifest generator policy

When a task needs a suite manifest but the repository layout is conventional:

- prefer `scripts/generate_suite_manifest.py`
- use `manifest-generator-usage.md` as the invocation contract
- keep discovery shallow and conservative
- when useful, emit a discovery report so users can correct the manifest with minimal guesswork
- require manual manifest edits for unusual or ambiguous project types rather than broadening inference too early

## Selection rules

- Global baseline reference -> `global-template.md`
- Global policy references -> `subagents-policy.md`, `web-task-policy.md`, `document-tools-policy.md`, `tool-report-policy.md`, `commit-policy.md`
- Skill-backed workflows -> `$web-task-routing`, `$document-tools-routing`
- Root file -> `root-template.md`
- .NET back-end child file -> `dotnet-backend-child-template.md`
- NestJS back-end child file -> `nestjs-backend-child-template.md`
- Spring Boot back-end child file -> `spring-boot-backend-child-template.md`
- Front-end child file -> `frontend-child-template.md`
- Field merge reference -> `merge-strategy.md`
- Root `CLAUDE.md` should be generated from `claude-template.md` after AGENTS generation.
- `CLAUDE.md` should include root and child `AGENTS.md` paths via `@...` lines, rewritten relative to the final `CLAUDE.md` output path.
- Do not generate `CLAUDE.md` in child directories.
- Project-local trace directories remain a repository concern, not a host concern. If the repository rule set standardizes on `.codex/` for local traces, Claude and Gemini should reuse that same project directory instead of creating host-specific siblings.

## Overwrite policy

- If the target location already contains `AGENTS.md`, first ask the user whether to overwrite it.
- Without explicit confirmation, do not modify the existing file.
- Before confirmation, do only the minimum analysis needed to explain what would change.
- For repository root generation, apply the same overwrite confirmation rule to `CLAUDE.md`.

## Performance policy

- Start with root-level and first-level directory inspection only.
- Exclude `.git`, `node_modules`, `dist`, `build`, `out`, `coverage`, `.vite`, `bin`, and `obj` by default.
- Read only the minimum configuration files needed for the selected template.
- For multi-project generation, process targets one by one rather than recursively scanning the whole repository up front.

## Final checks

- The `##` section list must match the chosen template.
- Commands must exist in local files.
- Paths must exist.
- The result must not contain unresolved placeholders such as `[...]` or `<...>`.
- The result must not contain names copied from unrelated repositories.
- When generating repository root files, `CLAUDE.md` must include root and generated child AGENTS include paths.
- No child-directory `CLAUDE.md` files should be generated.
- If local facts are missing, leave only a cautious generic sentence or omit the variable subsection; do not invent facts.
- If local facts are missing and `facts-schema.md` defines a fallback sentence, use that sentence verbatim.
- Bullet order inside variable sections must match the schema order.
- Once final checks pass, stop and return the result without proposing extra stylistic improvements.


