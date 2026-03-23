"""Function normalization placeholders."""

from __future__ import annotations

from typing import Any

from billing_dsl_agent.types.function import (
    DataType,
    ExpressionType,
    FuncScope,
    FunctionClassDef,
    FunctionDef,
    FunctionParamDef,
    FunctionRegistry,
    FunctionTypeRef,
)


def normalize_function_registry(raw_function_data: dict[str, Any]) -> FunctionRegistry:
    """Normalize raw function payload into FunctionRegistry."""

    raw_function_data = raw_function_data or {}
    native_classes = _normalize_native_classes(raw_function_data.get("native_func") or [])
    custom_classes = _normalize_custom_classes(
        raw_function_data.get("func")
        or raw_function_data.get("predefined_func")
        or []
    )
    return FunctionRegistry(native_classes=native_classes, predefined_classes=custom_classes)


def _normalize_native_classes(raw_native_classes: list[Any]) -> list[FunctionClassDef]:
    if isinstance(raw_native_classes, dict):
        raw_native_classes = [raw_native_classes]
    return [
        _normalize_function_class(raw_class, is_native=True)
        for raw_class in raw_native_classes
        if isinstance(raw_class, dict)
    ]


def _normalize_custom_classes(raw_custom_classes: list[Any]) -> list[FunctionClassDef]:
    if isinstance(raw_custom_classes, dict):
        raw_custom_classes = [raw_custom_classes]
    return [
        _normalize_function_class(raw_class, is_native=False)
        for raw_class in raw_custom_classes
        if isinstance(raw_class, dict)
    ]


def _normalize_function_class(raw_class: dict[str, Any], is_native: bool) -> FunctionClassDef:
    raw_class = raw_class or {}
    class_name = str(raw_class.get("class_name", ""))
    raw_func_list = raw_class.get("func_list") or []

    functions = [
        (_normalize_native_function(item, class_name) if is_native else _normalize_custom_function(item, class_name))
        for item in raw_func_list
        if isinstance(item, dict)
    ]

    return FunctionClassDef(
        name=class_name,
        description=str(raw_class.get("class_desc", raw_class.get("description", ""))),
        functions=functions,
    )


def _normalize_native_function(raw_func: dict[str, Any], class_name: str) -> FunctionDef:
    raw_func = raw_func or {}
    scope = _normalize_scope(raw_func.get("func_scope"))
    raw_return = raw_func.get("return_type")
    return FunctionDef(
        id=raw_func.get("func_id") or raw_func.get("id"),
        class_name=class_name,
        method_name=str(raw_func.get("func_name", raw_func.get("method_name", ""))),
        description=str(raw_func.get("func_desc", raw_func.get("description", ""))),
        scope=scope,
        params=_normalize_param_list(raw_func.get("param_list") or []),
        return_type=_normalize_return_type(raw_return),
        is_native=True,
        need_import=bool(raw_func.get("need_import", False)),
        import_path=raw_func.get("import_path"),
        func_so=str(raw_func.get("func_so", "")),
        metadata={
            "raw": raw_func,
            "raw_func_scope": raw_func.get("func_scope"),
            "raw_func_so": raw_func.get("func_so"),
            "raw_return_type": raw_return,
        },
    )


def _normalize_custom_function(raw_func: dict[str, Any], class_name: str) -> FunctionDef:
    raw_func = raw_func or {}
    scope = _normalize_scope(raw_func.get("func_scope"))
    raw_return = raw_func.get("return_type")
    content_meta = _extract_func_content_metadata(raw_func.get("func_content"))
    return FunctionDef(
        id=raw_func.get("func_id") or raw_func.get("id"),
        class_name=class_name,
        method_name=str(raw_func.get("func_name", raw_func.get("method_name", ""))),
        description=str(raw_func.get("func_desc", raw_func.get("description", ""))),
        scope=scope,
        params=_normalize_param_list(raw_func.get("param_list") or []),
        return_type=_normalize_return_type(raw_return),
        is_native=False,
        need_import=bool(raw_func.get("need_import", False)),
        import_path=raw_func.get("import_path"),
        func_so=str(raw_func.get("func_so", "")),
        metadata={
            "raw": raw_func,
            "raw_func_scope": raw_func.get("func_scope"),
            "raw_func_so": raw_func.get("func_so"),
            "raw_return_type": raw_return,
            **content_meta,
        },
    )


def _normalize_param_list(raw_param_list: list[Any]) -> list[FunctionParamDef]:
    params: list[FunctionParamDef] = []
    for raw_param in raw_param_list:
        if not isinstance(raw_param, dict):
            continue
        raw_data_type = str(raw_param.get("data_type", ""))
        raw_data_type_name = str(raw_param.get("data_type_name", ""))
        raw_is_list = bool(raw_param.get("is_list", False))
        raw_is_output = bool(raw_param.get("is_output", False))
        params.append(
            FunctionParamDef(
                name=str(raw_param.get("param_name", raw_param.get("name", ""))),
                type=_normalize_function_type_ref(raw_data_type, raw_data_type_name, raw_is_list),
                description=str(raw_param.get("description", "")),
                required=not raw_is_output,
                metadata={
                    "raw": raw_param,
                    "raw_data_type": raw_param.get("data_type"),
                    "raw_data_type_name": raw_param.get("data_type_name"),
                    "raw_is_list": raw_param.get("is_list"),
                    "raw_is_output": raw_param.get("is_output"),
                },
            )
        )
    return params


def _normalize_return_type(raw_return_type: dict[str, Any] | None) -> FunctionTypeRef | None:
    if not isinstance(raw_return_type, dict):
        return None
    return _normalize_function_type_ref(
        raw_data_type=str(raw_return_type.get("data_type", "")),
        raw_data_type_name=str(raw_return_type.get("data_type_name", "")),
        is_list=bool(raw_return_type.get("is_list", False)),
    )


def _normalize_function_type_ref(raw_data_type: str, raw_data_type_name: str, is_list: bool) -> FunctionTypeRef:
    lowered = (raw_data_type or "").strip().lower()
    known = {item.value for item in DataType}
    normalized_kind = lowered if lowered in known else (lowered or DataType.BASIC.value)

    normalized_name = (raw_data_type_name or "").strip() or (normalized_kind.upper())

    return FunctionTypeRef(
        kind=normalized_kind,
        name=normalized_name,
        is_list=bool(is_list),
        metadata={
            "raw_data_type": raw_data_type,
            "raw_data_type_name": raw_data_type_name,
            "raw_is_list": is_list,
        },
    )


def _extract_func_content_metadata(raw_func_content: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw_func_content, dict):
        return {
            "raw_expression_type": None,
            "raw_expression": None,
            "raw_cdsl": None,
            "raw_func_content": raw_func_content,
        }

    raw_expression_type = raw_func_content.get("expression_type")
    normalized_expression_type = str(raw_expression_type or "").strip().lower()
    if normalized_expression_type not in {item.value for item in ExpressionType}:
        normalized_expression_type = normalized_expression_type or None

    return {
        "raw_expression_type": normalized_expression_type,
        "raw_expression": raw_func_content.get("expression"),
        "raw_cdsl": raw_func_content.get("cdsl"),
        "raw_func_content": raw_func_content,
    }


def _normalize_scope(raw_scope: Any) -> str:
    scope = str(raw_scope or FuncScope.GLOBAL.value).strip().lower()
    known_scopes = {item.value for item in FuncScope}
    return scope if scope in known_scopes else FuncScope.GLOBAL.value
