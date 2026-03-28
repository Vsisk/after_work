from billing_dsl_agent.bo_models import BORegistry
from billing_dsl_agent.context_loader import load_context_registry_from_json
from billing_dsl_agent.resource_loader import LoadedResources
from billing_dsl_agent.resource_normalizer import ResourceNormalizer


def test_resource_normalizer_prefers_context_registry_nodes_by_id() -> None:
    context_payload = {
        "global_context": {
            "property_id": "gc_001",
            "property_name": "billInvoice",
            "sub_properties": [
                {
                    "property_id": "cust_info",
                    "property_name": "customerInfo",
                    "return_type": {"data_type": "bo", "data_type_name": "CustomerInfo", "is_list": False},
                    "children": [
                        {
                            "property_id": "cust_id",
                            "property_name": "CUST_ID",
                            "return_type": {"data_type": "STRING", "data_type_name": "STRING", "is_list": False},
                        }
                    ],
                }
            ],
        },
        "sub_gobal_context": {
            "property_id": "sgc_001",
            "property_name": "bizExt",
            "sub_properties": [],
        },
    }

    loaded = LoadedResources(
        context_registry=load_context_registry_from_json(context_payload),
        bo_registry=BORegistry(),
        function_payload={"functions": []},
        edsl_tree={},
    )

    registry = ResourceNormalizer().normalize(loaded)
    assert "context:$ctx$.billInvoice" in registry.contexts
    assert "context:$ctx$.billInvoice.customerInfo" in registry.contexts
    assert "context:$ctx$.billInvoice.customerInfo.CUST_ID" in registry.contexts
    assert "context:$ctx$.bizExt" in registry.contexts
