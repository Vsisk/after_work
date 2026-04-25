from billing_dsl_agent.environment import EnvironmentBuilder
from billing_dsl_agent.models import (
    BOResource,
    ContextResource,
    FunctionResource,
    NodeDef,
    ResourceRegistry,
)
from billing_dsl_agent.semantic_selector import MockSemanticSelector


def test_environment_builder_signature_and_debug_strategy_remain_compatible() -> None:
    registry = ResourceRegistry(
        contexts={
            "context:$ctx$.billCycleId": ContextResource(
                resource_id="context:$ctx$.billCycleId",
                name="billCycleId",
                path="$ctx$.billCycleId",
                scope="global",
                domain="billing",
                description="账期标识",
            )
        },
        bos={
            "bo:BillBO": BOResource(
                resource_id="bo:BillBO",
                bo_name="BillBO",
                field_ids=["billCycleId"],
                domain="billing",
                description="账单对象",
            )
        },
        functions={
            "function:Currency.GetRate": FunctionResource(
                resource_id="function:Currency.GetRate",
                function_id="function:Currency.GetRate",
                name="GetRate",
                full_name="Currency.GetRate",
                description="查询汇率",
                return_type="decimal",
            )
        },
        edsl_tree={"node_type": "leaf", "id": "root"},
    )
    builder = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=5))
    filtered = builder.build_filtered_environment(
        node_info=NodeDef(node_id="n1", node_path="$", node_name="rate", description="根据账期查询汇率"),
        user_query="根据账期查询汇率",
        registry=registry,
    )

    assert filtered.selected_global_context_ids == ["context:$ctx$.billCycleId"]
    assert filtered.selected_bo_ids == ["bo:BillBO"]
    assert filtered.selected_function_ids == ["function:Currency.GetRate"]
    assert filtered.selection_debug is not None
    assert filtered.selection_debug.global_context.strategy == "id_summary_plus_selector"
    assert filtered.selection_debug.bo.strategy == "id_summary_plus_selector"
    assert filtered.selection_debug.function.strategy == "id_summary_plus_selector"
    assert filtered.selection_debug.local_context.strategy == "rule_only"
    assert filtered.selection_debug.global_context.retrieval_debug["resource_type"] == "context"
