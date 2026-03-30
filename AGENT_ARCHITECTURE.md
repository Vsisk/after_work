# Billing DSL Agent Architecture

本文档描述当前 `billing_dsl_agent` 的收敛后架构。系统统一为**单一主链路**：

`generate_dsl(request)`
→ `EnvironmentBuilder`
→ `LLMPlanner`
→ `PlanValidator (repair loop <= 2)`
→ `ASTBuilder`
→ `DSLRenderer`
→ `FinalValidator`
→ `GenerateDSLResponse`

---

## 1. 目录与模块

核心模块固定为：

- `billing_dsl_agent/agent_entry.py`
- `billing_dsl_agent/environment.py`
- `billing_dsl_agent/llm_planner.py`
- `billing_dsl_agent/plan_validator.py`
- `billing_dsl_agent/ast_builder.py`
- `billing_dsl_agent/dsl_renderer.py`
- `billing_dsl_agent/models.py`

Prompt 资源：

- `billing_dsl_agent/prompts/plan_prompt.txt`
- `billing_dsl_agent/prompts/repair_prompt.txt`
- `billing_dsl_agent/prompts/namingsql_param_prompt.txt`

测试目录：

- `billing_dsl_agent/tests/`

---

## 2. 核心设计原则

1. **LLM 负责方案生成**：计划生成与修复由 `LLMPlanner` 完成。
2. **本地只做强校验**：`PlanValidator` 不做规则猜测，仅验证引用与参数合法性。
3. **确定性落地**：`ASTBuilder` 与 `DSLRenderer` 将合法计划稳定转为 DSL。
4. **统一契约**：`PlanDraft` 是 LLM 与系统之间唯一计划契约。
5. **不改 DSL 语法**：渲染层仅按既有表达式语义输出 DSL 文本。

---

## 3. 数据模型（models.py）

所有 dataclass 集中在 `models.py`，包括：

- `NodeDef`
- `Environment`
- `PlanDraft`
- `ExprNode`
- `ExprKind`
- `ValuePlan`
- `ValidationResult`
- `GenerateDSLRequest`
- `GenerateDSLResponse`

### 3.1 PlanDraft 统一结构

`PlanDraft` 字段：

- `intent_summary: str`
- `expression_pattern: str`
- `context_refs: List[str]`
- `bo_refs: List[dict]`
- `function_refs: List[str]`
- `semantic_slots: Dict[str, Any]`
- `raw_plan: Dict[str, Any]`

`expression_pattern` 允许值：

- `direct_ref`
- `if`
- `select_one`
- `select`
- `fetch_one`
- `fetch`
- `function_call`

---

## 4. 主链路详细说明

### 4.1 EnvironmentBuilder（environment.py）

输入 `GenerateDSLRequest`，输出 `Environment`：

- `context_schema`
- `bo_schema`
- `function_schema`
- `node_schema`
- `context_paths`

其中 `context_paths` 通过 flatten 生成，例如：

- `customer.gender` → `$ctx$.customer.gender`
- `customer.id` → `$ctx$.customer.id`

### 4.2 LLMPlanner（llm_planner.py）

方法：

- `plan(user_requirement, node_def, env) -> PlanDraft`
- `repair(invalid_plan, env, issues) -> Optional[PlanDraft]`

职责：

- 读取 prompt
- 调用 OpenAI client（当前支持 stub）
- 解析结构化输出为 `PlanDraft`

### 4.3 PlanValidator（plan_validator.py）

方法：

- `validate(plan, env) -> ValidationResult`

校验内容：

1. context path 是否存在
2. `expression_pattern` 是否合法
3. BO 是否存在
4. BO 字段是否存在
5. function 是否存在
6. namingSQL 参数：
   - `value` 不为空
   - `value_source_type` ∈ `{context, constant}`
   - `value_source_type=context` 时引用 path 必须存在

repair loop：

- 最多 2 次
- 每次失败后调用 `LLMPlanner.repair(...)`

### 4.4 ASTBuilder（ast_builder.py）

方法：

- `build_ast(plan) -> ExprNode`

支持 `ExprKind`：

- `LITERAL`
- `CONTEXT_REF`
- `LOCAL_REF`
- `QUERY_CALL`
- `FUNCTION_CALL`
- `IF_EXPR`
- `BINARY_OP`
- `FIELD_ACCESS`
- `LIST_LITERAL`
- `INDEX_ACCESS`

### 4.5 DSLRenderer（dsl_renderer.py）

方法：

- `render(expr) -> str`

示例输出：

- `if($ctx$.customer.gender == "男", "MR.", "Ms.")`

### 4.6 FinalValidator（agent_entry.py）

用于 DSL 末端合法性校验（当前包含：

- DSL 非空
- 括号平衡

最终返回 `GenerateDSLResponse`。

---

## 5. NamingSQL 参数约定

在 `PlanDraft.bo_refs` 中约定：

```json
[
  {
    "bo_name": "...",
    "query_mode": "fetch_one",
    "params": [
      {
        "param_name": "...",
        "value": "...",
        "value_source_type": "context|constant"
      }
    ]
  }
]
```

本地 `PlanValidator` 对上述结构执行强校验；失败将进入 repair loop。

---

## 6. 测试基线

当前测试覆盖以下关键场景：

- `test_if_expr`
- `test_select_one`
- `test_function_call`
- `test_namingsql_param`
- `test_context_ref`
- `test_plan_validator_detect_fake_ctx`
- `test_plan_validator_empty_param`
- `test_repair_loop`

---

## 7. 已删除的冗余职责

已从架构中移除 rule-based 推断链路及其冗余树状结构（意图树、绑定树、operation tree、matcher 体系等），避免本地规则猜测依赖，统一为：

**LLM Planning + Strong Validation + Deterministic DSL Generation**。
