from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class ContextPropertyDef:
    id: str = ""
    name: str = ""
    description: str = ""
    allow_modify: bool = False
    value_type: str = ""
    children: List["ContextPropertyDef"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedContextNode:
    resource_id: str
    context_kind: str
    source_context_id: str
    property_name: str
    annotation: str
    access_path: str
    parent_resource_id: str
    depth: int
    return_data_type: str
    return_data_type_name: str
    is_list: bool
    is_leaf: bool
    is_expandable: bool
    child_ids: List[str] = field(default_factory=list)
    source_type: str = ""
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextRegistry:
    global_root: Optional[ContextPropertyDef] = None
    local_roots: List[ContextPropertyDef] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    nodes_by_id: Dict[str, NormalizedContextNode] = field(default_factory=dict)
    nodes_by_access_path: Dict[str, NormalizedContextNode] = field(default_factory=dict)
    descendants_by_root_context: Dict[str, List[str]] = field(default_factory=dict)
    roots_by_context_kind: Dict[str, str] = field(default_factory=dict)
