# [SpringBoot后端项目名] 子目录指南

本文件作用于 `[SpringBoot后端目录]` 及其子目录。未特别说明的事项，继承仓库根目录 `AGENTS.md`。

## 项目结构

__CHILD_STRUCTURE_OVERVIEW__

## 后端改动边界

- `[MUST]` 优先沿用现有 Spring Boot 分层：[SpringBoot分层描述]。
- `[MUST]` `[SpringBoot入口模块]` 仅承载启动、配置、宿主、过滤器、拦截器和 HTTP 管道装配逻辑。
- `[MUST NOT]` 将核心业务规则堆到启动类、`@Controller`、`@RestController`、过滤器、拦截器或配置类中。
- `[MUST]` 业务流程、领域规则与模块编排优先放在 `[SpringBoot业务模块]` 对应包或既有业务模块。
- `[MUST]` 公共工具、基础框架、横切能力优先放在 `[SpringBoot公共模块]` 或既有公共模块；不得把业务专用逻辑伪装成通用工具。
- `[MUST]` 数据访问、Mapper、Repository、DAO、SQL 映射和 ORM 细节优先放在 [SpringBoot数据模块] 或既有数据访问目录。
- `[MUST]` 多模块结构 `[SpringBoot模块集合]` 已存在时，新增代码必须先匹配既有模块职责，不新建平行模块体系。
- `[MUST]` 涉及配置、日志、缓存、定时任务、权限、代码生成或数据访问改动时，同步检查 `[SpringBoot关键配置集合]` 与绑定代码。

### 生成目录与高风险 touchpoint

__GENERATED_BOUNDARIES__

## 命名与模型约定

- `[MUST]` Controller、Service、Mapper/Repository、Entity、DTO、VO、BO 等命名沿用项目既有业务术语。
- `[MUST NOT]` 在 Controller 或入口层重复声明已有 DTO、VO、Entity 或枚举。
- `[MUST]` 新增 Service、Handler、Listener、Job、Config、Mapper/Repository 时复用现有包路径和模块术语。
- `[MUST]` 请求参数、返回模型、数据库字段、枚举值、状态值与前后端契约保持一致，避免同一概念出现多个近义命名。
- `[DEFAULT]` 同类逻辑重复达到 3 处及以上时，再评估通用化抽象。
- `[MUST]` Java 版本要求：`[SpringBoot Java版本]`。

## 配置与启动约定

- `[MUST]` 新增配置项时说明用途、默认行为、是否必填、受影响入口或模块。
- `[MUST]` 涉及启动流程、Spring Bean 注册、自动配置、Profile、过滤器、拦截器、切面或安全配置时，优先检查 `[SpringBoot入口模块]` 与 `[SpringBoot关键配置集合]`。
- `[MUST]` 涉及 `application*.yml`、`application*.yaml`、`application*.properties`、`bootstrap*` 或外部配置绑定时，只读取示例或非敏感配置原文；真实环境配置只确认存在性和字段结构。
- `[MUST]` 涉及日志、缓存、定时任务、消息队列、文件存储、第三方 SDK 或外部服务调用时，明确配置来源、失败处理路径和回滚关注点。

### 配置 touchpoint

__CONFIG_TOUCHPOINT_DETAILS__

## 依赖与数据边界

- `[MUST]` 数据访问主链路：`[SpringBoot数据访问主链路]`。
- `[MUST]` 涉及数据库结构、Entity、Mapper XML、Repository、DAO、SQL、事务或分页改动时，同步检查业务服务、数据访问层、配置和相关契约。
- `[MUST]` [SpringBoot SQL工具链约束]
- `[MUST]` [SpringBoot SQL脚本目录约束]
- `[MUST]` SQL 脚本必须在文件名、交付说明或任务记录中明确用途、执行顺序、回滚关注点和数据风险。
- `[MUST]` 一个 SQL 脚本只承载一类独立变更，不在同一文件混合 schema 变更、补数、排查查询或人工执行说明。
- `[MUST NOT]` 在 Controller、Service 或入口层绕过既有 Mapper/Repository/DAO 封装直接访问底层数据源。
- `[MUST NOT]` 未确认固定归档位置前，不在功能目录、临时目录、项目根目录或平行 SQL 目录零散创建 `.sql` 文件。
- `[MUST]` 涉及 `DROP`、`ALTER COLUMN`、批量 `UPDATE/DELETE` 或其他高风险 SQL 时，在交付中说明影响范围、回滚思路与执行前置条件。

## 构建与依赖约定

- `[MUST]` 使用 `[SpringBoot构建工具]` 和项目既有 wrapper/构建文件，不新增脱离 Maven/Gradle 主链路的并行脚本。
- `[MUST]` Maven 多模块项目新增依赖时优先检查父 `pom.xml`、目标模块 `pom.xml` 和依赖管理方式；Gradle 多模块项目优先检查 settings、根 build 文件和目标模块 build 文件。
- `[MUST]` 新增依赖或调整接入方式时，在交付中说明受影响模块、配置项、兼容性和回滚关注点。
- `[MUST]` 生成代码、代码生成器、Mapper XML、OpenAPI/Swagger 或注解处理器发生变化时，优先使用项目既有生成链路维护，不手工改写生成结果。

## 验证要求

- `[MUST]` 默认先执行与改动范围最接近的最小验证。
- `[DEFAULT]` 开发迭代阶段优先执行 `[SpringBoot快速验证命令]`。
- `[DEFAULT]` 常见验证顺序：
  - `[SpringBoot测试命令]`
  - `[SpringBoot构建验证命令]`
  - `[SpringBoot启动命令]`
- `[MUST]` 涉及入口启动链路、配置绑定、Bean 注册、Profile、权限、安全、缓存、队列或外部服务接入时，补充最小启动验证或说明无法执行的原因。
- `[MUST]` 涉及数据库结构、Mapper XML、Repository/DAO、事务或 SQL 改动时，补充对应 mapper/repository/service 测试；无法覆盖时说明剩余风险。
- `[MUST]` 沿用本子项目既有测试框架、断言风格与测试夹具结构。
- `[MUST NOT]` 不新增脱离现有构建链与测试链的自定义验证脚本（除非任务明确要求）。
- `[MUST]` 测试失败时，需要报告失败现象、复现步骤和初步观察。

### 验证矩阵

__VALIDATION_MATRIX__

## 常用命令

```powershell
[SpringBoot命令 1]
[SpringBoot命令 2]
[SpringBoot命令 3]
[SpringBoot命令 4]
[SpringBoot命令 5]
```
