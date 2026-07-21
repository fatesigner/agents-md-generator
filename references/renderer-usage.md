# Renderer Usage

This document describes the local helper script that renders `AGENTS.md` and `CLAUDE.md` from normalized facts JSON.

Script path:

- `scripts/render_agents_from_facts.py`

## Scope

The script is intentionally narrow:

- it does not scan repositories
- it does not infer facts
- it does not choose targets automatically
- it only renders templates from already prepared facts JSON

Use it after:

1. target scope selection
2. local fact extraction
3. facts normalization into the agreed structure

## Command

Use the project-approved Python environment for skill/template tooling:

```powershell
C:\Users\Fatesigner\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe `
  scripts/render_agents_from_facts.py `
  --template root `
  --facts .codex/root-facts.json `
  --output AGENTS.md
```

Supported template values:

- `root`
- `backend-child`
- `spring-boot-backend-child`
- `nestjs-backend-child`
- `frontend-child`
- `userscripts-child`
- `claude`

## Expected input shape

The script expects normalized JSON derived from `facts-schema.md`.

### Root example

```json
{
  "host_profile": {
    "host": "codex",
    "global_rule_path": "~/.codex/AGENTS.md",
    "project_trace_dir": ".codex",
    "user_home_dir": "~/.codex"
  },
  "repository_profile": {
    "repo_shape": "前后端分离多项目仓库"
  },
  "database_profile_binding": {
    "project_identifier": "example-project",
    "default_production_read_target": "backend-prod-ro"
  },
  "top_level_entries": [
    {
      "path": "backend",
      "project_type": "后端",
      "description": "API 与业务服务"
    },
    {
      "path": "web",
      "project_type": "前端",
      "description": "Web 管理端"
    }
  ],
  "child_agents_paths": [
    {
      "path": "backend/AGENTS.md"
    },
    {
      "path": "web/AGENTS.md"
    }
  ],
  "environment": {
    "package_managers": [
      {
        "name": "npm",
        "version": "10"
      }
    ],
    "runtimes": [
      {
        "name": "Node.js",
        "version": "22"
      }
    ]
  },
  "command_refs": [
    {
      "scope": "web",
      "path": "web/AGENTS.md"
    }
  ]
}
```

`database_profile_binding` is optional. When absent or empty, the renderer omits the complete `### 数据库 Profile 绑定` subsection. The project identifier and optional default production-read target must be supplied explicitly and match `[A-Za-z0-9][A-Za-z0-9._-]*`; the renderer never infers either value. A default target without a project identifier is rejected.

### Backend child example

```json
{
  "project_identity": {
    "project_name": "Account Backend",
    "path": "backend"
  },
  "structure": {
    "entry_project": "Server.Starter",
    "contracts": [
      "Server.BizContract"
    ],
    "services": [
      "Server.BizService"
    ],
    "data_access": [
      "Server.Repository"
    ],
    "solution_file": "Server.sln"
  },
  "boundaries": {
    "layering_description": "Starter -> BizService -> Repository",
    "module_example": "Account",
    "key_config_paths": "appsettings.example.json"
  },
  "config_touchpoints": {
    "files": [
      {
        "name": "appsettings.example.json"
      }
    ]
  },
  "validation": {
    "entry_project_path": "backend/Server.Starter"
  },
  "commands": {
    "build": "dotnet build backend/Server.sln",
    "test": "dotnet test backend/tests/Server.Tests.csproj",
    "dev": "dotnet run --project backend/Server.Starter"
  }
}
```

### Frontend child example

```json
{
  "project_identity": {
    "project_name": "web",
    "path": "web"
  },
  "structure": {
    "source_dirs": [
      {
        "path": "src/app"
      },
      {
        "path": "src/shared"
      }
    ],
    "app_dirs": [
      {
        "path": "src/app/views"
      },
      {
        "path": "src/app/router"
      }
    ]
  },
  "boundaries": {
    "route_dir": "src/app/router",
    "state_dir": "src/store",
    "shared_dirs_text": "src/shared、src/components",
    "api_dir": "src/api",
    "theme_dir": "src/styles",
    "type_dir": "src/types"
  },
  "config_touchpoints": {
    "files": [
      {
        "name": "vite.config.ts"
      },
      {
        "name": "tsconfig.json"
      }
    ]
  },
  "environment": {
    "build_tool": "Vite",
    "test_tool": "Vitest",
    "style_tools": [
      "ESLint",
      "Prettier"
    ],
    "lockfile": "package-lock.json",
    "package_manager": "npm",
    "node_version": ">=22"
  },
  "validation": {
    "quick_command": "npm run lint",
    "minimal_build_command": "npm run build",
    "unit_test_command": "npm run test"
  },
  "commands": {
    "dev": "npm run dev",
    "build": "npm run build",
    "test": "npm run test",
    "lint": "npm run lint"
  }
}
```

### Claude include example

```json
{
  "repository_root": "C:/path/to/repo",
  "child_agents_paths": [
    {
      "path": "backend/AGENTS.md"
    },
    {
      "path": "web/AGENTS.md"
    }
  ]
}
```

When rendering the `claude` template, the renderer rewrites `@...` include lines relative to the final `--output` path. For example, rendering to root `CLAUDE.md` produces `@AGENTS.md` and `@web/AGENTS.md`; rendering to another allowed location rewrites the relative paths accordingly.

## Guarantees

- fixed template selection by `--template`
- fixed placeholder mapping
- fixed line removal for unused repeated placeholders
- failure on unresolved placeholders

## Limitations

- The script currently supports the bundled root/backend/frontend/userscripts/claude templates only.
- It expects facts to be pre-normalized.
- It does not yet generate facts JSON from local repository scans.
