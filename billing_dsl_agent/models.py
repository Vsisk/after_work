from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


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
    retrieval_debug: Dict[str, Any] = Field(default_factory=dict)


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
    type: Literal["literal"] = Field(description="节点类型。固定填写 `literal`。")
    value: Any = Field(
        default=None,
        description="字面量值本身。仅在需要直接传入常量时填写，例如字符串、数字、布尔值或 null。不要把 context 路径、变量名、函数名写到这里。",
    )


class ContextRefPlanNode(StrictModel):
    type: Literal["context_ref"] = Field(description="节点类型。固定填写 `context_ref`。")
    path: str = Field(
        description="上下文变量完整路径。必须是可直接写入 DSL 的完整路径，例如 `$ctx$.billStatement.prepareId`。全局 context 使用 `$ctx$.` 前缀；不要填写 id、name、属性片段或拆分字段。",
    )


class LocalRefPlanNode(StrictModel):
    type: Literal["local_ref"] = Field(description="节点类型。固定填写 `local_ref`。")
    path: str = Field(
        description="局部上下文变量完整路径。必须是可直接写入 DSL 的完整路径，例如 `$local$.currentCycle`。这里只填写完整 path，不要填写 id、name 或属性片段。",
    )


class VarRefPlanNode(StrictModel):
    type: Literal["var_ref"] = Field(description="节点类型。固定填写 `var_ref`。")
    name: str = Field(description="变量名。仅在引用当前计划中已定义的变量时填写，例如 `customer_gender`。不要填写 context path、函数名或资源 id。")


class QueryPairPlanNode(StrictModel):
    param_name: str = Field(
        validation_alias=AliasChoices("param_name", "key", "field"),
        description="namingSQL 参数名，对应最终 DSL 中 `pair(param_name, value)` 的第一个值，例如 `OFFERING_ID`。这里只填写参数名，不要填写 id。",
    )
    value_expr: "ExprPlanNode" = Field(
        validation_alias=AliasChoices("value_expr", "value"),
        description="参数值表达式节点，对应最终 DSL 中 `pair(param_name, value)` 的第二个值。可表示 context path、变量引用、常量或函数调用结果。不要输出拼接后的 `pair(...)` 字符串。",
    )


class FunctionCallPlanNode(StrictModel):
    type: Literal["function_call"] = Field(description="节点类型。固定填写 `function_call`。")
    function_id: str = Field(default="", description="兼容 function id 输入。")
    function_name: str = Field(
        default="",
        description="函数名称，例如 `Common.Double2Str`。优先填写这个字段。这里只填写函数名，不要填写 function id、display name 或其他引用字段。",
    )
    args: List["ExprPlanNode"] = Field(
        default_factory=list,
        description="按顺序传入的函数参数表达式节点列表。每个元素只表示一个参数值本身；不要为单个参数再输出 id、name、raw_expr 等无关 key。",
    )


class QueryCallPlanNode(StrictModel):
    type: Literal["query_call"] = Field(description="节点类型。固定填写 `query_call`。")
    query_kind: Literal["select", "select_one", "fetch", "fetch_one"] = Field(
        description="查询调用类型。`select`/`select_one` 表示按 BO 查询；`fetch`/`fetch_one` 表示调用 namingSQL。",
    )
    bo_id: str = Field(default="", description="兼容 BO id 输入。")
    source_name: str = Field(
        description="查询目标名称。`select`/`select_one` 时填写 BO 名称，例如 `BB_PREP_SUB`；`fetch`/`fetch_one` 时填写 namingSQL 名称，例如 `E_RT_QUERY_BY_OFFERINGID`。这里只填写名称，不要填写 id、ref 或 display_name。",
    )
    field: str = Field(default="", description="select/select_one 兼容目标字段。")
    data_source: str = Field(default="", description="兼容数据源字段。")
    naming_sql_id: str = Field(default="", description="fetch/fetch_one 兼容 namingSQL id。")
    filter_expr: ExprPlanNode | None = Field(
        default=None,
        validation_alias=AliasChoices("filter_expr", "where"),
        description="select/select_one 的完整过滤表达式节点。推荐作为主字段填写，例如表达 `it.PREPARE_ID == $ctx$.billStatement.prepareId and it.BILL_CYCLE_ID == $ctx$.billStatement.billCycleId` 的表达式树。不要再同时输出重复的 field/operator/value 拆分字段。",
    )
    filters: List[QueryPairPlanNode] = Field(default_factory=list, validation_alias=AliasChoices("filters"))
    params: List[QueryPairPlanNode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("params", "pairs"),
        description="fetch/fetch_one 的参数列表。每个元素对应最终 DSL 中的一个 `pair(param_name, value)`。这里只填写结构化参数，不要输出拼接后的 `pair(...)` 字符串。",
    )


class IfPlanNode(StrictModel):
    type: Literal["if"] = Field(description="节点类型。固定填写 `if`。")
    condition: "ExprPlanNode" = Field(description="条件表达式节点。")
    then_expr: "ExprPlanNode" = Field(description="条件为真时返回的表达式节点。")
    else_expr: "ExprPlanNode" = Field(description="条件为假时返回的表达式节点。")


class BinaryOpPlanNode(StrictModel):
    type: Literal["binary_op"] = Field(description="节点类型。固定填写 `binary_op`。")
    operator: str = Field(description="二元运算符，例如 `==`、`and`、`+`。只填写 DSL 支持的运算符。")
    left: "ExprPlanNode" = Field(description="左侧表达式节点。")
    right: "ExprPlanNode" = Field(description="右侧表达式节点。")


class UnaryOpPlanNode(StrictModel):
    type: Literal["unary_op"] = Field(description="节点类型。固定填写 `unary_op`。")
    operator: str = Field(description="一元运算符，例如 `not`。")
    operand: "ExprPlanNode" = Field(description="一元运算的目标表达式节点。")


class FieldAccessPlanNode(StrictModel):
    type: Literal["field_access"] = Field(description="节点类型。固定填写 `field_access`。")
    base: "ExprPlanNode" = Field(description="被访问字段的基础表达式节点。")
    field: str = Field(description="字段名，例如 `amount`。这里只填写字段名本身。")


class IndexAccessPlanNode(StrictModel):
    type: Literal["index_access"] = Field(description="节点类型。固定填写 `index_access`。")
    base: "ExprPlanNode" = Field(description="被索引的基础表达式节点。")
    index: "ExprPlanNode" = Field(description="索引表达式节点。")


class ListLiteralPlanNode(StrictModel):
    type: Literal["list_literal"] = Field(description="节点类型。固定填写 `list_literal`。")
    items: List["ExprPlanNode"] = Field(default_factory=list, description="列表中的表达式节点，按顺序填写。")


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
    kind: Literal["variable"] = Field(description="定义类型。固定填写 `variable`。")
    name: str = Field(description="变量名，例如 `customer_gender`。")
    expr: ExprPlanNode = Field(description="变量的表达式节点。")


DefinitionNode = VariableDefinitionNode


class ProgramPlanLimits(StrictModel):
    max_definitions: int = Field(default=6, description="允许的最大 definitions 数量。")
    max_expr_depth_per_definition: int = Field(default=4, description="每个 definition 中表达式树的最大深度。")
    max_return_expr_depth: int = Field(default=5, description="return_expr 表达式树的最大深度。")
    max_total_expr_nodes: int = Field(default=50, description="整份计划允许的最大表达式节点数。")
    max_if_nodes_total: int = Field(default=6, description="整份计划允许的最大 if 节点数量。")


class ProgramPlan(StrictModel):
    definitions: List[DefinitionNode] = Field(default_factory=list, description="变量定义列表。没有预定义步骤时可为空数组。")
    return_expr: ExprPlanNode = Field(description="最终返回的表达式节点。")
    raw_plan: str | Dict[str, Any] | None = Field(default=None, description="原始计划文本或对象，仅用于调试与追踪。")
    diagnostics: List[PlanDiagnostic] = Field(default_factory=list, description="计划诊断信息列表，通常由系统填充。")


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
ExprNode.model_rebuild()
