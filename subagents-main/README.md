<a href="https://github.com/VoltAgent/voltagent">
    <img width="1500" height="500" alt="codex" src="https://github.com/user-attachments/assets/35f56654-e3e7-4023-a7d5-acd5215455de" />
</a>

<br />
<br />

<div align="center">
    <strong>The awesome collection of 138 Codex subagents across 10 categories.</strong>
    <br />
    <br />
</div>

   
<div align="center">
    
[![Awesome](https://awesome.re/badge.svg)](https://awesome.re)
![Subagent Count](https://img.shields.io/badge/subagents-138-blue?style=classic)
[![Last Update](https://img.shields.io/github/last-commit/VoltAgent/awesome-codex-subagents?label=Last%20update&style=classic)](https://github.com/VoltAgent/awesome-codex-subagents)
[![Discord](https://img.shields.io/discord/1361559153780195478.svg?label=&logo=discord&logoColor=ffffff&color=7389D8&labelColor=6A7EC2)](https://s.voltagent.dev/discord)

<br />


<div align="center">
    <strong>More awesome collections for developers</strong>
    <br />
    <br />
</div>

[![Agent Skills](https://img.shields.io/static/v1?label=%E2%9A%A1%20Agent&message=Skills%2012k&color=black&style=classic)](https://github.com/VoltAgent/awesome-agent-skills)
[![Claude Code Subagents](https://img.shields.io/static/v1?label=Claude&message=Code%20Subagents%2014k&color=D97757&style=classic&logo=claude&logoColor=D97757)](https://github.com/VoltAgent/awesome-claude-code-subagents)
[![OpenClaw Skills](https://img.shields.io/static/v1?label=%F0%9F%A6%9E%20OpenClaw&message=Skills%2040k&color=f53e36&style=classic)](https://github.com/VoltAgent/awesome-openclaw-skills)
[![AI Agent Papers](https://img.shields.io/static/v1?label=arxiv&message=Agent%20Papers%20328&color=b31b1b&style=classic&logo=arxiv)](https://github.com/VoltAgent/awesome-ai-agent-papers)
</div>


# Awesome Codex Subagents

This repository serves as the definitive collection of [Codex Subagents](https://developers.openai.com/codex/subagents), specialized AI assistants designed for specific development tasks. Written specifically for Codex and aligned with the official docs.

## Installation

Use Codex custom agent directories exactly as documented:

- `~/.codex/agents/` for global agents (available in all projects)
- `.codex/agents/` for project-specific agents (higher precedence in that repo)

1. Clone this repository.
2. Copy the `.toml` agent files you want into one of the directories above.
3. Restart or refresh your Codex session if needed.
4. Delegate explicitly in prompts (Codex does not auto-spawn custom subagents).

Examples:
```bash
mkdir -p ~/.codex/agents
cp 01-core-development/backend-developer.toml ~/.codex/agents/
```

```bash
mkdir -p .codex/agents
cp 04-quality-security/reviewer.toml .codex/agents/
```

If you use agent configuration in Codex, keep it in `.codex/config.toml` under `[agents]` as described in the official docs.


### Subagent Storage Locations

| Type | Path | Availability | Precedence |
|------|------|--------------|------------|
| Project Subagents | `.codex/agents/` | Current project only | Higher |
| Global Subagents | `~/.codex/agents/` | All projects | Lower |

Note: When naming conflicts occur, project-specific subagents override global ones.


## Subagent Structure

Each subagent uses a Codex-native `.toml` format:

```toml
name = "subagent-name"
description = "When this agent should be invoked"
model = "gpt-5.6-terra"
model_reasoning_effort = "medium"
sandbox_mode = "read-only"

[instructions]
text = """
You are a [role description and expertise areas]...

[Agent-specific checklists, patterns, and guidelines]...
"""
```

### Smart Model Routing

Each subagent includes `model` and `model_reasoning_effort` fields that route it to the right quality/cost tier:

| Tier | Configuration | When It's Used | Examples |
|------|---------------|----------------|----------|
| Focused | `gpt-5.6-luna` + `medium` | Clear, repeatable, low-risk work with objective tests or structured acceptance criteria | `test-automator`, `refactoring-specialist` |
| Lite | `gpt-5.6-terra` + `low` | Narrow, well-scoped work where low latency matters more than depth | `ui-fixer-lite` |
| Fast | `gpt-5.6-terra` + `medium` | First-pass, lightweight, bounded, and upgradeable work: fast scanning, synthesis, scope narrowing, readonly exploration, lightweight planning/orchestration, high-signal review, and lighter research tasks | `search-specialist`, `research-analyst`, `agent-organizer`, `reviewer-lite`, `code-mapper` |
| Balanced | `gpt-5.6-terra` + `high` | Structured implementation, framework work, and bounded analysis with multiple edge cases | `backend-developer`, `frontend-developer`, `data-engineer` |
| Deep | `gpt-5.6-sol` + `high` | Deep reasoning for architecture, security, infrastructure, and high-risk debugging | `security-auditor`, `architect-reviewer`, `fintech-engineer` |
| Arbiter | `gpt-5.6-sol` + `xhigh` | One converged, high-error-cost decision after evidence and alternatives have been narrowed | `decision-arbiter` |

Focused and Fast agents should produce a clear upgrade signal when the task touches security, payments, authentication/authorization, production incidents, destructive database changes, architecture boundaries, complex debugging, shared contracts, cross-module writes, or final merge/release decisions.

Escalation happens at a new spawn boundary, not by hot-switching a running custom agent. Keep the same bounded responsibility and move only the affected work through Luna -> Terra -> Sol high. Use `decision-arbiter` only when one high-error-cost decision remains after the evidence and alternatives are already narrowed.

### Sandbox Mode Philosophy

Each subagent's `sandbox_mode` field controls filesystem access:
- **Read-only agents** (reviewers, auditors): `sandbox_mode = "read-only"` - analyze without modifying
- **Workspace-write agents** (developers, engineers): `sandbox_mode = "workspace-write"` - create and modify files


## Categories

### [01. Core Development](01-core-development/)

Essential development subagents for everyday coding tasks.

- [**api-designer**](01-core-development/api-designer.toml) - REST and GraphQL API architect
- [**backend-developer**](01-core-development/backend-developer.toml) - Server-side expert for scalable APIs
- [**code-mapper**](01-core-development/code-mapper.toml) - Code path mapping and ownership boundary analysis
- [**electron-pro**](01-core-development/electron-pro.toml) - Desktop application expert
- [**frontend-developer**](01-core-development/frontend-developer.toml) - UI/UX specialist for React, Vue, and Angular
- [**fullstack-developer**](01-core-development/fullstack-developer.toml) - End-to-end feature development
- [**graphql-architect**](01-core-development/graphql-architect.toml) - GraphQL schema and federation expert
- [**microservices-architect**](01-core-development/microservices-architect.toml) - Distributed systems designer
- [**mobile-developer**](01-core-development/mobile-developer.toml) - Cross-platform mobile specialist
- [**ui-designer**](01-core-development/ui-designer.toml) - Visual design and interaction specialist
- [**ui-fixer**](01-core-development/ui-fixer.toml) - Smallest safe patch for reproduced UI issues
- [**websocket-engineer**](01-core-development/websocket-engineer.toml) - Real-time communication specialist

### [02. Language Specialists](02-language-specialists/)

Language-specific experts with deep framework knowledge.
- [**angular-architect**](02-language-specialists/angular-architect.toml) - Angular 15+ enterprise patterns expert
- [**cpp-pro**](02-language-specialists/cpp-pro.toml) - C++ performance expert
- [**csharp-developer**](02-language-specialists/csharp-developer.toml) - .NET ecosystem specialist
- [**django-developer**](02-language-specialists/django-developer.toml) - Django 4+ web development expert
- [**dotnet-core-expert**](02-language-specialists/dotnet-core-expert.toml) - .NET 8 cross-platform specialist
- [**dotnet-framework-4.8-expert**](02-language-specialists/dotnet-framework-4.8-expert.toml) - .NET Framework legacy enterprise specialist
- [**elixir-expert**](02-language-specialists/elixir-expert.toml) - Elixir and OTP fault-tolerant systems expert
- [**flutter-expert**](02-language-specialists/flutter-expert.toml) - Flutter 3+ cross-platform mobile expert
- [**golang-pro**](02-language-specialists/golang-pro.toml) - Go concurrency specialist
- [**java-architect**](02-language-specialists/java-architect.toml) - Enterprise Java expert
- [**javascript-pro**](02-language-specialists/javascript-pro.toml) - JavaScript development expert
- [**kotlin-specialist**](02-language-specialists/kotlin-specialist.toml) - Modern JVM language expert
- [**laravel-specialist**](02-language-specialists/laravel-specialist.toml) - Laravel 10+ PHP framework expert
- [**nextjs-developer**](02-language-specialists/nextjs-developer.toml) - Next.js 14+ full-stack specialist
- [**php-pro**](02-language-specialists/php-pro.toml) - PHP web development expert
- [**powershell-5.1-expert**](02-language-specialists/powershell-5.1-expert.toml) - Windows PowerShell 5.1 and full .NET Framework automation specialist
- [**powershell-7-expert**](02-language-specialists/powershell-7-expert.toml) - Cross-platform PowerShell 7+ automation and modern .NET specialist
- [**python-pro**](02-language-specialists/python-pro.toml) - Python ecosystem master
- [**rails-expert**](02-language-specialists/rails-expert.toml) - Rails 8.1 rapid development expert
- [**react-specialist**](02-language-specialists/react-specialist.toml) - React 18+ modern patterns expert
- [**rust-engineer**](02-language-specialists/rust-engineer.toml) - Systems programming expert
- [**spring-boot-engineer**](02-language-specialists/spring-boot-engineer.toml) - Spring Boot 3+ microservices expert
- [**sql-pro**](02-language-specialists/sql-pro.toml) - Database query expert
- [**swift-expert**](02-language-specialists/swift-expert.toml) - iOS and macOS specialist
- [**typescript-pro**](02-language-specialists/typescript-pro.toml) - TypeScript specialist
- [**vue-expert**](02-language-specialists/vue-expert.toml) - Vue 3 Composition API expert


### [03. Infrastructure](03-infrastructure/)

DevOps, cloud, and deployment specialists.

- [**azure-infra-engineer**](03-infrastructure/azure-infra-engineer.toml) - Azure infrastructure and Az PowerShell automation expert
- [**cloud-architect**](03-infrastructure/cloud-architect.toml) - AWS/GCP/Azure specialist
- [**database-administrator**](03-infrastructure/database-administrator.toml) - Database management expert
- [**deployment-engineer**](03-infrastructure/deployment-engineer.toml) - Deployment automation specialist
- [**devops-engineer**](03-infrastructure/devops-engineer.toml) - CI/CD and automation expert
- [**devops-incident-responder**](03-infrastructure/devops-incident-responder.toml) - DevOps incident management
- [**docker-expert**](03-infrastructure/docker-expert.toml) - Docker containerization and optimization expert
- [**incident-responder**](03-infrastructure/incident-responder.toml) - System incident response expert
- [**kubernetes-specialist**](03-infrastructure/kubernetes-specialist.toml) - Container orchestration master
- [**network-engineer**](03-infrastructure/network-engineer.toml) - Network infrastructure specialist
- [**platform-engineer**](03-infrastructure/platform-engineer.toml) - Platform architecture expert
- [**security-engineer**](03-infrastructure/security-engineer.toml) - Infrastructure security specialist
- [**sre-engineer**](03-infrastructure/sre-engineer.toml) - Site reliability engineering expert
- [**terraform-engineer**](03-infrastructure/terraform-engineer.toml) - Infrastructure as Code expert
- [**terragrunt-expert**](03-infrastructure/terragrunt-expert.toml) - Terragrunt orchestration and DRY IaC specialist
- [**windows-infra-admin**](03-infrastructure/windows-infra-admin.toml) - Active Directory, DNS, DHCP, and GPO automation specialist

<details>
<summary><b>04. Quality & Security</b> — Testing, security, and code quality experts (17 agents)</summary>

### [04. Quality & Security](04-quality-security/)

- [**accessibility-tester**](04-quality-security/accessibility-tester.toml) - A11y compliance expert
- [**ad-security-reviewer**](04-quality-security/ad-security-reviewer.toml) - Active Directory security and GPO audit specialist
- [**architect-reviewer**](04-quality-security/architect-reviewer.toml) - Architecture review specialist
- [**browser-debugger**](04-quality-security/browser-debugger.toml) - Browser-based reproduction and client-side debugging
- [**chaos-engineer**](04-quality-security/chaos-engineer.toml) - System resilience testing expert
- [**code-reviewer**](04-quality-security/code-reviewer.toml) - Code quality guardian
- [**compliance-auditor**](04-quality-security/compliance-auditor.toml) - Regulatory compliance expert
- [**debugger**](04-quality-security/debugger.toml) - Advanced debugging specialist
- [**error-detective**](04-quality-security/error-detective.toml) - Error analysis and resolution expert
- [**penetration-tester**](04-quality-security/penetration-tester.toml) - Ethical hacking specialist
- [**performance-engineer**](04-quality-security/performance-engineer.toml) - Performance optimization expert
- [**powershell-security-hardening**](04-quality-security/powershell-security-hardening.toml) - PowerShell security hardening and compliance specialist
- [**qa-expert**](04-quality-security/qa-expert.toml) - Test automation specialist
- [**reviewer**](04-quality-security/reviewer.toml) - PR-style review for correctness, security, and regressions
- [**reviewer-lite**](04-quality-security/reviewer-lite.toml) - Fast first-pass review for top findings in a bounded scope
- [**security-auditor**](04-quality-security/security-auditor.toml) - Security vulnerability expert
- [**test-automator**](04-quality-security/test-automator.toml) - Test automation framework expert

</details>

<details>
<summary><b>05. Data & AI</b> — Data engineering, ML, and AI specialists (12 agents)</summary>

### [05. Data & AI](05-data-ai/)

- [**ai-engineer**](05-data-ai/ai-engineer.toml) - AI system design and deployment expert
- [**data-analyst**](05-data-ai/data-analyst.toml) - Data insights and visualization specialist
- [**data-engineer**](05-data-ai/data-engineer.toml) - Data pipeline architect
- [**data-scientist**](05-data-ai/data-scientist.toml) - Analytics and insights expert
- [**database-optimizer**](05-data-ai/database-optimizer.toml) - Database performance specialist
- [**llm-architect**](05-data-ai/llm-architect.toml) - Large language model architect
- [**machine-learning-engineer**](05-data-ai/machine-learning-engineer.toml) - Machine learning systems expert
- [**ml-engineer**](05-data-ai/ml-engineer.toml) - Machine learning specialist
- [**mlops-engineer**](05-data-ai/mlops-engineer.toml) - MLOps and model deployment expert
- [**nlp-engineer**](05-data-ai/nlp-engineer.toml) - Natural language processing expert
- [**postgres-pro**](05-data-ai/postgres-pro.toml) - PostgreSQL database expert
- [**prompt-engineer**](05-data-ai/prompt-engineer.toml) - Prompt optimization specialist

</details>

<details>
<summary><b>06. Developer Experience</b> — Tooling and developer productivity experts (13 agents)</summary>

### [06. Developer Experience](06-developer-experience/)

- [**build-engineer**](06-developer-experience/build-engineer.toml) - Build system specialist
- [**cli-developer**](06-developer-experience/cli-developer.toml) - Command-line tool creator
- [**dependency-manager**](06-developer-experience/dependency-manager.toml) - Package and dependency specialist
- [**documentation-engineer**](06-developer-experience/documentation-engineer.toml) - Technical documentation expert
- [**dx-optimizer**](06-developer-experience/dx-optimizer.toml) - Developer experience optimization specialist
- [**git-workflow-manager**](06-developer-experience/git-workflow-manager.toml) - Git workflow and branching expert
- [**legacy-modernizer**](06-developer-experience/legacy-modernizer.toml) - Legacy code modernization specialist
- [**mcp-developer**](06-developer-experience/mcp-developer.toml) - Model Context Protocol specialist
- [**powershell-module-architect**](06-developer-experience/powershell-module-architect.toml) - PowerShell module and profile architecture specialist
- [**powershell-ui-architect**](06-developer-experience/powershell-ui-architect.toml) - PowerShell UI/UX specialist for WinForms, WPF, Metro frameworks, and TUIs
- [**refactoring-specialist**](06-developer-experience/refactoring-specialist.toml) - Code refactoring expert
- [**slack-expert**](06-developer-experience/slack-expert.toml) - Slack platform and @slack/bolt specialist
- [**tooling-engineer**](06-developer-experience/tooling-engineer.toml) - Developer tooling specialist

</details>

<details>
<summary><b>07. Specialized Domains</b> — Domain-specific technology experts (12 agents)</summary>

### [07. Specialized Domains](07-specialized-domains/)

- [**api-documenter**](07-specialized-domains/api-documenter.toml) - API documentation specialist
- [**blockchain-developer**](07-specialized-domains/blockchain-developer.toml) - Web3 and crypto specialist
- [**embedded-systems**](07-specialized-domains/embedded-systems.toml) - Embedded and real-time systems expert
- [**fintech-engineer**](07-specialized-domains/fintech-engineer.toml) - Financial technology specialist
- [**game-developer**](07-specialized-domains/game-developer.toml) - Game development expert
- [**iot-engineer**](07-specialized-domains/iot-engineer.toml) - IoT systems developer
- [**m365-admin**](07-specialized-domains/m365-admin.toml) - Microsoft 365, Exchange Online, Teams, and SharePoint administration specialist
- [**mobile-app-developer**](07-specialized-domains/mobile-app-developer.toml) - Mobile application specialist
- [**payment-integration**](07-specialized-domains/payment-integration.toml) - Payment systems expert
- [**quant-analyst**](07-specialized-domains/quant-analyst.toml) - Quantitative analysis specialist
- [**risk-manager**](07-specialized-domains/risk-manager.toml) - Risk assessment and management expert
- [**seo-specialist**](07-specialized-domains/seo-specialist.toml) - Search engine optimization expert

</details>

<details>
<summary><b>08. Business & Product</b> — Product management and business analysis (11 agents)</summary>

### [08. Business & Product](08-business-product/)

- [**business-analyst**](08-business-product/business-analyst.toml) - Requirements specialist
- [**content-marketer**](08-business-product/content-marketer.toml) - Content marketing specialist
- [**customer-success-manager**](08-business-product/customer-success-manager.toml) - Customer success expert
- [**legal-advisor**](08-business-product/legal-advisor.toml) - Legal and compliance specialist
- [**product-manager**](08-business-product/product-manager.toml) - Product strategy expert
- [**project-manager**](08-business-product/project-manager.toml) - Project management specialist
- [**sales-engineer**](08-business-product/sales-engineer.toml) - Technical sales expert
- [**scrum-master**](08-business-product/scrum-master.toml) - Agile methodology expert
- [**technical-writer**](08-business-product/technical-writer.toml) - Technical documentation specialist
- [**ux-researcher**](08-business-product/ux-researcher.toml) - User research expert
- [**wordpress-master**](08-business-product/wordpress-master.toml) - WordPress development and optimization expert

</details>

<details>
<summary><b>09. Meta & Orchestration</b> — Agent coordination and meta-programming (12 entries)</summary>

### [09. Meta & Orchestration](09-meta-orchestration/)

- [**agent-installer**](09-meta-orchestration/agent-installer.toml) - Browse and install agents from this repository via GitHub
- [**agent-organizer**](09-meta-orchestration/agent-organizer.toml) - Multi-agent coordinator
- [**context-manager**](09-meta-orchestration/context-manager.toml) - Context optimization expert
- [**decision-arbiter**](09-meta-orchestration/decision-arbiter.toml) - Final read-only arbitration for one converged high-error-cost decision
- [**error-coordinator**](09-meta-orchestration/error-coordinator.toml) - Error handling and recovery specialist
- [**it-ops-orchestrator**](09-meta-orchestration/it-ops-orchestrator.toml) - IT operations workflow orchestration specialist
- [**knowledge-synthesizer**](09-meta-orchestration/knowledge-synthesizer.toml) - Knowledge aggregation expert
- [**multi-agent-coordinator**](09-meta-orchestration/multi-agent-coordinator.toml) - Advanced multi-agent orchestration
- [**performance-monitor**](09-meta-orchestration/performance-monitor.toml) - Agent performance optimization
- [**pied-piper**](https://github.com/sathish316/pied-piper/) - Orchestrate Team of AI Subagents for repetitive SDLC workflows
- [**task-distributor**](09-meta-orchestration/task-distributor.toml) - Task allocation specialist
- [**workflow-orchestrator**](09-meta-orchestration/workflow-orchestrator.toml) - Complex workflow automation

</details>

<details>
<summary><b>10. Research & Analysis</b> — Research, search, and analysis specialists (7 agents)</summary>

### [10. Research & Analysis](10-research-analysis/)

- [**competitive-analyst**](10-research-analysis/competitive-analyst.toml) - Competitive intelligence specialist
- [**data-researcher**](10-research-analysis/data-researcher.toml) - Data discovery and analysis expert
- [**docs-researcher**](10-research-analysis/docs-researcher.toml) - Documentation-backed API and framework verification
- [**market-researcher**](10-research-analysis/market-researcher.toml) - Market analysis and consumer insights
- [**research-analyst**](10-research-analysis/research-analyst.toml) - Comprehensive research specialist
- [**search-specialist**](10-research-analysis/search-specialist.toml) - Advanced information retrieval expert
- [**trend-analyst**](10-research-analysis/trend-analyst.toml) - Emerging trends and forecasting expert

</details>

## Understanding Subagents

Subagents are specialized AI assistants that enhance Codex's capabilities by providing task-specific expertise. They act as dedicated helpers that Codex can call upon when encountering particular types of work.

### What Makes Subagents Special?

**Independent Context Windows**
Every subagent operates within its own isolated context space, preventing cross-contamination between different tasks and maintaining clarity in the primary conversation thread.

**Domain-Specific Intelligence**
Subagents come equipped with carefully crafted instructions tailored to their area of expertise, resulting in superior performance on specialized tasks.

**Shared Across Projects**
After creating a subagent, you can utilize it throughout various projects and distribute it among team members to ensure consistent development practices.

**Controlled Delegation**
Codex can delegate after a direct request or when applicable `AGENTS.md` or skill instructions request it. Installing a custom agent alone does not trigger it; define the independent work, ownership boundary, and expected result shape.

### Core Advantages

- **Memory Efficiency**: Isolated contexts prevent the main conversation from becoming cluttered with task-specific details
- **Enhanced Accuracy**: Specialized prompts and configurations lead to better results in specific domains
- **Workflow Consistency**: Team-wide subagent sharing ensures uniform approaches to common tasks
- **Codex-Native**: Uses `.toml` agent files aligned with official Codex subagent docs

### Example Workflows

**PR review workflow:**
```text
Review this bounded change with parallel subagents. Have reviewer-lite inspect the changed files for top correctness, regression, security, and missing-test risks. Have docs_researcher verify the framework APIs this patch depends on. If reviewer-lite finds material risk, run reviewer on only the highest-risk file subset or risk theme. Summarize the findings with file references.
```

**Bug investigation workflow:**
```text
Investigate the broken settings flow. Have code_mapper trace the owning code paths, browser_debugger reproduce the bug in the browser, and frontend_developer propose the smallest fix after the failure is understood. Wait for the read-heavy agents first, then continue.
```

**Repo exploration and planning workflow:**
```text
Use search_specialist to locate the code related to payment retries, knowledge_synthesizer to summarize the current design, and refactoring_specialist to propose a minimal refactor plan. Return a concrete action list.
```
## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- Submit new subagents via PR
- Improve existing definitions
- Report issues and bugs


## License

MIT License - see [LICENSE](LICENSE)

This repository is a curated collection of subagent definitions contributed by both the maintainers and the community. All subagents are provided "as is" without warranty. We do not audit or guarantee the security or correctness of any subagent. Review before use, the maintainers accept no liability for any issues arising from their use.

If you find an issue with a listed subagent or want your contribution removed, please open an issue in this repository and we'll address it promptly.
