"""Context normalization placeholders."""

from __future__ import annotations

from typing import Any

from billing_dsl_agent.types.context import ContextPropertyDef, ContextRegistry


def normalize_context_registry(raw_context_data: dict[str, Any]) -> ContextRegistry:
    """Normalize raw context payload into ContextRegistry."""

    raw_context_data = raw_context_data or {}

    global_raw = raw_context_data.get("global_context")
    if not isinstance(global_raw, dict):
        global_raw = raw_context_data if isinstance(raw_context_data, dict) else {}
    global_root = _normalize_property_tree(global_raw, scope="global")

    local_candidates = raw_context_data.get("local_contexts") or raw_context_data.get("local_context") or []
    if isinstance(local_candidates, dict):
        local_candidates = [local_candidates]
    local_roots = [
        _normalize_property_tree(item, scope="local")
        for item in local_candidates
        if isinstance(item, dict)
    ]

    return ContextRegistry(global_root=global_root, local_roots=local_roots)


def _normalize_property_tree(raw_node: dict[str, Any], scope: str) -> ContextPropertyDef:
    raw_node = raw_node or {}

    value_type, return_meta = _extract_return_type(raw_node)
    sql_query = _extract_sql_query(raw_node)
    children = _normalize_children(raw_node, scope)

    property_type = str(raw_node.get("property_type", "basic") or "basic")
    value_source_type = str(raw_node.get("value_source_type", "") or "")

    cdsl_value = raw_node.get("cdsl")
    expression_value = raw_node.get("expression")

    metadata: dict[str, Any] = {
        "raw": raw_node,
        "raw_property_type": raw_node.get("property_type"),
        "raw_value_source_type": raw_node.get("value_source_type"),
        "raw_return_is_list": return_meta.get("raw_return_is_list"),
        "raw_return_data_type": return_meta.get("raw_return_data_type"),
        "raw_return_data_type_name": return_meta.get("raw_return_data_type_name"),
    }
    if sql_query is not None:
        metadata["sql_query"] = sql_query
        metadata["raw_sql_query"] = sql_query
    if expression_value is not None:
        metadata["expression"] = expression_value
    if cdsl_value is not None:
        metadata["cdsl"] = cdsl_value

    return ContextPropertyDef(
        id=str(raw_node.get("property_id", raw_node.get("id", ""))),
        name=str(raw_node.get("property_name", raw_node.get("name", ""))),
        description=str(raw_node.get("annotation", raw_node.get("description", ""))),
        scope=str(raw_node.get("scope", scope)),
        property_type=property_type,
        value_type=value_type,
        allow_modify=bool(raw_node.get("allow_modify", False)),
        nullable=bool(raw_node.get("nullable", True)),
        cdsl=str(cdsl_value) if cdsl_value is not None else "",
        expression=str(expression_value) if expression_value is not None else "",
        value_source_type=value_source_type,
        children=children,
        metadata=metadata,
    )


def _normalize_children(raw_node: dict[str, Any], scope: str) -> list[ContextPropertyDef]:
    sub_properties = raw_node.get("sub_properties") or []
    return_sub_properties = raw_node.get("return_sub_properties") or []
    merged_children = [*sub_properties, *return_sub_properties]
    return [
        _normalize_property_tree(child, scope)
        for child in merged_children
        if isinstance(child, dict)
    ]


def _extract_return_type(raw_node: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    return_type = raw_node.get("return_type")
    if not isinstance(return_type, dict):
        return_type = {}

    raw_return_data_type = return_type.get("data_type", raw_node.get("data_type"))
    raw_return_data_type_name = return_type.get("data_type_name", raw_node.get("data_type_name"))
    raw_return_is_list = return_type.get("is_list", raw_node.get("is_list"))

    value_type = None
    if raw_return_data_type_name not in (None, ""):
        value_type = str(raw_return_data_type_name)
    elif raw_return_data_type not in (None, ""):
        value_type = str(raw_return_data_type)

    return value_type, {
        "raw_return_is_list": raw_return_is_list,
        "raw_return_data_type": raw_return_data_type,
        "raw_return_data_type_name": raw_return_data_type_name,
    }


def _extract_sql_query(raw_node: dict[str, Any]) -> dict[str, Any] | None:
    raw_sql_query = raw_node.get("sql_query")
    if not isinstance(raw_sql_query, dict):
        return None
    return {
        "bo_name": raw_sql_query.get("bo_name"),
        "naming_sql": raw_sql_query.get("naming_sql"),
        "sql_conditions": raw_sql_query.get("sql_conditions") or [],
    }
