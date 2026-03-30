from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List

from billing_dsl_agent.models import NormalizedLocalContextNode, RawLocalContextWithSource, VisibleLocalContextSet


@dataclass(slots=True)
class _ConflictState:
    by_property_id: Dict[str, NormalizedLocalContextNode] = field(default_factory=dict)
    by_property_name: Dict[str, NormalizedLocalContextNode] = field(default_factory=dict)


def _stable_resource_id(property_id: str, source_node_path: str, property_name: str) -> str:
    pid = property_id.strip()
    if pid:
        return f"local_context:{pid}"
    seed = f"{source_node_path}:{property_name}".encode("utf-8")
    digest = hashlib.md5(seed).hexdigest()[:12]
    return f"local_context:fallback:{digest}"


def _to_normalized(item: RawLocalContextWithSource) -> NormalizedLocalContextNode | None:
    payload = dict(item.payload)
    property_name = str(payload.get("property_name") or payload.get("name") or "").strip()
    if not property_name:
        return None
    property_id = str(payload.get("property_id") or payload.get("id") or "").strip()
    return NormalizedLocalContextNode(
        resource_id=_stable_resource_id(property_id, item.source_node_path, property_name),
        property_id=property_id,
        property_name=property_name,
        access_path=f"$local$.{property_name}",
        property_type=str(payload.get("property_type") or "normal"),
        annotation=str(payload.get("annotation") or payload.get("description") or ""),
        source_node_path=item.source_node_path,
        source_node_id=item.source_node_id,
        depth=item.depth,
        data_source=dict(payload.get("data_source") or {}),
        raw_payload=payload,
    )


def _apply_property_id_rule(state: _ConflictState, node: NormalizedLocalContextNode, warnings: List[str]) -> NormalizedLocalContextNode:
    if not node.property_id:
        return node
    existing = state.by_property_id.get(node.property_id)
    if existing is None:
        return node
    if node.depth >= existing.depth:
        warnings.append(
            f"property_id_override:{node.property_id}:use_nearer:{node.source_node_path}:replace:{existing.source_node_path}"
        )
        return node
    return existing


def _apply_property_name_rule(state: _ConflictState, node: NormalizedLocalContextNode, warnings: List[str]) -> NormalizedLocalContextNode:
    existing = state.by_property_name.get(node.property_name)
    if existing is None:
        return node
    if existing.property_id and node.property_id and existing.property_id == node.property_id:
        return node if node.depth >= existing.depth else existing
    warnings.append(
        f"property_name_conflict:{node.property_name}:near={node.property_id or '<empty>'}:far={existing.property_id or '<empty>'}"
    )
    return node if node.depth >= existing.depth else existing


def normalize_local_contexts(resolved_contexts: List[RawLocalContextWithSource]) -> VisibleLocalContextSet:
    state = _ConflictState()
    ordered: List[NormalizedLocalContextNode] = []
    source_trace: List[str] = []
    warnings: List[str] = []

    for item in resolved_contexts:
        normalized = _to_normalized(item)
        if normalized is None:
            source_trace.append(f"skip_invalid_local_context:{item.source_node_path}")
            continue
        source_trace.append(
            f"collect:{normalized.resource_id}:name={normalized.property_name}:source={normalized.source_node_path}:depth={normalized.depth}"
        )
        chosen = _apply_property_id_rule(state, normalized, warnings)
        chosen = _apply_property_name_rule(state, chosen, warnings)
        state.by_property_name[chosen.property_name] = chosen
        if chosen.property_id:
            state.by_property_id[chosen.property_id] = chosen
        ordered.append(normalized)

    nodes_by_id = {node.resource_id: node for node in state.by_property_name.values()}
    ordered_nodes = sorted(nodes_by_id.values(), key=lambda item: (item.depth, item.source_node_path, item.property_name))
    nodes_by_property_name = {node.property_name: node for node in ordered_nodes}
    return VisibleLocalContextSet(
        nodes_by_id=nodes_by_id,
        nodes_by_property_name=nodes_by_property_name,
        ordered_nodes=ordered_nodes,
        source_trace=source_trace,
        warnings=warnings,
    )
