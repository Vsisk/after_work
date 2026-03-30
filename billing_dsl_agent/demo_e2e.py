from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from billing_dsl_agent.llm_planner import PlannerDetailPayload, PlannerSkeletonPayload
from billing_dsl_agent.agent_entry import DSLAgent
from billing_dsl_agent.environment import EnvironmentBuilder
from billing_dsl_agent.llm_planner import LLMPlanner
from billing_dsl_agent.models import LLMAttemptRecord, LLMErrorRecord
from billing_dsl_agent.models import GenerateDSLRequest, GenerateDSLResponse, NodeDef
from billing_dsl_agent.resource_loader import InMemoryResourceProvider, ResourceLoader
from billing_dsl_agent.semantic_selector import OpenAISemanticSelector
from billing_dsl_agent.services.llm_client import OpenAILLMClient, StructuredExecutionResult

DEMO_SITE_ID = "demo-site"
DEMO_PROJECT_ID = "demo-project"
DEFAULT_REQUIREMENT = "generate title from customer gender"
DEFAULT_NODE_PATH = "$.children[0].children[0]"
DEFAULT_NODE_NAME = "title"
_DEMO_RESOURCE_PATH = Path(__file__).resolve().with_name("demo_virtual_resources.json")


def load_demo_resource_fixture() -> dict[str, Any]:
    return json.loads(_DEMO_RESOURCE_PATH.read_text(encoding="utf-8"))


def build_demo_dataset() -> dict[tuple[str, str], dict[str, Any]]:
    fixture = load_demo_resource_fixture()
    return {
        (str(fixture["site_id"]), str(fixture["project_id"])): dict(fixture["payload"]),
    }


def build_demo_request(
    *,
    requirement: str = DEFAULT_REQUIREMENT,
    node_path: str = DEFAULT_NODE_PATH,
    node_name: str = DEFAULT_NODE_NAME,
    node_id: str = "demo-node-001",
) -> GenerateDSLRequest:
    return GenerateDSLRequest(
        user_requirement=requirement,
        site_id=DEMO_SITE_ID,
        project_id=DEMO_PROJECT_ID,
        node_def=NodeDef(
            node_id=node_id,
            node_path=node_path,
            node_name=node_name,
            description="demo node for end-to-end DSL generation",
        ),
    )


class DemoStubLLMClient:
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
        payload = dict(prompt_params or {})
        if stage == "semantic_select":
            raw_response = self._semantic_select(payload)
        elif stage == "plan_skeleton":
            raw_response = self._plan_skeleton(payload)
        elif stage == "plan_detail":
            raw_response = self._plan_detail(payload)
        elif stage == "repair":
            raw_response = self._repair(payload)
        else:
            raw_response = self._plan(payload)

        parsed = None
        errors: list[LLMErrorRecord] = []
        if raw_response is not None:
            try:
                if response_parser is not None:
                    parsed = response_parser(raw_response)
                elif response_model is not None:
                    parsed = response_model.model_validate(raw_response)
            except Exception as exc:
                errors.append(
                    LLMErrorRecord(
                        stage=stage,
                        code="response_schema_error",
                        message=str(exc),
                        raw_payload=raw_response if isinstance(raw_response, dict) else None,
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
                request_payload=payload,
                response_payload=raw_response,
                parsed_ok=parsed is not None and not errors,
                errors=errors,
            ),
        )

    def _semantic_select(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidates = self._load_json(payload, "candidate_list_json") or []
        max_items = int(payload.get("max_items") or payload.get("input", {}).get("max_items") or 5)
        query_text = " ".join(
            [
                str(payload.get("task_type") or ""),
                str(payload.get("user_query") or ""),
                str(payload.get("node_def_json") or ""),
            ]
        ).lower()
        scored: list[tuple[float, str]] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            resource_id = str(item.get("resource_id") or "").strip()
            if not resource_id:
                continue
            text = " ".join(
                [
                    resource_id,
                    str(item.get("description") or ""),
                    " ".join(str(tag) for tag in item.get("tags") or []),
                ]
            ).lower()
            score = self._score_overlap(query_text, text)
            scored.append((score, resource_id))
        scored.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)
        selected = [resource_id for _, resource_id in scored[:max_items]]
        return {"resource_id_list": selected}

    def _plan_skeleton(self, payload: dict[str, Any]) -> dict[str, Any]:
        planner_context = self._load_json(payload, "planner_context_json") or {}
        user_query = str(planner_context.get("user_query") or "").lower()
        return PlannerSkeletonPayload.model_validate(
            {
                "expression_pattern": "function_call" if "title" in user_query or "salutation" in user_query else "query_call",
                "require_context": True,
                "require_bo": "fetch" in user_query or "query" in user_query,
                "require_function": "title" in user_query or "salutation" in user_query or "gender" in user_query,
                "require_local_context": False,
                "require_global_context": True,
                "require_namingsql": "fetch" in user_query,
                "require_binding": "fetch" in user_query,
                "notes": "demo stub skeleton",
            }
        ).model_dump(mode="python")

    def _plan_detail(self, payload: dict[str, Any]) -> dict[str, Any]:
        environment = payload.get("environment") or self._load_json(payload, "environment_json") or {}
        user_requirement = str(payload.get("user_requirement") or "").lower()
        plan_payload = self._plan({"user_requirement": user_requirement, "environment": environment})
        return PlannerDetailPayload.model_validate({"plan": plan_payload, "notes": "demo stub detail"}).model_dump(mode="python")

    def _plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        requirement = str(payload.get("user_requirement") or payload.get("input", {}).get("user_requirement") or "").lower()
        environment = payload.get("environment") or payload.get("input", {}).get("environment") or {}
        function_ids = set(environment.get("selected_function_ids") or [])
        context_ids = set(environment.get("selected_global_context_ids") or [])
        if "function:Customer.GetSalutation" in function_ids and (
            "title" in requirement or "salutation" in requirement or "gender" in requirement
        ):
            gender_path = self._resolve_context_path(environment, context_ids, suffix=".gender") or "$ctx$.customer.gender"
            return {
                "definitions": [],
                "return_expr": {
                    "type": "function_call",
                    "function_id": "function:Customer.GetSalutation",
                    "function_name": "Customer.GetSalutation",
                    "args": [{"type": "context_ref", "path": gender_path}],
                },
            }

        invoice_id_path = self._resolve_context_path(environment, context_ids, suffix=".id") or "$ctx$.customer.id"
        return {
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
                        "value": {"type": "context_ref", "path": invoice_id_path},
                    }
                ],
            },
        }

    def _repair(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        invalid_plan = payload.get("invalid_plan") or payload.get("input", {}).get("invalid_plan") or {}
        issues = payload.get("issues") or payload.get("input", {}).get("issues") or []
        issue_codes = {str(item.get("code") or "") for item in issues if isinstance(item, dict)}
        if "unknown_context_ref" not in issue_codes and "naming_sql_param_mismatch" not in issue_codes:
            return invalid_plan if isinstance(invalid_plan, dict) else None

        environment = payload.get("environment") or payload.get("input", {}).get("environment") or {}
        customer_id_path = self._resolve_context_path(environment, set(environment.get("selected_global_context_ids") or []), suffix=".id")
        if not isinstance(invalid_plan, dict):
            return None
        repaired = json.loads(json.dumps(invalid_plan))
        if "return_expr" in repaired and isinstance(repaired["return_expr"], dict):
            return_expr = repaired["return_expr"]
            if return_expr.get("type") == "query_call":
                if customer_id_path:
                    for pair in return_expr.get("pairs") or []:
                        if isinstance(pair, dict) and isinstance(pair.get("value"), dict):
                            pair["value"]["path"] = customer_id_path
                if "naming_sql_param_mismatch" in issue_codes:
                    return_expr["pairs"] = [
                        {
                            "key": "id",
                            "value": {"type": "context_ref", "path": customer_id_path or "$ctx$.customer.id"},
                        }
                    ]
            if return_expr.get("type") == "function_call" and customer_id_path:
                for arg in return_expr.get("args") or []:
                    if isinstance(arg, dict) and arg.get("type") == "context_ref":
                        arg["path"] = customer_id_path.replace(".id", ".gender")
        return repaired

    def _load_json(self, payload: dict[str, Any], key: str) -> Any:
        value = payload.get(key)
        if value is None and isinstance(payload.get("input"), dict):
            value = payload["input"].get(key)
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return value

    def _resolve_context_path(self, environment: dict[str, Any], context_ids: set[str], *, suffix: str) -> str | None:
        for item in environment.get("selected_global_contexts") or []:
            if not isinstance(item, dict):
                continue
            resource_id = str(item.get("resource_id") or "")
            path = str(item.get("path") or "")
            if resource_id in context_ids and path.endswith(suffix):
                return self._strip_demo_root(path)
        return None

    def _strip_demo_root(self, path: str) -> str:
        return re.sub(r"^\$ctx\$\.root\.", "$ctx$.", path)

    def _score_overlap(self, left: str, right: str) -> float:
        left_terms = {token for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", left) if token}
        right_terms = {token for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", right) if token}
        overlap = len(left_terms & right_terms)
        return overlap + (0.01 * len(right_terms))


class OpenAIExecutorAdapter:
    def __init__(self, client: OpenAILLMClient | None = None):
        self.client = client or OpenAILLMClient()

    def generate_raw(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: dict[str, Any] | None = None,
        response_format: dict[str, Any] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.client.invoke_raw(
            prompt_key=prompt_key,
            lang=lang,
            prompt_params=prompt_params,
            response_format=response_format,
            **kwargs,
        )

    def execute_structured(self, **kwargs: Any) -> Any:
        return self.client.execute_structured(**kwargs)


def build_demo_agent(mode: str = "stub") -> DSLAgent:
    dataset = build_demo_dataset()
    loader = ResourceLoader(provider=InMemoryResourceProvider(dataset=dataset))
    if mode == "openai":
        client = OpenAIExecutorAdapter()
    else:
        client = DemoStubLLMClient()

    planner = LLMPlanner(client=client, prompt_lang="en")
    selector = OpenAISemanticSelector(client=client, prompt_lang="en", default_top_k=5)
    environment_builder = EnvironmentBuilder(semantic_selector=selector)
    return DSLAgent(
        llm_planner=planner,
        resource_loader=loader,
        environment_builder=environment_builder,
    )


def run_demo(
    *,
    mode: str = "stub",
    requirement: str = DEFAULT_REQUIREMENT,
    node_path: str = DEFAULT_NODE_PATH,
    node_name: str = DEFAULT_NODE_NAME,
) -> GenerateDSLResponse:
    agent = build_demo_agent(mode=mode)
    request = build_demo_request(requirement=requirement, node_path=node_path, node_name=node_name)
    return agent.generate_dsl(request)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Billing DSL agent end-to-end with virtual demo resources.")
    parser.add_argument("--mode", choices=("stub", "openai"), default="stub", help="stub is deterministic; openai uses configured API credentials.")
    parser.add_argument("--requirement", default=DEFAULT_REQUIREMENT, help="User requirement sent into the DSL agent.")
    parser.add_argument("--node-path", default=DEFAULT_NODE_PATH, help="Target node path for generation.")
    parser.add_argument("--node-name", default=DEFAULT_NODE_NAME, help="Target node name for generation.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the full response JSON.")
    args = parser.parse_args(argv)

    response = run_demo(
        mode=args.mode,
        requirement=args.requirement,
        node_path=args.node_path,
        node_name=args.node_name,
    )

    if args.pretty:
        print(response.model_dump_json(indent=2, exclude_none=True))
    else:
        output = {
            "success": response.success,
            "dsl": response.dsl,
            "failure_reason": response.failure_reason,
            "plan_issue_codes": [item.code for item in (response.validation.issues if response.validation else [])],
            "selected_resources": response.debug.resource_selection.model_dump(mode="python") if response.debug and response.debug.resource_selection else None,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    return 0 if response.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
