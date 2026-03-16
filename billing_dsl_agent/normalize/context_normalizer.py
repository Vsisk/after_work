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

    def _normalize_property(raw: dict[str, Any], default_scope: str) -> ContextPropertyDef:
        children_raw = list(raw.get("sub_properties", [])) + list(raw.get("return_sub_properties", []))
        return ContextPropertyDef(
            id=str(raw.get("property_id", "")),
            name=str(raw.get("property_name", "")),
            description=str(raw.get("annotation", "")),
            scope=str(raw.get("scope", default_scope)),
            property_type=str(raw.get("property_type", "basic")),
            value_type=raw.get("data_type"),
            allow_modify=bool(raw.get("allow_modify", False)),
            cdsl=str(raw.get("cdsl", "")),
            children=[_normalize_property(child, default_scope) for child in children_raw],
            metadata={"raw": raw},
        )

    global_raw = raw_context_data.get("global_context", {})
    global_root = _normalize_property(global_raw, "global")
    local_roots = [_normalize_property(item, "local") for item in raw_context_data.get("local_contexts", [])]
    return ContextRegistry(global_root=global_root, local_roots=local_roots)
