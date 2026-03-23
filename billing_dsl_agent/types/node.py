"""Node metadata definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .common import DSLDataType


@dataclass(slots=True)
class NodeDef:
    """Target XML node definition for DSL generation."""

    node_id: str
    node_path: str
    node_name: str
    data_type: DSLDataType = DSLDataType.UNKNOWN
    description: str = ""
    parent_node_path: Optional[str] = None
    required: bool = False
