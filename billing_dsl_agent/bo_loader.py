from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from billing_dsl_agent.bo_models import (
    BODef,
    BOFieldDef,
    BOQueryCapability,
    BORegistry,
    NamingSQLDef,
    ParameterDef,
    RwRuleTerm,
    TypeRef,
)


def load_bo_registry_from_json(data: Dict[str, Any]) -> BORegistry:
    system_rows = data.get("sys_bo_list") if isinstance(data, dict) else None
    custom_rows = data.get("custom_bo_list") if isinstance(data, dict) else None

    system_bos = _normalize_bo_list(system_rows)
    custom_bos = _normalize_bo_list(custom_rows)
    return BORegistry(system_bos=system_bos, custom_bos=custom_bos)


def load_bo_registry_from_file(path: str) -> BORegistry:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return BORegistry()
    return load_bo_registry_from_json(payload)


def _normalize_bo_list(raw_list: Any) -> List[BODef]:
    if not isinstance(raw_list, list):
        return []
    bos: List[BODef] = []
    for row in raw_list:
        if not isinstance(row, dict):
            continue
        bos.append(_normalize_bo(row))
    return bos


def _normalize_bo(row: Dict[str, Any]) -> BODef:
    bo_name = _as_text(row.get("bo_name"))
    description = _as_text(row.get("bo_desc"))
    fields = _normalize_fields(row.get("property_list"))
    naming_sqls = _normalize_naming_sqls(row.get("or_mapping_list"))
    rw_rules = _normalize_rw_rules(row.get("rw_rule_list"))

    return BODef(
        bo_name=bo_name,
        description=description,
        fields=fields,
        query_capability=BOQueryCapability(naming_sqls=naming_sqls),
        rw_rule_list=rw_rules,
        metadata={
            "bo_desc": description,
            "is_virtual_bo": bool(row.get("is_virtual_bo", False)),
            "or_mapping_count": len(row.get("or_mapping_list") or []),
            "rw_rule_count": len(row.get("rw_rule_list") or []),
        },
    )


def _normalize_fields(raw_fields: Any) -> List[BOFieldDef]:
    if not isinstance(raw_fields, list):
        return []
    fields: List[BOFieldDef] = []
    for item in raw_fields:
        if not isinstance(item, dict):
            continue
        type_ref = _to_type_ref(item)
        fields.append(
            BOFieldDef(
                name=_as_text(item.get("field_name")),
                description=_as_text(item.get("description")),
                type_ref=type_ref,
                metadata={
                    "raw_data_type": _as_text(item.get("data_type")),
                    "raw_data_type_name": _as_text(item.get("data_type_name")),
                    "raw_is_list": bool(item.get("is_list", False)),
                    "length": _as_text(item.get("length")),
                    "default_value": _as_text(item.get("default_value")),
                },
            )
        )
    return fields


def _normalize_naming_sqls(raw_mappings: Any) -> List[NamingSQLDef]:
    if not isinstance(raw_mappings, list):
        return []
    naming_sqls: List[NamingSQLDef] = []
    for mapping in raw_mappings:
        if not isinstance(mapping, dict):
            continue
        mapping_meta = {
            "or_mapping_id": _as_text(mapping.get("or_mapping_id")),
            "or_mapping_name": _as_text(mapping.get("or_mapping_name")),
            "or_mapping_data_source": _as_text(mapping.get("or_mapping_data_source")),
            "is_monthly": bool(mapping.get("is_monthly", False)),
            "real_table_name": _as_text(mapping.get("real_table_name")),
        }
        raw_sqls = mapping.get("naming_sql_list")
        if not isinstance(raw_sqls, list):
            continue
        for sql_row in raw_sqls:
            if not isinstance(sql_row, dict):
                continue
            naming_sqls.append(
                NamingSQLDef(
                    id=_as_text(sql_row.get("naming_sql_id")),
                    name=_as_text(sql_row.get("sql_name")),
                    label=_as_text(sql_row.get("label_name")),
                    description=_as_text(sql_row.get("sql_description")),
                    sql=_as_text(sql_row.get("sql_command")),
                    params=_normalize_params(sql_row.get("param_list")),
                    metadata={
                        "is_customized": bool(sql_row.get("is_customized", False)),
                        "is_sync": bool(sql_row.get("is_sync", False)),
                        **mapping_meta,
                    },
                )
            )
    return naming_sqls


def _normalize_params(raw_params: Any) -> List[ParameterDef]:
    if not isinstance(raw_params, list):
        return []
    params: List[ParameterDef] = []
    for item in raw_params:
        if not isinstance(item, dict):
            continue
        params.append(
            ParameterDef(
                name=_as_text(item.get("param_name")),
                type_ref=_to_type_ref(item),
                metadata={
                    "raw_data_type": _as_text(item.get("data_type")),
                    "raw_data_type_name": _as_text(item.get("data_type_name")),
                    "raw_is_list": bool(item.get("is_list", False)),
                    "raw_payload": dict(item),
                },
            )
        )
    return params


def _normalize_rw_rules(raw_rules: Any) -> List[RwRuleTerm]:
    if not isinstance(raw_rules, list):
        return []
    rw_rules: List[RwRuleTerm] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        rw_rules.append(
            RwRuleTerm(
                rw_rule_id=_as_text(item.get("rw_rule_id")),
                app_scene=_as_text(item.get("app_scene")),
                read_or_mapping_id=_as_text(item.get("read_or_mapping_id")),
                insert_or_mapping_id=_as_text(item.get("insert_or_mapping_id")),
                update_or_mapping_id=_as_text(item.get("update_or_mapping_id")),
                delete_or_mapping_id=_as_text(item.get("delete_or_mapping_id")),
            )
        )
    return rw_rules


def _to_type_ref(row: Dict[str, Any]) -> TypeRef:
    return TypeRef(
        is_list=bool(row.get("is_list", False)),
        data_type=_as_text(row.get("data_type")),
        data_type_name=_as_text(row.get("data_type_name")),
    )


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""
