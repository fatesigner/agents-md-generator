# Facts Catalog

This document defines which repository facts should be extracted to enrich generated `AGENTS.md` files while keeping output stable.

Use this file together with:

- `facts-schema.md`: normalized intermediate structure
- `render-policy.md`: section mapping and display rules

## Design goal

The generator should become more detailed by extracting more verified facts, not by writing freer prose.

- Detail comes from broader fact coverage.
- Stability comes from fixed schema, fixed ordering, and fixed rendering rules.
- If a fact cannot be verified, do not infer it from convention alone.

## Detail levels

Use one of these detail levels during facts extraction:

- `basic`
  - Extract only the minimum facts needed to produce a correct file.
  - Suitable for quick generation or low-context repositories.
- `standard`
  - Default mode.
  - Extract the main structure, commands, validation, config touchpoints, and boundaries.
- `rich`
  - Extract as much verified detail as possible within the shallow-scan and target-scope limits.
  - May include extra command categories, environment modes, code generation steps, and additional structure annotations.

For the same repository and the same detail level, keep fact coverage stable across runs.

## Fact groups

All extracted facts should belong to one of the following groups.

### 1. Repository profile

Purpose:

- Describe repository shape and top-level project composition.

Fields:

- `repo_shape`
- `summary_line`
- `top_level_entries`
- `child_targets`

Allowed evidence:

- root directory listing
- first-level child directory listing
- root manifest files such as `package.json`, `.sln`, workspace files

### 2. Structure details

Purpose:

- Describe important source, test, script, config, docs, and generated directories.

Fields:

- `entry_dirs`
- `source_dirs`
- `shared_dirs`
- `feature_dirs`
- `test_dirs`
- `sql_script_dirs`
- `script_dirs`
- `docs_dirs`
- `generated_dirs`
- `avoid_paths`

Allowed evidence:

- shallow directory listing inside the target scope
- config references to known directories
- existing child `AGENTS.md` paths when relevant

### 3. Command details

Purpose:

- Capture runnable commands instead of general statements.

Fields:

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

Allowed evidence:

- `package.json`
- `Makefile`
- `justfile`
- `.csproj`
- solution-level build files
- repository scripts directory
- README command examples only when clearly executable and consistent with local files

### 4. Validation details

Purpose:

- Define minimal and supplementary local verification steps.

Fields:

- `minimal_command`
- `supplementary_commands`
- `smoke_entry`
- `manual_risk_notes`

Allowed evidence:

- test config files
- project scripts
- build config files
- local docs with explicit validation steps

### 5. Config touchpoints

Purpose:

- Identify configuration files that affect development or runtime behavior without leaking sensitive content.

Fields:

- `config_files`
- `example_config_files`
- `runtime_mode_files`
- `binding_files`

Allowed evidence:

- file existence only for sensitive config
- safe reading of non-sensitive example config or tool config
- config references from source code or manifests

### 6. Boundaries and risk areas

Purpose:

- Mark editable scope, generated artifacts, and paths that should usually not be touched.

Fields:

- `allowed_paths`
- `avoid_paths`
- `generated_paths`
- `high_risk_touchpoints`
- `sql_tooling`

Allowed evidence:

- target scope
- output directories in build configs
- code generation config
- repository conventions already expressed in local docs or AGENTS files

### 7. Database profile binding

Purpose:

- Bind a repository root to the stable project namespace used by `$operate-database-profiles` without exposing connection metadata or credentials.

Fields:

- `database_profile_binding.project_identifier`
- `database_profile_binding.default_production_read_target`

Allowed evidence:

- explicit user confirmation
- an approved project-generation manifest
- an existing managed repository rule whose exact identifier has been verified

Never infer either value from a directory name, Git remote, solution name, database name, target list, unique candidate, or prior task. The default production-read target is optional and requires an explicit project identifier. Omit the complete subsection when the project identifier is absent.

## Field-level extraction rules

### Required fields by target

For `root` targets:

- `repo_shape`
- `top_level_entries`
- `child_targets` when child generation is requested
- at least one environment or command reference when locally verified

For `child` targets:

- `project_identity`
- `source_dirs` or a structure fallback
- `commands.dev` or another locally verified primary command
- `validation.minimal_command` or the validation fallback
- `config_files` or the config fallback

Child identity naming rule:

- For front-end child targets, `project_identity.project_name` should use the target directory name by default.
- Do not use `package.json.name` as the displayed child-project title unless the user explicitly asks for package-name-based titles.
- For back-end child targets, keep using the directory name unless a more specific local project identity is explicitly required by the template.

### Optional but high-value fields

Prefer to extract these in `standard` or `rich` mode when locally verified:

- `shared_dirs`
- `feature_dirs`
- `sql_script_dirs`
- `typecheck`
- `preview`
- `codegen`
- `migrate`
- `runtime_mode_files`
- `generated_paths`

### Rich-only expansion

In `rich` mode, also try to extract:

- multiple environment modes such as `dev`, `test`, `prod`
- command wrappers such as workspace scripts or orchestration scripts
- explicit code generation pipelines
- more specific structure notes, such as shared-vs-page-local component placement
- supplementary validation flows beyond the minimum command
- validation matrix entries keyed by change type, such as logic, type/API, routing/auth, build, code generation, and data access changes
- generated paths that should normally be maintained by code generation commands instead of manual edits
- high-risk touchpoints such as auth, routing guards, database migrations, runtime config binding, request middleware, and cross-page state
- config touchpoints by file name only, including example configs, runtime-mode files, and config binding directories

Rich mode must remain evidence-based:

- Do not read sensitive configuration contents.
- Do not infer framework directories unless they exist locally.
- Do not add project advice outside template-defined rich blocks.
- Do not expand beyond the target project scope or the approved shallow-scan boundary.

Do not enter unrelated deep directories just to satisfy rich mode.

## Confidence and evidence

Each extracted fact should be judged with an internal confidence level:

- `high`: directly verified from a local file or path
- `medium`: verified from two consistent weak signals
- `low`: likely but not directly verifiable

Rendering rules:

- Render `high` confidence facts directly.
- Render `medium` confidence facts only if the evidence is still local and specific.
- Do not render `low` confidence facts. Use fallback wording instead.

## Exclusions

Do not extract the following into rendered facts unless the user explicitly asks:

- full dependency lists
- verbose version matrices
- transient tool cache paths
- low-signal utility directories
- secret-bearing config values
- speculative architecture claims

## Coverage checklist

Use this checklist before rendering:

- Did we identify the repository or child project type?
- Did we capture the main source/test/config areas?
- Did we capture the most important runnable commands?
- Did we capture the minimal verification path?
- Did we capture the main config touchpoints safely?
- Did we capture editable scope and avoid paths?

If coverage is incomplete, prefer a stable fallback sentence over speculative detail.
