from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class NodeDef:
    node_id: str
    node_path: str
    node_name: str
    data_type: str = "unknown"
    description: str = ""


@dataclass(slots=True)
class Environment:
    context_paths: List[str] = field(default_factory=list)
    bo_schema: Dict[str, List[str]] = field(default_factory=dict)
    function_schema: List[str] = field(default_factory=list)
    node_schema: Dict[str, Any] = field(default_factory=dict)
    context_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlanDraft:
    intent_summary: str
    expression_pattern: str
    context_refs: List[str] = field(default_factory=list)
    bo_refs: List[dict] = field(default_factory=list)
    function_refs: List[str] = field(default_factory=list)
    semantic_slots: Dict[str, Any] = field(default_factory=dict)
    raw_plan: Dict[str, Any] = field(default_factory=dict)


class ExprKind(str, Enum):
    LITERAL = "LITERAL"
    CONTEXT_REF = "CONTEXT_REF"
    LOCAL_REF = "LOCAL_REF"
    QUERY_CALL = "QUERY_CALL"
    FUNCTION_CALL = "FUNCTION_CALL"
    IF_EXPR = "IF_EXPR"
    BINARY_OP = "BINARY_OP"
    FIELD_ACCESS = "FIELD_ACCESS"
    LIST_LITERAL = "LIST_LITERAL"
    INDEX_ACCESS = "INDEX_ACCESS"


@dataclass(slots=True)
class ExprNode:
    kind: ExprKind
    value: Any = None
    children: List["ExprNode"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ValuePlan:
    target_node_path: str
    expr: Optional[ExprNode] = None


@dataclass(slots=True)
class ValidationResult:
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    repaired_plan: Optional[PlanDraft] = None


@dataclass(slots=True)
class GenerateDSLRequest:
    user_requirement: str
    node_def: NodeDef
    context_schema: Dict[str, Any] = field(default_factory=dict)
    bo_schema: Dict[str, List[str]] = field(default_factory=dict)
    function_schema: List[str] = field(default_factory=list)


@dataclass(slots=True)
class GenerateDSLResponse:
    success: bool
    dsl: str = ""
    plan: Optional[PlanDraft] = None
    ast: Optional[ExprNode] = None
    validation: Optional[ValidationResult] = None
    failure_reason: str = ""
