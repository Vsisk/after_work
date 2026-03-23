"""Index helpers for resource lookup in matching/planning stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Sequence

from billing_dsl_agent.types.bo import BODef, BOFieldDef, BORegistry, NamingSQLDef
from billing_dsl_agent.types.context import (
    ContextFieldDef,
    ContextPropertyDef,
    ContextRegistry,
    ContextVarDef,
)
from billing_dsl_agent.types.function import FunctionClassDef, FunctionDef, FunctionRegistry
from billing_dsl_agent.types.request_response import GenerateDSLRequest


@dataclass(slots=True)
class ContextIndex:
    """Fast lookup index for context variables and field-like paths."""

    by_name: Dict[str, ContextVarDef] = field(default_factory=dict)
    by_path: Dict[str, ContextVarDef] = field(default_factory=dict)


@dataclass(slots=True)
class BOIndex:
    """Fast lookup index for BO definitions."""

    by_name: Dict[str, BODef] = field(default_factory=dict)


@dataclass(slots=True)
class FunctionIndex:
    """Fast lookup index for function definitions."""

    by_full_name: Dict[str, FunctionDef] = field(default_factory=dict)
    by_method_name: Dict[str, List[FunctionDef]] = field(default_factory=dict)


@dataclass(slots=True)
class ResourceIndexes:
    """All lookup indexes built from normalized registries."""

    context_path_index: Dict[str, ContextPropertyDef] = field(default_factory=dict)
    context_name_index: Dict[str, List[ContextPropertyDef]] = field(default_factory=dict)
    bo_index: Dict[str, BODef] = field(default_factory=dict)
    bo_field_index: Dict[str, Dict[str, BOFieldDef]] = field(default_factory=dict)
    naming_sql_index: Dict[str, NamingSQLDef] = field(default_factory=dict)
    function_full_name_index: Dict[str, FunctionDef] = field(default_factory=dict)
    function_method_name_index: Dict[str, List[FunctionDef]] = field(default_factory=dict)


class DefaultResourceIndexService:
    """Build and query indexes used by parser/matcher/planner stages."""

    def build_from_registries(
        self,
        context_registry: ContextRegistry,
        bo_registry: BORegistry,
        function_registry: FunctionRegistry,
    ) -> ResourceIndexes:
        """Build all resource indexes from registries."""

        return ResourceIndexes(
            context_path_index=build_context_path_index(context_registry),
            context_name_index=build_context_name_index(context_registry),
            bo_index=build_bo_index(bo_registry),
            bo_field_index=build_bo_field_index(bo_registry),
            naming_sql_index=build_naming_sql_index(bo_registry),
            function_full_name_index=build_function_full_name_index(function_registry),
            function_method_name_index=build_function_method_name_index(function_registry),
        )

    @staticmethod
    def find_context_by_exact_path(indexes: ResourceIndexes, path: str) -> ContextPropertyDef | None:
        """Find one context property by exact path."""

        return indexes.context_path_index.get(path)

    @staticmethod
    def find_context_candidates_by_name(indexes: ResourceIndexes, name: str) -> List[ContextPropertyDef]:
        """Find context properties by name."""

        return list(indexes.context_name_index.get(name, []))

    @staticmethod
    def find_bo(indexes: ResourceIndexes, bo_name: str) -> BODef | None:
        """Find BO definition by name."""

        return indexes.bo_index.get(bo_name)

    @staticmethod
    def find_bo_field(indexes: ResourceIndexes, bo_name: str, field_name: str) -> BOFieldDef | None:
        """Find BO field definition by bo and field name."""

        return indexes.bo_field_index.get(bo_name, {}).get(field_name)

    @staticmethod
    def find_naming_sql(indexes: ResourceIndexes, naming_sql_name: str) -> NamingSQLDef | None:
        """Find naming sql by name."""

        return indexes.naming_sql_index.get(naming_sql_name)

    @staticmethod
    def find_function_by_full_name(indexes: ResourceIndexes, full_name: str) -> FunctionDef | None:
        """Find function by class.method full name."""

        return indexes.function_full_name_index.get(full_name)

    @staticmethod
    def find_function_candidates_by_method_name(indexes: ResourceIndexes, method_name: str) -> List[FunctionDef]:
        """Find function candidates by method name."""

        return list(indexes.function_method_name_index.get(method_name, []))


def build_context_path_index(context_registry: ContextRegistry) -> Dict[str, ContextPropertyDef]:
    """Build context path -> ContextPropertyDef index for global/local trees."""

    path_index: Dict[str, ContextPropertyDef] = {}
    _walk_context_tree(context_registry.global_root, "$ctx$", path_index, None)
    for local_root in context_registry.local_roots or []:
        _walk_context_tree(local_root, "$local$", path_index, None)
    return path_index


def build_context_name_index(context_registry: ContextRegistry) -> Dict[str, List[ContextPropertyDef]]:
    """Build context property-name -> candidates index."""

    name_index: Dict[str, List[ContextPropertyDef]] = {}
    _walk_context_tree(context_registry.global_root, "$ctx$", None, name_index)
    for local_root in context_registry.local_roots or []:
        _walk_context_tree(local_root, "$local$", None, name_index)
    return name_index


def _walk_context_tree(
    node: ContextPropertyDef | None,
    prefix: str,
    path_index: Dict[str, ContextPropertyDef] | None,
    name_index: Dict[str, List[ContextPropertyDef]] | None,
) -> None:
    """Walk context tree and collect path/name indexes."""

    if node is None:
        return

    node_name = (node.name or "").strip()
    current_path = f"{prefix}.{node_name}" if node_name else prefix

    if path_index is not None:
        path_index[current_path] = node

    if name_index is not None and node_name:
        name_index.setdefault(node_name, []).append(node)

    for child in node.children or []:
        _walk_context_tree(child, current_path, path_index, name_index)


def build_bo_index(bo_registry: BORegistry) -> Dict[str, BODef]:
    """Build BO name -> BODef index."""

    index: Dict[str, BODef] = {}
    for bo in _iter_bos(bo_registry):
        bo_name = (bo.name or "").strip()
        if bo_name:
            index[bo_name] = bo
    return index


def build_bo_field_index(bo_registry: BORegistry) -> Dict[str, Dict[str, BOFieldDef]]:
    """Build BO name -> field name -> BOFieldDef index."""

    field_index: Dict[str, Dict[str, BOFieldDef]] = {}
    for bo in _iter_bos(bo_registry):
        bo_name = (bo.name or "").strip()
        if not bo_name:
            continue
        inner: Dict[str, BOFieldDef] = {}
        for field_def in bo.fields or []:
            field_name = (field_def.name or "").strip()
            if field_name:
                inner[field_name] = field_def
        field_index[bo_name] = inner
    return field_index


def build_naming_sql_index(bo_registry: BORegistry) -> Dict[str, NamingSQLDef]:
    """Build namingSQL name -> NamingSQLDef index."""

    naming_sql_index: Dict[str, NamingSQLDef] = {}
    for bo in _iter_bos(bo_registry):
        naming_sqls = bo.query_capability.naming_sqls if bo.query_capability else []
        for naming_sql in naming_sqls or []:
            name = (naming_sql.name or "").strip()
            if not name:
                continue
            # Keep first on duplicate names; could be extended to List[NamingSQLDef] index later.
            naming_sql_index.setdefault(name, naming_sql)
    return naming_sql_index


def _iter_bos(bo_registry: BORegistry) -> Iterable[BODef]:
    """Yield all BOs in a registry."""

    return [*(bo_registry.system_bos or []), *(bo_registry.custom_bos or [])]


def build_function_full_name_index(function_registry: FunctionRegistry) -> Dict[str, FunctionDef]:
    """Build function full_name -> FunctionDef index."""

    index: Dict[str, FunctionDef] = {}
    for fn in _iter_functions(function_registry):
        full_name = (fn.full_name or "").strip()
        if full_name:
            index[full_name] = fn
    return index


def build_function_method_name_index(function_registry: FunctionRegistry) -> Dict[str, List[FunctionDef]]:
    """Build function method_name -> FunctionDef[] candidates index."""

    index: Dict[str, List[FunctionDef]] = {}
    for fn in _iter_functions(function_registry):
        method_name = (fn.method_name or "").strip()
        if method_name:
            index.setdefault(method_name, []).append(fn)
    return index


def _iter_functions(function_registry: FunctionRegistry) -> Iterable[FunctionDef]:
    """Yield all functions across native and predefined classes."""

    classes = [*(function_registry.native_classes or []), *(function_registry.predefined_classes or [])]
    for cls in classes:
        for fn in cls.functions or []:
            yield fn


def build_resource_indexes_from_request(request: GenerateDSLRequest) -> ResourceIndexes:
    """Build resource indexes from request payload with lightweight adapters."""

    return DefaultResourceIndexService().build_from_registries(
        context_registry=_build_context_registry_from_request(request),
        bo_registry=BORegistry(system_bos=list(request.available_bos or []), custom_bos=[]),
        function_registry=_build_function_registry_from_request(request.available_functions or []),
    )


def _build_context_registry_from_request(request: GenerateDSLRequest) -> ContextRegistry:
    """Adapt flat request context vars into ContextRegistry."""

    global_root = ContextPropertyDef(
        id="request_global_root",
        name="",
        scope="global",
        children=[_context_var_to_property(var) for var in request.global_context_vars or []],
    )
    local_roots = [_context_var_to_property(var) for var in request.local_context_vars or []]
    return ContextRegistry(global_root=global_root, local_roots=local_roots)


def _context_var_to_property(var: ContextVarDef) -> ContextPropertyDef:
    """Convert ContextVarDef to tree node used by ContextRegistry."""

    return ContextPropertyDef(
        id=var.name,
        name=var.name,
        description=var.description,
        scope=var.scope.value,
        value_type=var.data_type.value,
        nullable=var.nullable,
        children=[_context_field_to_property(field) for field in var.fields or []],
        metadata={"from_context_var": var},
    )


def _context_field_to_property(field: ContextFieldDef) -> ContextPropertyDef:
    """Convert ContextFieldDef to ContextPropertyDef child node."""

    return ContextPropertyDef(
        id=field.name,
        name=field.name,
        description=field.description,
        value_type=field.data_type.value,
        nullable=field.nullable,
    )


def _build_function_registry_from_request(functions: Sequence[FunctionDef]) -> FunctionRegistry:
    """Adapt flat request functions into FunctionRegistry."""

    class_map: Dict[str, FunctionClassDef] = {}
    for fn in functions:
        class_name = (fn.class_name or "").strip()
        if class_name not in class_map:
            class_map[class_name] = FunctionClassDef(name=class_name, functions=[])
        class_map[class_name].functions.append(fn)
    return FunctionRegistry(native_classes=list(class_map.values()), predefined_classes=[])


# Legacy compatibility helpers for existing matcher/tests using flat resources.
def build_context_index_from_vars(context_vars: Iterable[ContextVarDef]) -> ContextIndex:
    """Build legacy ContextIndex from flat ContextVarDef list."""

    by_name: Dict[str, ContextVarDef] = {}
    by_path: Dict[str, ContextVarDef] = {}
    for var in context_vars:
        by_name[var.name] = var
        by_path[var.name] = var
        for field_def in var.fields:
            by_path[f"{var.name}.{field_def.name}"] = var
    return ContextIndex(by_name=by_name, by_path=by_path)


def build_bo_index_from_list(bos: Iterable[BODef]) -> BOIndex:
    """Build legacy BOIndex from flat BODef list."""

    return BOIndex(by_name={bo.name: bo for bo in bos})


def build_function_index(functions: Iterable[FunctionDef]) -> FunctionIndex:
    """Build legacy FunctionIndex from flat FunctionDef list."""

    by_full_name: Dict[str, FunctionDef] = {}
    by_method_name: Dict[str, List[FunctionDef]] = {}
    for fn in functions:
        by_full_name[fn.full_name] = fn
        by_method_name.setdefault(fn.method_name, []).append(fn)
    return FunctionIndex(by_full_name=by_full_name, by_method_name=by_method_name)
