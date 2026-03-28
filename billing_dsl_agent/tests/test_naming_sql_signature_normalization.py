from billing_dsl_agent.bo_loader import load_bo_registry_from_json
from billing_dsl_agent.context_models import ContextRegistry
from billing_dsl_agent.resource_loader import LoadedResources
from billing_dsl_agent.resource_normalizer import ResourceNormalizer


def _bo_payload() -> dict:
    return {
        "sys_bo_list": [
            {
                "bo_name": "BB_BILL_INVOICE",
                "bo_desc": "发票BO",
                "property_list": [{"field_name": "id", "data_type": "basic", "data_type_name": "String", "is_list": False}],
                "or_mapping_list": [
                    {
                        "or_mapping_data_source": "billdb",
                        "naming_sql_list": [
                            {
                                "naming_sql_id": "invoice_query_001",
                                "sql_name": "queryInvoice",
                                "sql_description": "查询发票",
                                "sql_command": "select * from invoice where id=:invoiceId",
                                "param_list": [
                                    {
                                        "param_name": "END_DATE",
                                        "data_type": "basic",
                                        "data_type_name": "Date",
                                        "is_list": False,
                                    },
                                    {
                                        "param_name": "invoiceIds",
                                        "data_type": "bo",
                                        "data_type_name": "BB_BILL_INVOICE",
                                        "is_list": True,
                                    },
                                ],
                            },
                            {
                                "naming_sql_id": "invoice_query_002",
                                "sql_name": "queryInvoiceFallback",
                                "param_list": [
                                    {
                                        "param_name": "MISSING_TYPE",
                                        "is_list": False,
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }


def test_resource_normalizer_keeps_naming_sql_param_signatures() -> None:
    loaded = LoadedResources(
        context_registry=ContextRegistry(),
        bo_registry=load_bo_registry_from_json(_bo_payload()),
        function_payload={"functions": []},
        edsl_tree={},
    )
    registry = ResourceNormalizer().normalize(loaded)

    bo = registry.bos["bo:BB_BILL_INVOICE"]
    assert "invoice_query_001" in bo.naming_sql_signature_by_key

    signature = bo.naming_sql_signature_by_key["invoice_query_001"]
    assert signature["naming_sql_name"] == "queryInvoice"
    assert signature["params"][0]["param_name"] == "END_DATE"
    assert signature["params"][0]["data_type"] == "basic"
    assert signature["params"][0]["data_type_name"] == "Date"
    assert signature["params"][0]["is_list"] is False

    fallback = bo.naming_sql_signature_by_key["invoice_query_002"]
    assert fallback["params"][0]["normalized_type_ref"]["is_unknown"] is True


def test_resource_manager_prompt_contains_naming_sql_defs() -> None:
    loaded = LoadedResources(
        context_registry=ContextRegistry(),
        bo_registry=load_bo_registry_from_json(_bo_payload()),
        function_payload={"functions": []},
        edsl_tree={},
    )
    registry = ResourceNormalizer().normalize(loaded)

    from billing_dsl_agent.models import NodeDef
    from billing_dsl_agent.resource_manager import ResourceManager

    payload = ResourceManager().build_candidate_prompt_payload(
        user_query="查询发票 END_DATE",
        node_def=NodeDef(node_id="n1", node_name="invoice", node_path="invoice.path"),
        context_registry_or_vars=registry.contexts,
        bo_registry_or_list=registry.bos,
        function_registry_or_list=registry.functions,
    )

    assert payload["bo_candidates"]
    matched = payload["bo_candidates"][0]
    assert "naming_sql_defs" in matched
    assert matched["naming_sql_defs"][0]["params"][0]["data_type"] == "basic"
