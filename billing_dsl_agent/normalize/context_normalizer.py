"""Context normalization placeholders."""

from __future__ import annotations

from typing import Any

from billing_dsl_agent.types.context import ContextPropertyDef, ContextRegistry


def normalize_context_registry(raw_context_data: dict[str, Any]) -> ContextRegistry:
    """Normalize raw context payload into ContextRegistry.

    Conversion notes:
    - `global_context` maps to `global_root`.
    - Child nodes may appear in `sub_properties` or `return_sub_properties`.
    - `property_id`, `property_name`, `annotation`, `property_type`, `data_type`,
      `allow_modify`, and `cdsl` are mapped into `ContextPropertyDef` fields.
    """

    raw_context_data = raw_context_data or {}

    def _normalize_property(raw: dict[str, Any] | None, default_scope: str) -> ContextPropertyDef:
        """Recursively convert raw context property node to typed node."""

        raw = raw or {}
        sub_props = raw.get("sub_properties") or []
        return_sub_props = raw.get("return_sub_properties") or []
        merged_children = [*sub_props, *return_sub_props]
        children = [
            _normalize_property(child, default_scope)
            for child in merged_children
            if isinstance(child, dict)
        ]

        return ContextPropertyDef(
            id=str(raw.get("property_id", raw.get("id", ""))),
            name=str(raw.get("property_name", raw.get("name", ""))),
            description=str(raw.get("annotation", raw.get("description", ""))),
            scope=str(raw.get("scope", default_scope)),
            property_type=str(raw.get("property_type", "basic")),
            value_type=str(raw.get("data_type")) if raw.get("data_type") is not None else None,
            allow_modify=bool(raw.get("allow_modify", False)),
            nullable=bool(raw.get("nullable", True)),
            cdsl=str(raw.get("cdsl", "")),
            children=children,
            metadata={"raw": raw},
        )

    global_raw = raw_context_data.get("global_context") or {}
    global_root = _normalize_property(global_raw, "global")

    local_candidates = (
        raw_context_data.get("local_contexts")
        or raw_context_data.get("local_context")
        or []
    )
    if isinstance(local_candidates, dict):
        local_candidates = [local_candidates]
    local_roots = [_normalize_property(item, "local") for item in local_candidates if isinstance(item, dict)]

    return ContextRegistry(global_root=global_root, local_roots=local_roots)
