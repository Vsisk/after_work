"""Context definitions for environment and normalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .common import ContextScope, DSLDataType


@dataclass(slots=True)
class ContextFieldDef:
    """Flat context field metadata."""

    name: str
    data_type: DSLDataType = DSLDataType.UNKNOWN
    description: str = ""
    nullable: bool = True


@dataclass(slots=True)
class ContextVarDef:
    """Context variable available to DSL generation."""

    name: str
    scope: ContextScope
    data_type: DSLDataType = DSLDataType.UNKNOWN
    description: str = ""
    nullable: bool = True
    fields: List[ContextFieldDef] = field(default_factory=list)
    inherited_from: Optional[str] = None


@dataclass(slots=True)
class ContextPropertyDef:
    """Raw tree-like context structure used in normalization layer."""

    id: str
    name: str
    description: str = ""
    scope: str = "global"
    property_type: str = "basic"
    value_type: Optional[str] = None
    allow_modify: bool = False
    nullable: bool = True
    cdsl: str = ""
    children: List["ContextPropertyDef"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextRegistry:
    """Normalized registry for global/local context trees."""

    global_root: ContextPropertyDef
    local_roots: List[ContextPropertyDef] = field(default_factory=list)
