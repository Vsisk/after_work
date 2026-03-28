from __future__ import annotations

from dataclasses import dataclass

from billing_dsl_agent.datatype_models import DatatypeKind
from billing_dsl_agent.models import FilteredEnvironment, NodeDef, ProgramPlan
from billing_dsl_agent.runtime_config_loader import DatatypeDefaults


MONEY_KEYWORDS = (
    "金额",
    "货币",
    "币种",
    "money",
    "currency",
    "amount",
    "小数",
    "保留",
)
TIME_KEYWORDS = (
    "时间",
    "日期",
    "时区",
    "format time",
    "time format",
    "date",
    "timestamp",
)


@dataclass(slots=True)
class DatatypeClassifier:
    """Rule-first datatype classifier; can be extended with LLM fallback later."""

    def classify(
        self,
        user_query: str,
        node_info: NodeDef,
        value_plan: ProgramPlan,
        candidate_resources: FilteredEnvironment,
        datatype_defaults: DatatypeDefaults,
    ) -> DatatypeKind:
        query = (user_query or "").lower()
        text = " ".join([query, (node_info.node_name or "").lower(), (node_info.description or "").lower()])

        if any(keyword.lower() in text for keyword in MONEY_KEYWORDS):
            return DatatypeKind.MONEY
        if any(keyword.lower() in text for keyword in TIME_KEYWORDS):
            return DatatypeKind.TIME
        return DatatypeKind.SIMPLE_STRING

