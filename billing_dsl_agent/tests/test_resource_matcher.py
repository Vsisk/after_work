from billing_dsl_agent.services.resource_matcher import DefaultResourceMatcher
from billing_dsl_agent.types.bo import BODef
from billing_dsl_agent.types.common import ContextScope, DSLDataType
from billing_dsl_agent.types.context import ContextFieldDef, ContextVarDef
from billing_dsl_agent.types.function import FunctionDef
from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent, OperationIntent
from billing_dsl_agent.types.plan import ResolvedEnvironment


def test_resource_matcher_matches_context_bo_and_function() -> None:
    matcher = DefaultResourceMatcher()
    intent = NodeIntent(
        raw_requirement=(
            "使用 billStatement.prepareId 查询 SYS_BE，并调用 Common.Double2Str 进行格式化"
        ),
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[
            IntentSourceType.CONTEXT,
            IntentSourceType.BO_QUERY,
            IntentSourceType.FUNCTION,
        ],
        operations=[OperationIntent(op_type="query", description="select_one SYS_BE by prepareId")],
    )
    env = ResolvedEnvironment(
        global_context_vars=[
            ContextVarDef(
                name="billStatement",
                scope=ContextScope.GLOBAL,
                fields=[ContextFieldDef(name="prepareId")],
            )
        ],
        available_bos=[BODef(id="1", name="SYS_BE")],
        available_functions=[FunctionDef(id="f1", class_name="Common", method_name="Double2Str")],
    )

    binding = matcher.match(intent, env)

    assert binding.is_satisfied is True
    assert any(b.var_name == "billStatement" for b in binding.context_bindings)
    assert any(b.bo_name == "SYS_BE" for b in binding.bo_bindings)
    assert any(b.class_name == "Common" and b.method_name == "Double2Str" for b in binding.function_bindings)


def test_resource_matcher_sets_missing_resource_when_required_source_unmatched() -> None:
    matcher = DefaultResourceMatcher()
    intent = NodeIntent(
        raw_requirement="请从未知函数里取值",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.FUNCTION],
    )
    env = ResolvedEnvironment(available_functions=[])

    binding = matcher.match(intent, env)

    assert binding.is_satisfied is False
    assert any(m.resource_type == "function" for m in binding.missing_resources)
