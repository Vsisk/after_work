from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from billing_dsl_agent.context_models import ContextPropertyDef, ContextRegistry


def load_context_registry_from_json(data: Dict[str, Any]) -> ContextRegistry:
    payload = data if isinstance(data, dict) else {}
    global_root = _normalize_node(_resolve_global_context(payload.get("global_context")))
    if global_root is None:
        global_root = ContextPropertyDef(
            id="",
            name="",
            description="",
            allow_modify=False,
            value_type="",
            children=[],
            metadata={"raw_property_type": "", "raw_value_source_type": "sub_property_wise"},
        )

    sub_global_nodes = _normalize_sub_global(payload.get("sub_global_context"))
    for node in sub_global_nodes:
        node.metadata["is_sub_global_context"] = True
    global_root.children.extend(sub_global_nodes)

    return ContextRegistry(
        global_root=global_root,
        local_roots=sub_global_nodes,
        metadata={"version": _as_text(payload.get("version"))},
    )


def _resolve_global_context(raw_global: Any) -> Dict[str, Any]:
    if not isinstance(raw_global, dict):
        return {}

    if "custom_context" not in raw_global and "system_context" not in raw_global:
        return raw_global

    custom_context = raw_global.get("custom_context")
    system_context = raw_global.get("system_context")
    custom_payload = custom_context if isinstance(custom_context, dict) else {}
    system_payload = system_context if isinstance(system_context, dict) else {}

    merged_sub_properties: List[Dict[str, Any]] = []
    for item in custom_payload.get("sub_properties") or []:
        if isinstance(item, dict):
            merged_sub_properties.append(item)
    for item in system_payload.get("sub_properties") or []:
        if isinstance(item, dict):
            merged_sub_properties.append(item)

    base = custom_payload or system_payload
    return {
        "property_id": base.get("property_id"),
        "property_name": base.get("property_name"),
        "property_type": base.get("property_type"),
        "annotation": base.get("annotation"),
        "allow_modify": base.get("allow_modify", False),
        "value_source_type": "sub_property_wise",
        "sub_properties": merged_sub_properties,
    }


def load_context_registry_from_file(path: str) -> ContextRegistry:
    content = Path(path).read_text(encoding="utf-8")
    data = json.loads(content)
    if not isinstance(data, dict):
        return load_context_registry_from_json({})
    return load_context_registry_from_json(data)


def build_context_path_map(context_registry: ContextRegistry) -> Dict[str, ContextPropertyDef]:
    path_map: Dict[str, ContextPropertyDef] = {}
    root = context_registry.global_root
    if root is None:
        return path_map

    path_map["$ctx$"] = root

    def walk(node: ContextPropertyDef, parent_path: str) -> None:
        for index, child in enumerate(node.children):
            segment = _path_segment(child, index)
            child_path = f"{parent_path}.{segment}" if segment else parent_path
            path_map[child_path] = child
            walk(child, child_path)

    walk(root, "$ctx$")
    return path_map


def _normalize_sub_global(raw_sub: Any) -> List[ContextPropertyDef]:
    if isinstance(raw_sub, dict):
        node = _normalize_node(raw_sub)
        return [node] if node else []
    if isinstance(raw_sub, list):
        nodes: List[ContextPropertyDef] = []
        for row in raw_sub:
            node = _normalize_node(row)
            if node:
                nodes.append(node)
        return nodes
    return []


def _normalize_node(raw: Any) -> ContextPropertyDef | None:
    if not isinstance(raw, dict):
        return None

    return_type = raw.get("return_type") if isinstance(raw.get("return_type"), dict) else {}
    value_type_name = _as_text(return_type.get("data_type_name"))
    value_type = value_type_name or _as_text(return_type.get("data_type"))

    metadata = {
        "raw_property_type": _as_text(raw.get("property_type")),
        "raw_value_source_type": _as_text(raw.get("value_source_type")),
        "raw_return_is_list": bool(return_type.get("is_list", False)),
        "raw_return_data_type": _as_text(return_type.get("data_type")),
        "raw_return_data_type_name": _as_text(return_type.get("data_type_name")),
    }

    value_source_type = _as_text(raw.get("value_source_type"))
    children = _normalize_children(raw.get("sub_properties")) if value_source_type == "sub_property_wise" else []

    if value_source_type == "cdsl":
        metadata["cdsl"] = _as_text(raw.get("cdsl"))
    elif value_source_type == "edsl_expression":
        metadata["expression"] = _as_text(raw.get("expression"))
    elif value_source_type == "sql":
        metadata["sql_query"] = _normalize_sql_query(raw.get("sql_query"))

    return ContextPropertyDef(
        id=_as_text(raw.get("property_id")),
        name=_as_text(raw.get("property_name")),
        description=_as_text(raw.get("annotation")),
        allow_modify=bool(raw.get("allow_modify", False)),
        value_type=value_type,
        children=children,
        metadata=metadata,
    )


def _normalize_children(raw_children: Any) -> List[ContextPropertyDef]:
    if not isinstance(raw_children, list):
        return []
    children: List[ContextPropertyDef] = []
    for raw_child in raw_children:
        child = _normalize_node(raw_child)
        if child is not None:
            children.append(child)
    return children


def _normalize_sql_query(raw_sql_query: Any) -> Dict[str, Any]:
    if not isinstance(raw_sql_query, dict):
        return {"bo_name": "", "naming_sql": "", "sql_conditions": []}
    conditions = raw_sql_query.get("sql_conditions")
    safe_conditions: List[Dict[str, str]] = []
    if isinstance(conditions, list):
        for item in conditions:
            if not isinstance(item, dict):
                continue
            safe_conditions.append(
                {
                    "param_name": _as_text(item.get("param_name")),
                    "param_value": _as_text(item.get("param_value")),
                }
            )

    return {
        "bo_name": _as_text(raw_sql_query.get("bo_name")),
        "naming_sql": _as_text(raw_sql_query.get("naming_sql")),
        "sql_conditions": safe_conditions,
    }


def _path_segment(node: ContextPropertyDef, index: int) -> str:
    raw = node.name.strip() if isinstance(node.name, str) else ""
    if raw:
        return raw.replace(" ", "_")
    if node.id:
        return node.id
    return f"unnamed_{index}"


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""
