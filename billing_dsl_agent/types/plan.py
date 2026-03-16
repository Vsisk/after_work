"""Environment resolution and binding models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .bo import BODef
from .common import ContextScope, QueryMode
from .context import ContextVarDef
from .function import FunctionDef


@dataclass(slots=True)
class ResolvedEnvironment:
    """Resolved runtime environment used by matching/planning."""

    global_context_vars: List[ContextVarDef] = field(default_factory=list)
    local_context_vars: List[ContextVarDef] = field(default_factory=list)
    available_bos: List[BODef] = field(default_factory=list)
    available_functions: List[FunctionDef] = field(default_factory=list)


@dataclass(slots=True)
class ContextBinding:
    """Binding entry for referenced context variable."""

    var_name: str
    scope: ContextScope
    field_name: Optional[str] = None


@dataclass(slots=True)
class BOBinding:
    """Binding entry for BO or namingSQL usage."""

    bo_name: str
    query_mode: QueryMode
    naming_sql_name: Optional[str] = None
    selected_field_names: List[str] = field(default_factory=list)


@dataclass(slots=True)
class FunctionBinding:
    """Binding entry for function usage."""

    class_name: str
    method_name: str


@dataclass(slots=True)
class MissingResource:
    """Describes an unavailable required resource."""

    resource_type: str
    resource_name: str
    reason: str


@dataclass(slots=True)
class ResourceBinding:
    """Aggregate binding result for intent against environment."""

    context_bindings: List[ContextBinding] = field(default_factory=list)
    bo_bindings: List[BOBinding] = field(default_factory=list)
    function_bindings: List[FunctionBinding] = field(default_factory=list)
    missing_resources: List[MissingResource] = field(default_factory=list)

    @property
    def is_satisfied(self) -> bool:
        return len(self.missing_resources) == 0
