from __future__ import annotations

from dataclasses import dataclass

from billing_dsl_agent.datatype_models import DatatypeKind, DatatypeValidationResult
from billing_dsl_agent.expression_ref_validator import ExpressionRefValidator
from billing_dsl_agent.models import FilteredEnvironment, ValidationIssue


@dataclass(slots=True)
class DatatypeValidator:
    expression_validator: ExpressionRefValidator

    def validate(self, datatype_obj: dict, env: FilteredEnvironment) -> DatatypeValidationResult:
        issues: list[ValidationIssue] = []
        if not isinstance(datatype_obj, dict):
            return DatatypeValidationResult(
                is_valid=False,
                issues=[ValidationIssue(code="datatype_not_object", message="datatype must be object", path="datatype")],
            )

        datatype_value = datatype_obj.get("data_type")
        if datatype_value not in {item.value for item in DatatypeKind}:
            issues.append(
                ValidationIssue(code="invalid_data_type", message=f"unsupported data_type: {datatype_value}", path="datatype.data_type")
            )
            return DatatypeValidationResult(is_valid=False, issues=issues)

        if datatype_value == DatatypeKind.SIMPLE_STRING.value:
            return DatatypeValidationResult(is_valid=True, issues=[])

        if datatype_value == DatatypeKind.TIME.value:
            issues.extend(self._require_keys(datatype_obj, ["region_id_expression", "time_format_expression"]))
            for key in ["region_id_expression", "time_format_expression"]:
                if key in datatype_obj:
                    issues.extend(self.expression_validator.validate(datatype_obj.get(key), env, f"datatype.{key}"))
            return DatatypeValidationResult(is_valid=not issues, issues=issues)

        if datatype_value == DatatypeKind.MONEY.value:
            required = [
                "currency_id_expression",
                "int_delimiter_expression",
                "intp_delimiter_expression",
                "round_method_expression",
                "currency_unit",
                "decimal_precision",
                "zero_padding",
            ]
            issues.extend(self._require_keys(datatype_obj, required))
            for key in ["currency_id_expression", "int_delimiter_expression", "intp_delimiter_expression", "round_method_expression"]:
                if key in datatype_obj:
                    issues.extend(self.expression_validator.validate(datatype_obj.get(key), env, f"datatype.{key}"))
            for key in ["currency_unit", "decimal_precision", "zero_padding"]:
                value = datatype_obj.get(key)
                if value is None or str(value).strip() == "":
                    issues.append(ValidationIssue(code="datatype_required_field_missing", message=f"{key} is required", path=f"datatype.{key}"))
            return DatatypeValidationResult(is_valid=not issues, issues=issues)

        return DatatypeValidationResult(is_valid=False, issues=issues)

    def _require_keys(self, payload: dict, keys: list[str]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for key in keys:
            value = payload.get(key)
            if value is None or (isinstance(value, str) and not value.strip()):
                issues.append(
                    ValidationIssue(
                        code="datatype_required_field_missing",
                        message=f"{key} is required",
                        path=f"datatype.{key}",
                    )
                )
        return issues

