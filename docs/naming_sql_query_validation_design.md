# DSL 查询表达式与 NamingSQL 参数强校验设计

## 背景与需求来源

用户要求在“生成语法（DSL）阶段”增加强校验，覆盖以下两类能力：

1. 查询表达式参数校验
   - `select(BO名称, 过滤条件表达式)`
   - `select_one(BO名称, 过滤条件表达式)`
   - `fetch(naming-sql名称, pair(...), pair(...), ...)`
   - `fetch_one(naming-sql名称, pair(...), pair(...), ...)`
2. NamingSQL 参数校验
   - 依据 naming-sql 定义（通过 `naming_sql_id` 定位）校验生成表达式中的 pair 参数
   - 规则：参数名完全一致 + 数量完全一致
   - 校验失败后进入 repair loop 自动修复

## 需求澄清结论

1. `select/select_one` 的过滤条件允许多个条件并支持 `and/or` 组合。
2. 过滤条件模型升级为通用布尔表达式 AST，而非仅 `filters:[{field,value}]`。
3. 生成 plan 时可使用 `naming_sql_id` 指定目标 naming-sql；最终 DSL 渲染仍以 naming-sql 名称作为 fetch/fetch_one 的第一参数。
4. 对 fetch/fetch_one 的 pair 是否“至少一个”不做额外强约束；但若提供 pair，则必须满足 naming-sql 参数集合“名称一致 + 数量一致”。
5. 校验失败进入 repair loop 自动修复，不直接终止。
6. 新增强校验立即生效，不做灰度开关。

## WHAT（做什么）

### 1. 扩展查询表达式 AST

- 新增/扩展布尔表达式节点，覆盖：
  - 比较：`== != > >= < <=`
  - 逻辑：`and / or / not`
  - 分组（通过树形嵌套表达）
- `select/select_one` 从“扁平 filters”迁移为“通用 where AST”。
- `fetch/fetch_one` 的参数保持 key-value（pair）语义，但与 naming-sql 参数定义做集合一致性校验。

### 2. 增强 PlanValidator

- 查询形态校验：
  - `select/select_one`：source 必须可解析为 BO；where AST 必须合法。
  - `fetch/fetch_one`：source 必须可定位到 naming-sql（通过 `naming_sql_id`，并可回落名称解析）；pair 参数参与 naming-sql 参数一致性校验。
- NamingSQL 参数一致性校验：
  - 从资源中读取 `param_list`（param_name 列表）
  - 将表达式里的 pair key 集合与定义集合做“等值比较”
  - 集合不一致或数量不一致报校验错误，进入 repair loop。

### 3. 渲染层语义调整

- `fetch/fetch_one` 渲染为：
  - `fetch(namingSqlName, pair(k1,v1), pair(k2,v2), ...)`
  - `fetch_one(namingSqlName, pair(k1,v1), ...)`
- `select/select_one` 渲染 where AST（包含 and/or 组合）到当前 DSL 可接受的表达式文本。

### 4. Repair loop 联动

- 新错误码加入 validator issues（如：`invalid_query_shape`、`naming_sql_param_mismatch` 等）。
- 在 repair prompt 中补充错误语义，使 LLM 能针对性修正：
  - 换用正确 naming-sql
  - 对齐 pair 参数名与数量
  - 修复 where AST 结构

### 5. 测试覆盖

- 单测：
  - select/select_one 的 where AST 合法与非法样例
  - fetch/fetch_one 的 naming_sql_id + param_list 一致性校验
  - pair 参数缺失/冗余/拼写错误触发错误并可修复
- 集成：
  - 生成 → 校验失败 → repair → 通过 → DSL 渲染文本正确

## WHY（为什么这样做）

1. 当前模型虽支持 query_kind，但缺少“按表达式类型差异化校验”的约束，容易产生语义正确性问题。
2. naming-sql 的参数定义天然可作为强约束来源，按 param_list 做一致性校验可显著降低运行时失败。
3. 引入 where AST 能表达真实业务中的复合过滤条件，避免扁平 filters 无法覆盖复杂逻辑。
4. repair loop 自动修复可降低人工干预成本，保持生成链路稳定。

## HOW（如何实现）

### 模块改造范围（预期）

- `billing_dsl_agent/models.py`
  - 扩展 QueryCallPlanNode 与表达式节点类型（where AST / pair 结构）
- `billing_dsl_agent/plan_validator.py`
  - 增加 query shape 校验、where AST 校验、naming-sql 参数一致性校验
- `billing_dsl_agent/ast_builder.py`
  - 将 plan 中 where/pair 结构转换为 ExprNode
- `billing_dsl_agent/dsl_renderer.py`
  - 按 query_kind 分别渲染 select/fetch 语法；fetch 使用 naming-sql 名称
- `billing_dsl_agent/prompts/plan_prompt.txt`
  - 约束 LLM 输出新的结构与 query_kind 语义
- `billing_dsl_agent/prompts/repair_prompt.txt`
  - 补充新错误码与修复指引
- `billing_dsl_agent/tests/*`
  - 增加/更新单测与主流程测试

### 核心算法要点

1. naming-sql 解析
   - 优先 `naming_sql_id` 精确定位
   - 若 ID 缺失，可按名称匹配；若多义则报错并进入 repair
2. 参数一致性
   - expected = naming-sql param_name 列表（去空、规范化）
   - actual = pair 的 key 列表（去空、规范化）
   - 判定：`set(expected) == set(actual)` 且 `len(expected) == len(actual)`
3. where AST 校验
   - 递归检查节点类型、操作符、左右子树完整性
   - field 引用需落在 BO 可用字段集合内

## 兼容性与风险

- 兼容性：旧计划格式（legacy pattern + filters）需保留转换兼容，避免历史调用全量失败。
- 风险：
  - naming-sql 名称不唯一导致歧义
  - 历史 prompt 仍输出旧结构，短期可能触发更多 repair
- 缓解：
  - 优先 ID 驱动
  - prompt 明确新 schema
  - 测试覆盖 repair 成功路径

## 验收标准

1. select/select_one 支持 and/or 复合过滤并可通过 validator。
2. fetch/fetch_one 输出 naming-sql 名称，且基于 naming_sql_id 对 pair 参数完成“名称+数量一致”校验。
3. 校验失败可进入 repair 并在合理样例中修复通过。
4. 相关测试全部通过。
