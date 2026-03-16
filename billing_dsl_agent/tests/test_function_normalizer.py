from billing_dsl_agent.normalize.function_normalizer import normalize_function_registry


def test_normalize_function_registry_native_mapping() -> None:
    raw = {
        "native_func": [
            {
                "class_name": "Common",
                "class_desc": "common funcs",
                "func_list": [
                    {
                        "func_id": "f1",
                        "func_name": "Double2Str",
                        "func_desc": "convert",
                        "func_scope": "global",
                        "func_so": "common.so",
                        "param_list": [
                            {
                                "param_name": "num",
                                "data_type": "basic",
                                "data_type_name": "DOUBLE",
                                "is_list": False,
                            }
                        ],
                    }
                ],
            }
        ]
    }

    registry = normalize_function_registry(raw)

    assert len(registry.native_classes) == 1
    cls = registry.native_classes[0]
    assert cls.name == "Common"
    assert cls.description == "common funcs"
    fn = cls.functions[0]
    assert fn.method_name == "Double2Str"
    assert fn.is_native is True
    assert fn.params[0].name == "num"
    assert fn.return_type is None
