from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from billing_dsl_agent.models import NormalizedTypeRef


class ResourceManager:
    """Normalize raw function resources into the runtime registry shape."""

    def normalize_functions(self, function_payload: Dict[str, Any]) -> Dict[str, Any]:
        version = str(function_payload.get("version", ""))
        normalized: List[Dict[str, Any]] = []

        for source_key, source_type in (("native_func", "native"), ("func", "custom")):
            class_rows = function_payload.get(source_key) or []
            if not isinstance(class_rows, list):
                continue
            for class_row in class_rows:
                if not isinstance(class_row, dict):
                    continue
                class_name = self._safe_text(class_row.get("class_name"))
                class_desc = self._safe_text(class_row.get("class_desc"))
                func_list = class_row.get("func_list") or []
                if not isinstance(func_list, list):
                    continue
                for func_row in func_list:
                    if not isinstance(func_row, dict):
                        continue
                    func_name = self._safe_text(func_row.get("func_name"))
                    if not func_name:
                        continue
                    func_id = self._safe_text(func_row.get("func_id"))
                    full_name = f"{class_name}.{func_name}" if class_name else func_name
                    return_type_raw = self._extract_return_type_raw(func_row.get("return_type"))
                    normalized.append(
                        {
                            "id": func_id or full_name,
                            "name": func_name,
                            "full_name": full_name,
                            "class_name": class_name,
                            "class_desc": class_desc,
                            "description": self._safe_text(func_row.get("func_desc")) or class_desc,
                            "scope": self._safe_text(func_row.get("func_scope")) or ("global" if source_type == "native" else "custom"),
                            "source_type": source_type,
                            "function_kind": "native_func" if source_key == "native_func" else "func",
                            "shared_object": self._safe_text(func_row.get("func_so")),
                            "expression_type": self._safe_text((func_row.get("func_content") or {}).get("expression_type")),
                            "expression": self._safe_text((func_row.get("func_content") or {}).get("expression")),
                            "cdsl": self._safe_text((func_row.get("func_content") or {}).get("cdsl")),
                            "params": self._normalize_param_list(func_row.get("param_list")),
                            "return_type": self._normalize_return_type(func_row.get("return_type")),
                            "return_type_raw": return_type_raw,
                            "normalized_return_type_ref": asdict(normalize_function_type(return_type_raw)),
                            "source_metadata": {
                                "source_key": source_key,
                                "class_name": class_name,
                                "scope": self._safe_text(func_row.get("func_scope")),
                            },
                            "raw_payload": dict(func_row),
                        }
                    )

        return {"version": version, "functions": normalized}

    def normalize_functions_to_file(self, function_payload: Dict[str, Any], output_path: str) -> Dict[str, Any]:
        normalized = self.normalize_functions(function_payload)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        return normalized

    def _normalize_param_list(self, raw_params: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw_params, list):
            return []
        params: List[Dict[str, Any]] = []
        for idx, row in enumerate(raw_params):
            if not isinstance(row, dict):
                continue
            param_name = self._safe_text(row.get("param_name")) or f"param_{idx}"
            param_type_raw = (
                self._safe_text(row.get("data_type"))
                or self._safe_text(row.get("type"))
                or self._safe_text(row.get("data_type_name"))
            )
            normalized_type_ref = normalize_function_type(param_type_raw)
            params.append(
                {
                    "param_id": self._safe_text(row.get("param_id")) or f"{param_name}:{idx}",
                    "param_name": param_name,
                    "param_type_raw": param_type_raw,
                    "normalized_param_type": normalized_type_ref.normalized_type,
                    "type_ref": asdict(normalized_type_ref),
                    "data_type": self._safe_text(row.get("data_type")),
                    "type": self._safe_text(row.get("type")),
                    "data_type_name": self._safe_text(row.get("data_type_name")),
                    "is_list": bool(row.get("is_list", False) or normalized_type_ref.is_list),
                    "item_type": normalized_type_ref.item_type,
                    "is_optional": row.get("is_optional"),
                    "is_output": bool(row.get("is_output", False)),
                    "raw_payload": dict(row),
                }
            )
        return params

    def _normalize_return_type(self, return_type: Any) -> Dict[str, Any]:
        raw_type = self._extract_return_type_raw(return_type)
        normalized_type = normalize_function_type(raw_type)
        if not isinstance(return_type, dict):
            return {"data_type": "", "data_type_name": raw_type, "is_list": normalized_type.is_list}
        return {
            "data_type": self._safe_text(return_type.get("data_type")),
            "data_type_name": self._safe_text(return_type.get("data_type_name")) or raw_type,
            "is_list": bool(return_type.get("is_list", False) or normalized_type.is_list),
        }

    def _extract_return_type_raw(self, return_type: Any) -> str:
        if isinstance(return_type, dict):
            return (
                self._safe_text(return_type.get("data_type_name"))
                or self._safe_text(return_type.get("data_type"))
                or self._safe_text(return_type.get("type"))
            )
        return self._safe_text(return_type)

    def _safe_text(self, value: Any) -> str:
        return value if isinstance(value, str) else ""


def normalize_function_type(type_value: str | None) -> NormalizedTypeRef:
    raw_type = (type_value or "").strip()
    if not raw_type:
        return NormalizedTypeRef(raw_type="", normalized_type="unknown", category="unknown", is_unknown=True)
    compact = re.sub(r"\s+", "", raw_type)
    lower = compact.lower()
    list_match = re.match(r"^(?:list|array)\s*(?:<|\[)\s*([a-z0-9_$.]+)\s*(?:>|\])$", lower)
    if list_match:
        item_raw = list_match.group(1)
        item_ref = normalize_function_type(item_raw)
        normalized_item = item_ref.normalized_type if not item_ref.is_unknown else item_raw
        return NormalizedTypeRef(
            raw_type=raw_type,
            normalized_type=f"list[{normalized_item}]",
            category="collection",
            is_list=True,
            item_type=normalized_item,
            is_unknown=False,
        )
    alias_map = {
        "int": "int",
        "integer": "int",
        "long": "long",
        "string": "string",
        "str": "string",
        "bool": "boolean",
        "boolean": "boolean",
        "float": "float",
        "double": "double",
        "map": "map",
    }
    normalized = alias_map.get(lower)
    if normalized:
        return NormalizedTypeRef(
            raw_type=raw_type,
            normalized_type=normalized,
            category="basic" if normalized not in {"map"} else "object",
            is_unknown=False,
        )
    return NormalizedTypeRef(raw_type=raw_type, normalized_type="unknown", category="unknown", is_unknown=True)
