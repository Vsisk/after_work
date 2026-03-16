"""BO and namingSQL definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .common import ParameterDef, TypeRef


@dataclass(slots=True)
class BOFieldDef:
    """Field metadata for BO object."""

    name: str
    type: TypeRef
    description: str = ""
    nullable: bool = True


@dataclass(slots=True)
class NamingSQLDef:
    """Definition for namingSQL resources."""

    id: str
    name: str
    label: str = ""
    description: str = ""
    sql: str = ""
    params: List[ParameterDef] = field(default_factory=list)
    returns_list: bool = True
    is_customized: bool = False
    is_sync: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BOQueryCapability:
    """Query capabilities for a BO."""

    supports_select: bool = True
    supports_select_one: bool = True
    naming_sqls: List[NamingSQLDef] = field(default_factory=list)


@dataclass(slots=True)
class BODef:
    """Business Object definition."""

    id: Optional[str]
    name: str
    description: str = ""
    source: str = "system"
    is_virtual: bool = False
    fields: List[BOFieldDef] = field(default_factory=list)
    query_capability: BOQueryCapability = field(default_factory=BOQueryCapability)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BORegistry:
    """Grouped BO registry."""

    system_bos: List[BODef] = field(default_factory=list)
    custom_bos: List[BODef] = field(default_factory=list)
