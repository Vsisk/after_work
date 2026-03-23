"""DSL language specs and plan IR definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class DSLSpec:
    """Feature flags and grammar text for DSL syntax constraints."""

    version: str
    supports_method_definitions: bool = True
    supports_global_context: bool = True
    supports_local_context: bool = True
    supports_select_query: bool = True
    supports_fetch_query: bool = True
    supports_list_ops: bool = True
    supports_native_if: bool = True
    supports_exists: bool = True
    supports_nested_function_calls: bool = True
    raw_grammar_text: str = ""


class ExprKind(str, Enum):
    """Expression kinds in AST/IR plan."""

    LITERAL = "LITERAL"
    CONTEXT_REF = "CONTEXT_REF"
    LOCAL_REF = "LOCAL_REF"
    METHOD_REF = "METHOD_REF"
    FIELD_ACCESS = "FIELD_ACCESS"
    FUNCTION_CALL = "FUNCTION_CALL"
    QUERY_CALL = "QUERY_CALL"
    BINARY_OP = "BINARY_OP"
    IF_EXPR = "IF_EXPR"
    LIST_LITERAL = "LIST_LITERAL"
    INDEX_ACCESS = "INDEX_ACCESS"


@dataclass(slots=True)
class ExprNode:
    """Generic expression node for ValuePlan."""

    kind: ExprKind
    value: Any = None
    children: List["ExprNode"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MethodPlan:
    """Method definition plan node."""

    name: str
    expr: ExprNode


@dataclass(slots=True)
class ValuePlan:
    """Complete plan for one node's DSL generation."""

    target_node_path: str
    methods: List[MethodPlan] = field(default_factory=list)
    final_expr: Optional[ExprNode] = None
