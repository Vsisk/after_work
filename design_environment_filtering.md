# Environment 资源筛选链路增强设计

## What
在现有 Billing DSL Agent 架构上增强并串接以下主链路：

`agent entry -> loader -> normalization -> environment filter -> planner -> validator -> AST builder -> EDSL`

并实现三类资源（context / BO / function）独立筛选，且统一使用 `resource_id` 进行引用。

## Why
当前实现中的环境对象偏静态容器，planner 与 validator 主要依赖 path/name 字符串，缺少：

1. 真实加载层（site/project 维度）；
2. 稳定资源 ID 与 registry 回查；
3. context/BO/function 的独立语义筛选；
4. AB 节点数据源约束；
5. planner/validator/ast 对 filtered environment 的一致约束。

## How

### 新增与改造范围
1. 新增 `resource_loader.py`
   - `ResourceProvider` / `InMemoryResourceProvider` / `ResourceLoader`
   - 按 `site_id + project_id` 加载 context/bo/function 原始数据。

2. 新增 `resource_normalizer.py`
   - 将 loader 输出标准化为 `ResourceRegistry`。
   - 统一生成稳定 `resource_id`：
     - context: `context:$ctx$.a.b`
     - bo: `bo:BOName`
     - function: `function:Class.Func`

3. 增强 `models.py`
   - 扩展 `NodeDef`（支持 `is_ab`, `ab_data_sources`）
   - 新增 `ContextResource/BOResource/FunctionResource/ResourceRegistry/FilteredEnvironment`

4. 增强 `environment.py`
   - environment 成为筛选核心；
   - local context：基于 `node_path` 父链路筛选；
   - global context：domain recall + semantic selector；
   - bo：分 `is_ab` 分支，支持 data_source 约束；
   - function：独立语义筛选；
   - 三类资源分别调用 selector。

5. 新增 `semantic_selector.py`
   - 定义统一接口 `SemanticSelector.select(...)`；
   - `MockSemanticSelector` 通过 token overlap 排序，可替换为真实 OpenAI 语义检索。

6. 改造 `llm_planner.py`
   - planner 输入改为 `FilteredEnvironment`；
   - payload 仅暴露筛选后的 resource ids。

7. 改造 `plan_validator.py`
   - 校验 resource id 是否存在、是否在 filtered environment 中；
   - BO field/naming_sql/data_source/params 校验；
   - function 参数个数校验。

8. 改造 `ast_builder.py`
   - 严格通过 `resource_id` 回查 registry，生成最终 EDSL AST。

9. 改造 `agent_entry.py`
   - 串接完整主链路执行。

### 兼容性与风险
- 属于接口级变更（`GenerateDSLRequest` 输入结构、planner/validator/ast 构建输入）；
- 通过单测覆盖链路行为，保证功能真实性。

### 测试策略
覆盖以下场景：
1. loader 正常加载资源；
2. environment 正常筛选资源；
3. context / BO / function 独立筛选；
4. `is_ab` 分支逻辑；
5. planner 只使用筛选后资源；
6. AST builder 可生成合法 EDSL 片段；
7. validator 能发现非法引用。
