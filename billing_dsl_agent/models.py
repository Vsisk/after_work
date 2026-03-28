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
class BOResource:
    resource_id: str
    bo_name: str
    field_ids: List[str] = field(default_factory=list)
    data_source: str = ""
    naming_sql_ids: List[str] = field(default_factory=list)
    naming_sql_name_by_key: Dict[str, str] = field(default_factory=dict)
    naming_sql_param_names_by_key: Dict[str, List[str]] = field(default_factory=dict)
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
    function_registry: "FunctionRegistry" | None = None
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
class FunctionRegistry:
    functions_by_id: Dict[str, FunctionResource] = field(default_factory=dict)


@dataclass(slots=True)
class FilteredEnvironment:
    registry: ResourceRegistry
    selected_global_context_ids: List[str] = field(default_factory=list)
    selected_local_context_ids: List[str] = field(default_factory=list)
    selected_bo_ids: List[str] = field(default_factory=list)
    selected_function_ids: List[str] = field(default_factory=list)


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


class LiteralPlanNode(StrictModel):
    type: Literal["literal"]
    value: Any = None


class ContextRefPlanNode(StrictModel):
    type: Literal["context_ref"]
    path: str


class LocalRefPlanNode(StrictModel):
    type: Literal["local_ref"]
    path: str


class VarRefPlanNode(StrictModel):
    type: Literal["var_ref"]
    name: str


class QueryFilterPlanNode(StrictModel):
    field: str
    value: "ExprPlanNode"


class QueryPairPlanNode(StrictModel):
    key: str
    value: "ExprPlanNode"


class FunctionCallPlanNode(StrictModel):
    type: Literal["function_call"]
    function_name: str | None = None
    function_id: str | None = None
    args: List["ExprPlanNode"] = Field(default_factory=list)


class QueryCallPlanNode(StrictModel):
    type: Literal["query_call"]
    query_kind: Literal["select", "select_one", "fetch", "fetch_one"]
    source_name: str
    field: str | None = None
    bo_id: str | None = None
    data_source: str | None = None
    naming_sql_id: str | None = None
    filters: List[QueryFilterPlanNode] = Field(default_factory=list)
    where: "ExprPlanNode" | None = None
    pairs: List[QueryPairPlanNode] = Field(default_factory=list)


class IfPlanNode(StrictModel):
    type: Literal["if"]
    condition: "ExprPlanNode"
    then_expr: "ExprPlanNode"
    else_expr: "ExprPlanNode"


class BinaryOpPlanNode(StrictModel):
    type: Literal["binary_op"]
    operator: str
    left: "ExprPlanNode"
    right: "ExprPlanNode"


class UnaryOpPlanNode(StrictModel):
    type: Literal["unary_op"]
    operator: str
    operand: "ExprPlanNode"


class FieldAccessPlanNode(StrictModel):
    type: Literal["field_access"]
    base: "ExprPlanNode"
    field: str


class IndexAccessPlanNode(StrictModel):
    type: Literal["index_access"]
    base: "ExprPlanNode"
    index: "ExprPlanNode"


class ListLiteralPlanNode(StrictModel):
    type: Literal["list_literal"]
    items: List["ExprPlanNode"] = Field(default_factory=list)


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
