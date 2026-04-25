from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from billing_dsl_agent.llm_planner import LLMPlanner, StubOpenAIClient
from billing_dsl_agent.models import (
    ContextResource,
    FilteredEnvironment,
    FunctionResource,
    LLMAttemptRecord,
    LLMErrorRecord,
    NodeDef,
    ProgramPlan,
    ResourceRegistry,
    ValidationIssue,
)
from billing_dsl_agent.services.llm_client import StructuredExecutionResult


def _env() -> FilteredEnvironment:
    return FilteredEnvironment(
        registry=ResourceRegistry(),
        selected_global_context_ids=["context:$ctx$.customer.gender"],
        selected_function_ids=["function:Customer.GetSalutation"],
        selected_global_contexts=[
            ContextResource(
                resource_id="context:$ctx$.customer.gender",
                name="gender",
                path="$ctx$.customer.gender",
            )
        ],
        selected_functions=[
            FunctionResource(
                resource_id="function:Customer.GetSalutation",
                function_id="function:Customer.GetSalutation",
                name="GetSalutation",
                full_name="Customer.GetSalutation",
            )
        ],
    )


def _node() -> NodeDef:
    return NodeDef(node_id="n1", node_path="invoice.customer.title", node_name="title")


def _plan_response() -> dict[str, Any]:
    return {
        "definitions": [
            {
                "kind": "variable",
                "name": "customer_gender",
                "expr": {"type": "context_ref", "path": "$ctx$.customer.gender"},
            }
        ],
        "return_expr": {
            "type": "function_call",
            "function_id": "function:Customer.GetSalutation",
            "args": [{"type": "var_ref", "name": "customer_gender"}],
        },
    }


@dataclass(slots=True)
class SequencedStubClient:
    responses: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    last_payload: dict[str, Any] | None = None

    def execute_structured(
        self,
        *,
        prompt_key: str,
        lang: str,
        prompt_params: dict[str, Any] | None,
        response_model: Any,
        stage: str,
        attempt_index: int = 1,
        response_parser: Any = None,
        **kwargs: Any,
    ) -> StructuredExecutionResult[Any]:
        self.last_payload = dict(prompt_params or {})
        stage_counter = self.counters.get(stage, 0)
        self.counters[stage] = stage_counter + 1
        payloads = self.responses.get(stage) or []
        raw_response = payloads[min(stage_counter, len(payloads) - 1)] if payloads else None
        parsed = None
        errors: list[LLMErrorRecord] = []
        if raw_response is not None:
            try:
                parsed = response_parser(raw_response) if response_parser else response_model.model_validate(raw_response)
            except Exception as exc:
                errors.append(
                    LLMErrorRecord(
                        stage=stage,
                        code="response_schema_error",
                        message=str(exc),
                        raw_payload=raw_response,
                        exception_type=type(exc).__name__,
                    )
                )
        return StructuredExecutionResult(
            parsed=parsed,
            errors=errors,
            raw_payload=raw_response,
            attempt=LLMAttemptRecord(
                stage=stage,
                attempt_index=attempt_index,
                request_payload=self.last_payload,
                response_payload=raw_response,
                parsed_ok=parsed is not None and not errors,
                errors=errors,
            ),
        )


def test_plan_returns_program_plan_from_single_stage() -> None:
    planner = LLMPlanner(StubOpenAIClient(plan_response=_plan_response()))

    plan = planner.plan("generate title", _node(), _env())

    assert isinstance(plan, ProgramPlan)
    assert plan.return_expr.type == "function_call"
    assert len(planner.plan_attempts) == 1
    assert planner.plan_attempts[0].stage == "plan"


def test_plan_retries_once_after_invalid_response() -> None:
    client = SequencedStubClient(responses={"plan": [{"bad": "payload"}, _plan_response()]})
    planner = LLMPlanner(client)

    plan = planner.plan("generate title", _node(), _env())

    assert plan.return_expr.type == "function_call"
    assert len(planner.plan_attempts) == 2


def test_plan_failure_returns_diagnostic_plan() -> None:
    planner = LLMPlanner(StubOpenAIClient())

    plan = planner.plan("generate title", _node(), _env())

    assert plan.return_expr.type == "literal"
    assert any(item.code == "plan_parse_failed" for item in plan.diagnostics)


def test_planner_repair_payload_contains_structured_issues() -> None:
    client = StubOpenAIClient(plan_response={"definitions": [], "return_expr": {"type": "literal", "value": "ok"}}, repair_response=_plan_response())
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
