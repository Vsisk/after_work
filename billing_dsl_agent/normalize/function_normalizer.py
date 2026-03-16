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
    - `native_func` can hold native classes; predefined functions can be placed in
      sibling arrays such as `predefined_func`.
    - `class_name`, `class_desc`, `func_list` become FunctionClassDef.
    - Function fields map from `func_id`, `func_name`, `func_desc`, `func_scope`, `func_so`.
    - Parameter mappings use `param_list`, `param_name`, `data_type`, `data_type_name`, `is_list`.
    """

    def _normalize_param(raw_param: dict[str, Any]) -> FunctionParamDef:
        return FunctionParamDef(
            name=str(raw_param.get("param_name", "")),
            type=FunctionTypeRef(
                kind=str(raw_param.get("data_type", "unknown")),
                name=str(raw_param.get("data_type_name", "UNKNOWN")),
                is_list=bool(raw_param.get("is_list", False)),
            ),
        )

    def _normalize_function(raw_func: dict[str, Any], class_name: str, is_native: bool) -> FunctionDef:
        return FunctionDef(
            id=raw_func.get("func_id"),
            class_name=class_name,
            method_name=str(raw_func.get("func_name", "")),
            description=str(raw_func.get("func_desc", "")),
            scope=str(raw_func.get("func_scope", "global")),
            params=[_normalize_param(p) for p in raw_func.get("param_list", [])],
            is_native=is_native,
            func_so=str(raw_func.get("func_so", "")),
            metadata={"raw": raw_func},
        )

    def _normalize_class(raw_class: dict[str, Any], is_native: bool) -> FunctionClassDef:
        class_name = str(raw_class.get("class_name", ""))
        funcs = [_normalize_function(item, class_name=class_name, is_native=is_native) for item in raw_class.get("func_list", [])]
        return FunctionClassDef(
            name=class_name,
            description=str(raw_class.get("class_desc", "")),
            functions=funcs,
        )

    native_classes = [_normalize_class(item, True) for item in raw_function_data.get("native_func", [])]
    predefined_classes = [_normalize_class(item, False) for item in raw_function_data.get("predefined_func", [])]
    return FunctionRegistry(native_classes=native_classes, predefined_classes=predefined_classes)
