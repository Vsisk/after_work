from billing_dsl_agent.services.external_resource_loader import load_bo, load_context, load_function
from billing_dsl_agent.types.common import ContextScope, DSLDataType


def test_load_context_convert_registry_to_runtime_lists() -> None:
    payload = {
        "global_context": {
            "property_name": "billStatement",
            "return_type": {"data_type_name": "OBJECT"},
            "sub_properties": [
                {"property_name": "prepareId", "return_type": {"data_type_name": "STRING"}},
                {
                    "property_name": "billCycle",
                    "return_type": {"data_type_name": "OBJECT"},
                    "sub_properties": [
                        {"property_name": "cycleId", "return_type": {"data_type_name": "LONG"}},
                    ],
                },
            ],
        },
        "local_contexts": [
            {
                "property_name": "lineItem",
                "return_type": {"data_type_name": "OBJECT"},
                "sub_properties": [{"property_name": "amount", "return_type": {"data_type_name": "DOUBLE"}}],
            }
        ],
    }

    global_vars, local_vars = load_context(payload)

    assert len(global_vars) == 1
    assert len(local_vars) == 1
    assert global_vars[0].name == "billStatement"
    assert global_vars[0].scope == ContextScope.GLOBAL
    assert [field.name for field in global_vars[0].fields] == ["prepareId", "billCycle", "billCycle.cycleId"]
    assert global_vars[0].fields[2].data_type == DSLDataType.NUMBER

    assert local_vars[0].name == "lineItem"
    assert local_vars[0].scope == ContextScope.LOCAL
    assert [field.name for field in local_vars[0].fields] == ["amount"]


def test_load_bo_merge_system_and_custom_bos() -> None:
    payload = {
        "sys_bo_list": [{"bo_id": "1", "bo_name": "SYS_BE"}],
        "custom_bo_list": [{"bo_id": "2", "bo_name": "CUS_BE"}],
    }

    bos = load_bo(payload)

    assert [bo.name for bo in bos] == ["SYS_BE", "CUS_BE"]
    assert [bo.source for bo in bos] == ["system", "custom"]


def test_load_function_merge_native_and_predefined_functions() -> None:
    payload = {
        "native_func": [{"class_name": "Common", "func_list": [{"func_id": "n1", "func_name": "Now"}]}],
        "func": [{"class_name": "Custom", "func_list": [{"func_id": "c1", "func_name": "Build"}]}],
    }

    functions = load_function(payload)

    assert [f.full_name for f in functions] == ["Common.Now", "Custom.Build"]
    assert [f.is_native for f in functions] == [True, False]


def test_loaders_use_callable_hook_each_time_without_cache() -> None:
    state = {"count": 0}

    def payload_provider() -> dict:
        state["count"] += 1
        return {"custom_bo_list": [{"bo_name": f"CUS_{state['count']}"}]}

    first = load_bo(payload_provider)
    second = load_bo(payload_provider)

    assert first[0].name == "CUS_1"
    assert second[0].name == "CUS_2"
    assert state["count"] == 2
