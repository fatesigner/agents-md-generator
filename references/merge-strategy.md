# AGENTS Merge Strategy

本文件定义 `Global -> Root -> Child` 三层规则在生成阶段的字段级合并方式，供 `agents-md-generator` 统一执行。

## 目标

- 避免全局规则在 Root/Child 重复粘贴。
- 保证安全与隐私规则不会被下层放宽。
- 让仓库事实和子项目事实能就近覆盖。
- 为实现者提供可直接编码的决策表。

## 层级与优先级

- 层级顺序：Global baseline -> Root -> Child。
- 结果优先级：`Child > Root > Global`。
- 冲突时先按字段类型判定，再应用安全优先策略。

## 字段分类

将待填充信息分为 5 类：

1. `security_policy`：隐私、安全、脱敏、禁读禁传、自动化边界等硬约束。
2. `facts_scalar`：单值事实，如 `package_manager`、`node_version`、`entry_project`。
3. `facts_map`：键值集合，如 `commands`、`paths`、`config_files`。
4. `facts_list`：列表事实，如 `high_risk_operations`、`validation_steps`。
5. `section_text`：长段说明文本（固定章节正文）。

## 合并规则总表

| 字段类型 | 默认合并策略 | 冲突规则 | 备注 |
|---|---|---|---|
| `security_policy` | stricter-wins | 选择更严格约束 | 下层不得放宽上层硬约束 |
| `facts_scalar` | nearest-scope-wins | Child 覆盖 Root，Root 覆盖 Global | 仅允许已验证事实 |
| `facts_map` | key-wise merge | 同名 key 采用 nearest-scope-wins | 建议保留来源层级用于审计 |
| `facts_list` | union-dedupe | 若声明 `replace=true` 则整段替换 | 默认去重并保持稳定顺序 |
| `section_text` | reference-first | Root/Child 引用上层，不重复长文 | 只在本层补充差异段 |

## 安全优先策略

凡命中以下关键词域，必须执行 `stricter-wins`，忽略普通覆盖逻辑：

- 密钥、口令、Token、证书、私钥、连接串
- 联网、上传、外部 API、第三方服务
- 生产配置、客户数据、日志原文、备份文件
- 破坏性操作、越权目录访问

当下层文本出现“允许”而上层是“禁止”时：

- 最终结果保持“禁止”。
- 在生成备注记录 `conflict_security_downgrade_blocked`。

## 事实优先策略

对于路径、命令、配置文件名等事实字段：

- 必须来自本地已验证上下文（文件存在或脚本存在）。
- 近域优先：Child 事实优先于 Root，Root 事实优先于 Global 示例值。
- 不可验证事实不写入结果，改为省略或保守提示。

## 长文本处理策略

- Global 放完整通用规则。
- Root 章节保留固定标题，但正文尽量写成“继承声明 + 仓库补充”。
- Child 聚焦局部边界、局部命令、局部验证，不复制 Root/Global 长文。

## 稳定渲染顺序策略

为减少同输入多次生成的波动，合并后字段进入模板前必须再经过一次稳定排序。

- `section_text`：按模板章节顺序渲染，不允许互换章节。
- `facts_map.commands`：按固定键顺序渲染，禁止根据“更重要”或“更常用”临时换序。
- `facts_map.paths`、`facts_map.config_files`：按键名字典序或 schema 明确顺序渲染。
- `facts_list`：先去重，再按 schema 规则排序；若 schema 未规定，则保持提取顺序且同类任务中不得漂移。
- 缺失字段优先使用 schema 预定义回退文案，不临时改写。

## 标准执行流程

1. 加载模板层：`global-template.md`、目标模板（root 或 child）。
2. 收集并验证本地事实字段。
3. 将事实映射到 `facts-schema.md` 规定的固定结构。
4. 对结构化字段执行合并：
   - `security_policy` -> `stricter-wins`
   - `facts_scalar` -> `nearest-scope-wins`
   - `facts_map` -> `key-wise merge`
   - `facts_list` -> `union-dedupe`（或 `replace`）
5. 对合并后的字段执行稳定排序与缺失值回填。
6. 渲染模板占位符并应用继承声明。
7. 运行最终检查：
   - `##` 章节结构与目标模板一致
   - 命令与路径可验证
   - 无长段全局内容重复粘贴
   - 无安全降级冲突未处理
   - 同类字段顺序符合 schema 规定
   - 缺失值回退文案符合 schema 规定

## 建议的数据结构

```yaml
merge_context:
  policy:
    security: {}
    privacy: {}
  facts:
    scalar: {}
    map:
      commands: {}
      paths: {}
      config_files: {}
    list:
      high_risk_operations: []
      validations: []
  flags:
    replace_lists: []
  audit:
    conflicts: []
    missing_facts: []
```

## 冲突记录约定

出现冲突时建议记录以下结构，便于后续审计：

```json
{
  "field": "security.network",
  "global": "deny-by-default",
  "root": "allow",
  "resolved": "deny-by-default",
  "reason": "stricter-wins"
}
```

## 最小实现建议

- 先实现 `security_policy + facts_scalar + facts_map` 三类。
- 第二阶段再加入 `facts_list.replace` 与冲突审计输出。
- 未实现字段应显式回退为“继承上层，不主动展开”。
- 若尚未实现程序化渲染，至少要在提示与检查阶段强制遵循 `facts-schema.md` 的字段顺序与回退文案。
