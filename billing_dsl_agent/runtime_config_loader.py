from __future__ import annotations

from dataclasses import dataclass
import re

from pydantic import Field

from billing_dsl_agent.models import StrictModel


class TimeTypeDefaults(StrictModel):
    region_id_expression: str
    time_format_expression: str


class MoneyTypeDefaults(StrictModel):
    currency_id_expression: str
    int_delimiter_expression: str
    intp_delimiter_expression: str
    round_method_expression: str
    currency_unit: str
    decimal_precision: str
    zero_padding: str


class FlowTypeDefaults(StrictModel):
    flow_type_expression: str


class DatatypeDefaults(StrictModel):
    time: TimeTypeDefaults | None = None
    money: MoneyTypeDefaults | None = None
    flow: FlowTypeDefaults | None = None


class RuntimeConfig(StrictModel):
    datatype_defaults: DatatypeDefaults = Field(default_factory=DatatypeDefaults)


@dataclass(slots=True)
class RuntimeConfigLoader:
    """Load and normalize stable runtime datatype defaults from global_config."""

    def load(self, global_config: dict | None) -> RuntimeConfig:
        config = global_config or {}
        site_level = config.get("site_level_config") or {}
        defaults = DatatypeDefaults(
            time=self._load_time_defaults(site_level.get("time_type_config")),
            money=self._load_money_defaults(site_level.get("money_type_config")),
            flow=self._load_flow_defaults(site_level.get("flow_type_config")),
        )
        return RuntimeConfig(datatype_defaults=defaults)

    def _load_time_defaults(self, payload: dict | None) -> TimeTypeDefaults | None:
        if payload is None:
            return None
        data = TimeTypeDefaults.model_validate(payload)
        self._validate_expression(data.region_id_expression, "time_type_config.region_id_expression")
        self._validate_expression(data.time_format_expression, "time_type_config.time_format_expression")
        return data

    def _load_money_defaults(self, payload: dict | None) -> MoneyTypeDefaults | None:
        if payload is None:
            return None
        data = MoneyTypeDefaults.model_validate(payload)
        self._validate_expression(data.currency_id_expression, "money_type_config.currency_id_expression")
        self._validate_expression(data.int_delimiter_expression, "money_type_config.int_delimiter_expression")
        self._validate_expression(data.intp_delimiter_expression, "money_type_config.intp_delimiter_expression")
        self._validate_expression(data.round_method_expression, "money_type_config.round_method_expression")
        for field_name in ("currency_unit", "decimal_precision", "zero_padding"):
            value = getattr(data, field_name)
            if not str(value).strip():
                raise ValueError(f"money_type_config.{field_name} must not be empty")
        return data

    def _load_flow_defaults(self, payload: dict | None) -> FlowTypeDefaults | None:
        if payload is None:
            return None
        data = FlowTypeDefaults.model_validate(payload)
        self._validate_expression(data.flow_type_expression, "flow_type_config.flow_type_expression")
        return data

    def _validate_expression(self, expression: str, field_name: str) -> None:
        value = (expression or "").strip()
        if not value:
            raise ValueError(f"{field_name} must not be empty")
        if value.lower() in {"null", "none", "unknown", "tbd", "fake", "fake path"}:
            raise ValueError(f"{field_name} has forbidden placeholder value: {value}")
        if value.startswith("$ctx$."):
            if not re.match(r"^\$ctx\$\.[A-Za-z_][A-Za-z0-9_$.]*$", value):
                raise ValueError(f"{field_name} has invalid context expression: {value}")
            return
        if re.match(r'^".*"$|^\'.*\'$', value) or re.match(r"^-?\d+(?:\.\d+)?$", value):
            return
        raise ValueError(f"{field_name} has invalid expression literal: {value}")
