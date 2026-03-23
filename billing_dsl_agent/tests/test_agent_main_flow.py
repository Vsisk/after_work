from billing_dsl_agent.agent_entry import DSLAgent
from billing_dsl_agent.ast_builder import ASTBuilder
from billing_dsl_agent.environment import EnvironmentBuilder
from billing_dsl_agent.llm_planner import LLMPlanner, StubOpenAIClient
from billing_dsl_agent.models import GenerateDSLRequest, NodeDef
from billing_dsl_agent.plan_validator import PlanValidator
from billing_dsl_agent.resource_loader import InMemoryResourceProvider, ResourceLoader
from billing_dsl_agent.resource_normalizer import ResourceNormalizer
from billing_dsl_agent.semantic_selector import MockSemanticSelector


def _dataset() -> dict:
    return {
        ("site-a", "proj-1"): {
            "context": {
                "global_context": {
                    "property_id": "root",
                    "property_name": "全局",
                    "value_source_type": "sub_property_wise",
                    "sub_properties": [
                        {
                            "property_id": "gc_customer",
                            "property_name": "customer",
                            "annotation": "客户全局对象",
                            "value_source_type": "sub_property_wise",
                            "sub_properties": [
                                {"property_id": "gc_customer_gender", "property_name": "gender", "annotation": "客户性别", "value_source_type": "cdsl"},
                                {"property_id": "gc_customer_id", "property_name": "id", "annotation": "客户ID", "value_source_type": "cdsl"},
                            ],
                        }
                    ],
                },
                "sub_global_context": [
                    {
                        "property_id": "lc_invoice",
                        "property_name": "invoice",
                        "annotation": "单据局部上下文",
                        "value_source_type": "sub_property_wise",
                        "sub_properties": [
                            {
                                "property_id": "lc_invoice_customer",
                                "property_name": "customer",
                                "annotation": "单据中的客户",
                                "value_source_type": "sub_property_wise",
                                "sub_properties": [
                                    {"property_id": "lc_invoice_customer_gender", "property_name": "gender", "annotation": "局部客户性别", "value_source_type": "cdsl"}
                                ],
                            }
                        ],
                    }
                ],
            },
            "bo": {
                "sys_bo_list": [
                    {
                        "bo_name": "CustomerBO",
                        "bo_desc": "客户主数据",
                        "property_list": [{"field_name": "name"}, {"field_name": "gender"}],
                        "or_mapping_list": [{"or_mapping_data_source": "crm", "naming_sql_list": [{"sql_name": "findById"}]}],
                    }
                ],
                "custom_bo_list": [
                    {
                        "bo_name": "InvoiceBO",
                        "bo_desc": "发票数据",
                        "property_list": [{"field_name": "title"}],
                        "or_mapping_list": [{"or_mapping_data_source": "billing", "naming_sql_list": [{"sql_name": "findByInvoiceId"}]}],
                    }
                ],
            },
            "function": {
                "func": [
                    {
                        "class_name": "Customer",
                        "func_list": [
                            {
                                "func_name": "GetSalutation",
                                "func_desc": "根据性别返回称谓",
                                "param_list": [{"param_name": "gender"}],
                                "return_type": {"data_type_name": "string"},
                            }
                        ],
                    }
                ],
                "native_func": [
                    {
                        "class_name": "String",
                        "func_list": [
                            {
                                "func_name": "Upper",
                                "func_desc": "转大写",
                                "param_list": [{"param_name": "value"}],
                            }
                        ],
                    }
                ],
            },
        }
    }


def _build_agent(plan_response: dict) -> DSLAgent:
    provider = InMemoryResourceProvider(dataset=_dataset())
    loader = ResourceLoader(provider=provider)
    planner = LLMPlanner(StubOpenAIClient(plan_response=plan_response))
    env_builder = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=4))
    return DSLAgent(llm_planner=planner, resource_loader=loader, environment_builder=env_builder)


def _request(is_ab: bool = False, ab_sources: list[str] | None = None) -> GenerateDSLRequest:
    return GenerateDSLRequest(
        user_requirement="根据性别生成称谓",
        site_id="site-a",
        project_id="proj-1",
        node_def=NodeDef(
            node_id="n1",
            node_path="invoice.customer.title",
            node_name="title",
            description="客户称谓",
            is_ab=is_ab,
            ab_data_sources=ab_sources or [],
        ),
    )


def test_loader_normalization_and_filtering_pipeline() -> None:
    provider = InMemoryResourceProvider(dataset=_dataset())
    loader = ResourceLoader(provider=provider)
    loaded = loader.load("site-a", "proj-1")
    registry = ResourceNormalizer().normalize(loaded)
    filtered = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=4)).build_filtered_environment(
        node_info=_request().node_def,
        user_query="根据性别生成称谓",
        registry=registry,
    )

    assert registry.contexts
    assert registry.bos
    assert registry.functions
    assert filtered.selected_global_context_ids
    assert filtered.selected_bo_ids
    assert filtered.selected_function_ids


def test_context_bo_function_independent_filtering() -> None:
    provider = InMemoryResourceProvider(dataset=_dataset())
    registry = ResourceNormalizer().normalize(ResourceLoader(provider=provider).load("site-a", "proj-1"))
    filtered = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=1)).build_filtered_environment(
        node_info=_request().node_def,
        user_query="根据性别生成称谓",
        registry=registry,
    )

    assert len(filtered.selected_global_context_ids) == 1
    assert len(filtered.selected_bo_ids) == 1
    assert len(filtered.selected_function_ids) == 1


def test_bo_filter_respects_is_ab_data_source() -> None:
    provider = InMemoryResourceProvider(dataset=_dataset())
    registry = ResourceNormalizer().normalize(ResourceLoader(provider=provider).load("site-a", "proj-1"))

    filtered_non_ab = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=5)).build_filtered_environment(
        node_info=_request(is_ab=False).node_def,
        user_query="查询发票",
        registry=registry,
    )
    filtered_ab = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=5)).build_filtered_environment(
        node_info=_request(is_ab=True, ab_sources=["crm"]).node_def,
        user_query="查询发票",
        registry=registry,
    )

    assert len(filtered_non_ab.selected_bo_ids) >= 2
    assert filtered_ab.selected_bo_ids == ["bo:CustomerBO"]


def test_planner_only_sees_filtered_ids() -> None:
    plan = {
        "intent_summary": "function call",
        "expression_pattern": "function_call",
        "context_refs": ["context:$ctx$.customer.gender"],
        "function_refs": ["function:Customer.GetSalutation"],
        "semantic_slots": {"function_args": ["context:$ctx$.customer.gender"]},
    }
    agent = _build_agent(plan)
    response = agent.generate_dsl(_request())
    payload = agent.llm_planner.client.last_payload

    assert response.success is True
    assert payload is not None
    assert "selected_function_ids" in payload["environment"]
    assert "function:Customer.GetSalutation" in payload["environment"]["selected_function_ids"]


def test_ast_builder_builds_valid_edsl_by_resource_id() -> None:
    provider = InMemoryResourceProvider(dataset=_dataset())
    registry = ResourceNormalizer().normalize(ResourceLoader(provider=provider).load("site-a", "proj-1"))
    filtered = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=4)).build_filtered_environment(
        node_info=_request().node_def,
        user_query="根据性别生成称谓",
        registry=registry,
    )
    plan = LLMPlanner(
        StubOpenAIClient(
            plan_response={
                "intent_summary": "query",
                "expression_pattern": "fetch_one",
                "context_refs": ["context:$ctx$.customer.id"],
                "bo_refs": [
                    {
                        "bo_id": "bo:CustomerBO",
                        "field_id": "bo:CustomerBO:field:name",
                        "data_source": "crm",
                        "naming_sql_id": "bo:CustomerBO:sql:findById",
                        "params": [{"param_name": "id", "value": "context:$ctx$.customer.id", "value_source_type": "context"}],
                    }
                ],
            }
        )
    ).plan("x", _request().node_def, filtered)

    ast = ASTBuilder().build_ast(plan, filtered)
    assert ast.value == "CustomerBO"
    assert ast.metadata["target_field"] == "name"


def test_validator_detects_illegal_reference() -> None:
    provider = InMemoryResourceProvider(dataset=_dataset())
    registry = ResourceNormalizer().normalize(ResourceLoader(provider=provider).load("site-a", "proj-1"))
    filtered = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=1)).build_filtered_environment(
        node_info=_request().node_def,
        user_query="根据性别生成称谓",
        registry=registry,
    )

    bad_plan = LLMPlanner(
        StubOpenAIClient(
            plan_response={
                "intent_summary": "bad",
                "expression_pattern": "function_call",
                "context_refs": ["context:$ctx$.customer.gender"],
                "function_refs": ["function:String.Upper"],
                "semantic_slots": {"function_args": ["context:$ctx$.customer.gender"]},
            }
        )
    ).plan("x", _request().node_def, filtered)

    result = PlanValidator(planner=None).validate(bad_plan, filtered)
    assert result.is_valid is False
    assert any("function not in filtered environment" in issue for issue in result.issues)
