# Stable Facts Schema

This document defines the normalized facts structure used before rendering `AGENTS.md`.

The goal is not to expose raw scan output. The goal is to provide a stable intermediate representation so the same repository facts produce the same rendered sections and bullet order.

## Rules

- Extract facts first, render later.
- Keep keys in the documented order.
- Do not create extra sibling keys unless the template standard evolves.
- Only include verified facts.
- If a fact is missing, use the fallback rule defined for that field.

## Root facts schema

Render root-level facts in the following order:

```yaml
root_facts:
  host_profile:
    host:
    global_rule_path:
    project_trace_dir:
    user_home_dir:
  repository_profile:
    repo_shape:
    summary_line:
  top_level_entries:
    - path:
      project_type:
      description:
  child_agents_paths:
    - path:
  environment:
    package_managers:
      - name:
        version:
    runtimes:
      - name:
        version:
  database_profile_binding:
    project_identifier:
    default_production_read_target:
  command_refs:
    - scope:
      path:
  validation_refs:
    - scope:
      command:
  config_boundaries:
    - scope:
      files:
        - name:
```

## Child facts schema

Render child-level facts in the following order:

```yaml
child_facts:
  project_identity:
    path:
    project_type:
    inheritance_line:
  structure:
    entry_points:
      - path:
        purpose:
    source_dirs:
      - path:
        purpose:
    feature_dirs:
      - path:
        purpose:
    shared_dirs:
      - path:
        purpose:
    generated_dirs:
      - path:
        purpose:
    test_dirs:
      - path:
        purpose:
    script_dirs:
      - path:
        purpose:
    docs_dirs:
      - path:
        purpose:
    sql_script_dirs:
      - path:
        purpose:
  commands:
    install:
    dev:
    build:
    test:
    lint:
    format:
    typecheck:
    preview:
    codegen:
    migrate:
    seed:
  validation:
    quick_command:
    minimal_command:
    build_command:
    unit_test_command:
    e2e_test_command:
    typecheck_command:
    smoke_command:
    by_change_type:
      - change:
        command:
        reason:
    supplementary_commands:
      - command:
  environment:
    package_manager:
    lockfile:
    node_version:
  config_touchpoints:
    files:
      - name:
        purpose:
    example_files:
      - name:
        purpose:
    runtime_mode_files:
      - name:
        mode:
    binding_files:
      - name:
        purpose:
  boundaries:
    allowed_paths:
      - path:
    avoid_paths:
      - path:
    generated_paths:
      - path:
        purpose:
    high_risk_touchpoints:
      - path:
        reason:
```

## Stable ordering rules

- `top_level_entries`, `entry_points`, `source_dirs`, `feature_dirs`, `shared_dirs`, `generated_dirs`, `test_dirs`, `script_dirs`, `docs_dirs`, `sql_script_dirs`, `allowed_paths`, `avoid_paths`, `generated_paths`, and `high_risk_touchpoints` use path-ascending order.
- `child_agents_paths` use path-ascending order.
- `host_profile` uses fixed key order: `host`, `global_rule_path`, `project_trace_dir`, `user_home_dir`.
- `package_managers` and `runtimes` use name-ascending order.
- `config_boundaries.files` and `config_touchpoints.files` use file-name ascending order.
- Command fields use the fixed order: `install`, `dev`, `build`, `test`, `lint`, `format`, `typecheck`, `preview`, `codegen`, `migrate`, `seed`.
- Do not drop a command key and then reinsert it elsewhere as prose.
- `validation.by_change_type` uses the fixed extractor order and must not be reordered for perceived importance.

## Missing facts fallback rules

Use these fixed fallbacks instead of freeform paraphrase:

- Missing repository summary:
  - `当前仓库按本地已验证目录结构组织；未在浅层扫描中补充更多仓库概览。`
- Missing child AGENTS paths:
  - omit the child list subsection only if no child target is requested
- Missing runtime or package manager version:
  - `未在本地浅层扫描中确认具体版本；以项目配置文件或子目录 AGENTS.md 为准。`
- Missing command value:
  - `未在本地浅层扫描中确认对应命令；执行前先查看项目配置文件。`
- Missing validation command:
  - `未在本地浅层扫描中确认最小验证命令；执行前先查看项目测试配置。`
- Missing config file list:
  - `未在本地浅层扫描中确认额外配置文件；仅按已验证文件操作。`
- Missing config touchpoint details:
  - `未在本地浅层扫描中确认额外配置 touchpoint；仅按已验证文件操作。`
- Missing database profile binding:
  - omit the complete `### 数据库 Profile 绑定` subsection when the project identifier is absent; never infer the project identifier or default production-read target from a directory, repository, solution, database name, target list, or prior task
- Missing structure detail:
  - `未在本地浅层扫描中展开更多目录细节；需要时再做局部确认。`
- Missing validation matrix:
  - `未在本地浅层扫描中确认按改动类型区分的验证矩阵；执行前先查看项目测试配置。`
- Missing generated or high-risk paths:
  - `未在本地浅层扫描中确认生成目录或额外高风险 touchpoint；仍按全局敏感与高风险规则处理。`
- Missing SQL script directory:
  - `未在本地浅层扫描中确认现有 SQL 脚本目录；默认优先使用 db/migrations，其次考虑 database/migrations 或 sql/migrations。`
- Missing SQL tooling:
  - `未在本地浅层扫描中确认现有数据库迁移工具链；默认先复用仓库既有迁移方式，只有在已存在 SQL 脚本体系或任务明确要求时才新增裸 SQL 文件。`

## Rendering discipline

- Facts should be rendered into the nearest matching template subsection only.
- Do not duplicate the same fact in multiple sections unless the template explicitly requires a reference.
- If a subsection is optional and all its fields are missing, either:
  - use the fixed fallback sentence for that subsection, or
  - omit the subsection only when this document explicitly allows omission.
- Once a fallback is chosen for a field class, use the same fallback wording across runs.
