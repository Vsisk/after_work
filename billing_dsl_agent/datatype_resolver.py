from __future__ import annotations

import re
from dataclasses import dataclass

from billing_dsl_agent.datatype_models import DatatypeKind
from billing_dsl_agent.models import FilteredEnvironment, NodeDef
from billing_dsl_agent.runtime_config_loader import RuntimeConfig


TIME_FORMAT_RE = re.compile(r"(?P<format>y{2,4}[-/]?M{1,2}[-/]?d{1,2}(?:[\sT:]?H{1,2}:?m{1,2}:?s{1,2})?)", re.IGNORECASE)
CTX_PATH_RE = re.compile(r"\$ctx\$\.[A-Za-z_][A-Za-z0-9_$.]*")


@dataclass(slots=True)
class DatatypeResolver:
    """Resolve datatype object with defaults-first strategy and minimal overrides."""

    def resolve(
        self,
        datatype_kind: DatatypeKind,
        runtime_config: RuntimeConfig,
        user_query: str,
        node_info: NodeDef,
        candidate_resources: FilteredEnvironment,
    ) -> dict:
        defaults = runtime_config.datatype_defaults
        query = user_query or ""

        if datatype_kind == DatatypeKind.SIMPLE_STRING:
            return {"data_type": DatatypeKind.SIMPLE_STRING.value}

        if datatype_kind == DatatypeKind.TIME:
            if defaults.time is None:
                raise ValueError("time datatype defaults missing in runtime config")
            data = defaults.time.model_dump()
            explicit_format = self._extract_time_format(query)
            if explicit_format:
                data["time_format_expression"] = f'"{explicit_format}"'
            data["data_type"] = DatatypeKind.TIME.value
            return data

        if datatype_kind == DatatypeKind.MONEY:
            if defaults.money is None:
                raise ValueError("money datatype defaults missing in runtime config")
            data = defaults.money.model_dump()
            override_currency_expr = self._extract_currency_expression(query)
            if override_currency_expr:
                data["currency_id_expression"] = override_currency_expr
            data["data_type"] = DatatypeKind.MONEY.value
            return data

        raise ValueError(f"unsupported datatype kind: {datatype_kind}")

    def _extract_time_format(self, user_query: str) -> str | None:
        match = TIME_FORMAT_RE.search(user_query)
        if match:
            return match.group("format")
        return None

    def _extract_currency_expression(self, user_query: str) -> str | None:
        lower_query = user_query.lower()
        if "币种" not in user_query and "currency" not in lower_query:
            return None
        for token in CTX_PATH_RE.findall(user_query):
            if "currency" in token.lower() or "币种" in user_query:
                return token
        return None

