from billing_dsl_agent.services.simple_requirement_parser import SimpleRequirementParser
from billing_dsl_agent.types.common import DSLDataType
from billing_dsl_agent.types.intent import IntentSourceType
from billing_dsl_agent.types.node import NodeDef

_REQ_DIRECT_CONTEXT = "\u53d6\u5f53\u524d\u8d26\u5355\u7684 prepareId"
_REQ_SELECT_ONE = (
    "\u6839\u636e prepareId \u548c billCycleId \u67e5\u8be2 BB_PREP_SUB\uff0c"
    "\u53d6\u7b2c\u4e00\u6761\u8bb0\u5f55\u7684 regionId"
)
_REQ_FUNCTION_WRAP = "\u5c06\u91d1\u989d\u683c\u5f0f\u5316\u4e3a\u4e24\u4f4d\u5c0f\u6570"
_REQ_CONDITIONAL = "\u5982\u679c\u8d26\u671f\u4e3a0\u5219\u8fd4\u56deA\uff0c\u5426\u5219\u8fd4\u56deB"
_REQ_CONDITIONAL_MAPPING = (
    "\u5f53\u5ba2\u6237\u6027\u522b\u4e3a\u7537\u65f6\uff0c\u663e\u793a\"MR.\"\uff0c"
    "\u5f53\u5ba2\u6237\u6027\u522b\u4e3a\u5973\u65f6\uff0c\u663e\u793a\"Ms.\""
)


def _build_node_def() -> NodeDef:
    return NodeDef(
        node_id="node-1",
        node_path="/bill/value",
        node_name="value",
        data_type=DSLDataType.STRING,
    )


def test_parse_direct_context_intent() -> None:
    parser = SimpleRequirementParser()

    intent = parser.parse(_REQ_DIRECT_CONTEXT, _build_node_def())

    assert intent.raw_requirement == _REQ_DIRECT_CONTEXT
    assert IntentSourceType.CONTEXT in intent.source_types
    assert any(op.op_type == "read_context" for op in intent.operations)
    assert intent.semantic_slots.get("context_field_hints") is not None
    assert "prepareId" in intent.semantic_slots["context_field_hints"]


def test_parse_select_one_field_access_intent() -> None:
    parser = SimpleRequirementParser()

    intent = parser.parse(_REQ_SELECT_ONE, _build_node_def())

    assert IntentSourceType.BO_QUERY in intent.source_types
    assert any(op.op_type == "query_bo_select_one" for op in intent.operations)
    assert intent.semantic_slots.get("bo_name") == "BB_PREP_SUB"
    assert intent.semantic_slots.get("query_mode") == "select_one"
    assert intent.semantic_slots.get("target_field") == "regionId"
    assert "prepareId" in intent.semantic_slots.get("context_field_hints", [])
    assert "billCycleId" in intent.semantic_slots.get("context_field_hints", [])


def test_parse_function_wrap_intent() -> None:
    parser = SimpleRequirementParser()

    intent = parser.parse(_REQ_FUNCTION_WRAP, _build_node_def())

    assert IntentSourceType.FUNCTION in intent.source_types
    assert IntentSourceType.EXPRESSION in intent.source_types
    assert any(op.op_type == "call_function" for op in intent.operations)
    assert intent.semantic_slots.get("function_name") == "format_decimal"
    assert intent.semantic_slots.get("format_precision") == 2
    assert 2 in intent.semantic_slots.get("function_args_hint", [])


def test_parse_conditional_intent() -> None:
    parser = SimpleRequirementParser()

    intent = parser.parse(_REQ_CONDITIONAL, _build_node_def())

    assert IntentSourceType.CONDITIONAL in intent.source_types
    assert any(op.op_type == "build_conditional" for op in intent.operations)
    assert intent.semantic_slots.get("condition_field_hint") == "\u8d26\u671f"
    assert intent.semantic_slots.get("condition_operator") == "=="
    assert intent.semantic_slots.get("condition_value") == "0"
    assert intent.semantic_slots.get("true_output") == "A"
    assert intent.semantic_slots.get("false_output") == "B"


def test_parse_conditional_mapping_intent() -> None:
    parser = SimpleRequirementParser()

    intent = parser.parse(_REQ_CONDITIONAL_MAPPING, _build_node_def())

    assert IntentSourceType.CONDITIONAL in intent.source_types
    assert any(op.op_type == "build_conditional_mapping" for op in intent.operations)
    assert intent.semantic_slots.get("conditional_mapping") is True
    assert intent.semantic_slots.get("condition_field_hint") == "\u5ba2\u6237\u6027\u522b"
    assert intent.semantic_slots.get("condition_operator") == "=="
    assert intent.semantic_slots.get("condition_value") == "\u7537"
    assert intent.semantic_slots.get("true_output") == "MR."
    assert intent.semantic_slots.get("false_output") == "Ms."
