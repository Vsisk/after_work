import pytest

from billing_dsl_agent.agent_entry import DSLAgent
from billing_dsl_agent.datatype_validator import DatatypeValidator
from billing_dsl_agent.expression_ref_validator import ExpressionRefValidator
from billing_dsl_agent.llm_planner import LLMPlanner, StubOpenAIClient
from billing_dsl_agent.models import GenerateDSLRequest, NodeDef
from billing_dsl_agent.resource_loader import InMemoryResourceProvider, ResourceLoader
from billing_dsl_agent.resource_normalizer import ResourceNormalizer
from billing_dsl_agent.environment import EnvironmentBuilder
from billing_dsl_agent.semantic_selector import MockSemanticSelector


def _dataset() -> dict:
    return {
        ("site-a", "proj-1"): {
            "context": {
                "global_context": {
                    "property_id": "root",
                    "property_name": "root",
                    "value_source_type": "sub_property_wise",
                    "sub_properties": [
                        {
                            "property_id": "gc_customer",
                            "property_name": "customer",
                            "value_source_type": "sub_property_wise",
                            "sub_properties": [
                                {
                                    "property_id": "gc_customer_id",
                                    "property_name": "id",
                                    "value_source_type": "cdsl",
                                }
                            ],
                        }
                    ],
                }
            },
            "edsl": {"node_path": "invoice", "node_name": "invoice", "node_type": "parent", "children": []},
            "bo": {"sys_bo_list": [], "custom_bo_list": []},
            "function": {"func": [], "native_func": []},
        }
    }


def _request(user_requirement: str) -> GenerateDSLRequest:
    return GenerateDSLRequest(
        user_requirement=user_requirement,
        site_id="site-a",
        project_id="proj-1",
        node_def=NodeDef(node_id="n1", node_path="invoice.title", node_name="title", description="title"),
    )


def _build_agent(global_config: dict | None) -> DSLAgent:
    provider = InMemoryResourceProvider(dataset=_dataset())
    loader = ResourceLoader(provider=provider)
    planner = LLMPlanner(StubOpenAIClient(plan_response={"definitions": [], "return_expr": {"type": "literal", "value": "ok"}}))
    env_builder = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=2))
    return DSLAgent(
        llm_planner=planner,
        resource_loader=loader,
        environment_builder=env_builder,
        global_config=global_config,
    )


def _valid_global_config() -> dict:
    return {
        "site_level_config": {
            "time_type_config": {
                "region_id_expression": "$ctx$.customer.id",
                "time_format_expression": '"yyyyMMddHHmmss"',
            },
            "money_type_config": {
                "currency_id_expression": "$ctx$.customer.id",
                "int_delimiter_expression": "','",
                "intp_delimiter_expression": "'.'",
                "round_method_expression": "3",
                "currency_unit": "B",
                "decimal_precision": "2",
                "zero_padding": "Y",
            },
        }
    }


@pytest.mark.parametrize(
    "bad_config",
    [
        {"site_level_config": {"money_type_config": {"currency_id_expression": "$ctx$.customer.id"}}},
        {"site_level_config": {"time_type_config": {"region_id_expression": "$ctx$.customer.id"}}},
        {
            "site_level_config": {
                "time_type_config": {
                    "region_id_expression": "",
                    "time_format_expression": '"yyyyMMdd"',
                }
            }
        },
    ],
)
def test_invalid_runtime_config_fail_fast(bad_config: dict) -> None:
    with pytest.raises(Exception):
        _build_agent(bad_config)


def test_datatype_expression_validation_rejects_bad_values() -> None:
    agent = _build_agent(_valid_global_config())
    loaded = agent.resource_loader.load("site-a", "proj-1")
    env = agent.environment_builder.build_filtered_environment(
        node_info=_request("any").node_def,
        user_query="any",
        registry=ResourceNormalizer().normalize(loaded),
    )
    validator = DatatypeValidator(ExpressionRefValidator())

    datatype_obj = {
        "data_type": "money",
        "currency_id_expression": "$ctx$.fake.path",
        "int_delimiter_expression": "unknown",
        "intp_delimiter_expression": "",
        "round_method_expression": None,
        "currency_unit": "",
        "decimal_precision": "",
        "zero_padding": "",
    }

    result = validator.validate(datatype_obj, env)
    assert result.is_valid is False
    codes = {issue.code for issue in result.issues}
    assert "unknown_context_ref" in codes
    assert "expression_forbidden_value" in codes or "expression_null" in codes
    assert "datatype_required_field_missing" in codes


def test_debug_output_contains_datatype_plan_and_validation() -> None:
    agent = _build_agent(_valid_global_config())
    response = agent.generate_dsl(_request("普通文案输出"))

    assert response.success is True
    assert response.datatype_plan == {"kind": "simple_string"}
    assert isinstance(response.datatype_validation, dict)
    assert response.datatype_validation["is_valid"] is True
