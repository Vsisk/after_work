from billing_dsl_agent.models import NodeDef
from billing_dsl_agent.resource_manager import ResourceManager


def _sample_contexts() -> list[dict]:
    return [
        {"path": "$ctx$.customer.gender", "name": "gender", "description": "客户性别"},
        {"path": "$ctx$.customer.title", "name": "title", "description": "客户称谓"},
        {"path": "$ctx$.customer.salutation", "name": "salutation", "description": "称谓别名"},
        {"path": "$ctx$.prepareId", "name": "prepareId", "description": "预处理主键"},
        {"path": "$ctx$.billCycleId", "name": "billCycleId", "description": "账期标识"},
    ]


def _sample_bos() -> list[dict]:
    return [
        {
            "bo_name": "BB_PREP_SUB",
            "description": "预处理子表",
            "fields": ["prepareId", "billCycleId", "regionId"],
            "naming_sqls": [
                {
                    "naming_sql_id": "query_by_prepare_and_cycle_001",
                    "naming_sql_name": "QUERY_BY_PREPARE_AND_CYCLE",
                    "params": [
                        {
                            "param_name": "prepareId",
                            "data_type": "basic",
                            "data_type_name": "INT64",
                            "is_list": False,
                        },
                        {
                            "param_name": "billCycleId",
                            "data_type": "basic",
                            "data_type_name": "INT64",
                            "is_list": False,
                        },
                    ],
                }
            ],
        }
    ]


def _sample_functions() -> list[dict]:
    return [
        {
            "id": "function:Common.Double2Str",
            "name": "Double2Str",
            "full_name": "Common.Double2Str",
            "description": "数值转两位小数字符串",
            "return_type_raw": "String",
            "params": [
                {"param_name": "number", "param_type_raw": "Double", "normalized_param_type": "double"},
                {"param_name": "precision", "param_type_raw": "int", "normalized_param_type": "int"},
            ],
        },
        {
            "id": "function:Customer.GetSalutation",
            "name": "GetSalutation",
            "full_name": "Customer.GetSalutation",
            "description": "根据性别返回称谓",
            "return_type_raw": "String",
            "params": [{"param_name": "gender", "param_type_raw": "String", "normalized_param_type": "string"}],
        },
    ]


def test_build_indexes_basic() -> None:
    manager = ResourceManager()
    indexes = manager.build_indexes(_sample_contexts(), _sample_bos(), _sample_functions())

    assert "$ctx$.customer.gender" in indexes.context_by_path
    assert "gender" in indexes.context_by_name
    assert "bbprepsub" in indexes.bo_by_name
    assert "regionid" in indexes.bo_field_index
    assert "querybyprepareandcycle" in indexes.naming_sql_by_name
    assert "commondouble2str" in indexes.function_by_full_name
    assert "getsalutation" in indexes.function_by_name


def test_select_candidates_by_node_semantics() -> None:
    manager = ResourceManager()
    indexes = manager.build_indexes(_sample_contexts(), _sample_bos(), _sample_functions())
    node = NodeDef(
        node_id="n1",
        node_path="invoice.customerTitle",
        node_name="customerTitle",
        description="根据客户性别生成称谓",
    )

    candidates = manager.select_candidates(user_query="", node_def=node, indexes=indexes)
    context_names = {item.name for item in candidates.context_candidates}
    function_names = {item.full_name for item in candidates.function_candidates}

    assert "gender" in context_names
    assert "title" in context_names or "salutation" in context_names
    assert "Customer.GetSalutation" in function_names


def test_select_candidates_by_query_keywords() -> None:
    manager = ResourceManager()
    indexes = manager.build_indexes(_sample_contexts(), _sample_bos(), _sample_functions())
    node = NodeDef(node_id="n2", node_path="invoice.region", node_name="region")

    candidates = manager.select_candidates(
        user_query="根据 prepareId 和 billCycleId 查询 BB_PREP_SUB，取 regionId",
        node_def=node,
        indexes=indexes,
    )

    context_paths = {item.path for item in candidates.context_candidates}
    bo_names = {item.bo_name for item in candidates.bo_candidates}

    assert "$ctx$.prepareId" in context_paths
    assert "$ctx$.billCycleId" in context_paths
    assert "BB_PREP_SUB" in bo_names

    matched_bo = next(item for item in candidates.bo_candidates if item.bo_name == "BB_PREP_SUB")
    assert "regionId" in matched_bo.fields
    assert matched_bo.naming_sqls[0]["naming_sql_name"] == "QUERY_BY_PREPARE_AND_CYCLE"
    assert matched_bo.naming_sqls[0]["params"][0]["data_type"] == "basic"
    assert matched_bo.naming_sqls[0]["params"][0]["data_type_name"] == "INT64"


def test_select_candidates_apply_budget() -> None:
    manager = ResourceManager()
    contexts = _sample_contexts() + [
        {"path": f"$ctx$.ext.field{i}", "name": f"field{i}", "description": "扩展字段"}
        for i in range(20)
    ]
    indexes = manager.build_indexes(contexts, _sample_bos(), _sample_functions())
    node = NodeDef(node_id="n3", node_path="invoice.amount", node_name="amount", description="金额字段")

    candidates = manager.select_candidates(
        user_query="金额和称谓都需要",
        node_def=node,
        indexes=indexes,
        budget={"context_candidates": 3, "bo_candidates": 1, "function_candidates": 1},
    )

    assert len(candidates.context_candidates) <= 3
    assert len(candidates.bo_candidates) <= 1
    assert len(candidates.function_candidates) <= 1


def test_format_for_prompt() -> None:
    manager = ResourceManager()
    indexes = manager.build_indexes(_sample_contexts(), _sample_bos(), _sample_functions())
    node = NodeDef(node_id="n4", node_path="invoice.customer", node_name="customer")
    candidates = manager.select_candidates(
        user_query="根据 prepareId 和 billCycleId 查询 BB_PREP_SUB",
        node_def=node,
        indexes=indexes,
    )

    payload = manager.format_for_prompt(candidates)

    assert set(payload.keys()) == {"context_candidates", "bo_candidates", "function_candidates"}
    assert payload["context_candidates"]
    assert payload["bo_candidates"]
    assert payload["function_candidates"]
    assert {"path", "name", "description"}.issubset(payload["context_candidates"][0].keys())
    assert {"bo_name", "description", "fields", "naming_sqls"}.issubset(payload["bo_candidates"][0].keys())
    assert {"naming_sql_id", "naming_sql_name", "params"}.issubset(payload["bo_candidates"][0]["naming_sqls"][0].keys())
    assert {"function_id", "function_name", "description", "normalized_return_type", "params"}.issubset(
        payload["function_candidates"][0].keys()
    )


def test_normalize_functions_and_save(tmp_path) -> None:
    manager = ResourceManager()
    function_payload = {
        "version": "1.0.0",
        "native_func": [
            {
                "class_name": "UserManager",
                "class_desc": "用户管理模块",
                "func_list": [
                    {
                        "func_id": "get_user_by_id",
                        "func_name": "getUserById",
                        "func_desc": "根据ID获取用户信息",
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
                "class_desc": "合同分析工具类",
                "func_list": [
                    {
                        "func_name": "analyzePaymentTerms",
                        "func_desc": "分析合同中的付款条件",
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
