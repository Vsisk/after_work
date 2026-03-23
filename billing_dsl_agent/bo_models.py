from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True)
class TypeRef:
    is_list: bool = False
    data_type: str = ""
    data_type_name: str = ""


@dataclass(slots=True)
class ParameterDef:
    name: str = ""
    type_ref: TypeRef = field(default_factory=TypeRef)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NamingSQLDef:
    id: str = ""
    name: str = ""
    label: str = ""
    description: str = ""
    sql: str = ""
    params: List[ParameterDef] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BOQueryCapability:
    naming_sqls: List[NamingSQLDef] = field(default_factory=list)


@dataclass(slots=True)
class RwRuleTerm:
    rw_rule_id: str = ""
    app_scene: str = ""
    read_or_mapping_id: str = ""
    insert_or_mapping_id: str = ""
    update_or_mapping_id: str = ""
    delete_or_mapping_id: str = ""


@dataclass(slots=True)
class BOFieldDef:
    name: str = ""
    description: str = ""
    type_ref: TypeRef = field(default_factory=TypeRef)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BODef:
    bo_name: str = ""
    description: str = ""
    fields: List[BOFieldDef] = field(default_factory=list)
    query_capability: BOQueryCapability = field(default_factory=BOQueryCapability)
    rw_rule_list: List[RwRuleTerm] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BORegistry:
    system_bos: List[BODef] = field(default_factory=list)
    custom_bos: List[BODef] = field(default_factory=list)

    def all_bos(self) -> List[BODef]:
        return [*self.system_bos, *self.custom_bos]
