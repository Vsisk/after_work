from billing_dsl_agent.context_loader import build_context_path_map, load_context_registry_from_json


def _sample_context_json() -> dict:
    return {
        "version": "1.0.0",
        "global_context": {
            "property_id": "gc_001",
            "property_name": "全局上下文",
            "property_type": "system",
            "annotation": "系统级全局上下文配置",
            "allow_modify": False,
            "value_source_type": "sub_property_wise",
            "sub_properties": [
                {
                    "property_id": "gc_user_001",
                    "property_name": "当前用户信息",
                    "property_type": "system",
                    "annotation": "获取当前登录用户信息",
                    "allow_modify": False,
                    "value_source_type": "cdsl",
                    "cdsl": "CurrentUser.get()",
                    "return_type": {
                        "is_list": False,
                        "data_type": "bo",
                        "data_type_name": "UserInfo",
                    },
                },
                {
                    "property_id": "gc_time_001",
                    "property_name": "系统时间",
                    "property_type": "system",
                    "annotation": "获取当前系统时间",
                    "allow_modify": False,
                    "value_source_type": "edsl_expression",
                    "expression": "${system.currentDateTime()}",
                    "return_type": {
                        "is_list": False,
                        "data_type": "basic",
                        "data_type_name": "datetime",
                    },
                },
            ],
        },
        "sub_global_context": {
            "property_id": "sgc_001",
            "property_name": "子全局上下文",
            "property_type": "custom",
            "annotation": "局点自定义的子全局上下文",
            "allow_modify": True,
            "value_source_type": "sql",
            "sql_query": {
                "bo_name": "SystemConfig",
                "naming_sql": "getConfigByModule",
                "sql_conditions": [
                    {"param_name": "module", "param_value": "business"},
                    {"param_name": "env", "param_value": "production"},
                ],
            },
            "return_type": {
                "is_list": True,
                "data_type": "bo",
                "data_type_name": "ConfigItem",
            },
        },
    }


def test_load_context_registry_from_json_basic() -> None:
    registry = load_context_registry_from_json(_sample_context_json())
    assert registry.global_root is not None
    assert registry.global_root.id == "gc_001"
    assert any(child.id == "sgc_001" for child in registry.global_root.children)


def test_normalize_context_sub_properties() -> None:
    registry = load_context_registry_from_json(_sample_context_json())
    assert registry.global_root is not None
    names = {child.name for child in registry.global_root.children}
    assert "当前用户信息" in names
    assert "系统时间" in names


def test_normalize_context_cdsl_expression_sql() -> None:
    registry = load_context_registry_from_json(_sample_context_json())
    assert registry.global_root is not None

    user_ctx = next(child for child in registry.global_root.children if child.name == "当前用户信息")
    time_ctx = next(child for child in registry.global_root.children if child.name == "系统时间")
    sub_ctx = next(child for child in registry.global_root.children if child.name == "子全局上下文")

    assert user_ctx.metadata["cdsl"] == "CurrentUser.get()"
    assert time_ctx.metadata["expression"] == "${system.currentDateTime()}"
    assert sub_ctx.metadata["sql_query"]["bo_name"] == "SystemConfig"
    assert len(sub_ctx.metadata["sql_query"]["sql_conditions"]) == 2


def test_normalize_context_return_type_metadata() -> None:
    registry = load_context_registry_from_json(_sample_context_json())
    assert registry.global_root is not None
    user_ctx = next(child for child in registry.global_root.children if child.name == "当前用户信息")

    assert user_ctx.value_type == "UserInfo"
    assert user_ctx.metadata["raw_return_is_list"] is False
    assert user_ctx.metadata["raw_return_data_type"] == "bo"
    assert user_ctx.metadata["raw_return_data_type_name"] == "UserInfo"


def test_build_context_path_map() -> None:
    registry = load_context_registry_from_json(_sample_context_json())
    path_map = build_context_path_map(registry)

    assert "$ctx$" in path_map
    assert "$ctx$.当前用户信息" in path_map
    assert "$ctx$.系统时间" in path_map
    assert "$ctx$.子全局上下文" in path_map


def test_load_context_registry_missing_optional_fields() -> None:
    payload = {
        "global_context": {
            "property_id": "g1",
            "property_name": "root",
            "value_source_type": "sub_property_wise",
            "sub_properties": [
                {
                    "property_id": "c1",
                    "property_name": "c1",
                    "value_source_type": "sql",
                },
                {
                    "property_id": "c2",
                    "value_source_type": "cdsl",
                },
            ],
        }
    }
    registry = load_context_registry_from_json(payload)
    assert registry.global_root is not None
    assert len(registry.global_root.children) == 2
    child_sql = registry.global_root.children[0]
    assert child_sql.metadata["sql_query"]["sql_conditions"] == []
    child_cdsl = registry.global_root.children[1]
    assert child_cdsl.metadata["cdsl"] == ""


def test_load_context_registry_nested_custom_and_system_context() -> None:
    payload = {
        "global_context": {
            "custom_context": {
                "property_id": "root_custom",
                "property_name": "$ctx$",
                "annotation": "custom root",
                "allow_modify": True,
                "sub_properties": [
                    {
                        "property_id": "custom_child",
                        "property_name": "customValue",
                        "value_source_type": "cdsl",
                    }
                ],
            },
            "system_context": {
                "property_id": "root_system",
                "property_name": "$ctx$",
                "annotation": "system root",
                "allow_modify": True,
                "sub_properties": [
                    {
                        "property_id": "system_child",
                        "property_name": "systemValue",
                        "value_source_type": "cdsl",
                    }
                ],
            },
        }
    }

    registry = load_context_registry_from_json(payload)
    assert registry.global_root is not None
    child_names = {child.name for child in registry.global_root.children}
    assert "customValue" in child_names
    assert "systemValue" in child_names
