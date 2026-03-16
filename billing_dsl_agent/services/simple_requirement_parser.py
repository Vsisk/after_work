"""Rule-based mock requirement parser for MVP usage."""

from __future__ import annotations

from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent, OperationIntent
from billing_dsl_agent.types.node import NodeDef


class SimpleRequirementParser:
    """Parse requirement text into NodeIntent with lightweight keyword rules."""

    def parse(self, user_requirement: str, node_def: NodeDef) -> NodeIntent:
        text = (user_requirement or "").strip()
        lower = text.lower()

        source_types: list[IntentSourceType] = []
        operations: list[OperationIntent] = []

        if "context" in lower or "$ctx$" in lower or "上下文" in text:
            source_types.append(IntentSourceType.CONTEXT)
        if "local" in lower or "$local$" in lower or "局部" in text:
            source_types.append(IntentSourceType.LOCAL_CONTEXT)

        if "select_one" in lower:
            source_types.append(IntentSourceType.BO_QUERY)
            operations.append(OperationIntent(op_type="select_one", description="select_one query"))
        elif "select" in lower:
            source_types.append(IntentSourceType.BO_QUERY)
            operations.append(OperationIntent(op_type="select", description="select query"))

        if "fetch_one" in lower:
            source_types.append(IntentSourceType.NAMING_SQL)
            operations.append(OperationIntent(op_type="fetch_one", description="fetch_one query"))
        elif "fetch" in lower:
            source_types.append(IntentSourceType.NAMING_SQL)
            operations.append(OperationIntent(op_type="fetch", description="fetch query"))

        if "if" in lower or "条件" in text:
            source_types.append(IntentSourceType.CONDITIONAL)
            operations.append(OperationIntent(op_type="if", description="conditional expression"))

        if "exists" in lower:
            source_types.append(IntentSourceType.FUNCTION)
            operations.append(OperationIntent(op_type="exists", description="exists function"))

        if "(" in text or ")" in text or "函数" in text:
            source_types.append(IntentSourceType.FUNCTION)

        dedup_sources = list(dict.fromkeys(source_types))

        return NodeIntent(
            raw_requirement=text,
            target_node_path=node_def.node_path,
            target_node_name=node_def.node_name,
            target_data_type=node_def.data_type,
            source_types=dedup_sources,
            operations=operations,
        )
