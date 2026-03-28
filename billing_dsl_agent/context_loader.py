from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from billing_dsl_agent.context_models import ContextPropertyDef, ContextRegistry, NormalizedContextNode

EXPANDABLE_CONTEXT_TYPES = {"bo", "logic", "extattr"}
SCALAR_CONTEXT_TYPES = {"basic", "int64", "string", "date", "datetime", "double", "boolean"}


def normalize_contexts(context_payload: Dict[str, Any]) -> ContextRegistry:
    payload = context_payload if isinstance(context_payload, dict) else {}
    registry = ContextRegistry(metadata={"version": _as_text(payload.get("version"))})

    global_root = _normalize_context_root(payload.get("global_context"), "global_context", registry)
    sub_global_root = _normalize_context_root(
        payload.get("sub_gobal_context", payload.get("sub_global_context")),
        "sub_gobal_context",
        registry,
    )

    synthetic_root = ContextPropertyDef(
        id="$ctx$",
        name="$ctx$",
        description="",
        allow_modify=False,
        value_type="",
        children=[],
        metadata={"raw_property_type": "", "raw_value_source_type": "sub_property_wise"},
    )

    if global_root is not None:
        synthetic_root.children.append(global_root)
    if sub_global_root is not None:
        synthetic_root.children.append(sub_global_root)

    registry.global_root = synthetic_root
    registry.local_roots = [node for node in [sub_global_root] if node is not None]
    return registry


def load_context_registry_from_json(data: Dict[str, Any]) -> ContextRegistry:
    return normalize_contexts(data)


def _normalize_context_root(
    root_payload: Any,
    context_kind: str,
    registry: ContextRegistry,
) -> ContextPropertyDef | None:
    resolved_root = _resolve_global_context(root_payload) if context_kind == "global_context" else root_payload
    if not isinstance(resolved_root, dict):
        return None

    property_name = _as_text(resolved_root.get("property_name"))
    if not property_name:
        return None

    root_id = _as_text(resolved_root.get("property_id")) or property_name
    access_path = f"$ctx$.{property_name}"
    return_type = resolved_root.get("return_type") if isinstance(resolved_root.get("return_type"), dict) else {}
    return_data_type = _as_text(return_type.get("data_type"))
    return_data_type_name = _as_text(return_type.get("data_type_name"))

    root_resource_id = _build_resource_id(context_kind, access_path, root_id)
    root_node = NormalizedContextNode(
        resource_id=root_resource_id,
        context_kind=context_kind,
        source_context_id=root_id,
        property_name=property_name,
        annotation=_as_text(resolved_root.get("annotation")),
        access_path=access_path,
        parent_resource_id="",
        depth=0,
        return_data_type=return_data_type,
        return_data_type_name=return_data_type_name,
        is_list=bool(return_type.get("is_list", False)),
        is_leaf=True,
        is_expandable=is_expandable_context_type(return_data_type),
        child_ids=[],
        source_type="root",
        raw_payload=dict(resolved_root),
    )

    root_property = _normalize_node(resolved_root)
    if root_property is None:
        return None

    registry.nodes_by_id[root_resource_id] = root_node
    registry.nodes_by_access_path[access_path] = root_node
    registry.roots_by_context_kind[context_kind] = root_resource_id
    registry.descendants_by_root_context[root_resource_id] = []

    sub_properties = resolved_root.get("sub_properties")
    if isinstance(sub_properties, list):
        for child_payload in sub_properties:
            child_property, child_resource_id = _normalize_context_property(
                node_payload=child_payload,
                parent_path=access_path,
                parent_resource_id=root_resource_id,
                context_kind=context_kind,
                source_context_id=root_id,
                depth=1,
                root_resource_id=root_resource_id,
                source_type="sub_property",
                registry=registry,
            )
            if child_property is not None and child_resource_id:
                root_property.children.append(child_property)
                root_node.child_ids.append(child_resource_id)

    root_node.is_leaf = not root_node.child_ids
    root_node.is_expandable = bool(root_node.child_ids)
    return root_property


def _normalize_context_property(
    node_payload: Any,
    parent_path: str,
    parent_resource_id: str,
    context_kind: str,
    source_context_id: str,
    depth: int,
    root_resource_id: str,
    source_type: str,
    registry: ContextRegistry,
) -> Tuple[ContextPropertyDef | None, str]:
    if not isinstance(node_payload, dict):
        return None, ""

    property_name = _as_text(node_payload.get("property_name"))
    if not property_name:
        return None, ""

    access_path = f"{parent_path}.{property_name}"
    property_id = _as_text(node_payload.get("property_id")) or property_name
    return_type = node_payload.get("return_type") if isinstance(node_payload.get("return_type"), dict) else {}
    return_data_type = _as_text(return_type.get("data_type"))
    return_data_type_name = _as_text(return_type.get("data_type_name"))
    expandable = is_expandable_context_type(return_data_type)

    resource_id = _build_resource_id(context_kind, access_path, property_id)
    node = NormalizedContextNode(
        resource_id=resource_id,
        context_kind=context_kind,
        source_context_id=source_context_id,
        property_name=property_name,
        annotation=_as_text(node_payload.get("annotation")),
        access_path=access_path,
        parent_resource_id=parent_resource_id,
        depth=depth,
        return_data_type=return_data_type,
        return_data_type_name=return_data_type_name,
        is_list=bool(return_type.get("is_list", False)),
        is_leaf=True,
        is_expandable=expandable,
        child_ids=[],
        source_type=source_type,
        raw_payload=dict(node_payload),
    )
    registry.nodes_by_id[resource_id] = node
    registry.nodes_by_access_path[access_path] = node
    registry.descendants_by_root_context.setdefault(root_resource_id, []).append(resource_id)

    property_def = _normalize_node(node_payload)
    if property_def is None:
        return None, ""

    if expandable:
        raw_children = node_payload.get("children")
        if not isinstance(raw_children, list):
            raw_children = node_payload.get("sub_properties")
        if isinstance(raw_children, list):
            for child_payload in raw_children:
                child_property, child_resource_id = _normalize_context_property(
                    node_payload=child_payload,
                    parent_path=access_path,
                    parent_resource_id=resource_id,
                    context_kind=context_kind,
                    source_context_id=source_context_id,
                    depth=depth + 1,
                    root_resource_id=root_resource_id,
                    source_type="child_property",
                    registry=registry,
                )
                if child_property is not None and child_resource_id:
                    property_def.children.append(child_property)
                    node.child_ids.append(child_resource_id)

    node.is_leaf = not node.child_ids
    return property_def, resource_id


def is_expandable_context_type(data_type: str) -> bool:
    normalized = _as_text(data_type).strip().lower()
    if not normalized:
        return False
    if normalized in SCALAR_CONTEXT_TYPES:
        return False
    return normalized in EXPANDABLE_CONTEXT_TYPES


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


def _build_resource_id(context_kind: str, access_path: str, fallback_id: str) -> str:
    normalized_path = access_path.replace("$ctx$.", "") if access_path.startswith("$ctx$.") else access_path
    if normalized_path:
        return f"context:{context_kind}:{normalized_path}"
    return f"context:{context_kind}:{fallback_id}"


def _path_segment(node: ContextPropertyDef, index: int) -> str:
    raw = node.name.strip() if isinstance(node.name, str) else ""
    if raw:
        return raw.replace(" ", "_")
    if node.id:
        return node.id
    return f"unnamed_{index}"


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""
