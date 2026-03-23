from billing_dsl_agent.services.resource_matcher import DefaultResourceMatcher
from billing_dsl_agent.types.bo import BODef, BOFieldDef
from billing_dsl_agent.types.common import ContextScope, DSLDataType, QueryMode, TypeRef
from billing_dsl_agent.types.context import ContextFieldDef, ContextVarDef
from billing_dsl_agent.types.function import FunctionDef
from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent
from billing_dsl_agent.types.plan import ResolvedEnvironment


def test_match_context_field_hint() -> None:
    matcher = DefaultResourceMatcher()
    intent = NodeIntent(
        raw_requirement="\u53d6\u5f53\u524d\u8d26\u5355\u7684 prepareId",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.CONTEXT],
        semantic_slots={"context_field_hints": ["prepareId"]},
    )
    env = ResolvedEnvironment(
        global_context_vars=[
            ContextVarDef(
                name="billStatement",
                scope=ContextScope.GLOBAL,
                fields=[ContextFieldDef(name="prepareId", data_type=DSLDataType.STRING)],
            )
        ]
    )

    binding = matcher.match(intent, env)

    assert binding.is_satisfied is True
    assert len(binding.context_bindings) == 1
    assert binding.context_bindings[0].var_name == "billStatement"
    assert binding.context_bindings[0].field_name == "prepareId"
    assert binding.semantic_bindings["context:prepareId"] == "$ctx$.billStatement.prepareId"


def test_match_select_one_bo_and_field() -> None:
    matcher = DefaultResourceMatcher()
    intent = NodeIntent(
        raw_requirement="\u67e5\u8be2 BB_PREP_SUB \u53d6\u7b2c\u4e00\u6761\u8bb0\u5f55\u7684 regionId",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.BO_QUERY],
        semantic_slots={
            "bo_name": "BB_PREP_SUB",
            "query_mode": "select_one",
            "target_field": "regionId",
        },
    )
    env = ResolvedEnvironment(
        available_bos=[
            BODef(
                id="bo_1",
                name="BB_PREP_SUB",
                fields=[
                    BOFieldDef(name="regionId", type=TypeRef(kind="basic", name="string")),
                    BOFieldDef(name="prepareId", type=TypeRef(kind="basic", name="string")),
                ],
            )
        ]
    )

    binding = matcher.match(intent, env)

    assert binding.is_satisfied is True
    assert len(binding.bo_bindings) == 1
    assert binding.bo_bindings[0].bo_name == "BB_PREP_SUB"
    assert binding.bo_bindings[0].query_mode == QueryMode.SELECT_ONE
    assert binding.bo_bindings[0].selected_field_names == ["regionId"]
    assert binding.semantic_bindings["bo_name"] == "BB_PREP_SUB"
    assert binding.semantic_bindings["target_field"] == "regionId"


def test_match_function_by_name() -> None:
    matcher = DefaultResourceMatcher()
    intent = NodeIntent(
        raw_requirement="\u5bf9\u67d0\u503c\u8c03\u7528 Common.Double2Str",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.FUNCTION],
        semantic_slots={"function_name": "Common.Double2Str"},
    )
    env = ResolvedEnvironment(
        available_functions=[
            FunctionDef(id="fn_1", class_name="Common", method_name="Double2Str"),
            FunctionDef(id="fn_2", class_name="Common", method_name="Trim"),
        ]
    )

    binding = matcher.match(intent, env)

    assert binding.is_satisfied is True
    assert len(binding.function_bindings) == 1
    assert binding.function_bindings[0].class_name == "Common"
    assert binding.function_bindings[0].method_name == "Double2Str"
    assert binding.semantic_bindings["function_name"] == "Common.Double2Str"


def test_match_conditional_mapping_field() -> None:
    matcher = DefaultResourceMatcher()
    intent = NodeIntent(
        raw_requirement="\u5f53\u5ba2\u6237\u6027\u522b\u4e3a\u7537\u65f6\uff0c\u663e\u793aMR.",
        target_node_path="/customer/title",
        target_node_name="title",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.CONDITIONAL, IntentSourceType.CONTEXT],
        semantic_slots={
            "condition_field_hint": "\u5ba2\u6237\u6027\u522b",
            "condition_operator": "==",
            "condition_value": "\u7537",
        },
    )
    env = ResolvedEnvironment(
        global_context_vars=[
            ContextVarDef(
                name="customer",
                scope=ContextScope.GLOBAL,
                fields=[
                    ContextFieldDef(name="gender", data_type=DSLDataType.STRING),
                    ContextFieldDef(name="name", data_type=DSLDataType.STRING),
                ],
            )
        ]
    )

    binding = matcher.match(intent, env)

    assert binding.is_satisfied is True
    assert any(item.var_name == "customer" and item.field_name == "gender" for item in binding.context_bindings)
    assert binding.semantic_bindings["condition_field"] == "$ctx$.customer.gender"


def test_match_missing_resource_should_not_crash() -> None:
    matcher = DefaultResourceMatcher()
    intent = NodeIntent(
        raw_requirement="\u67e5\u8be2 UNKNOWN_BO \u53d6 regionId \u5e76\u8c03\u7528 Missing.Func",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.BO_QUERY, IntentSourceType.FUNCTION, IntentSourceType.CONTEXT],
        semantic_slots={
            "bo_name": "UNKNOWN_BO",
            "target_field": "regionId",
            "function_name": "Missing.Func",
            "context_field_hints": ["prepareId"],
        },
    )
    env = ResolvedEnvironment(
        global_context_vars=[],
        available_bos=[],
        available_functions=[],
    )

    binding = matcher.match(intent, env)

    assert binding.is_satisfied is False
    assert binding.context_bindings == []
    assert binding.bo_bindings == []
    assert binding.function_bindings == []
    assert any(item.resource_type == "context" for item in binding.missing_resources)
    assert any(item.resource_type == "bo" for item in binding.missing_resources)
    assert any(item.resource_type == "function" for item in binding.missing_resources)
