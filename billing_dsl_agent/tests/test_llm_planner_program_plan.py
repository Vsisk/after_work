from billing_dsl_agent.llm_planner import LLMPlanner, StubOpenAIClient
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
        plan_response={
            "definitions": [
                {
                    "kind": "variable",
                    "name": "customer_gender",
                    "expr": {"type": "context_ref", "path": "$ctx$.customer.gender"},
                }
            ],
            "return_expr": {"type": "var_ref", "name": "customer_gender"},
        }
    )
    planner = LLMPlanner(client)
    plan = planner.plan("generate title", _node(), _env())
    assert plan.definitions[0].name == "customer_gender"
    assert plan.return_expr.type == "var_ref"
    assert client.last_payload is not None
    assert client.last_payload["environment"]["selected_function_ids"] == ["function:Customer.GetSalutation"]
    assert client.last_payload["environment"]["selected_functions"][0]["resource_id"] == "function:Customer.GetSalutation"


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
        plan_response={
            "definitions": [],
            "return_expr": {"type": "literal", "value": "ok"},
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
