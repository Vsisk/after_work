from billing_dsl_agent.agent_entry import DSLAgent
from billing_dsl_agent.environment import EnvironmentBuilder
from billing_dsl_agent.llm_planner import LLMPlanner, StubOpenAIClient
from billing_dsl_agent.models import GenerateDSLRequest, NodeDef
from billing_dsl_agent.resource_loader import InMemoryResourceProvider, ResourceLoader
from billing_dsl_agent.resource_normalizer import ResourceNormalizer
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
                            "annotation": "customer object",
                            "value_source_type": "sub_property_wise",
                            "sub_properties": [
                                {
                                    "property_id": "gc_customer_gender",
                                    "property_name": "gender",
                                    "annotation": "customer gender",
                                    "value_source_type": "cdsl",
                                },
                                {
                                    "property_id": "gc_customer_id",
                                    "property_name": "id",
                                    "annotation": "customer id",
                                    "value_source_type": "cdsl",
                                },
                            ],
                        }
                    ],
                }
            },
            "edsl": {
                "node_path": "invoice",
                "node_name": "invoice",
                "node_type": "parent",
                "local_context": [
                    {"id": "lc-invoice-id", "name": "invoiceId", "description": "invoice id", "path": "$local$.invoiceId"}
                ],
                "children": [
                    {
                        "node_path": "invoice.customer",
                        "node_name": "customer",
                        "node_type": "parent list",
                        "local_context": [{"name": "customerLevel", "description": "customer level"}],
                        "children": [
                            {
                                "node_path": "invoice.customer.title",
                                "node_name": "title",
                                "node_type": "leaf",
                            }
                        ],
                    },
                    {
                        "node_path": "invoice.billing",
                        "node_name": "billing",
                        "node_type": "leaf",
                        "local_context": [{"name": "should_not_visible", "description": "hidden local"}],
                    },
                ],
            },
            "bo": {
                "sys_bo_list": [
                    {
                        "bo_name": "CustomerBO",
                        "bo_desc": "customer data",
                        "property_list": [{"field_name": "name"}, {"field_name": "gender"}, {"field_name": "id"}],
                        "or_mapping_list": [
                            {
                                "or_mapping_data_source": "crm",
                                "naming_sql_list": [
                                    {
                                        "naming_sql_id": "get_customer_by_id_001",
                                        "sql_name": "findById",
                                        "param_list": [{"param_name": "id"}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "custom_bo_list": [
                    {
                        "bo_name": "InvoiceBO",
                        "bo_desc": "invoice data",
                        "property_list": [{"field_name": "title"}],
                        "or_mapping_list": [
                            {
                                "or_mapping_data_source": "billing",
                                "naming_sql_list": [{"sql_name": "findByInvoiceId"}],
                            }
                        ],
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
                                "func_desc": "return salutation by gender",
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
                                "func_desc": "uppercase string",
                                "param_list": [{"param_name": "value", "type": "String"}],
                            },
                            {
                                "func_name": "Now",
                                "func_desc": "return now",
                                "param_list": [],
                            }
                        ],
                    }
                ],
            },
        }
    }


def _request(is_ab: bool = False, ab_sources: list[str] | None = None) -> GenerateDSLRequest:
    return GenerateDSLRequest(
        user_requirement="generate title from customer gender",
        site_id="site-a",
        project_id="proj-1",
        node_def=NodeDef(
            node_id="n1",
            node_path="invoice.customer.title",
            node_name="title",
            description="customer title",
            is_ab=is_ab,
            ab_data_sources=ab_sources or [],
        ),
    )


def _build_agent(plan_response: dict, repair_response: dict | None = None) -> DSLAgent:
    provider = InMemoryResourceProvider(dataset=_dataset())
    loader = ResourceLoader(provider=provider)
    planner = LLMPlanner(StubOpenAIClient(plan_response=plan_response, repair_response=repair_response))
    env_builder = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=4))
    return DSLAgent(llm_planner=planner, resource_loader=loader, environment_builder=env_builder)


def _build_filtered_env():
    provider = InMemoryResourceProvider(dataset=_dataset())
    loader = ResourceLoader(provider=provider)
    loaded = loader.load("site-a", "proj-1")
    registry = ResourceNormalizer().normalize(loaded)
    return EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=4)).build_filtered_environment(
        node_info=_request().node_def,
        user_query="generate title from customer gender",
        registry=registry,
    )


def test_loader_normalization_and_filtering_pipeline() -> None:
    filtered = _build_filtered_env()
    assert filtered.registry.contexts
    assert filtered.registry.bos
    assert filtered.registry.functions
    assert filtered.selected_global_context_ids
    assert filtered.selected_bo_ids
    assert filtered.selected_function_ids
    fn = filtered.registry.functions["function:Customer.GetSalutation"]
    assert fn.return_type == "string"
    assert fn.param_defs[0].normalized_param_type == "unknown"
    assert filtered.registry.functions["function:String.Now"].param_defs == []
    assert filtered.registry.function_registry is not None
    assert "function:Customer.GetSalutation" in filtered.registry.function_registry.functions_by_id


def test_local_context_inherits_from_edsl_ancestors() -> None:
    filtered = _build_filtered_env()
    local_resources = {cid: filtered.registry.contexts[cid] for cid in filtered.selected_local_context_ids}
    names = {item.name for item in local_resources.values()}
    assert "invoiceId" in names
    assert "customerLevel" in names


def test_only_parent_or_parent_list_provide_local_context() -> None:
    filtered = _build_filtered_env()
    names = {filtered.registry.contexts[cid].name for cid in filtered.selected_local_context_ids}
    assert "should_not_visible" not in names


def test_bo_filter_respects_is_ab_data_source() -> None:
    provider = InMemoryResourceProvider(dataset=_dataset())
    registry = ResourceNormalizer().normalize(ResourceLoader(provider=provider).load("site-a", "proj-1"))
    filtered_non_ab = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=5)).build_filtered_environment(
        node_info=_request(is_ab=False).node_def,
        user_query="query invoice",
        registry=registry,
    )
    filtered_ab = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=5)).build_filtered_environment(
        node_info=_request(is_ab=True, ab_sources=["crm"]).node_def,
        user_query="query invoice",
        registry=registry,
    )
    assert len(filtered_non_ab.selected_bo_ids) >= 2
    assert filtered_ab.selected_bo_ids == ["bo:CustomerBO"]


def test_planner_only_sees_filtered_ids() -> None:
    plan = {
        "definitions": [],
        "return_expr": {
            "type": "function_call",
            "function_id": "function:Customer.GetSalutation",
            "function_name": "Customer.GetSalutation",
            "args": [{"type": "context_ref", "path": "$ctx$.customer.gender"}],
        },
    }
    agent = _build_agent(plan)
    response = agent.generate_dsl(_request())
    payload = agent.llm_planner.client.last_payload
    assert response.success is True
    assert payload is not None
    assert "selected_function_ids" in payload["environment"]
    assert "function:Customer.GetSalutation" in payload["environment"]["selected_function_ids"]


def test_generate_dsl_renders_program_defs_and_final_expression() -> None:
    plan = {
        "raw_plan": "query gender then derive title",
        "definitions": [
            {
                "kind": "variable",
                "name": "customer_gender",
                "expr": {
                    "type": "query_call",
                    "query_kind": "select_one",
                    "source_name": "CustomerBO",
                    "bo_id": "bo:CustomerBO",
                    "field": "gender",
                    "data_source": "crm",
                    "naming_sql_id": "bo:CustomerBO:sql:findById",
                    "filters": [
                        {
                            "field": "id",
                            "value": {"type": "context_ref", "path": "$ctx$.customer.id"},
                        }
                    ],
                },
            },
            {
                "kind": "variable",
                "name": "title_prefix",
                "expr": {
                    "type": "if",
                    "condition": {
                        "type": "binary_op",
                        "operator": "==",
                        "left": {"type": "var_ref", "name": "customer_gender"},
                        "right": {"type": "literal", "value": "M"},
                    },
                    "then_expr": {"type": "literal", "value": "MR."},
                    "else_expr": {"type": "literal", "value": "MS."},
                },
            },
        ],
        "return_expr": {"type": "var_ref", "name": "title_prefix"},
    }
    agent = _build_agent(plan)
    response = agent.generate_dsl(_request())

    assert response.success is True
    assert response.dsl.splitlines() == [
        "def customer_gender = select_one(CustomerBO.gender, id=$ctx$.customer.id)",
        'def title_prefix = if(customer_gender == "M", "MR.", "MS.")',
        "title_prefix",
    ]


def test_invalid_repair_result_does_not_fallback_to_legacy_plan() -> None:
    invalid_plan = {
        "definitions": [
            {
                "kind": "variable",
                "name": "title_prefix",
                "expr": {"type": "var_ref", "name": "customer_gender"},
            }
        ],
        "return_expr": {"type": "var_ref", "name": "title_prefix"},
    }
    agent = _build_agent(plan_response=invalid_plan, repair_response=invalid_plan)
    response = agent.generate_dsl(_request())

    assert response.success is False
    assert response.failure_reason == "plan validation failed"
    assert response.validation is not None
    assert any(item.code == "undefined_var_ref" for item in response.validation.issues)


def test_select_one_supports_where_boolean_ast_render() -> None:
    plan = {
        "definitions": [],
        "return_expr": {
            "type": "query_call",
            "query_kind": "select_one",
            "source_name": "CustomerBO",
            "bo_id": "bo:CustomerBO",
            "field": "gender",
            "where": {
                "type": "binary_op",
                "operator": "and",
                "left": {
                    "type": "binary_op",
                    "operator": "==",
                    "left": {"type": "context_ref", "path": "$ctx$.customer.id"},
                    "right": {"type": "literal", "value": "C001"},
                },
                "right": {
                    "type": "binary_op",
                    "operator": "!=",
                    "left": {"type": "context_ref", "path": "$ctx$.customer.gender"},
                    "right": {"type": "literal", "value": ""},
                },
            },
        },
    }
    response = _build_agent(plan).generate_dsl(_request())
    assert response.success is True
    assert response.dsl == 'select_one(CustomerBO.gender, $ctx$.customer.id == "C001" and $ctx$.customer.gender != "")'


def test_fetch_one_renders_naming_sql_name_and_pair() -> None:
    plan = {
        "definitions": [],
        "return_expr": {
            "type": "query_call",
            "query_kind": "fetch_one",
            "source_name": "CustomerBO",
            "bo_id": "bo:CustomerBO",
            "naming_sql_id": "get_customer_by_id_001",
            "pairs": [
                {
                    "key": "id",
                    "value": {"type": "context_ref", "path": "$ctx$.customer.id"},
                }
            ],
        },
    }
    response = _build_agent(plan).generate_dsl(_request())
    assert response.success is True
    assert response.dsl == "fetch_one(findById, pair(id, $ctx$.customer.id))"


def test_fetch_pair_mismatch_repair_loop_success() -> None:
    invalid_plan = {
        "definitions": [],
        "return_expr": {
            "type": "query_call",
            "query_kind": "fetch_one",
            "source_name": "CustomerBO",
            "bo_id": "bo:CustomerBO",
            "naming_sql_id": "get_customer_by_id_001",
            "pairs": [
                {
                    "key": "wrongParam",
                    "value": {"type": "context_ref", "path": "$ctx$.customer.id"},
                }
            ],
        },
    }
    repaired_plan = {
        "definitions": [],
        "return_expr": {
            "type": "query_call",
            "query_kind": "fetch_one",
            "source_name": "findById",
            "bo_id": "bo:CustomerBO",
            "naming_sql_id": "get_customer_by_id_001",
            "pairs": [
                {
                    "key": "id",
                    "value": {"type": "context_ref", "path": "$ctx$.customer.id"},
                }
            ],
        },
    }
    response = _build_agent(plan_response=invalid_plan, repair_response=repaired_plan).generate_dsl(_request())
    assert response.success is True
    assert response.dsl == "fetch_one(findById, pair(id, $ctx$.customer.id))"
