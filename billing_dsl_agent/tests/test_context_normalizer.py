from billing_dsl_agent.normalize.context_normalizer import normalize_context_registry


def test_normalize_context_basic_property_tree() -> None:
    raw = {
        "global_context": {
            "property_id": "g1",
            "property_name": "billStatement",
            "value_source_type": "sub_property_wise",
            "sub_properties": [
                {
                    "property_id": "g1_1",
                    "property_name": "prepareId",
                    "annotation": "prepare id",
                },
                {
                    "property_id": "g1_2",
                    "property_name": "billCycleId",
                },
            ],
        }
    }

    registry = normalize_context_registry(raw)

    assert registry.global_root.id == "g1"
    assert registry.global_root.name == "billStatement"
    assert registry.global_root.value_source_type == "sub_property_wise"
    assert len(registry.global_root.children) == 2
    assert sorted(c.name for c in registry.global_root.children) == ["billCycleId", "prepareId"]


def test_normalize_context_preserve_return_type_metadata() -> None:
    raw = {
        "global_context": {
            "property_id": "g1",
            "property_name": "offerInfo",
            "return_type": {
                "is_list": True,
                "data_type": "bo",
                "data_type_name": "BB_OFFER_INFO",
            },
        }
    }

    registry = normalize_context_registry(raw)
    root = registry.global_root

    assert root.value_type == "BB_OFFER_INFO"
    assert root.metadata["raw_return_is_list"] is True
    assert root.metadata["raw_return_data_type"] == "bo"
    assert root.metadata["raw_return_data_type_name"] == "BB_OFFER_INFO"


def test_normalize_context_preserve_cdsl_expression_and_sql_query() -> None:
    raw = {
        "global_context": {
            "property_id": "g1",
            "property_name": "root",
            "sub_properties": [
                {
                    "property_id": "c1",
                    "property_name": "fromCdsl",
                    "value_source_type": "cdsl",
                    "cdsl": "$ctx$.billStatement.prepareId",
                },
                {
                    "property_id": "c2",
                    "property_name": "fromExpr",
                    "value_source_type": "edsl_expression",
                    "expression": "it.a + it.b",
                },
                {
                    "property_id": "c3",
                    "property_name": "fromSql",
                    "value_source_type": "sql",
                    "sql_query": {
                        "bo_name": "SYS_BE",
                        "naming_sql": "Q_BE",
                        "sql_conditions": ["it.BE_ID == 1"],
                    },
                },
            ],
        }
    }

    registry = normalize_context_registry(raw)
    children = {item.name: item for item in registry.global_root.children}

    assert children["fromCdsl"].cdsl == "$ctx$.billStatement.prepareId"
    assert children["fromExpr"].expression == "it.a + it.b"
    assert children["fromSql"].metadata["sql_query"]["bo_name"] == "SYS_BE"
    assert children["fromSql"].metadata["sql_query"]["naming_sql"] == "Q_BE"
    assert children["fromSql"].metadata["sql_query"]["sql_conditions"] == ["it.BE_ID == 1"]


def test_normalize_context_support_legacy_and_new_schema_shapes() -> None:
    legacy_raw = {
        "global_context": {
            "property_id": "legacy",
            "property_name": "legacyRoot",
            "data_type": "OBJECT",
            "sub_properties": [
                {"property_id": "legacy_1", "property_name": "x", "data_type": "LONG"}
            ],
        }
    }
    new_shape_raw = {
        "global_context": {
            "property_id": "new",
            "property_name": "newRoot",
            "return_type": {"data_type": "logic", "data_type_name": "LogicObj", "is_list": False},
            "return_sub_properties": [
                {"property_id": "new_1", "property_name": "y", "return_type": {"data_type": "basic", "data_type_name": "LONG"}}
            ],
        }
    }

    legacy_registry = normalize_context_registry(legacy_raw)
    new_registry = normalize_context_registry(new_shape_raw)

    assert legacy_registry.global_root.value_type == "OBJECT"
    assert len(legacy_registry.global_root.children) == 1
    assert new_registry.global_root.value_type == "LogicObj"
    assert len(new_registry.global_root.children) == 1
    assert new_registry.global_root.children[0].value_type == "LONG"
