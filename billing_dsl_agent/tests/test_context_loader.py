from billing_dsl_agent.context_loader import (
    build_context_path_map,
    is_expandable_context_type,
    load_context_registry_from_json,
)


def _sample_context_json() -> dict:
    return {
        "version": "1.0.0",
        "global_context": {
            "property_id": "gc_001",
            "property_name": "billInvoice",
            "property_type": "system",
            "annotation": "系统级全局上下文配置",
            "allow_modify": False,
            "value_source_type": "sub_property_wise",
            "sub_properties": [
                {
                    "property_id": "cust_info",
                    "property_name": "customerInfo",
                    "property_type": "system",
                    "annotation": "客户信息",
                    "allow_modify": False,
                    "value_source_type": "sub_property_wise",
                    "return_type": {"is_list": False, "data_type": "bo", "data_type_name": "CustomerInfo"},
                    "children": [
                        {
                            "property_id": "cust_id",
                            "property_name": "CUST_ID",
                            "annotation": "客户ID",
                            "return_type": {
                                "is_list": False,
                                "data_type": "STRING",
                                "data_type_name": "STRING",
                            },
                        }
                    ],
                },
                {
                    "property_id": "biz_date",
                    "property_name": "BIZ_DATE",
                    "property_type": "system",
                    "annotation": "业务日期",
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
        "sub_gobal_context": {
            "property_id": "sgc_001",
            "property_name": "bizExt",
            "property_type": "custom",
            "annotation": "子全局",
            "allow_modify": True,
            "value_source_type": "sub_property_wise",
            "sub_properties": [
                {
                    "property_id": "ext_code",
                    "property_name": "EXT_CODE",
                    "annotation": "扩展编码",
                    "return_type": {
                        "is_list": False,
                        "data_type": "STRING",
                        "data_type_name": "STRING",
                    },
                }
            ],
            "return_type": {
                "is_list": False,
                "data_type": "logic",
                "data_type_name": "BizExt",
            },
        },
    }


def test_load_context_registry_from_json_container_payload() -> None:
    registry = load_context_registry_from_json(_sample_context_json())

    assert registry.global_root is not None
    assert [child.name for child in registry.global_root.children] == ["billInvoice", "bizExt"]
    assert registry.roots_by_context_kind["global_context"].startswith("context:global_context:")
    assert registry.roots_by_context_kind["sub_gobal_context"].startswith("context:sub_gobal_context:")


def test_normalize_context_kind_and_access_path() -> None:
    registry = load_context_registry_from_json(_sample_context_json())

    global_root = registry.nodes_by_access_path["$ctx$.billInvoice"]
    sub_root = registry.nodes_by_access_path["$ctx$.bizExt"]
    leaf = registry.nodes_by_access_path["$ctx$.billInvoice.customerInfo.CUST_ID"]

    assert global_root.context_kind == "global_context"
    assert sub_root.context_kind == "sub_gobal_context"
    assert leaf.access_path == "$ctx$.billInvoice.customerInfo.CUST_ID"
    assert leaf.parent_resource_id == registry.nodes_by_access_path["$ctx$.billInvoice.customerInfo"].resource_id


def test_expandable_type_recursive_children_and_scalar_leaf() -> None:
    registry = load_context_registry_from_json(_sample_context_json())

    customer_info = registry.nodes_by_access_path["$ctx$.billInvoice.customerInfo"]
    cust_id = registry.nodes_by_access_path["$ctx$.billInvoice.customerInfo.CUST_ID"]
    biz_date = registry.nodes_by_access_path["$ctx$.billInvoice.BIZ_DATE"]

    assert customer_info.is_expandable is True
    assert customer_info.is_leaf is False
    assert cust_id.is_expandable is False
    assert cust_id.is_leaf is True
    assert biz_date.is_expandable is False


def test_registry_lookup_by_id_and_access_path() -> None:
    registry = load_context_registry_from_json(_sample_context_json())
    root_resource_id = registry.roots_by_context_kind["global_context"]
    root_node = registry.nodes_by_id[root_resource_id]

    assert registry.nodes_by_access_path[root_node.access_path].resource_id == root_resource_id
    assert registry.descendants_by_root_context[root_resource_id]


def test_input_key_sub_gobal_context_is_supported() -> None:
    payload = _sample_context_json()
    payload.pop("sub_gobal_context")
    payload["sub_global_context"] = {
        "property_id": "legacy_1",
        "property_name": "legacyRoot",
        "sub_properties": [],
    }

    registry = load_context_registry_from_json(payload)
    assert "$ctx$.legacyRoot" in registry.nodes_by_access_path


def test_build_context_path_map() -> None:
    registry = load_context_registry_from_json(_sample_context_json())
    path_map = build_context_path_map(registry)

    assert "$ctx$" in path_map
    assert "$ctx$.billInvoice" in path_map
    assert "$ctx$.billInvoice.customerInfo" in path_map
    assert "$ctx$.billInvoice.customerInfo.CUST_ID" in path_map
    assert "$ctx$.bizExt.EXT_CODE" in path_map


def test_is_expandable_context_type() -> None:
    assert is_expandable_context_type("bo") is True
    assert is_expandable_context_type("logic") is True
    assert is_expandable_context_type("extattr") is True
    assert is_expandable_context_type("basic") is False
    assert is_expandable_context_type("STRING") is False


def test_sub_properties_expand_even_without_return_type() -> None:
    payload = {
        "global_context": {
            "property_id": "root",
            "property_name": "root",
            "sub_properties": [
                {
                    "property_id": "customer",
                    "property_name": "customer",
                    "sub_properties": [
                        {"property_id": "gender", "property_name": "gender"},
                        {"property_id": "id", "property_name": "id"},
                    ],
                }
            ],
        }
    }

    registry = load_context_registry_from_json(payload)

    assert "$ctx$.root.customer.gender" in registry.nodes_by_access_path
    assert "$ctx$.root.customer.id" in registry.nodes_by_access_path
