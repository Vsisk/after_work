from billing_dsl_agent.resource_manager import ResourceManager


def test_normalize_functions_and_save(tmp_path) -> None:
    manager = ResourceManager()
    function_payload = {
        "version": "1.0.0",
        "native_func": [
            {
                "class_name": "UserManager",
                "class_desc": "user management",
                "func_list": [
                    {
                        "func_id": "get_user_by_id",
                        "func_name": "getUserById",
                        "func_desc": "get user by id",
                        "func_so": "/lib/user_manager.so",
                        "func_scope": "global",
                        "param_list": [
                            {
                                "is_list": False,
                                "data_type": "basic",
                                "data_type_name": "int",
                                "param_name": "userId",
                                "is_output": False,
                            }
                        ],
                        "return_type": {"is_list": False, "data_type": "bo", "data_type_name": "UserBO"},
                    }
                ],
            }
        ],
        "func": [
            {
                "class_name": "ContractAnalyzer",
                "class_desc": "contract analyzer",
                "func_list": [
                    {
                        "func_name": "analyzePaymentTerms",
                        "func_desc": "analyze payment terms",
                        "func_content": {
                            "expression_type": "edsl_expression",
                            "expression": "contract.paymentTerms.extract()",
                        },
                        "func_scope": "custom",
                        "param_list": [
                            {
                                "is_list": False,
                                "data_type": "bo",
                                "data_type_name": "ContractBO",
                                "param_name": "contract",
                                "is_output": False,
                            }
                        ],
                        "return_type": {"is_list": True, "data_type": "logic", "data_type_name": "PaymentTerm"},
                    }
                ],
            }
        ],
    }
    output_path = tmp_path / "normalized_functions.json"
    normalized = manager.normalize_functions_to_file(function_payload, str(output_path))

    assert normalized["version"] == "1.0.0"
    assert len(normalized["functions"]) == 2
    assert normalized["functions"][0]["full_name"] == "UserManager.getUserById"
    assert normalized["functions"][0]["shared_object"] == "/lib/user_manager.so"
    assert normalized["functions"][1]["full_name"] == "ContractAnalyzer.analyzePaymentTerms"
    assert normalized["functions"][1]["expression_type"] == "edsl_expression"
    assert normalized["functions"][1]["params"][0]["normalized_param_type"] == "unknown"
    assert normalized["functions"][0]["normalized_return_type_ref"]["normalized_type"] == "unknown"
    assert output_path.exists()


def test_normalize_functions_supports_type_alias_and_list() -> None:
    manager = ResourceManager()
    function_payload = {
        "func": [
            {
                "class_name": "Mask",
                "func_list": [
                    {
                        "func_name": "CustCallMask",
                        "func_desc": "mask",
                        "param_list": [
                            {"param_name": "iBeId", "data_type": "INT"},
                            {"param_name": "numbers", "type": "List<String>"},
                            {"param_name": "unknownParam"},
                        ],
                        "return_type": "String",
                    }
                ],
            }
        ]
    }
    normalized = manager.normalize_functions(function_payload)
    fn = normalized["functions"][0]
    assert fn["params"][0]["normalized_param_type"] == "int"
    assert fn["params"][1]["normalized_param_type"] == "list[string]"
    assert fn["params"][1]["is_list"] is True
    assert fn["params"][2]["normalized_param_type"] == "unknown"
    assert fn["normalized_return_type_ref"]["normalized_type"] == "string"
