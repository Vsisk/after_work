from billing_dsl_agent.agent_entry import DSLAgent
from billing_dsl_agent.environment import EnvironmentBuilder
from billing_dsl_agent.llm_planner import LLMPlanner, StubOpenAIClient
from billing_dsl_agent.models import GenerateDSLRequest, NodeDef
from billing_dsl_agent.plan_validator import parse_program_plan_payload
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
            node_path="$.children[0].children[0]",
            node_name="title",
            description="customer title",
            is_ab=is_ab,
            ab_data_sources=ab_sources or [],
        ),
    )


def _build_agent(plan_response: dict, repair_response: dict | None = None) -> DSLAgent:
    provider = InMemoryResourceProvider(dataset=_dataset())
    loader = ResourceLoader(provider=provider)
    planner = LLMPlanner(
        StubOpenAIClient(
            stage_responses={
                "plan_base": _infer_base_plan_response(plan_response),
                "plan_final": plan_response,
            },
            repair_response=repair_response,
        )
    )
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


def _iter_expr_nodes(payload):
    if isinstance(payload, dict):
        if isinstance(payload.get("type"), str):
            yield payload
        for value in payload.values():
            yield from _iter_expr_nodes(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_expr_nodes(item)


def _infer_return_shape(node_type: str | None) -> str:
    return {
        "literal": "literal_value",
        "context_ref": "direct_ref",
        "local_ref": "direct_ref",
        "var_ref": "direct_ref",
        "query_call": "query_result",
        "function_call": "function_result",
        "if": "conditional_result",
        "list_literal": "list_result",
        "index_access": "list_result",
        "field_access": "object_field",
    }.get(node_type or "", "unknown")


def _context_path_aliases(path: str) -> set[str]:
    aliases = {path}
    if path.startswith("$ctx$.root."):
        aliases.add("$ctx$." + path[len("$ctx$.root.") :])
    elif path.startswith("$ctx$."):
        aliases.add("$ctx$.root." + path[len("$ctx$.") :])
    return aliases


def _infer_base_plan_response(plan_response: dict) -> dict:
    env = _build_filtered_env()
    plan = parse_program_plan_payload(plan_response)
    path_to_context_id = {
        alias: item.resource_id
        for item in env.selected_global_contexts
        for alias in _context_path_aliases(item.path)
    }
    path_to_context_id.update({item.access_path: item.resource_id for item in env.visible_local_context.ordered_nodes})
    bo_by_id = {item.resource_id: item for item in env.selected_bos}
    function_ids = {item.resource_id for item in env.selected_functions}

    node_types: list[str] = []
    context_ids: list[str] = []
    bo_ids: list[str] = []
    referenced_function_ids: list[str] = []
    query_kinds: list[str] = []
    uses_condition = False

    for node in _iter_expr_nodes(plan.model_dump(mode="python")):
        node_type = node.get("type")
        if not node_type:
            continue
        if node_type not in node_types:
            node_types.append(node_type)
        if node_type in {"context_ref", "local_ref"}:
            resource_id = path_to_context_id.get(node.get("path"))
            if resource_id and resource_id not in context_ids:
                context_ids.append(resource_id)
        if node_type == "query_call":
            query_kind = node.get("query_kind")
            if query_kind and query_kind not in query_kinds:
                query_kinds.append(query_kind)
            bo_id = node.get("bo_id")
            if bo_id in bo_by_id and bo_id not in bo_ids:
                bo_ids.append(bo_id)
        if node_type == "function_call":
            function_id = node.get("function_id")
            if not function_id and node.get("function_name"):
                function_id = f"function:{node['function_name']}"
            if function_id in function_ids and function_id not in referenced_function_ids:
                referenced_function_ids.append(function_id)
        if node_type in {"if", "binary_op", "unary_op"}:
            uses_condition = True

    complexity = "low"
    if "query_call" in node_types or "if" in node_types or len(plan.definitions) > 1:
        complexity = "high"
    elif plan.definitions or "function_call" in node_types or len(node_types) > 2:
        complexity = "medium"

    return {
        "goal": "derive final program plan",
        "required_resources": {
            "context_refs": context_ids,
            "bo_refs": [
                {
                    "bo_id": bo.resource_id,
                    "bo_name": bo.bo_name,
                    "field_ids": list(bo.field_ids),
                    "naming_sql_ids": list(bo.naming_sql_ids),
                    "data_source": bo.data_source,
                    "available_query_kinds": [
                        *(
                            ["select_one", "select"]
                            if bo.field_ids
                            else []
                        ),
                        *(
                            ["fetch_one", "fetch"]
                            if bo.naming_sql_ids
                            else []
                        ),
                    ],
                }
                for bo_id, bo in bo_by_id.items()
                if bo_id in bo_ids
            ],
            "function_refs": referenced_function_ids,
        },
        "plan_shape": {
            "needs_definitions": bool(plan.definitions),
            "needs_query": "query_call" in node_types,
            "needs_condition": uses_condition,
            "needs_function_call": "function_call" in node_types,
            "estimated_complexity": complexity,
            "preferred_query_kinds": query_kinds,
        },
        "allowed_node_types": node_types or ["literal"],
        "return_shape": _infer_return_shape(getattr(plan.return_expr, "type", None)),
        "definition_hints": [
            {
                "name": definition.name,
                "purpose": "intermediate computation",
            }
            for definition in plan.definitions
        ],
        "validation_notes": [],
        "raw_reasoning_summary": "test-only inferred base plan",
    }


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
    assert "function:Customer.GetSalutation" in filtered.registry.functions
    assert filtered.selection_debug is not None
    assert filtered.selection_debug.global_context.selected_ids


def test_local_context_inherits_from_edsl_ancestors() -> None:
    filtered = _build_filtered_env()
    names = {item.property_name for item in filtered.visible_local_context.ordered_nodes}
    assert "invoiceId" in names
    assert "customerLevel" in names


def test_only_parent_or_parent_list_provide_local_context() -> None:
    filtered = _build_filtered_env()
    names = {item.property_name for item in filtered.visible_local_context.ordered_nodes}
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
    assert response.debug is not None
    assert response.debug.resource_selection is not None
    assert "function:Customer.GetSalutation" in response.debug.resource_selection.function.selected_ids


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
    assert any(item.code == "repair_no_progress" for item in response.validation.issues)
    assert response.debug is not None
    assert len(response.debug.repair_attempts) == 2


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
