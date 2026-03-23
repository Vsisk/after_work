"""BO normalization placeholders."""

from __future__ import annotations

from typing import Any

from billing_dsl_agent.types.bo import (
    BODef,
    BOFieldDef,
    BOQueryCapability,
    BORegistry,
    DataType,
    NamingSQLDef,
    RwRuleTerm,
)
from billing_dsl_agent.types.common import ParameterDef, TypeRef


def normalize_bo_registry(raw_bo_data: dict[str, Any]) -> BORegistry:
    """Normalize raw BO payload into BORegistry."""

    raw_bo_data = raw_bo_data or {}
    system_bos = _normalize_bo_list(raw_bo_data.get("sys_bo_list") or [], source="system")
    custom_bos = _normalize_bo_list(raw_bo_data.get("custom_bo_list") or [], source="custom")
    return BORegistry(system_bos=system_bos, custom_bos=custom_bos)


def _normalize_bo_list(raw_list: list[Any], source: str) -> list[BODef]:
    return [
        _normalize_single_bo(raw_bo=item, source=source)
        for item in raw_list
        if isinstance(item, dict)
    ]


def _normalize_single_bo(raw_bo: dict[str, Any], source: str) -> BODef:
    raw_bo = raw_bo or {}

    fields = _normalize_property_list(raw_bo.get("property_list") or [])
    rw_rules = _normalize_rw_rule_list(raw_bo.get("rw_rule_list") or [])
    naming_sqls, mapping_meta = _normalize_or_mapping_list(raw_bo.get("or_mapping_list") or [])

    return BODef(
        id=raw_bo.get("bo_id") or raw_bo.get("id"),
        name=str(raw_bo.get("bo_name", raw_bo.get("name", ""))),
        description=str(raw_bo.get("bo_desc", raw_bo.get("description", ""))),
        source=source,
        is_virtual=bool(raw_bo.get("is_virtual_bo", raw_bo.get("is_virtual", False))),
        fields=fields,
        rw_rule_list=rw_rules,
        query_capability=BOQueryCapability(naming_sqls=naming_sqls),
        metadata={
            "raw": raw_bo,
            "mapping_summary": mapping_meta,
        },
    )


def _normalize_property_list(raw_property_list: list[Any]) -> list[BOFieldDef]:
    fields: list[BOFieldDef] = []
    for raw_field in raw_property_list:
        if not isinstance(raw_field, dict):
            continue

        raw_type = str(raw_field.get("data_type", "")).strip().lower()
        type_ref = _to_type_ref(
            raw_data_type=raw_type,
            raw_data_type_name=str(raw_field.get("data_type_name", "UNKNOWN")),
            is_list=bool(raw_field.get("is_list", False)),
        )
        fields.append(
            BOFieldDef(
                name=str(raw_field.get("field_name", raw_field.get("name", ""))),
                type=type_ref,
                description=str(raw_field.get("description", "")),
                nullable=bool(raw_field.get("nullable", True)),
                metadata={
                    "length": raw_field.get("length"),
                    "default_value": raw_field.get("default_value"),
                    "raw_data_type": raw_field.get("data_type"),
                    "raw_data_type_name": raw_field.get("data_type_name"),
                    "raw_is_list": raw_field.get("is_list"),
                    "raw": raw_field,
                },
            )
        )
    return fields


def _normalize_rw_rule_list(raw_rw_rule_list: list[Any]) -> list[RwRuleTerm]:
    rules: list[RwRuleTerm] = []
    for raw_rule in raw_rw_rule_list:
        if not isinstance(raw_rule, dict):
            continue
        rules.append(
            RwRuleTerm(
                rw_rule_id=str(raw_rule.get("rw_rule_id", "")),
                app_scene=str(raw_rule.get("app_scene", "")),
                read_or_mapping_id=str(raw_rule.get("read_or_mapping_id", "")),
                insert_or_mapping_id=str(raw_rule.get("insert_or_mapping_id", "")),
                update_or_mapping_id=str(raw_rule.get("update_or_mapping_id", "")),
                delete_or_mapping_id=str(raw_rule.get("delete_or_mapping_id", "")),
            )
        )
    return rules


def _normalize_or_mapping_list(raw_or_mapping_list: list[Any]) -> tuple[list[NamingSQLDef], dict[str, Any]]:
    naming_sqls: list[NamingSQLDef] = []
    mapping_meta: dict[str, Any] = {"mapping_count": 0, "is_monthly_values": []}

    for raw_mapping in raw_or_mapping_list:
        if not isinstance(raw_mapping, dict):
            continue
        mapping_meta["mapping_count"] += 1
        mapping_meta["is_monthly_values"].append(raw_mapping.get("is_monthly"))

        mapping_metadata = {
            "is_monthly": raw_mapping.get("is_monthly"),
            "or_mapping_id": raw_mapping.get("or_mapping_id"),
        }
        for raw_sql in raw_mapping.get("naming_sql_list") or []:
            if not isinstance(raw_sql, dict):
                continue
            naming_sqls.append(_normalize_naming_sql(raw_sql, mapping_metadata=mapping_metadata))

    dedup: dict[tuple[str, str], NamingSQLDef] = {}
    for sql in naming_sqls:
        dedup[(sql.id, sql.name)] = sql

    return list(dedup.values()), mapping_meta


def _normalize_naming_sql(raw_sql: dict[str, Any], mapping_metadata: dict[str, Any] | None = None) -> NamingSQLDef:
    raw_sql = raw_sql or {}
    mapping_metadata = mapping_metadata or {}

    return NamingSQLDef(
        id=str(raw_sql.get("naming_sql_id", raw_sql.get("id", ""))),
        name=str(raw_sql.get("sql_name", raw_sql.get("name", ""))),
        label=str(raw_sql.get("label_name", raw_sql.get("label", ""))),
        description=str(raw_sql.get("sql_description", raw_sql.get("description", ""))),
        sql=str(raw_sql.get("sql_command", raw_sql.get("sql", ""))),
        params=_normalize_param_list(raw_sql.get("param_list") or []),
        returns_list=bool(raw_sql.get("returns_list", True)),
        is_customized=bool(raw_sql.get("is_customized", False)),
        is_sync=bool(raw_sql.get("is_sync", False)),
        metadata={
            "label_name": raw_sql.get("label_name"),
            "is_customized": raw_sql.get("is_customized"),
            "is_sync": raw_sql.get("is_sync"),
            "naming_sql_id": raw_sql.get("naming_sql_id"),
            "mapping": mapping_metadata,
            "raw": raw_sql,
        },
    )


def _normalize_param_list(raw_param_list: list[Any]) -> list[ParameterDef]:
    params: list[ParameterDef] = []
    for raw_param in raw_param_list:
        if not isinstance(raw_param, dict):
            continue
        params.append(
            ParameterDef(
                name=str(raw_param.get("param_name", "")),
                type=_to_type_ref(
                    raw_data_type=str(raw_param.get("data_type", "")),
                    raw_data_type_name=str(raw_param.get("data_type_name", "UNKNOWN")),
                    is_list=bool(raw_param.get("is_list", False)),
                ),
                description=str(raw_param.get("description", "")),
                metadata={"raw": raw_param},
            )
        )
    return params


def _to_type_ref(raw_data_type: str, raw_data_type_name: str, is_list: bool) -> TypeRef:
    lowered = (raw_data_type or "").strip().lower()
    if lowered in {item.value for item in DataType}:
        kind = lowered
    else:
        kind = lowered or "basic"

    return TypeRef(
        kind=kind,
        name=(raw_data_type_name or "UNKNOWN").strip() or "UNKNOWN",
        is_list=bool(is_list),
        metadata={
            "raw_data_type": raw_data_type,
            "raw_data_type_name": raw_data_type_name,
            "raw_is_list": is_list,
        },
    )
