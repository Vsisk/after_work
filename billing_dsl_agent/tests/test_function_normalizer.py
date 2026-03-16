from billing_dsl_agent.normalize.function_normalizer import normalize_function_registry


def _sample_function_payload() -> dict:
    return {
        "version": "1.0",
        "native_func": [
            {
                "class_name": "Common",
                "class_desc": "native common funcs",
                "func_list": [
                    {
                        "func_id": "f1",
                        "func_name": "Double2Str",
                        "func_desc": "convert double",
                        "func_so": "common.so",
                        "func_scope": "global",
                        "param_list": [
                            {
                                "param_name": "num",
                                "is_list": False,
                                "data_type": "basic",
                                "data_type_name": "DOUBLE",
                                "is_output": False,
                            },
                            {
                                "param_name": "out_msg",
                                "is_list": False,
                                "data_type": "basic",
                                "data_type_name": "STRING",
                                "is_output": True,
                            },
                        ],
                        "return_type": {
                            "is_list": False,
                            "data_type": "basic",
                            "data_type_name": "STRING",
                        },
                    }
                ],
            }
        ],
        "func": [
            {
                "class_name": "CustomFuncs",
                "class_desc": "custom class",
                "func_list": [
                    {
                        "func_name": "BuildValue",
                        "func_desc": "build from expression",
                        "func_scope": "custom",
                        "param_list": [
                            {
                                "param_name": "ctx",
                                "is_list": False,
                                "data_type": "logic",
                                "data_type_name": "ContextObj",
                                "is_output": False,
                            }
                        ],
                        "return_type": {
                            "is_list": True,
                            "data_type": "bo",
                            "data_type_name": "BB_ITEM",
                        },
                        "func_content": {
                            "expression_type": "edsl_expression",
                            "expression": "it.a + it.b",
                            "cdsl": "$ctx$.billStatement.prepareId",
                        },
                    }
                ],
            }
        ],
    }


def test_normalize_native_function_classes() -> None:
    registry = normalize_function_registry(_sample_function_payload())

    assert len(registry.native_classes) == 1
    cls = registry.native_classes[0]
    assert cls.name == "Common"
    assert cls.description == "native common funcs"
    assert len(cls.functions) == 1
    fn = cls.functions[0]
    assert fn.is_native is True
    assert fn.method_name == "Double2Str"
    assert fn.func_so == "common.so"
    assert fn.scope == "global"


def test_normalize_custom_function_classes() -> None:
    registry = normalize_function_registry(_sample_function_payload())

    assert len(registry.predefined_classes) == 1
    cls = registry.predefined_classes[0]
    assert cls.name == "CustomFuncs"
    assert len(cls.functions) == 1
    fn = cls.functions[0]
    assert fn.is_native is False
    assert fn.method_name == "BuildValue"
    assert fn.scope == "custom"


def test_normalize_function_params_preserve_metadata() -> None:
    registry = normalize_function_registry(_sample_function_payload())

    fn = registry.native_classes[0].functions[0]
    assert len(fn.params) == 2
    p1 = fn.params[0]
    p2 = fn.params[1]
    assert p1.type.kind == "basic"
    assert p1.type.name == "DOUBLE"
    assert p1.type.is_list is False
    assert p1.metadata["raw_data_type"] == "basic"
    assert p1.metadata["raw_data_type_name"] == "DOUBLE"
    assert p1.metadata["raw_is_list"] is False
    assert p1.metadata["raw_is_output"] is False
    assert p2.metadata["raw_is_output"] is True


def test_normalize_function_return_type() -> None:
    registry = normalize_function_registry(_sample_function_payload())

    native_fn = registry.native_classes[0].functions[0]
    custom_fn = registry.predefined_classes[0].functions[0]

    assert native_fn.return_type is not None
    assert native_fn.return_type.kind == "basic"
    assert native_fn.return_type.name == "STRING"
    assert native_fn.return_type.is_list is False

    assert custom_fn.return_type is not None
    assert custom_fn.return_type.kind == "bo"
    assert custom_fn.return_type.name == "BB_ITEM"
    assert custom_fn.return_type.is_list is True


def test_normalize_custom_function_preserve_expression_content() -> None:
    registry = normalize_function_registry(_sample_function_payload())

    fn = registry.predefined_classes[0].functions[0]
    assert fn.metadata["raw_expression_type"] == "edsl_expression"
    assert fn.metadata["raw_expression"] == "it.a + it.b"
    assert fn.metadata["raw_cdsl"] == "$ctx$.billStatement.prepareId"


def test_normalize_function_support_missing_optional_fields() -> None:
    raw = {
        "native_func": [{"class_name": "N", "func_list": [{"func_name": "f"}]}],
        "func": [{"class_name": "C", "func_list": [{"func_name": "g", "func_content": None}]}],
    }

    registry = normalize_function_registry(raw)

    native_fn = registry.native_classes[0].functions[0]
    custom_fn = registry.predefined_classes[0].functions[0]

    assert native_fn.func_so == ""
    assert native_fn.return_type is None
    assert native_fn.params == []

    assert custom_fn.return_type is None
    assert custom_fn.params == []
    assert custom_fn.metadata["raw_expression_type"] is None
    assert custom_fn.metadata["raw_expression"] is None
    assert custom_fn.metadata["raw_cdsl"] is None
