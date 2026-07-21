from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


IGNORED_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "out",
    "coverage",
    ".vite",
    "bin",
    "obj",
    "logs",
    "log",
    "tmp",
    "temp",
}

PACKAGE_MANAGER_LOCKS = {
    "package-lock.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "bun.lockb": "bun",
    "bun.lock": "bun",
}

PROJECT_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

FRONTEND_CONFIG_FILES = [
    "vite.config.ts",
    "vite.config.js",
    "webpack.config.js",
    "webpack.config.ts",
    "tsconfig.json",
    "tsconfig.app.json",
    "jest.config.js",
    "jest.config.ts",
    "vitest.config.ts",
    "vitest.config.js",
    ".eslintrc.js",
    ".eslintrc.cjs",
    "eslint.config.js",
    "eslint.config.mjs",
    ".prettierrc",
    ".prettierrc.js",
    "prettier.config.js",
]

USERSCRIPTS_CONFIG_FILES = [
    ".eslintrc.js",
    ".prettierrc.js",
    "babel.config.js",
    "jest.config.js",
    "jsconfig.json",
    "postcss.config.js",
    "stylelint.config.js",
    "tailwind.config.js",
    "tsconfig.json",
    "tsconfig.test.json",
]

NESTJS_BACKEND_CONFIG_FILES = [
    "tsconfig.json",
    "tsconfig.build.json",
    "tsconfig.swagger.json",
    "prisma.config.ts",
    "ecosystem.config.js",
    "production.yaml",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".prettierrc",
    ".prettierrc.js",
    "prettier.config.js",
]

SPRING_BOOT_CONFIG_FILES = [
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "application.yml",
    "application.yaml",
    "application.properties",
    "bootstrap.yml",
    "bootstrap.yaml",
    "bootstrap.properties",
]

FRONTEND_SOURCE_DIR_PRIORITY = {
    "src/api": 0,
    "src/app": 1,
    "src/assets": 2,
    "src/lib": 3,
    "src/public": 4,
    "src/mocks": 5,
}

FRONTEND_APP_DIR_PRIORITY = {
    "src/app/router": 0,
    "src/app/core": 1,
    "src/app/views": 2,
    "src/app/shared": 3,
    "src/app/styles": 4,
    "src/app/themes": 5,
    "src/app/types": 6,
}

USERSCRIPTS_SOURCE_DIR_PRIORITY = {
    "src/pages": 0,
    "src/services": 1,
    "src/styles": 2,
    "src/types": 3,
    "src/utils": 4,
}

USERSCRIPTS_PAGE_DIR_PRIORITY = {
    "src/pages/shared": 0,
    "src/pages/javbus": 1,
    "src/pages/spider-jd": 2,
}

SAFE_CONFIG_NAMES = [
    "appsettings.Development.json",
    "appsettings.Test.json",
    "appsettings.Staging.json",
    "appsettings.example.json",
    "appsettings.sample.json",
]

SQL_DIR_NAME_HINTS = (
    "sql",
    "migration",
    "migrations",
    "db",
    "database",
)

PREFERRED_SQL_DIR_CANDIDATES = (
    "db/migrations",
    "database/migrations",
    "sql/migrations",
    "db/scripts",
    "database/scripts",
    "sql/scripts",
)

SQL_TOOLING_MARKERS = {
    "Entity Framework Core": (
        "Microsoft.EntityFrameworkCore",
        "EntityFrameworkCore",
    ),
    "Flyway": (
        "flyway",
    ),
    "Liquibase": (
        "liquibase",
    ),
}

GENERATED_PATH_CANDIDATES = (
    "src/generated",
    "src/gen",
    "src/crud",
    "generated",
    "gen",
    "openapi",
    "prisma/generated",
    "target/generated-sources",
)

SCRIPT_DIR_CANDIDATES = (
    "scripts",
    "tools",
    "bin",
)

DOCS_DIR_CANDIDATES = (
    "docs",
    "doc",
)

HIGH_RISK_PATH_CANDIDATES = {
    "prisma": "数据库 schema、迁移或生成链路",
    "migrations": "数据库迁移脚本",
    "db/migrations": "数据库迁移脚本",
    "database/migrations": "数据库迁移脚本",
    "sql/migrations": "数据库迁移脚本",
    "src/auth": "认证与授权流程",
    "src/security": "认证与安全配置",
    "src/guards": "路由或接口准入控制",
    "src/interceptors": "请求处理管道",
    "src/middleware": "请求处理中间件",
    "src/config": "运行时配置绑定",
    "src/app/router": "前端路由与准入控制",
    "src/router": "前端路由与准入控制",
    "src/store": "跨页面状态管理",
    "src/stores": "跨页面状态管理",
}

EXAMPLE_CONFIG_NAMES = {
    ".env.example",
    ".env.sample",
    "appsettings.example.json",
    "appsettings.sample.json",
    "application-example.yml",
    "application-example.yaml",
    "application-example.properties",
}

RUNTIME_MODE_NAME_PREFIXES = (
    "application-",
    "bootstrap-",
    ".env.",
)

CONFIG_BINDING_CANDIDATES = (
    "src/config",
    "src/main/resources",
    "config",
)

SPRING_DATA_MARKERS = {
    "MyBatis": ("mybatis", "pagehelper"),
    "JPA": ("spring-boot-starter-data-jpa", "hibernate"),
    "JdbcTemplate": ("spring-jdbc", "jdbc"),
}

CHILD_TEMPLATES = {
    "dotnet-backend-child",
    "backend-child",
    "frontend-child",
    "userscripts-child",
    "nestjs-backend-child",
    "spring-boot-backend-child",
}


def default_detail_level_for_template(template: str) -> str:
    return "rich" if template in CHILD_TEMPLATES else "standard"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def relative_str(path: Path, base: Path) -> str:
    try:
        value = path.relative_to(base)
    except ValueError:
        value = path
    text = str(value).replace("\\", "/")
    return "." if text == "" else text


def shallow_dirs(path: Path) -> list[Path]:
    items = [
        item
        for item in path.iterdir()
        if item.is_dir() and item.name not in IGNORED_DIRS and not item.name.startswith(".")
    ]
    return sorted(items, key=lambda item: item.name.lower())


def shallow_files(path: Path) -> list[Path]:
    items = [item for item in path.iterdir() if item.is_file()]
    return sorted(items, key=lambda item: item.name.lower())


def first_existing(path: Path, candidates: list[str]) -> Path | None:
    for name in candidates:
        candidate = path / name
        if candidate.exists():
            return candidate
    return None


def sort_frontend_dirs(items: list[dict[str, str]], priority: dict[str, int]) -> list[dict[str, str]]:
    return sorted(
        items,
        key=lambda item: (
            priority.get(str(item.get("path", "")), 999),
            str(item.get("path", "")).lower(),
        ),
    )


def preferred_script(
    scripts: dict[str, Any],
    candidates: list[str],
    fallback: str,
) -> str:
    for key in candidates:
        value = scripts.get(key)
        if value:
            return str(value)
    return fallback


def package_script_invocation(package_manager: str, script_name: str) -> str:
    if package_manager == "pnpm":
        return f"pnpm {script_name}"
    if package_manager == "yarn":
        return f"yarn {script_name}"
    if package_manager == "bun":
        return f"bun run {script_name}"
    return f"npm run {script_name}"


def has_immediate_sql_files(path: Path) -> bool:
    return any(file.suffix.lower() == ".sql" for file in shallow_files(path))


def existing_path_items(target: Path, candidates: tuple[str, ...], purpose: str, limit: int = 8) -> list[dict[str, str]]:
    items = [
        {"path": candidate, "purpose": purpose}
        for candidate in candidates
        if (target / candidate).exists()
    ]
    return sorted(items, key=lambda item: item["path"].lower())[:limit]


def existing_high_risk_touchpoints(target: Path) -> list[dict[str, str]]:
    items = [
        {"path": candidate, "reason": reason}
        for candidate, reason in HIGH_RISK_PATH_CANDIDATES.items()
        if (target / candidate).exists()
    ]
    return sorted(items, key=lambda item: item["path"].lower())[:8]


def existing_config_details(target: Path) -> dict[str, list[dict[str, str]]]:
    example_files: list[dict[str, str]] = []
    runtime_mode_files: list[dict[str, str]] = []
    binding_files = existing_path_items(target, CONFIG_BINDING_CANDIDATES, "配置绑定入口", limit=5)
    for path in shallow_files(target):
        if path.name in EXAMPLE_CONFIG_NAMES:
            example_files.append({"name": path.name, "purpose": "示例配置，允许按需读取和同步字段"})
        if path.name.startswith(RUNTIME_MODE_NAME_PREFIXES):
            runtime_mode_files.append({"name": path.name, "mode": "运行模式配置，仅按文件名确认"})
    return {
        "example_files": sorted(example_files, key=lambda item: item["name"].lower()),
        "runtime_mode_files": sorted(runtime_mode_files, key=lambda item: item["name"].lower()),
        "binding_files": binding_files,
    }


def package_script_invocations(package_manager: str, scripts: dict[str, Any]) -> dict[str, str]:
    return {key: package_script_invocation(package_manager, key) for key in scripts}


def first_command(invocations: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for key in candidates:
        if key in invocations:
            return invocations[key]
    return None


def validation_matrix(invocations: dict[str, str], project_type: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    lint_or_test = first_command(invocations, ("lint", "test", "typecheck"))
    if lint_or_test:
        items.append({"change": "普通逻辑或局部实现改动", "command": lint_or_test, "reason": "优先使用最快可用脚本做目标验证"})
    typecheck = first_command(invocations, ("typecheck", "tsc", "lint"))
    if typecheck:
        items.append({"change": "类型、DTO、接口封装或状态结构改动", "command": typecheck, "reason": "优先覆盖类型与静态约束"})
    build = first_command(invocations, ("build", "build-prod", "package"))
    if build:
        items.append({"change": "构建配置、静态资源、生成产物或发布相关改动", "command": build, "reason": "需要验证打包链路"})
    e2e = first_command(invocations, ("test:e2e", "test-e2e", "e2e"))
    if e2e:
        items.append({"change": "路由、认证、权限、页面关键流程或接口主链路改动", "command": e2e, "reason": "需要覆盖跨模块流程"})
    codegen = first_command(invocations, ("codegen", "generate", "prisma:generate", "swagger:json"))
    if codegen:
        items.append({"change": "OpenAPI、Swagger、Prisma、Mapper 或生成代码改动", "command": codegen, "reason": "优先复用项目既有生成链路"})
    if project_type in {"backend", "spring-boot-backend"}:
        test = first_command(invocations, ("test",))
        if test:
            items.append({"change": "数据访问、事务、Mapper/Repository 或业务服务改动", "command": test, "reason": "优先覆盖服务与数据访问测试"})
    return items


def enrich_common_rich_facts(
    facts: dict[str, Any],
    target: Path,
    invocations: dict[str, str] | None = None,
) -> None:
    structure = facts.setdefault("structure", {})
    boundaries = facts.setdefault("boundaries", {})
    config_touchpoints = facts.setdefault("config_touchpoints", {})
    validation = facts.setdefault("validation", {})
    structure.setdefault(
        "generated_dirs",
        existing_path_items(target, GENERATED_PATH_CANDIDATES, "生成产物或生成源码目录"),
    )
    structure.setdefault(
        "script_dirs",
        existing_path_items(target, SCRIPT_DIR_CANDIDATES, "项目脚本或工具入口"),
    )
    structure.setdefault(
        "docs_dirs",
        existing_path_items(target, DOCS_DIR_CANDIDATES, "项目文档目录"),
    )
    generated_paths = structure.get("generated_dirs", [])
    if generated_paths:
        boundaries["generated_paths"] = generated_paths
    high_risk = existing_high_risk_touchpoints(target)
    if high_risk:
        boundaries["high_risk_touchpoints"] = high_risk
    config_touchpoints.update(existing_config_details(target))
    if invocations:
        matrix = validation_matrix(invocations, str(facts.get("project_identity", {}).get("project_type", "")))
        if matrix:
            validation["by_change_type"] = matrix


def detect_sql_script_dirs(target: Path) -> list[Path]:
    preferred_matches = [
        target / relative_path
        for relative_path in PREFERRED_SQL_DIR_CANDIDATES
        if (target / relative_path).is_dir()
    ]
    if preferred_matches:
        return sorted(preferred_matches, key=lambda item: str(item).lower())

    candidates: list[Path] = []
    for child in shallow_dirs(target):
        child_name = child.name.lower()
        if any(token in child_name for token in SQL_DIR_NAME_HINTS) or has_immediate_sql_files(child):
            candidates.append(child)
            continue
        for grandchild in shallow_dirs(child):
            grandchild_name = grandchild.name.lower()
            if any(token in grandchild_name for token in SQL_DIR_NAME_HINTS) or has_immediate_sql_files(grandchild):
                candidates.append(grandchild)
    unique_candidates = {str(path.resolve()).lower(): path for path in candidates}
    return sorted(unique_candidates.values(), key=lambda item: str(item).lower())


def detect_sql_tooling(target: Path) -> str | None:
    for candidate in (
        target / "flyway.conf",
        target / "liquibase.properties",
        target / "db.changelog.xml",
        target / "db.changelog.yaml",
        target / "db.changelog.yml",
        target / "db.changelog.json",
    ):
        if candidate.exists():
            if "flyway" in candidate.name.lower():
                return "Flyway"
            return "Liquibase"

    csproj_files = sorted(target.rglob("*.csproj"), key=lambda item: item.name.lower())
    for csproj in csproj_files[:12]:
        try:
            content = csproj.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lowered = content.lower()
        for tooling_name, markers in SQL_TOOLING_MARKERS.items():
            if any(marker.lower() in lowered for marker in markers):
                return tooling_name
    return None


def detect_spring_sql_tooling(target: Path) -> str | None:
    for candidate in (target / "pom.xml", target / "build.gradle", target / "build.gradle.kts"):
        content = read_text_safe(candidate).lower() if candidate.exists() else ""
        if "flyway" in content:
            return "Flyway"
        if "liquibase" in content:
            return "Liquibase"
    return detect_sql_tooling(target)


def read_maven_modules(pom_path: Path) -> list[str]:
    if not pom_path.exists():
        return []
    try:
        root = ET.fromstring(read_text_safe(pom_path))
    except ET.ParseError:
        return []
    modules: list[str] = []
    for element in root.findall(".//{*}modules/{*}module"):
        if element.text and element.text.strip():
            modules.append(element.text.strip())
    return sorted(modules)


def read_maven_property(pom_path: Path, property_name: str) -> str | None:
    if not pom_path.exists():
        return None
    try:
        root = ET.fromstring(read_text_safe(pom_path))
    except ET.ParseError:
        return None
    element = root.find(f".//{{*}}properties/{{*}}{property_name}")
    if element is not None and element.text and element.text.strip():
        return element.text.strip()
    return None


def detect_spring_build_tool(target: Path) -> dict[str, str]:
    if (target / "mvnw").exists():
        return {"tool": "Maven", "command": "./mvnw", "descriptor": "pom.xml"}
    if (target / "pom.xml").exists():
        return {"tool": "Maven", "command": "mvn", "descriptor": "pom.xml"}
    if (target / "gradlew").exists():
        return {"tool": "Gradle", "command": "./gradlew", "descriptor": "build.gradle"}
    if (target / "build.gradle.kts").exists() or (target / "build.gradle").exists():
        return {"tool": "Gradle", "command": "gradle", "descriptor": "build.gradle"}
    return {"tool": "未在本地浅层扫描中确认", "command": "mvn", "descriptor": "未在本地浅层扫描中确认构建文件"}


def detect_spring_data_access(target: Path) -> str:
    content = "\n".join(
        read_text_safe(path).lower()
        for path in (target / "pom.xml", target / "build.gradle", target / "build.gradle.kts")
        if path.exists()
    )
    matches = [
        name
        for name, markers in SPRING_DATA_MARKERS.items()
        if any(marker.lower() in content for marker in markers)
    ]
    return "、".join(matches) if matches else "未在本地浅层扫描中确认数据访问主链路"


def has_spring_mapper_markers(module_path: Path) -> bool:
    if any(
        candidate.exists()
        for candidate in (
            module_path / "src" / "main" / "resources" / "mapper",
            module_path / "src" / "main" / "java" / "mapper",
        )
    ):
        return True
    java_path = module_path / "src" / "main" / "java"
    return bool(list(java_path.glob("*/*/*/mapper"))[:1]) if java_path.exists() else False


def sort_spring_service_modules(modules: list[str]) -> list[str]:
    priority = {
        "system": 0,
        "service": 1,
        "biz": 2,
        "domain": 3,
        "quartz": 4,
    }
    return sorted(
        modules,
        key=lambda module: (
            min((rank for token, rank in priority.items() if token in module.lower()), default=99),
            module.lower(),
        ),
    )


def sort_spring_data_modules(modules: list[str]) -> list[str]:
    priority = {
        "system": 0,
        "data": 1,
        "repository": 2,
        "dao": 3,
        "mapper": 4,
        "infra": 5,
        "quartz": 6,
        "generator": 7,
    }
    return sorted(
        modules,
        key=lambda module: (
            min((rank for token, rank in priority.items() if token in module.lower()), default=99),
            module.lower(),
        ),
    )


def infer_project_type(path: Path) -> str:
    if (path / "pom.xml").exists() or (path / "build.gradle").exists() or (path / "build.gradle.kts").exists():
        return "Java/Spring 后端"
    if any(path.glob("*.sln")) or any(path.glob("*.csproj")):
        return "后端"
    package_json = path / "package.json"
    if package_json.exists():
        package = read_json(package_json)
        deps = {
            **package.get("dependencies", {}),
            **package.get("devDependencies", {}),
        }
        if any(name in deps for name in ("react", "vue", "next", "nuxt", "vite")):
            return "前端"
        return "Node 项目"
    return "目录"


def frontend_stack_description(path: Path) -> str:
    package_json = path / "package.json"
    if not package_json.exists():
        return "前端应用或页面工程"
    package = read_json(package_json)
    deps = {
        **package.get("dependencies", {}),
        **package.get("devDependencies", {}),
    }
    framework = ""
    if "vue" in deps:
        version = str(deps.get("vue", ""))
        framework = "Vue 3" if version.startswith("^3") or version.startswith("3") else "Vue"
    elif "react" in deps:
        framework = "React"
    elif "next" in deps:
        framework = "Next.js"
    elif "nuxt" in deps:
        framework = "Nuxt"
    elif "vite" in deps:
        framework = "Vite"
    language = "TypeScript" if any((path / name).exists() for name in ("tsconfig.json", "tsconfig.app.json")) else ""
    if framework and language:
        return f"{framework} + {language} 应用"
    if framework:
        return f"{framework} 前端应用"
    if language:
        return f"{language} 前端工程"
    return "前端应用或页面工程"


def backend_description(path: Path) -> str:
    if any(path.glob("*.sln")):
        if any(
            token in candidate.stem.lower()
            for candidate in path.rglob("*.csproj")
            for token in ("service", "biz", "application")
        ):
            return ".NET 解决方案与业务服务"
        return ".NET 解决方案"
    if any(path.glob("*.csproj")):
        return ".NET 后端项目"
    return "后端服务或解决方案"


def spring_description(path: Path) -> str:
    build = "Gradle" if (path / "build.gradle").exists() or (path / "build.gradle.kts").exists() else "Maven"
    modules = read_maven_modules(path / "pom.xml") if (path / "pom.xml").exists() else []
    if modules:
        return f"Spring Boot {build} 多模块后端服务"
    return f"Spring Boot {build} 后端服务"


def directory_description(path: Path) -> str:
    name = path.name.lower()
    if name in {"doc", "docs", "documentation"}:
        return "项目文档与规划材料"
    if name in {"aiprompt", "ai-prompt", "prompts", "prompt"}:
        return "AI 提示词、规则或生成材料"
    if name in {"tasks", "task"}:
        return "任务计划与过程留痕"
    if name in {"scripts", "tools"}:
        return "项目脚本与工具"
    if name in {"deploy", "deployment", "infrastructure", "infra"}:
        return "部署与基础设施配置"
    if any(child.suffix.lower() in {".md", ".mdx"} for child in shallow_files(path)):
        return "文档或说明材料"
    return "仓库子目录"


def describe_top_level_entry(path: Path, project_type: str) -> str:
    if project_type == "前端":
        return frontend_stack_description(path)
    if project_type == "后端":
        return backend_description(path)
    if project_type == "Java/Spring 后端":
        return spring_description(path)
    if project_type == "Node 项目":
        return "Node 工具或脚本工程"
    return directory_description(path)


def backend_child_dir_purpose(child: Path, structure: dict[str, Any]) -> tuple[str, str]:
    name = child.name
    lowered = name.lower()
    if name == structure.get("entry_project") or "starter" in lowered:
        return "feature_dirs", "启动、宿主与 HTTP 管道入口项目"
    if name in set(structure.get("contracts", [])) or "contract" in lowered:
        return "feature_dirs", "业务契约、接口与共享模型项目"
    if name in set(structure.get("services", [])) or "service" in lowered or "biz" in lowered:
        return "feature_dirs", "业务服务与流程编排项目"
    if name in set(structure.get("data_access", [])) or any(token in lowered for token in ("repository", "data", "infra")):
        return "feature_dirs", "仓储、数据访问与基础设施项目"
    if any(token in lowered for token in ("common", "shared", "core")):
        return "shared_dirs", "通用能力、共享契约或基础库"
    if lowered in {"scripts", "script", "tools"}:
        return "script_dirs", "数据库脚本、运维脚本或项目工具入口"
    if lowered in {"lib", "libs"}:
        return "shared_dirs", "本地依赖库或第三方程序集目录"
    return "feature_dirs", "后端模块或项目目录"


def backend_rich_structure_dirs(child_dirs: list[Path], target: Path, structure: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {
        "feature_dirs": [],
        "shared_dirs": [],
        "script_dirs": [],
    }
    for child in child_dirs[:8]:
        key, purpose = backend_child_dir_purpose(child, structure)
        groups[key].append({"path": relative_str(child, target), "purpose": purpose})
    return {key: value for key, value in groups.items() if value}


def infer_repo_shape(root: Path, child_dirs: list[Path]) -> str:
    has_frontend = False
    has_backend = False
    for child in child_dirs:
        project_type = infer_project_type(child)
        has_frontend = has_frontend or project_type == "前端"
        has_backend = has_backend or project_type in {"后端", "Java/Spring 后端"}
    if has_frontend and has_backend:
        return "前后端分离多项目仓库"
    if len(child_dirs) > 1:
        return "多项目仓库"
    if child_dirs:
        return "单项目仓库"
    return "按本地已验证目录结构组织的代码仓库"


def extract_root_facts(
    root: Path,
    child_agents: list[str],
    host: str = "codex",
    database_project_identifier: str | None = None,
    database_default_production_read_target: str | None = None,
) -> dict[str, Any]:
    if database_project_identifier and not PROJECT_IDENTIFIER_PATTERN.fullmatch(
        database_project_identifier
    ):
        raise ValueError(
            "database profile project identifier must match "
            "[A-Za-z0-9][A-Za-z0-9._-]*"
        )
    if database_default_production_read_target and not database_project_identifier:
        raise ValueError(
            "default production read target requires a database profile project identifier"
        )
    if (
        database_default_production_read_target
        and not PROJECT_IDENTIFIER_PATTERN.fullmatch(
            database_default_production_read_target
        )
    ):
        raise ValueError(
            "default production read target must match "
            "[A-Za-z0-9][A-Za-z0-9._-]*"
        )
    child_dirs = shallow_dirs(root)
    top_level_entries: list[dict[str, str]] = []
    for child in child_dirs[:8]:
        project_type = infer_project_type(child)
        description = describe_top_level_entry(child, project_type)
        top_level_entries.append(
            {
                "path": relative_str(child, root),
                "project_type": project_type,
                "description": description,
            }
        )

    package_managers: list[dict[str, str]] = []
    runtimes: list[dict[str, str]] = []
    for filename, manager in PACKAGE_MANAGER_LOCKS.items():
        if (root / filename).exists():
            package_managers.append({"name": manager})
    package_json = root / "package.json"
    if package_json.exists():
        package = read_json(package_json)
        if "packageManager" in package:
            manager_text = str(package["packageManager"])
            manager_name, _, manager_version = manager_text.partition("@")
            package_managers.append(
                {
                    "name": manager_name,
                    **({"version": manager_version} if manager_version else {}),
                }
            )
        node_version = package.get("engines", {}).get("node")
        if node_version:
            runtimes.append({"name": "Node.js", "version": str(node_version)})
    if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
        runtimes.append({"name": ".NET"})
    if (root / "pom.xml").exists() or (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        runtimes.append({"name": "Java/Spring"})

    unique_pm = {(item["name"], item.get("version", "")): item for item in package_managers}
    unique_rt = {(item["name"], item.get("version", "")): item for item in runtimes}

    host_profile = {
        "host": host,
        "global_rule_path": "~/.claude/CLAUDE.md" if host == "claude" else "~/.codex/AGENTS.md",
        "project_trace_dir": ".claude" if host == "claude" else ".codex",
        "user_home_dir": "~/.claude" if host == "claude" else "~/.codex",
    }

    return {
        "host_profile": host_profile,
        "repository_profile": {
            "repo_shape": infer_repo_shape(root, child_dirs),
            "summary_line": "当前仓库按本地已验证目录结构组织；未在浅层扫描中补充更多仓库概览。",
        },
        "top_level_entries": sorted(top_level_entries, key=lambda item: item["path"]),
        "child_agents_paths": [{"path": path} for path in sorted(child_agents)],
        "environment": {
            "package_managers": sorted(unique_pm.values(), key=lambda item: item["name"]),
            "runtimes": sorted(unique_rt.values(), key=lambda item: item["name"]),
        },
        "database_profile_binding": (
            {
                "project_identifier": database_project_identifier,
                **(
                    {
                        "default_production_read_target": database_default_production_read_target
                    }
                    if database_default_production_read_target
                    else {}
                ),
            }
            if database_project_identifier
            else {}
        ),
        "command_refs": [{"scope": "child", "path": path} for path in sorted(child_agents)],
        "validation_refs": [],
        "config_boundaries": [],
    }


def detect_frontend_environment(target: Path, package: dict[str, Any]) -> dict[str, Any]:
    deps = {
        **package.get("dependencies", {}),
        **package.get("devDependencies", {}),
    }
    build_tool = "未在本地浅层扫描中确认"
    if "vite" in deps or first_existing(target, ["vite.config.ts", "vite.config.js"]):
        build_tool = "Vite"
    elif first_existing(target, ["webpack.config.js", "webpack.config.ts"]):
        build_tool = "Webpack"

    has_vitest = "vitest" in deps or first_existing(target, ["vitest.config.ts", "vitest.config.js"])
    has_jest = "jest" in deps or first_existing(target, ["jest.config.js", "jest.config.ts"])
    has_playwright = "@playwright/test" in deps or "playwright" in deps
    test_tools: list[str] = []
    if has_vitest:
        test_tools.append("Vitest")
    if has_jest:
        test_tools.append("Jest")
    if has_playwright:
        test_tools.append("Playwright")
    test_tool = " + ".join(test_tools) if test_tools else "未在本地浅层扫描中确认"

    style_tools: list[str] = []
    if "eslint" in deps or first_existing(target, [".eslintrc.js", ".eslintrc.cjs", "eslint.config.js", "eslint.config.mjs"]):
        style_tools.append("ESLint")
    if "prettier" in deps or first_existing(target, [".prettierrc", ".prettierrc.js", "prettier.config.js"]):
        style_tools.append("Prettier")
    if "stylelint" in deps:
        style_tools.append("Stylelint")
    if "tailwindcss" in deps:
        style_tools.append("Tailwind CSS")
    if "unocss" in deps or first_existing(target, ["uno.config.ts", "uno.config.js", "uno.config.mjs"]):
        style_tools.append("UnoCSS")
    if "windicss" in deps or first_existing(target, ["windi.config.ts", "windi.config.js"]):
        style_tools.append("Windi CSS")

    package_manager = "npm"
    lockfile = "package-lock.json"
    for filename, manager in PACKAGE_MANAGER_LOCKS.items():
        if (target / filename).exists():
            package_manager = manager
            lockfile = filename
            break

    package_manager_meta = package.get("packageManager")
    if package_manager_meta:
        manager_name, _, _ = str(package_manager_meta).partition("@")
        if manager_name:
            package_manager = manager_name

    return {
        "build_tool": build_tool,
        "test_tool": test_tool,
        "style_tools": style_tools,
        "lockfile": lockfile,
        "package_manager": package_manager,
        "node_version": str(package.get("engines", {}).get("node", "以本地配置文件为准")),
    }


def detect_nestjs_backend_environment(target: Path, package: dict[str, Any]) -> dict[str, Any]:
    deps = {
        **package.get("dependencies", {}),
        **package.get("devDependencies", {}),
    }
    package_manager = "npm"
    lockfile = "package-lock.json"
    for filename, manager in PACKAGE_MANAGER_LOCKS.items():
        if (target / filename).exists():
            package_manager = manager
            lockfile = filename
            break

    package_manager_meta = package.get("packageManager")
    if package_manager_meta:
        manager_name, _, _ = str(package_manager_meta).partition("@")
        if manager_name:
            package_manager = manager_name

    toolchain: list[str] = []
    if any(key.startswith("@nestjs/") for key in deps):
        toolchain.append("NestJS")
    if "prisma" in deps or "@prisma/client" in deps or (target / "prisma").exists():
        toolchain.append("Prisma")
    if "jest" in deps:
        toolchain.append("Jest")
    if "@nestjs/swagger" in deps:
        toolchain.append("Swagger")

    return {
        "package_manager": package_manager,
        "lockfile": lockfile,
        "node_version": str(package.get("engines", {}).get("node", "以本地配置文件为准")),
        "toolchain": toolchain or ["Node.js 后端"],
    }


def detect_userscripts_environment(target: Path, package: dict[str, Any]) -> dict[str, Any]:
    deps = {
        **package.get("dependencies", {}),
        **package.get("devDependencies", {}),
    }
    package_manager = "npm"
    lockfile = "package-lock.json"
    for filename, manager in PACKAGE_MANAGER_LOCKS.items():
        if (target / filename).exists():
            package_manager = manager
            lockfile = filename
            break

    package_manager_meta = package.get("packageManager")
    if package_manager_meta:
        manager_name, _, _ = str(package_manager_meta).partition("@")
        if manager_name:
            package_manager = manager_name

    build_tool = "未在本地浅层扫描中确认"
    if "vite" in deps or (target / "build" / "vite.build.mjs").exists():
        build_tool = "Vite"

    test_tools: list[str] = []
    if "jest" in deps or (target / "jest.config.js").exists():
        test_tools.append("Jest")
    if "@playwright/test" in deps:
        test_tools.append("Playwright")
    test_tool = " + ".join(test_tools) if test_tools else "未在本地浅层扫描中确认"

    style_tools: list[str] = []
    if "eslint" in deps or (target / ".eslintrc.js").exists():
        style_tools.append("ESLint")
    if "prettier" in deps or (target / ".prettierrc.js").exists():
        style_tools.append("Prettier")
    if "stylelint" in deps or (target / "stylelint.config.js").exists():
        style_tools.append("Stylelint")
    if "tailwindcss" in deps or (target / "tailwind.config.js").exists():
        style_tools.append("Tailwind CSS")
    if "unocss" in deps or first_existing(target, ["uno.config.ts", "uno.config.js", "uno.config.mjs"]):
        style_tools.append("UnoCSS")
    if "windicss" in deps or first_existing(target, ["windi.config.ts", "windi.config.js"]):
        style_tools.append("Windi CSS")

    return {
        "package_manager": package_manager,
        "lockfile": lockfile,
        "node_version": str(package.get("engines", {}).get("node", "以本地配置文件为准")),
        "build_tool": build_tool,
        "test_tool": test_tool,
        "style_tools": style_tools,
    }


def extract_frontend_facts(root: Path, target: Path, detail_level: str) -> dict[str, Any]:
    package = read_json(target / "package.json") if (target / "package.json").exists() else {}
    scripts = package.get("scripts", {})
    src_path = target / "src"
    source_dirs = []
    if src_path.exists():
        for child in shallow_dirs(src_path):
            source_dirs.append({"path": relative_str(child, target)})
    source_dirs = sort_frontend_dirs(source_dirs, FRONTEND_SOURCE_DIR_PRIORITY)[:6]
    app_path = target / "src" / "app"
    app_dirs = []
    if app_path.exists():
        for child in shallow_dirs(app_path):
            app_dirs.append({"path": relative_str(child, target)})
    app_dirs = sort_frontend_dirs(app_dirs, FRONTEND_APP_DIR_PRIORITY)[:6]

    config_files = [
        {"name": path.name}
        for path in shallow_files(target)
        if path.name in FRONTEND_CONFIG_FILES
    ]
    boundaries = {
        "route_dir": "src/router",
        "state_dir": "未在本地浅层扫描中确认状态目录",
        "shared_dirs_text": "src/shared",
        "api_dir": "src/api",
        "theme_dir": "src/styles",
        "type_dir": "src/types",
    }
    known_paths = {item["path"] for item in source_dirs}
    app_known_paths = {item["path"] for item in app_dirs}
    if "src/app/router" in app_known_paths:
        boundaries["route_dir"] = "src/app/router"
    if "src/app/core" in app_known_paths:
        boundaries["state_dir"] = "src/app/core"
    elif "src/stores" in known_paths:
        boundaries["state_dir"] = "src/stores"
    elif "src/store" in known_paths:
        boundaries["state_dir"] = "src/store"
    shared_dirs = [
        path
        for path in known_paths.union(app_known_paths)
        if path in {"src/shared", "src/components", "src/lib", "src/app/shared"}
    ]
    if shared_dirs:
        boundaries["shared_dirs_text"] = "、".join(sorted(shared_dirs))
    if "src/services" in known_paths:
        boundaries["api_dir"] = "src/services"
    elif "src/api" in known_paths:
        boundaries["api_dir"] = "src/api"
    if "src/app/themes" in app_known_paths:
        boundaries["theme_dir"] = "src/app/themes"
    elif "src/app/styles" in app_known_paths:
        boundaries["theme_dir"] = "src/app/styles"
    elif "src/theme" in known_paths:
        boundaries["theme_dir"] = "src/theme"
    if "src/app/types" in app_known_paths:
        boundaries["type_dir"] = "src/app/types"
    elif "src/typings" in known_paths:
        boundaries["type_dir"] = "src/typings"

    environment = detect_frontend_environment(target, package)
    package_manager = str(environment.get("package_manager", "npm"))
    script_invocations = package_script_invocations(package_manager, scripts)
    preferred_command_keys = [
        "start",
        "dev",
        "type-check",
        "typecheck",
        "check",
        "lint",
        "build",
        "build-prod",
        "test",
        "test:e2e",
        "swagger:json",
        "generate",
    ]
    facts = {
        "project_identity": {
            "project_name": target.name,
            "path": relative_str(target, root),
            "project_type": "frontend",
            "inheritance_line": "继承仓库根目录 AGENTS.md",
        },
        "structure": {
            "entry_points": [
                {"path": candidate, "purpose": "应用入口"}
                for candidate in ("src/main.ts", "src/main.tsx", "src/main.js", "src/App.vue")
                if (target / candidate).exists()
            ],
            "source_dirs": source_dirs,
            "app_dirs": app_dirs,
            "test_dirs": [
                {"path": relative_str(child, target)}
                for child in shallow_dirs(target)
                if child.name.lower() in {"tests", "test", "__tests__"}
            ],
        },
        "commands": {
            key: str(scripts[key])
            for key in (
                "install",
                "start",
                "dev",
                "type-check",
                "typecheck",
                "check",
                "build",
                "build-prod",
                "test",
                "test:e2e",
                "lint",
                "format",
                "typecheck",
                "preview",
                "swagger:json",
                "generate",
            )
            if key in scripts
        },
        "validation": {
            "quick_command": preferred_script(
                script_invocations,
                ["type-check", "typecheck", "check", "lint", "test"],
                "未在本地浅层扫描中确认快速验证命令",
            ),
            "minimal_build_command": preferred_script(
                script_invocations,
                ["build-prod", "build"],
                "未在本地浅层扫描中确认最小构建命令",
            ),
            "unit_test_command": preferred_script(
                script_invocations,
                ["test"],
                "未在本地浅层扫描中确认单元测试命令",
            ),
            "e2e_test_command": preferred_script(
                script_invocations,
                ["test:e2e", "e2e"],
                "未在本地浅层扫描中确认端到端测试命令",
            ),
        },
        "config_touchpoints": {
            "files": sorted(config_files, key=lambda item: item["name"]),
        },
        "environment": environment,
        "boundaries": boundaries,
    }
    facts["commands"]["preferred_order"] = [
        key for key in preferred_command_keys if key in scripts
    ]
    if detail_level == "rich":
        for key in ("codegen", "generate", "migrate", "seed"):
            if key in scripts:
                facts["commands"][key] = str(scripts[key])
        if "src/views" in known_paths and not app_dirs:
            facts["structure"]["source_dirs"].append({"path": "src/views"})
        facts["structure"]["feature_dirs"] = existing_path_items(
            target,
            ("src/views", "src/pages", "src/features", "src/modules", "src/app/views"),
            "页面、功能或业务模块目录",
        )
        facts["structure"]["shared_dirs"] = existing_path_items(
            target,
            ("src/shared", "src/components", "src/lib", "src/app/shared", "src/app/components"),
            "共享组件、工具或跨页面能力",
        )
        enrich_common_rich_facts(facts, target, script_invocations)
    return facts


def extract_backend_facts(root: Path, target: Path, detail_level: str) -> dict[str, Any]:
    csproj_files = sorted(target.glob("*.csproj"), key=lambda item: item.name.lower())
    sln_files = sorted(target.glob("*.sln"), key=lambda item: item.name.lower())
    child_dirs = shallow_dirs(target)
    sql_script_dirs = detect_sql_script_dirs(target)
    sql_tooling = detect_sql_tooling(target)

    entry_project = first_existing(target, [f"{target.name}.Starter.csproj"])
    if not entry_project:
        starter_projects = [path for path in target.rglob("*.csproj") if "starter" in path.stem.lower()]
        entry_project = sorted(starter_projects, key=lambda item: str(item).lower())[0] if starter_projects else None

    contracts = sorted(
        {
            path.stem
            for path in target.rglob("*.csproj")
            if "contract" in path.stem.lower()
        }
    )
    services = sorted(
        {
            path.stem
            for path in target.rglob("*.csproj")
            if "service" in path.stem.lower() or "biz" in path.stem.lower()
        }
    )
    data_access = sorted(
        {
            path.stem
            for path in target.rglob("*.csproj")
            if any(token in path.stem.lower() for token in ("repository", "data", "infra"))
        }
    )
    safe_configs = [{"name": path.name} for path in shallow_files(target) if path.name in SAFE_CONFIG_NAMES]

    solution_file = relative_str(sln_files[0], root) if sln_files else "未在本地浅层扫描中确认解决方案文件"
    entry_project_name = (
        entry_project.stem
        if entry_project
        else (csproj_files[0].stem if csproj_files else "未在本地浅层扫描中确认入口项目")
    )
    entry_project_path = relative_str(entry_project.parent if entry_project else target, root)

    facts = {
        "project_identity": {
            "project_name": target.name,
            "path": relative_str(target, root),
            "project_type": "backend",
            "inheritance_line": "继承仓库根目录 AGENTS.md",
        },
        "structure": {
            "entry_project": entry_project_name,
            "contracts": contracts,
            "services": services,
            "data_access": data_access,
            "solution_file": solution_file,
            "source_dirs": [{"path": relative_str(child, target)} for child in child_dirs[:6]],
            "sql_script_dirs": [{"path": relative_str(path, target)} for path in sql_script_dirs],
        },
        "commands": {
            "build": f"dotnet build {solution_file}" if sln_files else f"dotnet build {relative_str(target, root)}",
            "dev": f"dotnet run --project {entry_project_path}" if entry_project else f"dotnet run --project {relative_str(target, root)}",
        },
        "validation": {
            "entry_project_path": entry_project_path,
        },
        "config_touchpoints": {
            "files": safe_configs,
        },
        "boundaries": {
            "layering_description": "按现有后端分层与模块边界组织",
            "module_example": child_dirs[0].name if child_dirs else "业务模块目录",
            "allowed_paths": [{"path": relative_str(target, root)}],
            **({"sql_tooling": sql_tooling} if sql_tooling else {}),
        },
    }

    test_projects = sorted(
        [path for path in target.rglob("*.csproj") if "test" in path.stem.lower()],
        key=lambda item: item.name.lower(),
    )
    if test_projects:
        facts["commands"]["test"] = f"dotnet test {relative_str(test_projects[0], root)}"
    if detail_level == "rich" and safe_configs:
        facts["boundaries"]["key_config_paths"] = "、".join(item["name"] for item in safe_configs)
    if detail_level == "rich":
        invocations = {key: str(value) for key, value in facts["commands"].items() if isinstance(value, str)}
        facts["structure"].update(
            backend_rich_structure_dirs(child_dirs, target, facts["structure"])
        )
        enrich_common_rich_facts(facts, target, invocations)
    return facts


def extract_spring_boot_backend_facts(root: Path, target: Path, detail_level: str) -> dict[str, Any]:
    build = detect_spring_build_tool(target)
    modules = read_maven_modules(target / "pom.xml")
    child_dirs = shallow_dirs(target)
    sql_script_dirs = detect_sql_script_dirs(target)
    sql_tooling = detect_spring_sql_tooling(target)
    java_version = (
        read_maven_property(target / "pom.xml", "java.version")
        or read_maven_property(target / "pom.xml", "maven.compiler.source")
        or "以本地构建配置为准"
    )

    module_paths = [module for module in modules if (target / module).exists()]
    entry_candidates = [
        module
        for module in module_paths
        if any(token in module.lower() for token in ("admin", "web", "boot", "starter", "app", "server"))
    ]
    entry_module = entry_candidates[0] if entry_candidates else (module_paths[0] if module_paths else relative_str(target, root))
    common_modules = [
        module
        for module in module_paths
        if any(token in module.lower() for token in ("common", "framework", "core", "base"))
    ]
    service_modules = [
        module
        for module in module_paths
        if any(token in module.lower() for token in ("system", "service", "biz", "domain", "quartz"))
    ]
    service_modules = sort_spring_service_modules(service_modules)
    data_modules = [
        module
        for module in module_paths
        if any(token in module.lower() for token in ("mapper", "dao", "repository", "data", "infra"))
        or has_spring_mapper_markers(target / module)
    ]
    data_modules = sort_spring_data_modules(data_modules)
    if not data_modules and detect_spring_data_access(target) != "未在本地浅层扫描中确认数据访问主链路":
        data_modules = service_modules[:1]

    source_dirs = []
    for child in child_dirs:
        if (child / "src" / "main" / "java").exists() or (child / "src" / "main" / "resources").exists():
            source_dirs.append({"path": relative_str(child, target)})
    if not source_dirs and (target / "src").exists():
        source_dirs.append({"path": "src"})

    config_files = [
        {"name": path.name}
        for path in shallow_files(target)
        if path.name in SPRING_BOOT_CONFIG_FILES
    ]
    entry_resources = target / entry_module / "src" / "main" / "resources"
    if entry_resources.exists():
        for path in shallow_files(entry_resources):
            if path.name in SPRING_BOOT_CONFIG_FILES:
                config_files.append({"name": f"{entry_module}/src/main/resources/{path.name}"})

    build_command = (
        f"{build['command']} clean package"
        if build["tool"] == "Maven"
        else f"{build['command']} build"
    )
    test_command = f"{build['command']} test"
    run_command = (
        f"{build['command']} spring-boot:run -pl {entry_module}"
        if build["tool"] == "Maven" and entry_module != relative_str(target, root)
        else f"{build['command']} spring-boot:run"
        if build["tool"] == "Maven"
        else f"{build['command']} bootRun"
    )

    sql_dir_text = "、".join(relative_str(path, target) for path in sql_script_dirs)
    facts = {
        "project_identity": {
            "project_name": target.name,
            "path": relative_str(target, root),
            "project_type": "spring-boot-backend",
            "inheritance_line": "继承仓库根目录 AGENTS.md",
        },
        "structure": {
            "entry_module": entry_module,
            "common_modules": common_modules,
            "service_modules": service_modules,
            "data_modules": data_modules,
            "source_dirs": source_dirs[:6],
            "sql_script_dirs": [{"path": relative_str(path, target)} for path in sql_script_dirs],
            "build_descriptor": build["descriptor"],
        },
        "commands": {
            "build": build_command,
            "test": test_command,
            "dev": run_command,
        },
        "validation": {
            "quick_command": test_command,
            "build_command": build_command,
            "test_command": test_command,
            "run_command": run_command,
        },
        "config_touchpoints": {
            "files": sorted(config_files, key=lambda item: item["name"]),
        },
        "environment": {
            "build_tool": build["tool"],
            "java_version": java_version,
            "data_access": detect_spring_data_access(target),
        },
        "boundaries": {
            "layering_description": "按 Spring Boot 入口模块、业务模块、通用/框架模块与数据访问边界组织",
            "module_text": "、".join(module_paths) if module_paths else "未在本地浅层扫描中确认多模块结构",
            "sql_dir_text": sql_dir_text or "未在本地浅层扫描中确认现有 SQL 脚本目录",
            **({"sql_tooling": sql_tooling} if sql_tooling else {}),
        },
    }
    if detail_level == "rich":
        facts["boundaries"]["source_dir_text"] = "、".join(item["path"] for item in source_dirs[:6]) if source_dirs else "未在本地浅层扫描中确认源码目录"
        facts["structure"]["feature_dirs"] = [
            {"path": module, "purpose": "Spring Boot 业务或功能模块"}
            for module in service_modules[:8]
        ]
        facts["structure"]["shared_dirs"] = [
            {"path": module, "purpose": "公共、框架或横切能力模块"}
            for module in common_modules[:6]
        ]
        enrich_common_rich_facts(
            facts,
            target,
            {
                "build": build_command,
                "test": test_command,
                "start": run_command,
            },
        )
    return facts


def extract_nestjs_backend_facts(root: Path, target: Path, detail_level: str) -> dict[str, Any]:
    package = read_json(target / "package.json") if (target / "package.json").exists() else {}
    scripts = package.get("scripts", {})
    environment = detect_nestjs_backend_environment(target, package)
    package_manager = str(environment.get("package_manager", "npm"))
    script_invocations = package_script_invocations(package_manager, scripts)

    config_files = [
        {"name": path.name}
        for path in shallow_files(target)
        if path.name in NESTJS_BACKEND_CONFIG_FILES
    ]

    source_dirs = [{"path": relative_str(child, target)} for child in shallow_dirs(target / "src")] if (target / "src").exists() else []
    generated_dirs: list[dict[str, str]] = []
    if (target / "src" / "crud").exists():
        generated_dirs.append({"path": "src/crud"})
    if (target / "src" / "generated").exists():
        generated_dirs.extend(
            {"path": relative_str(child, target)}
            for child in shallow_dirs(target / "src" / "generated")
        )
    preferred_command_keys = [
        "start:dev",
        "start-dev",
        "build",
        "test",
        "test-e2e",
        "lint",
        "prisma:generate",
        "swagger:json",
    ]

    entry_candidates = [
        "src/main.api.ts",
        "src/main.worker.ts",
        "src/main.ts",
    ]
    entry_files = [{"path": candidate} for candidate in entry_candidates if (target / candidate).exists()]
    if not entry_files:
        entry_files = [
            {"path": "未在本地浅层扫描中确认入口文件"},
            {"path": "未在本地浅层扫描中确认应用模块入口"},
        ]
    if (target / "src" / "modules").exists():
        module_dir = "src/modules"
    elif (target / "src" / "module").exists():
        module_dir = "src/module"
    else:
        module_dir = "未在本地浅层扫描中确认业务模块目录"
    database_dir = "src/core/modules/database" if (target / "src" / "core" / "modules" / "database").exists() else "未在本地浅层扫描中确认数据库目录"
    prisma_dir = "prisma" if (target / "prisma").exists() else "未在本地浅层扫描中确认 Prisma 目录"
    script_dir = "src/scripts" if (target / "src" / "scripts").exists() else ("scripts" if (target / "scripts").exists() else "未在本地浅层扫描中确认脚本目录")

    generated_dir_paths = [str(item.get("path", "")) for item in generated_dirs if item.get("path")]
    generated_dir_text = "、".join(generated_dir_paths) if generated_dir_paths else "未在本地浅层扫描中确认生成目录"

    facts = {
        "project_identity": {
            "project_name": target.name,
            "path": relative_str(target, root),
            "project_type": "nestjs-backend",
            "inheritance_line": "继承仓库根目录 AGENTS.md",
        },
        "structure": {
            "entry_files": entry_files,
            "source_dirs": source_dirs,
            "module_dir": module_dir,
            "database_dir": database_dir,
            "generated_dirs": generated_dirs,
            "prisma_dir": prisma_dir,
            "script_dir": script_dir,
        },
        "commands": {
            key: str(scripts[key])
            for key in (
                "start:dev",
                "start-dev",
                "build",
                "test",
                "test-e2e",
                "lint",
                "lint:fix",
                "format",
                "prisma:generate",
                "swagger:json",
            )
            if key in scripts
        },
        "validation": {
            "quick_command": preferred_script(
                script_invocations,
                ["test", "test-e2e", "build"],
                "未在本地浅层扫描中确认快速验证命令",
            ),
            "build_command": preferred_script(
                script_invocations,
                ["build"],
                "未在本地浅层扫描中确认构建命令",
            ),
            "test_command": preferred_script(
                script_invocations,
                ["test"],
                "未在本地浅层扫描中确认测试命令",
            ),
            "e2e_command": preferred_script(
                script_invocations,
                ["test-e2e"],
                "未在本地浅层扫描中确认端到端测试命令",
            ),
            "prisma_generate_command": preferred_script(
                script_invocations,
                ["prisma:generate"],
                "未在本地浅层扫描中确认 Prisma 生成命令",
            ),
            "swagger_command": preferred_script(
                script_invocations,
                ["swagger:json"],
                "未在本地浅层扫描中确认 Swagger 导出命令",
            ),
        },
        "config_touchpoints": {
            "files": sorted(config_files, key=lambda item: item["name"]),
        },
        "environment": environment,
        "boundaries": {
            "layering_description": "按 NestJS 启动入口、业务模块、数据库模块、Prisma 与生成目录分层组织",
            "generated_dir_text": generated_dir_text,
        },
    }
    facts["commands"]["preferred_order"] = [key for key in preferred_command_keys if key in scripts]
    if detail_level == "rich":
        facts["boundaries"]["source_dir_text"] = "、".join(item["path"] for item in source_dirs[:6]) if source_dirs else "未在本地浅层扫描中确认源码目录"
        facts["structure"]["feature_dirs"] = existing_path_items(
            target,
            ("src/modules", "src/module", "src/features", "src/domains"),
            "NestJS 业务模块目录",
        )
        facts["structure"]["shared_dirs"] = existing_path_items(
            target,
            ("src/common", "src/shared", "src/core", "src/libs"),
            "共享 provider、基础设施或横切能力",
        )
        enrich_common_rich_facts(facts, target, script_invocations)
    return facts


def extract_userscripts_facts(root: Path, target: Path, detail_level: str) -> dict[str, Any]:
    package = read_json(target / "package.json") if (target / "package.json").exists() else {}
    scripts = package.get("scripts", {})
    environment = detect_userscripts_environment(target, package)
    package_manager = str(environment.get("package_manager", "npm"))
    script_invocations = package_script_invocations(package_manager, scripts)

    source_dirs = [{"path": relative_str(child, target)} for child in shallow_dirs(target / "src")] if (target / "src").exists() else []
    source_dirs = sort_frontend_dirs(source_dirs, USERSCRIPTS_SOURCE_DIR_PRIORITY)[:5]
    page_dirs = [{"path": relative_str(child, target)} for child in shallow_dirs(target / "src" / "pages")] if (target / "src" / "pages").exists() else []
    page_dirs = sort_frontend_dirs(page_dirs, USERSCRIPTS_PAGE_DIR_PRIORITY)[:3]

    config_files = [
        {"name": path.name}
        for path in shallow_files(target)
        if path.name in USERSCRIPTS_CONFIG_FILES
    ]

    preferred_command_keys = ["start", "build", "test", "test:e2e"]
    shared_page_dir = "src/pages/shared" if (target / "src" / "pages" / "shared").exists() else "未在本地浅层扫描中确认共享页面目录"

    facts = {
        "project_identity": {
            "project_name": target.name,
            "path": relative_str(target, root),
            "project_type": "userscripts",
            "inheritance_line": "继承仓库根目录 AGENTS.md",
        },
        "structure": {
            "entry_points": [
                {"path": candidate, "purpose": "用户脚本入口或装配入口"}
                for candidate in ("src/entry.js", "src/entry.ts", "src/main.ts", "src/main.js")
                if (target / candidate).exists()
            ],
            "source_dirs": source_dirs,
            "page_dirs": page_dirs,
            "page_dir": "src/pages" if (target / "src" / "pages").exists() else "未在本地浅层扫描中确认页面目录",
            "service_dir": "src/services" if (target / "src" / "services").exists() else "未在本地浅层扫描中确认服务目录",
            "style_dir": "src/styles" if (target / "src" / "styles").exists() else "未在本地浅层扫描中确认样式目录",
            "type_dir": "src/types" if (target / "src" / "types").exists() else "未在本地浅层扫描中确认类型目录",
            "utils_dir": "src/utils" if (target / "src" / "utils").exists() else "未在本地浅层扫描中确认工具目录",
            "shared_page_dir": shared_page_dir,
            "entry_file": "src/entry.js" if (target / "src" / "entry.js").exists() else "未在本地浅层扫描中确认入口文件",
        },
        "commands": {
            key: str(scripts[key])
            for key in preferred_command_keys
            if key in scripts
        },
        "validation": {
            "quick_command": preferred_script(
                script_invocations,
                ["test", "start"],
                "未在本地浅层扫描中确认快速验证命令",
            ),
            "minimal_build_command": preferred_script(
                script_invocations,
                ["build"],
                "未在本地浅层扫描中确认最小构建命令",
            ),
            "unit_test_command": preferred_script(
                script_invocations,
                ["test"],
                "未在本地浅层扫描中确认单元测试命令",
            ),
            "e2e_test_command": preferred_script(
                script_invocations,
                ["test:e2e"],
                "未在本地浅层扫描中确认端到端测试命令",
            ),
        },
        "config_touchpoints": {
            "files": sorted(config_files, key=lambda item: item["name"]),
        },
        "environment": environment,
    }
    facts["commands"]["preferred_order"] = [key for key in preferred_command_keys if key in scripts]
    if detail_level == "rich":
        facts["structure"]["source_dir_text"] = "、".join(item["path"] for item in source_dirs) if source_dirs else "未在本地浅层扫描中确认源码目录"
        facts["structure"]["feature_dirs"] = page_dirs
        facts["structure"]["shared_dirs"] = existing_path_items(
            target,
            ("src/pages/shared", "src/services", "src/utils", "src/types"),
            "用户脚本共享能力或跨页面基础设施",
        )
        enrich_common_rich_facts(facts, target, script_invocations)
    return facts


def extract_claude_facts(root: Path, child_agents: list[str], host: str = "claude") -> dict[str, Any]:
    return {
        "host_profile": {
            "host": host,
            "project_trace_dir": ".claude" if host == "claude" else ".codex",
        },
        "repository_root": str(root).replace("\\", "/"),
        "child_agents_paths": [{"path": path} for path in sorted(child_agents)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract normalized AGENTS facts from a repository with shallow scanning."
    )
    parser.add_argument(
        "--template",
        required=True,
        choices=["root", "dotnet-backend-child", "backend-child", "frontend-child", "nestjs-backend-child", "spring-boot-backend-child", "userscripts-child", "claude"],
    )
    parser.add_argument("--root", required=True, help="Repository root path.")
    parser.add_argument(
        "--target",
        help="Target project path for child extraction. Defaults to --root for root/claude templates.",
    )
    parser.add_argument(
        "--detail-level",
        choices=["basic", "standard", "rich"],
        help="Fact extraction detail level. Defaults to rich for child templates and standard for root/claude.",
    )
    parser.add_argument(
        "--child-agent",
        action="append",
        default=[],
        help="Relative child AGENTS path. Can be repeated.",
    )
    parser.add_argument(
        "--host",
        default="codex",
        choices=["codex", "claude"],
        help="Host profile used for root/claude facts.",
    )
    parser.add_argument(
        "--database-project",
        help="Explicit database profile project identifier for the root template; never inferred.",
    )
    parser.add_argument(
        "--database-production-read-target",
        help="Explicit default production read target for the root template; requires --database-project.",
    )
    parser.add_argument("--output", required=True, help="Output JSON path.")
    args = parser.parse_args()

    if (args.database_project or args.database_production_read_target) and args.template != "root":
        parser.error("database profile binding options are valid only with --template root")
    if args.database_production_read_target and not args.database_project:
        parser.error("--database-production-read-target requires --database-project")

    root = Path(args.root).resolve()
    target = Path(args.target).resolve() if args.target else root
    detail_level = args.detail_level or default_detail_level_for_template(args.template)

    if args.template == "root":
        facts = extract_root_facts(
            root,
            args.child_agent,
            host=args.host,
            database_project_identifier=args.database_project,
            database_default_production_read_target=args.database_production_read_target,
        )
    elif args.template == "frontend-child":
        facts = extract_frontend_facts(root, target, detail_level)
    elif args.template == "userscripts-child":
        facts = extract_userscripts_facts(root, target, detail_level)
    elif args.template == "nestjs-backend-child":
        facts = extract_nestjs_backend_facts(root, target, detail_level)
    elif args.template == "spring-boot-backend-child":
        facts = extract_spring_boot_backend_facts(root, target, detail_level)
    elif args.template in {"dotnet-backend-child", "backend-child"}:
        facts = extract_backend_facts(root, target, detail_level)
    else:
        facts = extract_claude_facts(root, args.child_agent, host=args.host)

    write_json(Path(args.output), facts)


if __name__ == "__main__":
    main()
