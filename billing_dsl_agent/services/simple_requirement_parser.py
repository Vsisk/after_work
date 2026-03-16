"""Rule-based mock requirement parser for MVP usage."""

from __future__ import annotations

import re
from typing import List, Sequence

from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent, OperationIntent
from billing_dsl_agent.types.node import NodeDef


class SimpleRequirementParser:
    """Parse requirement text into NodeIntent with lightweight keyword rules."""

    _CONTEXT_KEYWORDS: Sequence[str] = ("$ctx$", "ctx", "context", "全局上下文")
    _LOCAL_CONTEXT_KEYWORDS: Sequence[str] = ("$local$", "local", "局部上下文")
    _BO_QUERY_KEYWORDS: Sequence[str] = ("select", "select_one", "查询", "查表")
    _NAMING_SQL_KEYWORDS: Sequence[str] = ("fetch", "fetch_one", "naming sql", "namingsql")
    _FUNCTION_KEYWORDS: Sequence[str] = ("if", "exists", "concat", "merge_list")
    _CONDITIONAL_KEYWORDS: Sequence[str] = ("if", "如果", "否则", "判断")
    _EXPRESSION_KEYWORDS: Sequence[str] = ("拼接", "计算", "表达式", "format", "格式化")

    def parse(self, user_requirement: str, node_def: NodeDef) -> NodeIntent:
        """Parse text requirement into a stable NodeIntent using simple rules."""

        raw_text = (user_requirement or "").strip()
        normalized_text = self._normalize_requirement_text(raw_text)

        source_types = self._detect_source_types(raw_text=raw_text, normalized_text=normalized_text)
        operations = self._detect_operations(
            raw_text=raw_text,
            normalized_text=normalized_text,
            source_types=source_types,
        )
        constraints = self._detect_constraints(raw_text=raw_text, normalized_text=normalized_text)

        return NodeIntent(
            raw_requirement=raw_text,
            target_node_path=node_def.node_path,
            target_node_name=node_def.node_name,
            target_data_type=node_def.data_type,
            source_types=source_types,
            operations=operations,
            constraints=constraints,
        )

    def _normalize_requirement_text(self, text: str) -> str:
        """Lowercase and collapse multi-space text for stable keyword matching."""

        return " ".join(text.lower().split())

    def _detect_source_types(self, raw_text: str, normalized_text: str) -> List[IntentSourceType]:
        """Infer source types from requirement keywords and function-like tokens."""

        source_types: List[IntentSourceType] = []

        if self._contains_any(raw_text, normalized_text, self._CONTEXT_KEYWORDS):
            source_types.append(IntentSourceType.CONTEXT)
        if self._contains_any(raw_text, normalized_text, self._LOCAL_CONTEXT_KEYWORDS):
            source_types.append(IntentSourceType.LOCAL_CONTEXT)
        if self._contains_any(raw_text, normalized_text, self._BO_QUERY_KEYWORDS):
            source_types.append(IntentSourceType.BO_QUERY)
        if self._contains_any(raw_text, normalized_text, self._NAMING_SQL_KEYWORDS):
            source_types.append(IntentSourceType.NAMING_SQL)

        function_like_tokens = self._extract_function_like_tokens(raw_text)
        if function_like_tokens or self._contains_any(raw_text, normalized_text, self._FUNCTION_KEYWORDS):
            source_types.append(IntentSourceType.FUNCTION)

        if self._contains_any(raw_text, normalized_text, self._EXPRESSION_KEYWORDS):
            source_types.append(IntentSourceType.EXPRESSION)
        if self._contains_any(raw_text, normalized_text, self._CONDITIONAL_KEYWORDS):
            source_types.append(IntentSourceType.CONDITIONAL)

        return self._dedup_source_types(source_types)

    def _detect_operations(
        self,
        raw_text: str,
        normalized_text: str,
        source_types: Sequence[IntentSourceType],
    ) -> List[OperationIntent]:
        """Build operation intents from detected source types and keywords."""

        operations: List[OperationIntent] = []

        if IntentSourceType.CONTEXT in source_types:
            operations.append(
                OperationIntent(
                    op_type="read_context",
                    description="Read value from global context.",
                    expected_inputs=["context_path_or_name"],
                )
            )

        if IntentSourceType.LOCAL_CONTEXT in source_types:
            operations.append(
                OperationIntent(
                    op_type="read_local_context",
                    description="Read value from local context.",
                    expected_inputs=["local_context_path_or_name"],
                )
            )

        if IntentSourceType.BO_QUERY in source_types:
            op_type = "query_bo"
            if "select_one" in normalized_text:
                op_type = "query_bo_select_one"
            elif "select" in normalized_text:
                op_type = "query_bo_select"
            operations.append(
                OperationIntent(
                    op_type=op_type,
                    description="Query BO resources.",
                    expected_inputs=["bo_name", "conditions"],
                )
            )

        if IntentSourceType.NAMING_SQL in source_types:
            op_type = "query_naming_sql"
            if "fetch_one" in normalized_text:
                op_type = "query_naming_sql_fetch_one"
            elif "fetch" in normalized_text:
                op_type = "query_naming_sql_fetch"
            operations.append(
                OperationIntent(
                    op_type=op_type,
                    description="Query naming sql resources.",
                    expected_inputs=["naming_sql_name", "params"],
                )
            )

        if IntentSourceType.FUNCTION in source_types:
            function_candidates = self._extract_function_like_tokens(raw_text)
            operations.append(
                OperationIntent(
                    op_type="call_function",
                    description="Call function candidate from requirement text.",
                    expected_inputs=function_candidates or ["function_name"],
                )
            )

        if IntentSourceType.EXPRESSION in source_types:
            operations.append(
                OperationIntent(
                    op_type="build_expression",
                    description="Build expression from requirement.",
                    expected_inputs=["expression_parts"],
                )
            )

        if IntentSourceType.CONDITIONAL in source_types:
            operations.append(
                OperationIntent(
                    op_type="build_conditional",
                    description="Build if/else conditional expression.",
                    expected_inputs=["condition", "true_expr", "false_expr"],
                )
            )

        if not operations:
            operations.append(
                OperationIntent(
                    op_type="interpret_requirement",
                    description="No explicit keyword matched; interpret plain requirement.",
                    expected_inputs=["requirement_text"],
                )
            )

        return self._dedup_operations(operations)

    def _detect_constraints(self, raw_text: str, normalized_text: str) -> List[str]:
        """Extract minimal constraints from obvious requirement hints."""

        constraints: List[str] = []
        if "不能为空" in raw_text or "not null" in normalized_text:
            constraints.append("result_must_not_be_null")
        if "默认" in raw_text or "default" in normalized_text:
            constraints.append("should_have_default_fallback")
        return constraints

    @staticmethod
    def _contains_any(raw_text: str, normalized_text: str, probes: Sequence[str]) -> bool:
        """Return True when any probe appears in raw or normalized text."""

        return any(probe in raw_text or probe in normalized_text for probe in probes)

    @staticmethod
    def _extract_function_like_tokens(text: str) -> List[str]:
        """Extract tokens like `ClassName.MethodName` as function candidates."""

        pattern = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
        return [match.group(0) for match in pattern.finditer(text or "")]

    @staticmethod
    def _dedup_source_types(source_types: Sequence[IntentSourceType]) -> List[IntentSourceType]:
        """Deduplicate source types while keeping first appearance order."""

        deduped: List[IntentSourceType] = []
        seen: set[IntentSourceType] = set()
        for source in source_types:
            if source not in seen:
                seen.add(source)
                deduped.append(source)
        return deduped

    @staticmethod
    def _dedup_operations(operations: Sequence[OperationIntent]) -> List[OperationIntent]:
        """Deduplicate operations by op_type while keeping first operation."""

        deduped: List[OperationIntent] = []
        seen: set[str] = set()
        for op in operations:
            if op.op_type not in seen:
                seen.add(op.op_type)
                deduped.append(op)
        return deduped
