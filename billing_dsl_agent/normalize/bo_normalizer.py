"""BO normalization placeholders."""

from __future__ import annotations

from typing import Any

from billing_dsl_agent.types.bo import BODef, BOFieldDef, BOQueryCapability, BORegistry, NamingSQLDef
from billing_dsl_agent.types.common import ParameterDef, TypeRef


def normalize_bo_registry(raw_bo_data: dict[str, Any]) -> BORegistry:
    """Normalize raw BO payload into BORegistry.

    Conversion notes:
    - `sys_bo_list` -> `system_bos`, `custom_bo_list` -> `custom_bos`.
    - BO fields usually come from `or_mapping_list` entries mapped into `BOFieldDef`.
    - namingSQL definitions come from `naming_sql_list` with params from `param_list`.
    - Raw keys like `bo_desc`, `bo_name`, `is_virtual_bo`, `is_monthly`,
      `sql_command`, `sql_description`, `sql_name`, `naming_sql_id` are mapped
      into structured fields and metadata.
    """

    def _normalize_param(raw_param: dict[str, Any]) -> ParameterDef:
        return ParameterDef(
            name=str(raw_param.get("param_name", "")),
            type=TypeRef(
                kind=str(raw_param.get("data_type", "unknown")),
                name=str(raw_param.get("data_type_name", "UNKNOWN")),
                is_list=bool(raw_param.get("is_list", False)),
            ),
        )

    def _normalize_naming_sql(raw_sql: dict[str, Any]) -> NamingSQLDef:
        return NamingSQLDef(
            id=str(raw_sql.get("naming_sql_id", "")),
            name=str(raw_sql.get("sql_name", "")),
            description=str(raw_sql.get("sql_description", "")),
            sql=str(raw_sql.get("sql_command", "")),
            params=[_normalize_param(p) for p in raw_sql.get("param_list", [])],
            metadata={"raw": raw_sql},
        )

    def _normalize_bo(raw_bo: dict[str, Any], source: str) -> BODef:
        fields = [
            BOFieldDef(
                name=str(item.get("param_name", item.get("name", ""))),
                type=TypeRef(
                    kind=str(item.get("data_type", "unknown")),
                    name=str(item.get("data_type_name", "UNKNOWN")),
                    is_list=bool(item.get("is_list", False)),
                ),
            )
            for item in raw_bo.get("or_mapping_list", [])
        ]
        naming_sqls = [_normalize_naming_sql(item) for item in raw_bo.get("naming_sql_list", [])]
        return BODef(
            id=raw_bo.get("bo_id"),
            name=str(raw_bo.get("bo_name", "")),
            description=str(raw_bo.get("bo_desc", "")),
            source=source,
            is_virtual=bool(raw_bo.get("is_virtual_bo", False)),
            fields=fields,
            query_capability=BOQueryCapability(naming_sqls=naming_sqls),
            metadata={"is_monthly": raw_bo.get("is_monthly"), "raw": raw_bo},
        )

    system_bos = [_normalize_bo(raw, "system") for raw in raw_bo_data.get("sys_bo_list", [])]
    custom_bos = [_normalize_bo(raw, "custom") for raw in raw_bo_data.get("custom_bo_list", [])]
    return BORegistry(system_bos=system_bos, custom_bos=custom_bos)
