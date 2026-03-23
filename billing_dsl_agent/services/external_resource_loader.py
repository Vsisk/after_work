"""Load and convert external resource payloads into runtime resource lists."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from billing_dsl_agent.normalize.bo_normalizer import normalize_bo_registry
from billing_dsl_agent.normalize.context_normalizer import normalize_context_registry
from billing_dsl_agent.normalize.function_normalizer import normalize_function_registry
from billing_dsl_agent.types.bo import BODef
from billing_dsl_agent.types.common import ContextScope, DSLDataType
from billing_dsl_agent.types.context import ContextFieldDef, ContextPropertyDef, ContextVarDef
from billing_dsl_agent.types.function import FunctionDef

PayloadSource = Mapping[str, Any] | Callable[[], Mapping[str, Any] | None] | None


def load_context(payload: PayloadSource) -> tuple[list[ContextVarDef], list[ContextVarDef]]:
    """Load latest context payload and convert to global/local runtime var lists."""

    raw_payload = _resolve_payload(payload)
    registry = normalize_context_registry(raw_payload)

    global_vars = [_property_tree_to_context_var(registry.global_root, ContextScope.GLOBAL)]
    local_vars = [_property_tree_to_context_var(item, ContextScope.LOCAL) for item in registry.local_roots]
    return global_vars, local_vars


def load_bo(payload: PayloadSource) -> list[BODef]:
    """Load latest BO payload and merge system/custom registries into runtime BO list."""

    raw_payload = _resolve_payload(payload)
    registry = normalize_bo_registry(raw_payload)
    return [*registry.system_bos, *registry.custom_bos]


def load_function(payload: PayloadSource) -> list[FunctionDef]:
    """Load latest function payload and merge native/predefined registries into runtime function list."""

    raw_payload = _resolve_payload(payload)
    registry = normalize_function_registry(raw_payload)

    merged_classes = [*registry.native_classes, *registry.predefined_classes]
    runtime_functions: list[FunctionDef] = []
    for cls in merged_classes:
        runtime_functions.extend(cls.functions)
    return runtime_functions


def _resolve_payload(payload: PayloadSource) -> dict[str, Any]:
    """Resolve payload from static mapping or callable hook without caching."""

    if callable(payload):
        payload = payload()

    if not isinstance(payload, Mapping):
        return {}

    return dict(payload)


def _property_tree_to_context_var(root: ContextPropertyDef, scope: ContextScope) -> ContextVarDef:
    return ContextVarDef(
        name=root.name,
        scope=scope,
        data_type=_to_dsl_data_type(root.value_type),
        description=root.description,
        nullable=root.nullable,
        fields=_flatten_context_fields(root),
    )


def _flatten_context_fields(root: ContextPropertyDef) -> list[ContextFieldDef]:
    fields: list[ContextFieldDef] = []

    def walk(node: ContextPropertyDef, prefix: str = "") -> None:
        for child in node.children:
            if not child.name:
                continue
            field_name = f"{prefix}.{child.name}" if prefix else child.name
            fields.append(
                ContextFieldDef(
                    name=field_name,
                    data_type=_to_dsl_data_type(child.value_type),
                    description=child.description,
                    nullable=child.nullable,
                )
            )
            walk(child, prefix=field_name)

    walk(root)
    return fields


def _to_dsl_data_type(raw_value_type: str | None) -> DSLDataType:
    normalized = (raw_value_type or "").strip()
    if not normalized:
        return DSLDataType.UNKNOWN

    upper = normalized.upper()
    value_map = {item.value: item for item in DSLDataType}
    if upper in value_map:
        return value_map[upper]

    heuristic_map = {
        "STR": DSLDataType.STRING,
        "CHAR": DSLDataType.STRING,
        "TEXT": DSLDataType.STRING,
        "LONG": DSLDataType.NUMBER,
        "INT": DSLDataType.NUMBER,
        "DOUBLE": DSLDataType.NUMBER,
        "FLOAT": DSLDataType.NUMBER,
        "DECIMAL": DSLDataType.NUMBER,
        "BOOL": DSLDataType.BOOLEAN,
        "DATE": DSLDataType.DATE,
        "TIME": DSLDataType.DATETIME,
        "LIST": DSLDataType.LIST,
        "ARRAY": DSLDataType.LIST,
        "OBJECT": DSLDataType.OBJECT,
        "BO": DSLDataType.OBJECT,
        "LOGIC": DSLDataType.OBJECT,
    }
    for probe, data_type in heuristic_map.items():
        if probe in upper:
            return data_type

    return DSLDataType.UNKNOWN
