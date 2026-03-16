"""BO normalization placeholders."""

from __future__ import annotations

from typing import Any, Iterable

from billing_dsl_agent.types.bo import BODef, BOFieldDef, BOQueryCapability, BORegistry, NamingSQLDef
from billing_dsl_agent.types.common import ParameterDef, TypeRef


def normalize_bo_registry(raw_bo_data: dict[str, Any]) -> BORegistry:
    """Normalize raw BO payload into BORegistry.

    Conversion notes:
    - `sys_bo_list` -> `system_bos`, `custom_bo_list` -> `custom_bos`.
    - BO fields are parsed from `or_mapping_list` when mapping entries include
      field-like descriptors (`param_name` + type metadata).
    - namingSQL definitions can appear on BO level (`naming_sql_list`) and/or inside
      each `or_mapping_list` entry (`naming_sql_list`).
    - Raw keys like `bo_desc`, `bo_name`, `is_virtual_bo`, `is_monthly`,
      `sql_command`, `sql_description`, `sql_name`, `naming_sql_id` are mapped
      into structured fields and metadata.
    """

    raw_bo_data = raw_bo_data or {}

    def _to_type_ref(raw_type: dict[str, Any]) -> TypeRef:
        return TypeRef(
            kind=str(raw_type.get("data_type", "unknown")),
            name=str(raw_type.get("data_type_name", "UNKNOWN")),
            is_list=bool(raw_type.get("is_list", False)),
        )

    def _normalize_param(raw_param: dict[str, Any]) -> ParameterDef:
        raw_param = raw_param or {}
        return ParameterDef(
            name=str(raw_param.get("param_name", "")),
            type=_to_type_ref(raw_param),
            description=str(raw_param.get("description", "")),
        )

    def _normalize_naming_sql(raw_sql: dict[str, Any]) -> NamingSQLDef:
        raw_sql = raw_sql or {}
        return NamingSQLDef(
            id=str(raw_sql.get("naming_sql_id", raw_sql.get("id", ""))),
            name=str(raw_sql.get("sql_name", raw_sql.get("name", ""))),
            label=str(raw_sql.get("label", "")),
            description=str(raw_sql.get("sql_description", raw_sql.get("description", ""))),
            sql=str(raw_sql.get("sql_command", raw_sql.get("sql", ""))),
            params=[_normalize_param(p) for p in (raw_sql.get("param_list") or []) if isinstance(p, dict)],
            returns_list=bool(raw_sql.get("returns_list", True)),
            is_customized=bool(raw_sql.get("is_customized", False)),
            is_sync=bool(raw_sql.get("is_sync", False)),
            metadata={"raw": raw_sql},
        )

    def _collect_naming_sqls(raw_bo: dict[str, Any]) -> list[NamingSQLDef]:
        candidates: list[dict[str, Any]] = []
        candidates.extend(item for item in (raw_bo.get("naming_sql_list") or []) if isinstance(item, dict))
        for mapping in (raw_bo.get("or_mapping_list") or []):
            if not isinstance(mapping, dict):
                continue
            nested = mapping.get("naming_sql_list") or []
            candidates.extend(item for item in nested if isinstance(item, dict))

        dedup: dict[tuple[str, str], NamingSQLDef] = {}
        for raw_sql in candidates:
            normalized = _normalize_naming_sql(raw_sql)
            dedup[(normalized.id, normalized.name)] = normalized
        return list(dedup.values())

    def _collect_fields(or_mapping_list: Iterable[Any]) -> list[BOFieldDef]:
        fields: list[BOFieldDef] = []
        for item in or_mapping_list:
            if not isinstance(item, dict):
                continue
            field_name = item.get("param_name") or item.get("name")
            if not field_name:
                continue
            fields.append(
                BOFieldDef(
                    name=str(field_name),
                    type=_to_type_ref(item),
                    description=str(item.get("description", "")),
                    nullable=bool(item.get("nullable", True)),
                )
            )
        return fields

    def _normalize_bo(raw_bo: dict[str, Any], source: str) -> BODef:
        raw_bo = raw_bo or {}
        fields = _collect_fields(raw_bo.get("or_mapping_list") or [])
        naming_sqls = _collect_naming_sqls(raw_bo)
        return BODef(
            id=raw_bo.get("bo_id") or raw_bo.get("id"),
            name=str(raw_bo.get("bo_name", raw_bo.get("name", ""))),
            description=str(raw_bo.get("bo_desc", raw_bo.get("description", ""))),
            source=source,
            is_virtual=bool(raw_bo.get("is_virtual_bo", raw_bo.get("is_virtual", False))),
            fields=fields,
            query_capability=BOQueryCapability(naming_sqls=naming_sqls),
            metadata={
                "is_monthly": raw_bo.get("is_monthly"),
                "raw": raw_bo,
            },
        )

    system_bos = [_normalize_bo(raw, "system") for raw in (raw_bo_data.get("sys_bo_list") or []) if isinstance(raw, dict)]
    custom_bos = [_normalize_bo(raw, "custom") for raw in (raw_bo_data.get("custom_bo_list") or []) if isinstance(raw, dict)]
    return BORegistry(system_bos=system_bos, custom_bos=custom_bos)
