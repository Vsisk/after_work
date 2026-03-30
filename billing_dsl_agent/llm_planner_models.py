from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from billing_dsl_agent.models import (
    ExprPlanNode,
    NodeDef,
    PlanDiagnostic,
    ProgramPlanLimits,
    StrictModel,
    VariableDefinitionNode,
)


class AllowedNodeType(str, Enum):
    LITERAL = "literal"
    CONTEXT_REF = "context_ref"
    LOCAL_REF = "local_ref"
    VAR_REF = "var_ref"
    QUERY_CALL = "query_call"
    FUNCTION_CALL = "function_call"
    IF = "if"
    BINARY_OP = "binary_op"
    UNARY_OP = "unary_op"
    FIELD_ACCESS = "field_access"
    INDEX_ACCESS = "index_access"
    LIST_LITERAL = "list_literal"


class ReturnShape(str, Enum):
    LITERAL_VALUE = "literal_value"
    DIRECT_REF = "direct_ref"
    QUERY_RESULT = "query_result"
    FUNCTION_RESULT = "function_result"
    CONDITIONAL_RESULT = "conditional_result"
    LIST_RESULT = "list_result"
    OBJECT_FIELD = "object_field"
    UNKNOWN = "unknown"


class ComplexityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AllowedQueryKind(str, Enum):
    SELECT_ONE = "select_one"
    FETCH_ONE = "fetch_one"
    SELECT = "select"
    FETCH = "fetch"


class DefinitionKind(str, Enum):
    VARIABLE = "variable"


class ResourceRefTerm(StrictModel):
    resource_id: str
    ref: str
    label: str = ""
    description: str = ""
    category: str = ""


class BOSelectionTerm(StrictModel):
    bo_id: str
    bo_name: str
    field_ids: list[str] = Field(default_factory=list)
    naming_sql_ids: list[str] = Field(default_factory=list)
    data_source: str = ""
    available_query_kinds: list[AllowedQueryKind] = Field(default_factory=list)


class DefinitionHintTerm(StrictModel):
    name: str
    purpose: str
    suggested_source: str = ""
    reuse_in_return_expr: bool = False


class FieldConstraintTerm(StrictModel):
    field_path: str
    required: bool = True
    description: str = ""
    allowed_values: list[str] = Field(default_factory=list)
    max_items: int | None = None


class BasePlanInput(StrictModel):
    user_query: str
    node_info: NodeDef
    candidate_contexts: list[ResourceRefTerm] = Field(default_factory=list)
    candidate_bos: list[BOSelectionTerm] = Field(default_factory=list)
    candidate_functions: list[ResourceRefTerm] = Field(default_factory=list)
    planner_runtime_limits: ProgramPlanLimits = Field(default_factory=ProgramPlanLimits)
    legacy_hints: dict[str, Any] = Field(default_factory=dict)


class BasePlanResources(StrictModel):
    context_refs: list[str] = Field(default_factory=list)
    bo_refs: list[BOSelectionTerm] = Field(default_factory=list)
    function_refs: list[str] = Field(default_factory=list)


class BasePlanShape(StrictModel):
    needs_definitions: bool = False
    needs_query: bool = False
    needs_condition: bool = False
    needs_function_call: bool = False
    estimated_complexity: ComplexityLevel = ComplexityLevel.LOW
    preferred_query_kinds: list[AllowedQueryKind] = Field(default_factory=list)


class BasePlan(StrictModel):
    goal: str
    required_resources: BasePlanResources = Field(default_factory=BasePlanResources)
    plan_shape: BasePlanShape = Field(default_factory=BasePlanShape)
    allowed_node_types: list[AllowedNodeType] = Field(default_factory=list)
    return_shape: ReturnShape = ReturnShape.UNKNOWN
    definition_hints: list[DefinitionHintTerm] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
    raw_reasoning_summary: str | None = None


class FilteredPlanSpecInput(StrictModel):
    base_plan: BasePlan
    planner_limits: ProgramPlanLimits = Field(default_factory=ProgramPlanLimits)
    global_supported_node_types: list[AllowedNodeType] = Field(default_factory=list)
    global_supported_query_kinds: list[AllowedQueryKind] = Field(default_factory=list)


class FilteredPlanSpec(StrictModel):
    allowed_definition_kinds: list[DefinitionKind] = Field(default_factory=list)
    allowed_node_types: list[AllowedNodeType] = Field(default_factory=list)
    allowed_query_kinds: list[AllowedQueryKind] = Field(default_factory=list)
    allow_definitions: bool = False
    max_definitions: int = 0
    max_expr_depth_per_definition: int = 0
    max_return_expr_depth: int = 0
    max_total_expr_nodes: int = 0
    allowed_return_shapes: list[ReturnShape] = Field(default_factory=list)
    field_constraints: list[FieldConstraintTerm] = Field(default_factory=list)
    example_output_skeleton: dict[str, Any] = Field(default_factory=dict)
    final_plan_schema_version: str = "final-plan-v1"
    allowed_binary_operators: list[str] = Field(default_factory=list)
    allowed_unary_operators: list[str] = Field(default_factory=list)


class FilteredResourceBundle(StrictModel):
    context_refs: list[ResourceRefTerm] = Field(default_factory=list)
    bo_refs: list[BOSelectionTerm] = Field(default_factory=list)
    function_refs: list[ResourceRefTerm] = Field(default_factory=list)


class FinalPlanInput(StrictModel):
    user_query: str
    node_info: NodeDef
    base_plan: BasePlan
    filtered_spec: FilteredPlanSpec
    filtered_resources: FilteredResourceBundle = Field(default_factory=FilteredResourceBundle)
    runtime_limits: ProgramPlanLimits = Field(default_factory=ProgramPlanLimits)


class InternalFinalPlan(StrictModel):
    definitions: list[VariableDefinitionNode] = Field(default_factory=list)
    return_expr: ExprPlanNode
    raw_plan: dict[str, Any] | None = None
    diagnostics: list[PlanDiagnostic] = Field(default_factory=list)


class StageError(StrictModel):
    stage_name: str
    prompt_key: str
    prompt_version: str
    raw_output: dict[str, Any] | None = None
    parse_error: str = ""
    validation_error: str = ""
    retry_count: int = 0


class PlannerDiagnostics(StrictModel):
    stage_trace: list[str] = Field(default_factory=list)
    stage_errors: list[StageError] = Field(default_factory=list)
