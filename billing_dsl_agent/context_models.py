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
class ContextRegistry:
    global_root: Optional[ContextPropertyDef] = None
    local_roots: List[ContextPropertyDef] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
