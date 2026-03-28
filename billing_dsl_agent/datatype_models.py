from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field

from billing_dsl_agent.models import StrictModel, ValidationIssue


class DatatypeKind(str, Enum):
    SIMPLE_STRING = "simple_string"
    TIME = "time"
    MONEY = "money"


class SimpleStringDataType(StrictModel):
    data_type: Literal["simple_string"] = "simple_string"


class TimeDataType(StrictModel):
    data_type: Literal["time"] = "time"
    region_id_expression: str
    time_format_expression: str


class MoneyDataType(StrictModel):
    data_type: Literal["money"] = "money"
    currency_id_expression: str
    int_delimiter_expression: str
    intp_delimiter_expression: str
    round_method_expression: str
    currency_unit: str
    decimal_precision: str
    zero_padding: str


DataTypeModel = Annotated[
    SimpleStringDataType | TimeDataType | MoneyDataType,
    Field(discriminator="data_type"),
]


class DatatypeValidationResult(StrictModel):
    is_valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)

