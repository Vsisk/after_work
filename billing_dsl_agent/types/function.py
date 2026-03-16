"""Function metadata models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class FunctionTypeRef:
    """Type reference for function signatures."""

    kind: str
    name: str
    is_list: bool = False


@dataclass(slots=True)
class FunctionParamDef:
    """Function parameter definition."""

    name: str
    type: FunctionTypeRef
    description: str = ""
    required: bool = True


@dataclass(slots=True)
class FunctionDef:
    """Function definition from native/predefined registries."""

    id: Optional[str]
    class_name: str
    method_name: str
    description: str = ""
    scope: str = "global"
    params: List[FunctionParamDef] = field(default_factory=list)
    return_type: Optional[FunctionTypeRef] = None
    is_native: bool = False
    need_import: bool = False
    import_path: Optional[str] = None
    func_so: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.class_name}.{self.method_name}" if self.class_name else self.method_name


@dataclass(slots=True)
class FunctionClassDef:
    """Function class/grouping definition."""

    name: str
    description: str = ""
    functions: List[FunctionDef] = field(default_factory=list)


@dataclass(slots=True)
class FunctionRegistry:
    """Function registry including native and predefined function classes."""

    native_classes: List[FunctionClassDef] = field(default_factory=list)
    predefined_classes: List[FunctionClassDef] = field(default_factory=list)
