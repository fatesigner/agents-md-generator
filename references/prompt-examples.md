# Prompt Examples

Use these prompts when invoking `agents-md-generator` in strict template mode.

## 1. Single-project repository

```text
使用 agents-md-generator 为当前仓库生成根目录 AGENTS.md。
要求：
1. 按标准模板填充，不要自由改写章节结构
2. 这是单项目仓库，不生成子目录 AGENTS.md
3. 只根据当前项目的目录结构、命令、配置和验证方式填充变量区
4. 除项目事实区外，其余规则正文保持模板一致
5. 若已存在 AGENTS.md，先提示我确认是否覆盖；未确认前不要修改文件
6. 先做浅层扫描，不要一开始全仓库递归搜索
7. 先输出结构化 facts 摘要，再基于这些 facts 渲染 AGENTS.md
8. section 顺序、变量区 bullet 顺序、缺失事实回退文案必须保持稳定
9. 生成并校验完成后直接结束，不主动提出措辞优化、压缩风格或继续收紧的建议
```

Short form:

```text
使用 agents-md-generator 按标准模板为当前单项目仓库生成根目录 AGENTS.md，只填充项目事实区；如果已存在 AGENTS.md，先询问是否覆盖，并使用浅层扫描；生成完成并校验后直接停止，不追加风格优化建议。
```

## 2. Multi-project front-end/back-end repository

```text
使用 agents-md-generator 为当前仓库生成完整的 AGENTS.md 体系。
要求：
1. 先生成根目录 AGENTS.md
2. 再为以下子项目生成子目录 AGENTS.md：
   - backend
   - web
3. 根目录使用标准根模板
4. 子目录分别使用标准后端子模板和前端子模板
5. 不要自由改写二级标题结构
6. 除仓库概览、项目结构、命令、验证、配置文件名外，其余正文保持模板一致
7. 子目录明确继承根目录，不复制根目录通用规则
8. 若目标位置已存在 AGENTS.md，先提示我确认是否覆盖；未确认前不要修改文件
9. 先做浅层扫描，并按目录逐个处理，不要全仓库深度递归
10. 先输出结构化 facts 摘要，再按模板顺序渲染根目录和子目录文件
11. section 顺序、变量区 bullet 顺序、缺失事实回退文案必须保持稳定
12. 生成并校验完成后直接结束，不主动提出措辞优化、压缩风格或继续收紧的建议
```

Short form:

```text
使用 agents-md-generator 按标准模板为当前多项目仓库生成 AGENTS.md 体系：根目录一份，子项目各一份，只填充项目事实区；如已存在 AGENTS.md，先询问是否覆盖，并按目录逐个浅层处理；生成完成并校验后直接停止，不追加风格优化建议。
```

## 3. Multi-project mixed-type repository

```text
使用 agents-md-generator 为当前仓库生成完整的 AGENTS.md 体系。
要求：
1. 先生成根目录 AGENTS.md
2. 再为以下子项目生成子目录 AGENTS.md：
   - admin-web
   - mobile-web
   - miniprogram
   - api-server
3. 根目录使用标准根模板，并以目录清单方式描述仓库概览，不要把仓库强行写成“后端 + 前端”二分结构
4. 子目录按项目实际类型选择最接近的标准子模板
5. 除仓库概览、项目结构、命令、验证、配置文件名外，其余正文保持模板一致
6. 子目录明确继承根目录，不复制根目录通用规则
7. 若目标位置已存在 AGENTS.md，先提示我确认是否覆盖；未确认前不要修改文件
8. 先做浅层扫描，并按目录逐个处理，不要全仓库深度递归
9. 先输出结构化 facts 摘要，再按模板顺序渲染各文件
10. section 顺序、变量区 bullet 顺序、缺失事实回退文案必须保持稳定
11. 生成并校验完成后直接结束，不主动提出措辞优化、压缩风格或继续收紧的建议
```

Short form:

```text
使用 agents-md-generator 按标准模板为当前多类型子项目仓库生成 AGENTS.md 体系：根目录一份，子项目各一份；根目录按目录清单描述仓库结构，只填充项目事实区；如已存在 AGENTS.md，先询问是否覆盖，并按目录逐个浅层处理；生成完成并校验后直接停止，不追加风格优化建议。
```

## 4. Only generate child-project AGENTS.md

### Back-end child project

```text
使用 agents-md-generator，为 backend 目录生成子目录 AGENTS.md。
要求：
1. 继承当前根目录 AGENTS.md
2. 使用标准后端子模板
3. 只填充本地项目结构、配置、验证和命令
4. 不复制根目录通用规则
5. 保持模板章节结构不变
6. 若已存在 AGENTS.md，先提示我确认是否覆盖；未确认前不要修改文件
7. 只扫描 backend 目录及其必要配置文件，不要全仓库递归
8. 先输出 backend 的结构化 facts 摘要，再按模板顺序渲染
9. section 顺序、变量区 bullet 顺序、缺失事实回退文案必须保持稳定
10. 生成并校验完成后直接结束，不主动提出措辞优化、压缩风格或继续收紧的建议
```

### Front-end child project

```text
使用 agents-md-generator，为 web 目录生成子目录 AGENTS.md。
要求：
1. 继承当前根目录 AGENTS.md
2. 使用标准前端子模板
3. 只填充本地目录结构、样式约定、命令和验证方式
4. 不复制根目录通用规则
5. 保持模板章节结构不变
6. 若已存在 AGENTS.md，先提示我确认是否覆盖；未确认前不要修改文件
7. 只扫描 web 目录及其必要配置文件，不要全仓库递归
8. 先输出 web 的结构化 facts 摘要，再按模板顺序渲染
9. section 顺序、变量区 bullet 顺序、缺失事实回退文案必须保持稳定
10. 生成并校验完成后直接结束，不主动提出措辞优化、压缩风格或继续收紧的建议
```

### Multiple child projects at once

```text
使用 agents-md-generator，为以下子项目生成子目录 AGENTS.md：
- backend
- web
- mobile

要求：
1. 继承当前根目录 AGENTS.md
2. 后端使用标准后端子模板，前端使用标准前端子模板
3. 只填充本地结构、命令、验证和配置边界
4. 不要改动根目录 AGENTS.md
5. 保持模板章节结构固定
6. 若目标位置已存在 AGENTS.md，先提示我确认是否覆盖；未确认前不要修改文件
7. 按目录逐个处理，不做全仓库深度递归
8. 先分别输出各子项目的结构化 facts 摘要，再按模板顺序渲染
9. section 顺序、变量区 bullet 顺序、缺失事实回退文案必须保持稳定
10. 生成并校验完成后直接结束，不主动提出措辞优化、压缩风格或继续收紧的建议
```

Short form:

```text
使用 agents-md-generator 按标准子模板为指定子项目生成 AGENTS.md，继承根目录规则，只填充本地事实；如已存在 AGENTS.md，先询问是否覆盖，并使用浅层逐项处理；生成完成并校验后直接停止，不追加风格优化建议。
```

