"""Function normalization placeholders."""

from __future__ import annotations

from typing import Any

from billing_dsl_agent.types.function import (
    FunctionClassDef,
    FunctionDef,
    FunctionParamDef,
    FunctionRegistry,
    FunctionTypeRef,
)


def normalize_function_registry(raw_function_data: dict[str, Any]) -> FunctionRegistry:
    """Normalize raw function payload into FunctionRegistry.

    Conversion notes:
    - `native_func` holds native classes.
    - `class_name`, `class_desc`, `func_list` become FunctionClassDef.
    - Function fields map from `func_id`, `func_name`, `func_desc`, `func_scope`, `func_so`.
    - Parameter mappings use `param_list`, `param_name`, `data_type`, `data_type_name`, `is_list`.
    - Return type is optional and remains `None` when not provided.
    """

    raw_function_data = raw_function_data or {}

    def _to_type_ref(raw_type: dict[str, Any]) -> FunctionTypeRef:
        raw_type = raw_type or {}
        return FunctionTypeRef(
            kind=str(raw_type.get("data_type", "unknown")),
            name=str(raw_type.get("data_type_name", "UNKNOWN")),
            is_list=bool(raw_type.get("is_list", False)),
        )

    def _normalize_param(raw_param: dict[str, Any]) -> FunctionParamDef:
        raw_param = raw_param or {}
        return FunctionParamDef(
            name=str(raw_param.get("param_name", raw_param.get("name", ""))),
            type=_to_type_ref(raw_param),
            description=str(raw_param.get("description", "")),
            required=bool(raw_param.get("required", True)),
        )

    def _normalize_function(raw_func: dict[str, Any], class_name: str, is_native: bool) -> FunctionDef:
        raw_func = raw_func or {}
        return FunctionDef(
            id=raw_func.get("func_id") or raw_func.get("id"),
            class_name=class_name,
            method_name=str(raw_func.get("func_name", raw_func.get("method_name", ""))),
            description=str(raw_func.get("func_desc", raw_func.get("description", ""))),
            scope=str(raw_func.get("func_scope", "global")),
            params=[_normalize_param(p) for p in (raw_func.get("param_list") or []) if isinstance(p, dict)],
            return_type=_to_type_ref(raw_func.get("return_type", {})) if raw_func.get("return_type") else None,
            is_native=is_native,
            need_import=bool(raw_func.get("need_import", False)),
            import_path=raw_func.get("import_path"),
            func_so=str(raw_func.get("func_so", "")),
            metadata={"raw": raw_func},
        )

    def _normalize_class(raw_class: dict[str, Any], is_native: bool) -> FunctionClassDef:
        raw_class = raw_class or {}
        class_name = str(raw_class.get("class_name", ""))
        funcs = [
            _normalize_function(item, class_name=class_name, is_native=is_native)
            for item in (raw_class.get("func_list") or [])
            if isinstance(item, dict)
        ]
        return FunctionClassDef(
            name=class_name,
            description=str(raw_class.get("class_desc", raw_class.get("description", ""))),
            functions=funcs,
        )

    native_raw = raw_function_data.get("native_func") or []
    if isinstance(native_raw, dict):
        native_raw = [native_raw]
    native_classes = [_normalize_class(item, True) for item in native_raw if isinstance(item, dict)]

    predefined_raw = raw_function_data.get("predefined_func") or []
    if isinstance(predefined_raw, dict):
        predefined_raw = [predefined_raw]
    predefined_classes = [_normalize_class(item, False) for item in predefined_raw if isinstance(item, dict)]

    return FunctionRegistry(native_classes=native_classes, predefined_classes=predefined_classes)
