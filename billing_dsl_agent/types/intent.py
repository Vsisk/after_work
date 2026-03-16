"""Intent layer models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List

from .common import DSLDataType


class IntentSourceType(str, Enum):
    """Source categories inferred from requirements."""

    CONTEXT = "CONTEXT"
    LOCAL_CONTEXT = "LOCAL_CONTEXT"
    BO_QUERY = "BO_QUERY"
    NAMING_SQL = "NAMING_SQL"
    FUNCTION = "FUNCTION"
    LITERAL = "LITERAL"
    EXPRESSION = "EXPRESSION"
    LIST_OP = "LIST_OP"
    CONDITIONAL = "CONDITIONAL"


@dataclass(slots=True)
class OperationIntent:
    """Operation-level intent hint."""

    op_type: str
    description: str
    expected_inputs: List[str] = field(default_factory=list)


@dataclass(slots=True)
class NodeIntent:
    """Structured intent for a target node."""

    raw_requirement: str
    target_node_path: str
    target_node_name: str
    target_data_type: DSLDataType
    source_types: List[IntentSourceType] = field(default_factory=list)
    operations: List[OperationIntent] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
