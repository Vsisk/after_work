from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from billing_dsl_agent.models import RawLocalContextWithSource


@dataclass(frozen=True, slots=True)
class JsonPathStep:
    kind: str
    value: str | int


def parse_json_path(node_path: str) -> List[JsonPathStep]:
    path = str(node_path or "").strip()
    if not path:
        raise ValueError("node_path is empty")
    if path[0] != "$":
        raise ValueError("node_path must start with $")

    steps: List[JsonPathStep] = []
    index = 1
    length = len(path)
    while index < length:
        token = path[index]
        if token == ".":
            index += 1
            start = index
            while index < length and path[index] not in ".[]":
                index += 1
            key = path[start:index]
            if not key:
                raise ValueError(f"invalid node_path segment near index {start}")
            steps.append(JsonPathStep(kind="key", value=key))
            continue
        if token == "[":
            index += 1
            start = index
            while index < length and path[index] != "]":
                index += 1
            if index >= length:
                raise ValueError("missing closing ] in node_path")
            raw_index = path[start:index].strip()
            if not raw_index.isdigit():
                raise ValueError(f"only integer index is supported in node_path, got: {raw_index}")
            steps.append(JsonPathStep(kind="index", value=int(raw_index)))
            index += 1
            continue
        raise ValueError(f"unsupported token {token!r} in node_path")
    return steps


def resolve_node_chain(edsl_tree: Dict[str, Any], node_path: str) -> List[Tuple[str, Any]]:
    steps = parse_json_path(node_path)
    current: Any = edsl_tree
    chain: List[Tuple[str, Any]] = [("$", current)]
    current_path = "$"

    for step in steps:
        if step.kind == "key":
            if not isinstance(current, dict):
                raise ValueError(f"path {current_path} is not object, cannot access key {step.value}")
            key = str(step.value)
            if key not in current:
                raise ValueError(f"key {key} not found at {current_path}")
            current = current[key]
            current_path = f"{current_path}.{key}"
            chain.append((current_path, current))
            continue

        if not isinstance(current, list):
            raise ValueError(f"path {current_path} is not array, cannot access index {step.value}")
        item_index = int(step.value)
        if item_index < 0 or item_index >= len(current):
            raise ValueError(f"index {item_index} out of range at {current_path}")
        current = current[item_index]
        current_path = f"{current_path}[{item_index}]"
        chain.append((current_path, current))

    return chain


def _iter_local_context_items(local_context: Any) -> Sequence[Dict[str, Any]]:
    if isinstance(local_context, list):
        return [item for item in local_context if isinstance(item, dict)]
    if isinstance(local_context, dict):
        return [local_context]
    return []


def _allow_local_context_node(node: Dict[str, Any]) -> bool:
    node_type = str(node.get("node_type") or node.get("type") or "").strip().lower().replace("_", " ")
    return node_type in {"parent", "parent list"}


def resolve_visible_local_contexts(edsl_tree: Dict[str, Any], node_path: str) -> List[RawLocalContextWithSource]:
    chain = resolve_node_chain(edsl_tree, node_path)
    resolved: List[RawLocalContextWithSource] = []

    for depth, (source_path, node) in enumerate(chain):
        if not isinstance(node, dict):
            continue
        if not _allow_local_context_node(node):
            continue
        for item in _iter_local_context_items(node.get("local_context")):
            resolved.append(
                RawLocalContextWithSource(
                    payload=dict(item),
                    source_node_path=source_path,
                    source_node_id=str(node.get("id") or node.get("node_id") or ""),
                    depth=depth,
                )
            )
    return resolved
