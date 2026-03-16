"""Common enums and shared value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class DSLDataType(str, Enum):
    """Supported DSL-oriented data types for node/context/function metadata."""

    STRING = "STRING"
    MONEY = "MONEY"
    DATE = "DATE"
    DATETIME = "DATETIME"
    SIMPLE_STRING = "SIMPLE_STRING"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    OBJECT = "OBJECT"
    LIST = "LIST"
    UNKNOWN = "UNKNOWN"


class ContextScope(str, Enum):
    """Context variable scope."""

    GLOBAL = "GLOBAL"
    LOCAL = "LOCAL"


class QueryMode(str, Enum):
    """Supported query modes in DSL query calls."""

    SELECT = "SELECT"
    SELECT_ONE = "SELECT_ONE"
    FETCH = "FETCH"
    FETCH_ONE = "FETCH_ONE"


@dataclass(slots=True)
class TypeRef:
    """Data type reference for BO schema components."""

    kind: str
    name: str
    is_list: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParameterDef:
    """Parameter definition for namingSQL or other typed signatures."""

    name: str
    type: TypeRef
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MethodDef:
    """Rendered method definition in final DSL output."""

    name: str
    body: str


@dataclass(slots=True)
class GeneratedDSL:
    """Rendered DSL document with method definitions and final value expression."""

    methods: List[MethodDef] = field(default_factory=list)
    value_expression: str = ""

    def to_text(self) -> str:
        lines = [f"def {m.name}: {m.body}" for m in self.methods]
        lines.append(self.value_expression)
        return "\n".join(lines)


@dataclass(slots=True)
class StructuredExplanation:
    """Structured explanation for generated plan and resulting DSL."""

    intent_summary: str
    used_context_vars: List[str] = field(default_factory=list)
    used_local_vars: List[str] = field(default_factory=list)
    used_bos: List[str] = field(default_factory=list)
    used_naming_sqls: List[str] = field(default_factory=list)
    used_functions: List[str] = field(default_factory=list)
    method_summaries: List[str] = field(default_factory=list)
    final_expression_summary: str = ""


__all__ = [
    "DSLDataType",
    "ContextScope",
    "QueryMode",
    "TypeRef",
    "ParameterDef",
    "MethodDef",
    "GeneratedDSL",
    "StructuredExplanation",
]
