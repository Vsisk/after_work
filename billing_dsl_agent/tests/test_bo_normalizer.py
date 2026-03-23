from billing_dsl_agent.normalize.bo_normalizer import normalize_bo_registry


def _sample_bo_payload() -> dict:
    return {
        "sys_bo_list": [
            {
                "bo_id": "bo-1",
                "bo_name": "SYS_TEST_BO",
                "bo_desc": "system bo",
                "is_virtual_bo": True,
                "property_list": [
                    {
                        "field_name": "prepareId",
                        "description": "prepare id",
                        "is_list": False,
                        "data_type": "key",
                        "data_type_name": "LONG",
                        "length": "32",
                        "default_value": "0",
                    },
                    {
                        "field_name": "attrs",
                        "description": "attrs",
                        "is_list": True,
                        "data_type": "extattr",
                        "data_type_name": "MAP",
                        "length": "256",
                        "default_value": "{}",
                    },
                ],
                "rw_rule_list": [
                    {
                        "rw_rule_id": "rw-1",
                        "app_scene": "bill",
                        "read_or_mapping_id": "orm-read",
                        "insert_or_mapping_id": "orm-insert",
                        "update_or_mapping_id": "orm-update",
                        "delete_or_mapping_id": "orm-delete",
                    }
                ],
                "or_mapping_list": [
                    {
                        "or_mapping_id": "orm-read",
                        "is_monthly": True,
                        "naming_sql_list": [
                            {
                                "is_customized": True,
                                "is_sync": True,
                                "label_name": "Read SQL",
                                "naming_sql_id": "sql-1",
                                "sql_name": "Q_BY_PREPARE_ID",
                                "sql_description": "query prepare",
                                "sql_command": "select * from t where id = :prepare_id",
                                "param_list": [
                                    {
                                        "param_name": "prepare_id",
                                        "data_type": "basic",
                                        "data_type_name": "LONG",
                                        "is_list": False,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
        "custom_bo_list": [
            {
                "bo_name": "CUSTOM_BO",
                "bo_desc": "custom bo",
                "property_list": [],
                "or_mapping_list": [],
                "rw_rule_list": [],
            }
        ],
    }


def test_normalize_bo_with_property_list() -> None:
    registry = normalize_bo_registry(_sample_bo_payload())

    assert len(registry.system_bos) == 1
    bo = registry.system_bos[0]
    assert bo.name == "SYS_TEST_BO"
    assert len(bo.fields) == 2
    assert bo.fields[0].name == "prepareId"
    assert bo.fields[0].type.kind == "key"
    assert bo.fields[0].type.name == "LONG"


def test_normalize_bo_preserve_rw_rule_list() -> None:
    registry = normalize_bo_registry(_sample_bo_payload())

    bo = registry.system_bos[0]
    assert len(bo.rw_rule_list) == 1
    rw = bo.rw_rule_list[0]
    assert rw.rw_rule_id == "rw-1"
    assert rw.read_or_mapping_id == "orm-read"
    assert rw.update_or_mapping_id == "orm-update"


def test_normalize_bo_collect_naming_sqls_from_or_mapping() -> None:
    registry = normalize_bo_registry(_sample_bo_payload())

    bo = registry.system_bos[0]
    assert len(bo.query_capability.naming_sqls) == 1
    sql = bo.query_capability.naming_sqls[0]
    assert sql.id == "sql-1"
    assert sql.name == "Q_BY_PREPARE_ID"
    assert sql.label == "Read SQL"
    assert sql.metadata["mapping"]["is_monthly"] is True
    assert sql.metadata["mapping"]["or_mapping_id"] == "orm-read"


def test_normalize_bo_field_preserve_property_metadata() -> None:
    registry = normalize_bo_registry(_sample_bo_payload())

    field = registry.system_bos[0].fields[0]
    assert field.metadata["length"] == "32"
    assert field.metadata["default_value"] == "0"
    assert field.metadata["raw_data_type"] == "key"
    assert field.metadata["raw_data_type_name"] == "LONG"
    assert field.metadata["raw_is_list"] is False


def test_normalize_bo_registry_handles_empty_fields_without_crash() -> None:
    registry = normalize_bo_registry({"sys_bo_list": [{"bo_name": "B1"}]})
    bo = registry.system_bos[0]

    assert bo.name == "B1"
    assert bo.fields == []
    assert bo.rw_rule_list == []
    assert bo.query_capability.naming_sqls == []
