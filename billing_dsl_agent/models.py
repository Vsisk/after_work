from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(slots=True)
class ContextResource:
    resource_id: str
    name: str
    path: str
    scope: str = "global"
    domain: str = "default"
    description: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass(slots=True)
class RawLocalContextWithSource:
    payload: Dict[str, Any]
    source_node_path: str
    source_node_id: str = ""
    depth: int = 0


@dataclass(slots=True)
class NormalizedLocalContextNode:
    resource_id: str
    property_id: str
    property_name: str
    access_path: str
    property_type: str = "normal"
    annotation: str = ""
    source_node_path: str = ""
    source_node_id: str = ""
    depth: int = 0
    data_source: Dict[str, Any] = field(default_factory=dict)
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VisibleLocalContextSet:
    nodes_by_id: Dict[str, NormalizedLocalContextNode] = field(default_factory=dict)
    nodes_by_property_name: Dict[str, NormalizedLocalContextNode] = field(default_factory=dict)
    ordered_nodes: List[NormalizedLocalContextNode] = field(default_factory=list)
    source_trace: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass(slots=True)
class BOResource:
    resource_id: str
    bo_name: str
    field_ids: List[str] = field(default_factory=list)
    data_source: str = ""
    naming_sql_ids: List[str] = field(default_factory=list)
    naming_sqls: List["NormalizedNamingSQLDef"] = field(default_factory=list)
    naming_sqls_by_id: Dict[str, "NormalizedNamingSQLDef"] = field(default_factory=dict)
    naming_sql_name_by_key: Dict[str, str] = field(default_factory=dict)
    naming_sql_param_names_by_key: Dict[str, List[str]] = field(default_factory=dict)
    naming_sql_signatures_by_key: Dict[str, List["NormalizedNamingSQLParam"]] = field(default_factory=dict)
    scope: str = "system"
    domain: str = "default"
    description: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass(slots=True)
class FunctionResource:
    resource_id: str
    function_id: str
    name: str
    full_name: str
    description: str = ""
    function_kind: str = "func"
    signature: str = ""
    signature_display: str = ""
    params: List[str] = field(default_factory=list)
    param_defs: List["FunctionParamResource"] = field(default_factory=list)
    return_type_raw: str = ""
    return_type: str = ""
    return_type_ref: "NormalizedTypeRef" | None = None
    source_metadata: Dict[str, Any] = field(default_factory=dict)
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    scope: str = "func"
    tags: List[str] = field(default_factory=list)


@dataclass(slots=True)
class ResourceRegistry:
    contexts: Dict[str, ContextResource] = field(default_factory=dict)
    bos: Dict[str, BOResource] = field(default_factory=dict)
    functions: Dict[str, FunctionResource] = field(default_factory=dict)
    edsl_tree: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedTypeRef:
    raw_type: str = ""
    normalized_type: str = "unknown"
    category: str = "unknown"
    is_list: bool = False
    item_type: str | None = None
    is_unknown: bool = True


@dataclass(slots=True)
class FunctionParamResource:
    param_id: str
    param_name: str
    param_type_raw: str = ""
    normalized_param_type: str = "unknown"
    type_ref: NormalizedTypeRef | None = None
    is_list: bool = False
    item_type: str | None = None
    is_optional: bool | None = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedNamingTypeRef:
    data_type: str = ""
    data_type_name: str = ""
    is_list: bool | None = None
    is_unknown: bool = True


@dataclass(slots=True)
class NormalizedNamingSQLParam:
    param_id: str
    param_name: str
    data_type: str = ""
    data_type_name: str = ""
    is_list: bool | None = None
    normalized_type_ref: "NormalizedNamingTypeRef | None" = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedNamingSQLDef:
    naming_sql_id: str
    naming_sql_name: str
    bo_id: str
    description: str = ""
    params: List["NormalizedNamingSQLParam"] = field(default_factory=list)
    signature_display: str = ""
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FilteredEnvironment:
    registry: ResourceRegistry
    selected_global_context_ids: List[str] = field(default_factory=list)
    selected_local_context_ids: List[str] = field(default_factory=list)
    selected_bo_ids: List[str] = field(default_factory=list)
    selected_function_ids: List[str] = field(default_factory=list)
    selected_global_contexts: List[ContextResource] = field(default_factory=list)
    visible_local_context: VisibleLocalContextSet = field(default_factory=VisibleLocalContextSet)
    selected_bos: List[BOResource] = field(default_factory=list)
    selected_functions: List[FunctionResource] = field(default_factory=list)
    selection_debug: "EnvironmentSelectionBundle | None" = None


@dataclass(slots=True)
class Environment:
    filtered: FilteredEnvironment
    context_paths: List[str] = field(default_factory=list)
    bo_schema: Dict[str, List[str]] = field(default_factory=dict)
    function_schema: List[Any] = field(default_factory=list)
    node_schema: Dict[str, Any] = field(default_factory=dict)
    context_schema: Dict[str, Any] = field(default_factory=dict)


class NodeDef(StrictModel):
    node_id: str
    node_path: str
    node_name: str
    data_type: str = "unknown"
    description: str = ""
    is_ab: bool = False
    ab_data_sources: List[str] = Field(default_factory=list)


class PlanDiagnostic(StrictModel):
    code: str
    message: str
    path: str = ""
    severity: str = "info"


class ValidationIssue(StrictModel):
    code: str
    message: str
    path: str = ""
    severity: str = "error"


class LLMErrorRecord(StrictModel):
    stage: str
    code: str
    message: str
    raw_text: str = ""
    raw_payload: Dict[str, Any] | None = None
    exception_type: str = ""


class LLMAttemptRecord(StrictModel):
    stage: str
    attempt_index: int
    request_payload: Dict[str, Any] | None = None
    response_payload: Dict[str, Any] | None = None
    parsed_ok: bool = False
    errors: List[LLMErrorRecord] = Field(default_factory=list)


class ResourceSelectionOutput(StrictModel):
    resource_id_list: List[str] = Field(default_factory=list)


class ResourceSelectionDebug(StrictModel):
    resource_type: str
    strategy: str
    candidate_ids: List[str] = Field(default_factory=list)
    selected_ids: List[str] = Field(default_factory=list)
    fallback_used: bool = False
    llm_errors: List[LLMErrorRecord] = Field(default_factory=list)


class EnvironmentSelectionBundle(StrictModel):
    global_context: ResourceSelectionDebug
    local_context: ResourceSelectionDebug
    bo: ResourceSelectionDebug
    function: ResourceSelectionDebug


class GenerateDSLDebug(StrictModel):
    resource_selection: EnvironmentSelectionBundle | None = None
    plan_attempts: List[LLMAttemptRecord] = Field(default_factory=list)
    repair_attempts: List[LLMAttemptRecord] = Field(default_factory=list)
    llm_errors: List[LLMErrorRecord] = Field(default_factory=list)


class LiteralPlanNode(StrictModel):
    type: Literal["literal"] = Field(
        description="表达式节点类型，固定为 `literal`。"
    )
    value: Any = Field(
        default=None,
        description="字面量值本身。可填写数字、字符串、布尔值或 null。示例：`1`、`\"ok\"`。",
    )


class ContextRefPlanNode(StrictModel):
    type: Literal["context_ref"] = Field(
        description="表达式节点类型，固定为 `context_ref`。"
    )
    path: str = Field(
        description="全局上下文变量完整路径。必须可直接写入 DSL，例如 `$ctx$.billStatement.prepareId`。不要填写 id、name 或路径片段。"
    )


class LocalRefPlanNode(StrictModel):
    type: Literal["local_ref"] = Field(
        description="表达式节点类型，固定为 `local_ref`。"
    )
    path: str = Field(
        description="局部上下文变量完整路径。必须可直接写入 DSL，例如 `$local$.currentCycle`。不要填写 id、name 或路径片段。"
    )


class VarRefPlanNode(StrictModel):
    type: Literal["var_ref"] = Field(
        description="表达式节点类型，固定为 `var_ref`。"
    )
    name: str = Field(description="变量名，例如 `amount`。")


class QueryFilterPlanNode(StrictModel):
    field: str = Field(
        description="【内部兼容字段】过滤左值字段名（如 `PREPARE_ID`）。优先使用 `query_call.filter_expr`，不要在 LLM 输出中单独拆分此字段。"
    )
    value: "ExprPlanNode" = Field(
        description="【内部兼容字段】过滤右值表达式节点。优先使用 `query_call.filter_expr`。"
    )


class QueryPairPlanNode(StrictModel):
    key: str = Field(
        description="【内部兼容字段】pair 的参数名（第一项）。优先使用 `query_call.params[].param_name`。"
    )
    value: "ExprPlanNode" = Field(
        description="【内部兼容字段】pair 的参数值表达式（第二项）。优先使用 `query_call.params[].value_expr`。"
    )


class FetchParamPlanNode(StrictModel):
    param_name: str = Field(
        description="namingSQL 的参数名，对应 DSL `pair(param_name, value)` 的第一项。示例：`OFFERING_ID`。不要填写参数 id。"
    )
    value_expr: str = Field(
        description="参数值表达式，对应 DSL `pair(param_name, value)` 的第二项。示例：`oid`、`$ctx$.billStatement.prepareId`。不要填写 `pair(...)` 拼接字符串。"
    )


class FunctionCallPlanNode(StrictModel):
    type: Literal["function_call"] = Field(
        description="表达式节点类型，固定为 `function_call`。"
    )
    function_name: str | None = Field(
        default=None,
        description="函数名称（首选）。示例：`Common.Double2Str`。只填写名称，不要填写 function id。",
    )
    function_id: str | None = Field(
        default=None,
        description="【内部兼容字段】函数 id。仅兼容旧链路，LLM 不应填写。",
    )
    args: List["ExprPlanNode"] = Field(
        default_factory=list,
        description="按顺序传入的参数表达式节点列表。每个参数应表达真实值语义。",
    )


class QueryCallPlanNode(StrictModel):
    type: Literal["query_call"] = Field(
        description="表达式节点类型，固定为 `query_call`。"
    )
    query_kind: Literal["select", "select_one", "fetch", "fetch_one"] = Field(
        description="查询调用类型。`select/select_one` 使用 BO；`fetch/fetch_one` 使用 namingSQL。"
    )
    source_name: str = Field(
        description="【兼容字段】查询目标名称。select 场景等价于 `bo_name`，fetch 场景等价于 `naming_sql_name`。"
    )
    bo_name: str | None = Field(
        default=None,
        description="select/select_one 的 BO 名称。示例：`BB_PREP_SUB`。只填写名称，不要填写 BO id。",
    )
    filter_expr: str | None = Field(
        default=None,
        description="select/select_one 的完整过滤表达式。示例：`it.PREPARE_ID == $ctx$.billStatement.prepareId`。使用 `it.FIELD` 引用 BO 字段，不要拆分为多个子字段。",
    )
    naming_sql_name: str | None = Field(
        default=None,
        description="fetch/fetch_one 的 namingSQL 名称。示例：`E_RT_QUERY_BY_OFFERINGID`。只填写名称，不要填写 id。",
    )
    params: List[FetchParamPlanNode] = Field(
        default_factory=list,
        description="fetch/fetch_one 的结构化参数列表。每项对应最终 DSL 的一个 `pair(param_name, value)`。",
    )
    field: str | None = Field(
        default=None,
        description="【内部兼容字段】旧版单字段过滤键，LLM 不应填写。",
    )
    bo_id: str | None = Field(
        default=None,
        description="【内部兼容字段】BO id，仅兼容旧链路，LLM 不应填写。",
    )
    data_source: str | None = Field(
        default=None,
        description="数据源标记。仅在系统已知且需要强校验时填写，通常可留空。",
    )
    naming_sql_id: str | None = Field(
        default=None,
        description="【内部兼容字段】namingSQL id，仅兼容旧链路，LLM 不应填写。",
    )
    filters: List[QueryFilterPlanNode] = Field(
        default_factory=list,
        description="【内部兼容字段】拆分过滤条件列表。优先使用 `filter_expr`。",
    )
    where: ExprPlanNode | None = Field(
        default=None,
        description="【内部兼容字段】过滤表达式 AST。优先使用 `filter_expr`。",
    )
    pairs: List[QueryPairPlanNode] = Field(
        default_factory=list,
        description="【内部兼容字段】拆分 pair 参数列表。优先使用 `params`。",
    )


class IfPlanNode(StrictModel):
    type: Literal["if"] = Field(description="表达式节点类型，固定为 `if`。")
    condition: "ExprPlanNode" = Field(description="if 条件表达式。")
    then_expr: "ExprPlanNode" = Field(description="条件为真时返回的表达式。")
    else_expr: "ExprPlanNode" = Field(description="条件为假时返回的表达式。")


class BinaryOpPlanNode(StrictModel):
    type: Literal["binary_op"] = Field(description="表达式节点类型，固定为 `binary_op`。")
    operator: str = Field(description="二元操作符，例如 `==`、`and`、`+`。")
    left: "ExprPlanNode" = Field(description="左操作数表达式。")
    right: "ExprPlanNode" = Field(description="右操作数表达式。")


class UnaryOpPlanNode(StrictModel):
    type: Literal["unary_op"] = Field(description="表达式节点类型，固定为 `unary_op`。")
    operator: str = Field(description="一元操作符，例如 `not`、`-`。")
    operand: "ExprPlanNode" = Field(description="一元操作数表达式。")


class FieldAccessPlanNode(StrictModel):
    type: Literal["field_access"] = Field(description="表达式节点类型，固定为 `field_access`。")
    base: "ExprPlanNode" = Field(description="被取字段的基础表达式。")
    field: str = Field(description="字段名。")


class IndexAccessPlanNode(StrictModel):
    type: Literal["index_access"] = Field(description="表达式节点类型，固定为 `index_access`。")
    base: "ExprPlanNode" = Field(description="被索引的基础表达式。")
    index: "ExprPlanNode" = Field(description="索引表达式。")


class ListLiteralPlanNode(StrictModel):
    type: Literal["list_literal"] = Field(description="表达式节点类型，固定为 `list_literal`。")
    items: List["ExprPlanNode"] = Field(default_factory=list, description="列表字面量中的元素表达式列表。")


ExprPlanNode = Annotated[
    LiteralPlanNode
    | ContextRefPlanNode
    | LocalRefPlanNode
    | VarRefPlanNode
    | FunctionCallPlanNode
    | QueryCallPlanNode
    | IfPlanNode
    | BinaryOpPlanNode
    | UnaryOpPlanNode
    | FieldAccessPlanNode
    | IndexAccessPlanNode
    | ListLiteralPlanNode,
    Field(discriminator="type"),
]


class VariableDefinitionNode(StrictModel):
    kind: Literal["variable"]
    name: str
    expr: ExprPlanNode


class MethodDefinitionNode(StrictModel):
    kind: Literal["method"]
    name: str
    params: List[str] = Field(default_factory=list)
    body: ExprPlanNode


DefinitionNode = Annotated[
    VariableDefinitionNode | MethodDefinitionNode,
    Field(discriminator="kind"),
]


class LegacyPlanDraft(StrictModel):
    intent_summary: str = ""
    expression_pattern: str = ""
    context_refs: List[str] = Field(default_factory=list)
    bo_refs: List[dict[str, Any]] = Field(default_factory=list)
    function_refs: List[str] = Field(default_factory=list)
    semantic_slots: Dict[str, Any] = Field(default_factory=dict)
    raw_plan: Dict[str, Any] = Field(default_factory=dict)


class ProgramPlanLimits(StrictModel):
    max_definitions: int = 6
    max_expr_depth_per_definition: int = 4
    max_return_expr_depth: int = 5
    max_total_expr_nodes: int = 50
    max_if_nodes_total: int = 6


class ProgramPlan(StrictModel):
    definitions: List[DefinitionNode] = Field(default_factory=list)
    return_expr: ExprPlanNode
    raw_plan: str | Dict[str, Any] | None = None
    diagnostics: List[PlanDiagnostic] = Field(default_factory=list)
    legacy_plan: LegacyPlanDraft | None = None


class ExprKind(str, Enum):
    LITERAL = "LITERAL"
    CONTEXT_REF = "CONTEXT_REF"
    LOCAL_REF = "LOCAL_REF"
    VAR_REF = "VAR_REF"
    QUERY_CALL = "QUERY_CALL"
    FUNCTION_CALL = "FUNCTION_CALL"
    IF_EXPR = "IF_EXPR"
    BINARY_OP = "BINARY_OP"
    UNARY_OP = "UNARY_OP"
    FIELD_ACCESS = "FIELD_ACCESS"
    LIST_LITERAL = "LIST_LITERAL"
    INDEX_ACCESS = "INDEX_ACCESS"


class ExprNode(StrictModel):
    kind: ExprKind
    value: Any = None
    children: List["ExprNode"] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VariableDefNode(StrictModel):
    name: str
    expr: ExprNode


class ReturnNode(StrictModel):
    expr: ExprNode


class ProgramNode(StrictModel):
    definitions: List[VariableDefNode] = Field(default_factory=list)
    return_node: ReturnNode


class ValuePlan(StrictModel):
    target_node_path: str
    expr: ExprNode | None = None
    program: ProgramNode | None = None


class ValidationResult(StrictModel):
    is_valid: bool
    issues: List[ValidationIssue] = Field(default_factory=list)
    repaired_plan: ProgramPlan | None = None
    repair_attempts: List[LLMAttemptRecord] = Field(default_factory=list)
    llm_errors: List[LLMErrorRecord] = Field(default_factory=list)


class GenerateDSLRequest(StrictModel):
    user_requirement: str
    node_def: NodeDef
    site_id: str = ""
    project_id: str = ""


class GenerateDSLResponse(StrictModel):
    success: bool
    dsl: str = ""
    plan: ProgramPlan | None = None
    ast: ProgramNode | None = None
    validation: ValidationResult | None = None
    failure_reason: str = ""
    debug: GenerateDSLDebug | None = None


QueryFilterPlanNode.model_rebuild()
QueryPairPlanNode.model_rebuild()
FunctionCallPlanNode.model_rebuild()
QueryCallPlanNode.model_rebuild()
IfPlanNode.model_rebuild()
BinaryOpPlanNode.model_rebuild()
UnaryOpPlanNode.model_rebuild()
FieldAccessPlanNode.model_rebuild()
IndexAccessPlanNode.model_rebuild()
ListLiteralPlanNode.model_rebuild()
VariableDefinitionNode.model_rebuild()
MethodDefinitionNode.model_rebuild()
ExprNode.model_rebuild()
