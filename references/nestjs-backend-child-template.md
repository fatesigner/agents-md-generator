# [NestJS后端项目名] 子目录指南

本文件作用于 `[NestJS后端目录]` 及其子目录。未特别说明的事项，继承仓库根目录 `AGENTS.md`。

## 项目结构

__CHILD_STRUCTURE_OVERVIEW__

## 后端改动边界

- `[MUST]` 优先沿用现有 NestJS 分层：[NestJS分层描述]。
- `[MUST]` `[NestJS入口文件 1]` 与 `[NestJS入口文件 2]` 仅承载启动、配置、宿主和 HTTP 管道逻辑。
- `[MUST NOT]` 将核心业务规则堆到入口文件、临时脚本或控制器外层装配代码中。
- `[MUST]` 业务流程与模块编排优先放在 `[NestJS业务目录]`。
- `[MUST]` 数据访问、Prisma 相关封装与数据库实现细节优先放在 `[NestJS数据库目录]` 与 `[NestJS Prisma目录]`。
- `[MUST]` 生成代码目录 `[NestJS生成目录集合]` 默认优先通过生成链路维护，未明确要求时不手工改写生成结果。
- `[MUST]` 涉及 Swagger、生成代码、配置、模板、缓存或日志改动时，同步检查 `[NestJS关键配置集合]`。

### 生成目录与高风险 touchpoint

__GENERATED_BOUNDARIES__

## 命名与模型约定

- `[MUST]` DTO、实体、接口模型优先放在对应模块或既有类型目录，沿用当前业务术语。
- `[MUST NOT]` 在入口层或控制器层重复声明已有契约。
- `[MUST]` 后端函数、类和 provider 保持单一职责，避免在同一实现混合多类业务意图。
- `[DEFAULT]` 同类逻辑重复达到 3 处及以上时，再评估通用化抽象。
- `[MUST]` 新增服务类、处理器、配置类时复用现有模块术语与目录命名。
- `[MUST]` Web、业务、数据访问与 Prisma 共享概念统一命名，避免同字段多命名。

## 接口与类型联动

- `[MUST]` DTO、实体、Prisma model、返回字段、Swagger/OpenAPI 契约或生成代码发生变化时，同步检查控制器、服务、数据访问层与相关类型定义。
- `[MUST]` 接口命名、字段命名、枚举值与状态值沿用既有后端术语，并与数据库模型、DTO 和对外契约保持一致。
- `[MUST NOT]` 在同一条 NestJS 链路中引入同义字段名或仅前后缀不同的重复命名。
- `[MUST]` 新增 DTO、返回模型、查询参数类型、事件载荷或仓储类型声明时，优先复用既有契约文件、模块类型目录或生成结果。
- `[MUST NOT]` 在控制器、服务或临时转换层重复声明相同结构；若仅为映射而新增类型，需说明与原契约的职责差异。
- `[MUST]` 涉及认证、权限、租户、缓存键、队列消息、文件上传元数据或第三方回调结构改动时，明确受影响入口、字段来源、回退逻辑与兼容性影响。

## 配置与数据边界

- `[MUST]` 涉及数据库结构、DTO、实体、返回字段或 Prisma 生成结果变化时，同步检查：
  - `[NestJS Prisma目录]`
  - `[NestJS数据库目录]`
  - `[NestJS生成目录集合]`
  - 相关模块 DTO、实体、服务与控制器
- `[MUST]` 涉及 Swagger、导出脚本或代码生成改动时，同步检查 `[NestJS脚本目录]` 与相关生成命令。
- `[MUST]` 涉及缓存、队列、第三方 SDK、文件上传或外部服务调用时，明确配置来源、失败路径和回滚关注点。
- `[MUST]` 新增配置项时说明用途、默认行为、是否必填以及受影响模块。

### 配置 touchpoint

__CONFIG_TOUCHPOINT_DETAILS__

## 异步错误处理约定

- `[MUST]` 根据异步逻辑职责选择 `await-to-js` 或 `try/catch/finally`，不机械统一写法。
- `[MUST]` 当一次后端流程包含多个异步步骤，或存在统一收尾动作（如事务状态恢复、锁释放、上下文清理、审计/日志收尾）时，使用 `try/catch/finally`。
- `[MUST]` 当存在“无论成功失败都必须执行”的收尾动作时，使用 `finally` 承担收尾职责。
- `[DEFAULT]` 当代码仅包含单个异步调用，失败后只需本地分支处理、无需统一 cleanup 时，可使用 `await-to-js`。
- `[MUST NOT]` 已存在外层 `try/catch/finally` 时，不为同一异步链路机械再包一层 `await-to-js`；若无明显可读性收益，应保持单一控制流。
- `[MUST NOT]` 不得使用异常作为常规流程控制手段；高频、可预期的失败分支优先使用条件判断而非 `throw/catch`。
- `[DEFAULT]` 控制器入口、服务编排、任务执行链路、外部服务调用、需要统一日志或资源收尾的流程，优先使用 `try/catch/finally`。
- `[DEFAULT]` 单次读取、容错探测、失败后直接 fallback 的短链路调用，可优先使用 `await-to-js`。
- `[MUST]` 可复用服务方法、领域动作、仓储封装若仍需让上层感知失败，`catch` 后必须重新抛出，或改为不在当前层捕获；不得无说明地吞掉异常。
- `[DEFAULT]` 仅承担当前层错误转换、补充日志上下文或统一异常映射的封装层，可在当前层捕获并转换后继续抛出。

## 代码风格与格式化执行

- `[MUST]` 若项目存在 ESLint/Prettier 配置或对应脚本，新增或修改 JS/TS/NestJS 代码后必须至少执行一次与改动匹配的自动修复；涉及导入顺序、未使用导入、可自动修复规则时，优先执行 ESLint auto-fix，而不是仅执行 Prettier 格式化。
- `[MUST]` 若项目存在 ESLint/Prettier 配置或对应脚本，生成新文件后必须立即执行一次针对该文件的 lint/fix 或等价自动修复，再继续后续实现。
- `[MUST]` 优先使用 `package.json` 已定义脚本执行自动修复、格式化与校验，不自行发明命令。
- `[DEFAULT]` 若项目使用 VS Code 且 ESLint 扩展已接管代码操作，`Fix all auto-fixable problems` / `source.fixAll.eslint` 视为与 `eslint --fix` 等价的自动修复入口。
- `[DEFAULT]` 自动修复与格式化命令优先级：
  - `[NestJS格式化命令 1]`
  - `[NestJS格式化命令 2]`
  - `[NestJS格式化命令 3]`
  - 若无脚本，仅对改动文件执行最小化自动修复/格式化命令
- `[MUST]` 若项目使用 `simple-import-sort/imports`、`import/order` 或同类 ESLint 可修复规则，导入顺序应通过 ESLint auto-fix 修复，不得期待 Prettier 单独产出正确顺序。
- `[MUST]` 若存在 `.eslintrc*`、`eslint.config.*`、`.prettierrc*`、`prettier.config.*`，必须以项目本地配置为准，不使用全局默认风格。
- `[MUST]` 若项目未配置 ESLint/Prettier 或无可用脚本，不得臆造命令或临时安装依赖；需在交付中说明现状并执行可用的最小验证。
- `[MUST]` 默认仅格式化本次改动文件，避免无关全仓改写。
- `[MUST]` 格式化或修复命令失败时，在交付中说明失败原因、已尝试命令与剩余风险。

## 包管理与命令约定

- `[MUST]` 存在 `[NestJS锁文件]` 时优先使用 `[NestJS包管理器]`。
- `[MUST]` Node 版本要求：`[NestJS Node 版本要求]`。
- `[DEFAULT]` 常用命令：

```powershell
[NestJS命令 1]
[NestJS命令 2]
[NestJS命令 3]
[NestJS命令 4]
[NestJS命令 5]
[NestJS命令 6]
```

- `[MUST]` 若存在多套 script、mode 或环境命令，涉及环境差异时明确使用的脚本、模式与目标环境。

## 验证要求

- `[MUST]` 默认先执行与改动范围最接近的最小验证。
- `[DEFAULT]` 开发迭代阶段优先执行 `[NestJS快速验证命令]`，避免每次改动都执行全量构建或全量测试。
- `[DEFAULT]` 常见验证顺序：
  - `[NestJS验证命令 1]`
  - `[NestJS验证命令 2]`
  - `[NestJS验证命令 3]`
- `[MUST]` 以下场景必须补充执行 `[NestJS验证命令 4]` 或 `[NestJS验证命令 5]`：
  - 涉及 Prisma schema、迁移、生成代码或数据库访问封装改动
  - 涉及 Swagger、OpenAPI、DTO、返回结构或生成链路改动
  - 涉及共享模块、公共 provider、鉴权、缓存、队列、文件上传或外部服务接入，且影响面无法通过局部验证覆盖
- `[MUST]` 若未执行较重验证，在交付中说明未执行原因、替代验证与剩余风险。
- `[MUST]` 沿用本子项目既有测试框架、断言风格与测试夹具结构。
- `[MUST NOT]` 不新增脱离现有构建链与测试链的自定义验证脚本（除非任务明确要求）。
- `[MUST]` 测试失败时，需要报告失败现象、复现步骤和初步观察。

### 验证矩阵

__VALIDATION_MATRIX__
