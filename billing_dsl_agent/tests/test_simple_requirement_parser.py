from billing_dsl_agent.services.simple_requirement_parser import SimpleRequirementParser
from billing_dsl_agent.types.common import DSLDataType
from billing_dsl_agent.types.intent import IntentSourceType
from billing_dsl_agent.types.node import NodeDef


def _build_node_def() -> NodeDef:
    return NodeDef(
        node_id="node-1",
        node_path="/bill/value",
        node_name="value",
        data_type=DSLDataType.STRING,
    )


def test_parse_context_requirement() -> None:
    parser = SimpleRequirementParser()

    intent = parser.parse(
        user_requirement="请从全局上下文 $ctx$.billStatement.prepareId 和 local input 取值",
        node_def=_build_node_def(),
    )

    assert IntentSourceType.CONTEXT in intent.source_types
    assert IntentSourceType.LOCAL_CONTEXT in intent.source_types
    assert any(op.op_type == "read_context" for op in intent.operations)
    assert any(op.op_type == "read_local_context" for op in intent.operations)


def test_parse_query_requirement() -> None:
    parser = SimpleRequirementParser()

    intent = parser.parse(
        user_requirement="select_one SYS_BE 后再 fetch naming sql queryById 做查询",
        node_def=_build_node_def(),
    )

    assert IntentSourceType.BO_QUERY in intent.source_types
    assert IntentSourceType.NAMING_SQL in intent.source_types
    assert any(op.op_type.startswith("query_bo") for op in intent.operations)
    assert any(op.op_type.startswith("query_naming_sql") for op in intent.operations)


def test_parse_function_and_conditional_requirement() -> None:
    parser = SimpleRequirementParser()

    intent = parser.parse(
        user_requirement="如果 exists 则用 Common.Double2Str format 金额，否则拼接默认值",
        node_def=_build_node_def(),
    )

    assert IntentSourceType.FUNCTION in intent.source_types
    assert IntentSourceType.CONDITIONAL in intent.source_types
    assert IntentSourceType.EXPRESSION in intent.source_types
    assert any(op.op_type == "call_function" for op in intent.operations)
    assert any(op.op_type == "build_conditional" for op in intent.operations)


def test_parse_requirement_should_not_crash_on_plain_text() -> None:
    parser = SimpleRequirementParser()

    intent = parser.parse(
        user_requirement="请帮我生成账单节点结果",
        node_def=_build_node_def(),
    )

    assert intent.raw_requirement == "请帮我生成账单节点结果"
    assert intent.target_node_path == "/bill/value"
    assert intent.target_node_name == "value"
    assert intent.target_data_type == DSLDataType.STRING
    assert len(intent.operations) >= 1
