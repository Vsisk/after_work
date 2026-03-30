from billing_dsl_agent.llm_planner import LLMPlanner, PlannerSkeleton, StubOpenAIClient
from billing_dsl_agent.models import (
    BOResource,
    ContextResource,
    FilteredEnvironment,
    FunctionResource,
    NodeDef,
    NormalizedLocalContextNode,
    ResourceRegistry,
    ValidationIssue,
    VisibleLocalContextSet,
)


def _env() -> FilteredEnvironment:
    return FilteredEnvironment(
        registry=ResourceRegistry(),
        selected_global_context_ids=["context:$ctx$.customer.gender"],
        selected_local_context_ids=["local_context:lc_invoice_id"],
        selected_bo_ids=["bo:CustomerBO"],
        selected_function_ids=["function:Customer.GetSalutation"],
        selected_global_contexts=[
            ContextResource(
                resource_id="context:$ctx$.customer.gender",
                name="gender",
                path="$ctx$.customer.gender",
            )
        ],
        visible_local_context=VisibleLocalContextSet(
            nodes_by_id={
                "local_context:lc_invoice_id": NormalizedLocalContextNode(
                    resource_id="local_context:lc_invoice_id",
                    property_id="lc_invoice_id",
                    property_name="invoiceId",
                    access_path="$local$.invoiceId",
                )
            },
            nodes_by_property_name={
                "invoiceId": NormalizedLocalContextNode(
                    resource_id="local_context:lc_invoice_id",
                    property_id="lc_invoice_id",
                    property_name="invoiceId",
                    access_path="$local$.invoiceId",
                )
            },
            ordered_nodes=[
                NormalizedLocalContextNode(
                    resource_id="local_context:lc_invoice_id",
                    property_id="lc_invoice_id",
                    property_name="invoiceId",
                    access_path="$local$.invoiceId",
                )
            ],
        ),
        selected_bos=[
            BOResource(
                resource_id="bo:CustomerBO",
                bo_name="CustomerBO",
                field_ids=["bo:CustomerBO:field:gender"],
            )
        ],
        selected_functions=[
            FunctionResource(
                resource_id="function:Customer.GetSalutation",
                function_id="Customer.GetSalutation",
                name="GetSalutation",
                full_name="Customer.GetSalutation",
            )
        ],
    )


def _node() -> NodeDef:
    return NodeDef(node_id="n1", node_path="invoice.customer.title", node_name="title")


def test_llm_planner_returns_program_plan() -> None:
    client = StubOpenAIClient(
        stage_responses={
            "plan_skeleton": {
                "expression_pattern": "function_call",
                "require_context": True,
                "require_bo": False,
                "require_function": True,
                "require_local_context": False,
                "require_global_context": True,
                "require_namingsql": False,
                "require_binding": True,
                "notes": "function call expected",
            },
            "plan_detail": {
                "definitions": [
                    {
                        "kind": "variable",
                        "name": "customer_gender",
                        "expr": {"type": "context_ref", "path": "$ctx$.customer.gender"},
                    }
                ],
                "return_expr": {
                    "type": "function_call",
                    "function_id": "Customer.GetSalutation",
                    "args": [{"type": "var_ref", "name": "customer_gender"}],
                },
            },
        }
    )
    planner = LLMPlanner(client)
    plan = planner.plan("generate title", _node(), _env())
    assert plan.definitions[0].name == "customer_gender"
    assert plan.return_expr.type == "function_call"
    assert len(planner.plan_attempts) == 2
    assert planner.plan_attempts[0].stage == "plan_skeleton"
    assert planner.plan_attempts[1].stage == "plan_detail"


def test_llm_planner_adapts_legacy_payload() -> None:
    planner = LLMPlanner(
        StubOpenAIClient(
            plan_response={
                "intent_summary": "legacy function call",
                "expression_pattern": "function_call",
                "context_refs": ["context:$ctx$.customer.gender"],
                "function_refs": ["function:Customer.GetSalutation"],
                "semantic_slots": {"function_args": ["context:$ctx$.customer.gender"]},
            }
        )
    )
    plan = planner.plan("generate title", _node(), _env())
    assert plan.legacy_plan is not None
    assert plan.return_expr.type == "function_call"


def test_llm_planner_repair_payload_contains_structured_issues() -> None:
    client = StubOpenAIClient(
        stage_responses={
            "plan_skeleton": {
                "expression_pattern": "literal",
                "require_context": False,
                "require_bo": False,
                "require_function": False,
                "require_local_context": False,
                "require_global_context": False,
                "require_namingsql": False,
                "require_binding": False,
                "notes": "literal",
            },
            "plan_detail": {
                "definitions": [],
                "return_expr": {"type": "literal", "value": "ok"},
            },
        },
        repair_response={
            "definitions": [],
            "return_expr": {"type": "literal", "value": "fixed"},
        },
    )
    planner = LLMPlanner(client)
    invalid_plan = planner.plan("generate title", _node(), _env())
    repaired = planner.repair(
        invalid_plan,
        _env(),
        [ValidationIssue(code="undefined_var_ref", message="missing variable", path="return_expr")],
    )
    assert repaired is not None
    assert client.last_payload is not None
    assert client.last_payload["issues"][0]["code"] == "undefined_var_ref"


def test_detail_stage_trims_resources_by_skeleton_requirements() -> None:
    client = StubOpenAIClient(
        stage_responses={
            "plan_skeleton": {
                "expression_pattern": "literal",
                "require_context": False,
                "require_bo": False,
                "require_function": False,
                "require_local_context": False,
                "require_global_context": False,
                "require_namingsql": False,
                "require_binding": False,
                "notes": "literal",
            },
            "plan_detail": {
                "definitions": [],
                "return_expr": {"type": "literal", "value": "ok"},
            },
        }
    )
    planner = LLMPlanner(client)
    planner.plan("return literal", _node(), _env())
    assert client.last_payload is not None
    assert client.last_payload["environment"]["selected_global_contexts"] == []
    assert client.last_payload["environment"]["selected_bos"] == []
    assert client.last_payload["environment"]["selected_functions"] == []


def test_skeleton_parser_infers_flags_from_program_plan_payload() -> None:
    planner = LLMPlanner(StubOpenAIClient())
    skeleton = planner._parse_skeleton_payload(
        {
            "definitions": [],
            "return_expr": {
                "type": "function_call",
                "function_id": "Customer.GetSalutation",
                "args": [{"type": "context_ref", "path": "$ctx$.customer.gender"}],
            },
        }
    )
    assert isinstance(skeleton, PlannerSkeleton)
    assert skeleton.require_function is True
    assert skeleton.require_global_context is True


def test_planner_falls_back_to_legacy_plan_when_stages_fail() -> None:
    planner = LLMPlanner(
        StubOpenAIClient(
            stage_responses={"plan_skeleton": {"bad": "payload"}},
            plan_response={
                "definitions": [],
                "return_expr": {"type": "literal", "value": "legacy"},
            },
        )
    )
    plan = planner.plan("legacy fallback", _node(), _env())
    assert plan.return_expr.type == "literal"
    assert len(planner.plan_attempts) == 2
    assert planner.plan_attempts[-1].stage == "plan"
