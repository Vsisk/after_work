# Environment 资源筛选链路增强设计（修正版）

## What
在现有 Billing DSL Agent 架构上增强并串接以下主链路：

`agent entry -> loader -> normalization -> environment filter -> planner -> validator -> AST builder -> EDSL`

并实现三类资源（context / BO / function）独立筛选，且统一使用 `resource_id` 进行引用。

## Why
本次修正重点是 context 来源纠偏：

1. `local context` 必须来自 `edsl.json` 的节点树祖先递归，不来自 context.json；
2. `global context` 必须来自 `context.json`，并做语义筛选；
3. 二者来源、处理流程、selector 阶段必须解耦。

## How

### loader 职责拆分
- `context.json`：只承载 global context 源数据。
- `edsl.json`：承载节点树 + local_context 源数据。
- 两者都通过 `site_id + project_id` 加载。

### normalizer 职责
- 将 `context.json` 归一化为 global context registry（稳定 resource_id）。
- 保留 `edsl_tree` 原始结构进入 registry，供后续 local context 解析。

### environment/context selector 职责
- 阶段 1：`resolve_local_context_from_edsl_tree(node_path)`
  - 在 edsl 树中定位目标节点；
  - 沿祖先链递归向上；
  - 仅 `parent` / `parent list` 节点参与 local_context 收集；
  - 若缺失显式 id，生成稳定资源 id。
- 阶段 2：`select_global_context_from_context_json(user_query, node_info)`
  - 对 global context 做候选召回 + 语义排序。

### 其余模块
- planner：只看 filtered ids；
- validator：校验引用存在性和 filtered-membership；
- ast builder：通过 resource_id 回查 registry。

### 测试策略
覆盖：
1. loader + normalization + filtering 主链路；
2. local context 沿 node path 祖先继承；
3. 仅 parent / parent list 提供 local context；
4. global context 来自 context.json 而非 edsl；
5. context/bo/function 独立筛选；
6. is_ab BO 分支；
7. planner/validator/ast 联动正确。
