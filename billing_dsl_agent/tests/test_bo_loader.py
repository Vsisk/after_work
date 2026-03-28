from billing_dsl_agent.bo_loader import load_bo_registry_from_json


def _sample_bo_json() -> dict:
    return {
        "sys_bo_list": [
            {
                "bo_name": "User",
                "bo_desc": "系统用户表",
                "is_virtual_bo": False,
                "property_list": [
                    {
                        "field_name": "id",
                        "description": "用户ID",
                        "is_list": False,
                        "data_type": "key",
                        "data_type_name": "int",
                        "length": "11",
                        "default_value": "0",
                    },
                    {
                        "field_name": "roles",
                        "description": "用户角色列表",
                        "is_list": True,
                        "data_type": "logic",
                        "data_type_name": "UserRole",
                    },
                ],
                "or_mapping_list": [
                    {
                        "or_mapping_id": "user_db_mapping_001",
                        "or_mapping_name": "用户数据库映射",
                        "or_mapping_data_source": "main_database",
                        "is_monthly": False,
                        "real_table_name": "sys_users",
                        "naming_sql_list": [
                            {
                                "naming_sql_id": "get_user_by_id_001",
                                "is_customized": False,
                                "is_sync": False,
                                "label_name": "根据ID查询用户",
                                "sql_name": "getUserById",
                                "sql_description": "通过用户ID查询用户信息",
                                "sql_command": "SELECT * FROM sys_users WHERE id = :userId",
                                "param_list": [
                                    {
                                        "param_name": "userId",
                                        "is_list": False,
                                        "data_type": "basic",
                                        "data_type_name": "int",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "rw_rule_list": [
                    {
                        "rw_rule_id": "user_rw_rule_001",
                        "app_scene": "user_management",
                        "read_or_mapping_id": "user_db_mapping_001",
                        "insert_or_mapping_id": "user_db_mapping_001",
                        "update_or_mapping_id": "user_db_mapping_001",
                        "delete_or_mapping_id": "user_db_mapping_001",
                    }
                ],
            }
        ],
        "custom_bo_list": [
            {
                "bo_name": "ContractInfo",
                "bo_desc": "合同信息业务对象",
                "is_virtual_bo": False,
                "property_list": [
                    {
                        "field_name": "contractId",
                        "description": "合同编号",
                        "is_list": False,
                        "data_type": "key",
                        "data_type_name": "string",
                    }
                ],
                "or_mapping_list": [
                    {
                        "or_mapping_id": "contract_es_mapping_001",
                        "or_mapping_name": "合同ES映射",
                        "or_mapping_data_source": "elasticsearch",
                        "is_monthly": True,
                        "real_table_name": "contracts",
                    }
                ],
                "rw_rule_list": [
                    {
                        "rw_rule_id": "contract_rw_rule_001",
                        "app_scene": "contract_processing",
                        "read_or_mapping_id": "contract_es_mapping_001",
                    }
                ],
            }
        ],
    }


def test_load_bo_registry_from_json_basic() -> None:
    registry = load_bo_registry_from_json(_sample_bo_json())
    assert len(registry.system_bos) == 1
    assert len(registry.custom_bos) == 1


def test_normalize_bo_fields() -> None:
    registry = load_bo_registry_from_json(_sample_bo_json())
    user_bo = registry.system_bos[0]
    assert len(user_bo.fields) == 2
    first_field = user_bo.fields[0]
    assert first_field.name == "id"
    assert first_field.metadata["length"] == "11"
    assert first_field.metadata["default_value"] == "0"
    assert first_field.metadata["raw_data_type"] == "key"


def test_normalize_naming_sqls() -> None:
    registry = load_bo_registry_from_json(_sample_bo_json())
    user_bo = registry.system_bos[0]
    naming_sqls = user_bo.query_capability.naming_sqls
    assert len(naming_sqls) == 1
    sql_def = naming_sqls[0]
    assert sql_def.name == "getUserById"
    assert sql_def.metadata["or_mapping_id"] == "user_db_mapping_001"
    assert sql_def.metadata["or_mapping_data_source"] == "main_database"
    assert len(sql_def.params) == 1
    assert sql_def.params[0].name == "userId"
    assert sql_def.params[0].type_ref.data_type == "basic"
    assert sql_def.params[0].type_ref.data_type_name == "int"
    assert sql_def.params[0].type_ref.is_list is False
    assert sql_def.params[0].metadata["raw_payload"]["param_name"] == "userId"


def test_normalize_rw_rules() -> None:
    registry = load_bo_registry_from_json(_sample_bo_json())
    user_bo = registry.system_bos[0]
    assert len(user_bo.rw_rule_list) == 1
    assert user_bo.rw_rule_list[0].rw_rule_id == "user_rw_rule_001"


def test_load_bo_registry_missing_optional_fields() -> None:
    payload = {
        "sys_bo_list": [{"bo_name": "X"}],
        "custom_bo_list": [{"bo_name": "Y", "or_mapping_list": [{"or_mapping_id": "m1"}]}],
    }
    registry = load_bo_registry_from_json(payload)

    assert len(registry.system_bos) == 1
    assert len(registry.custom_bos) == 1
    assert registry.system_bos[0].fields == []
    assert registry.system_bos[0].query_capability.naming_sqls == []
    assert registry.system_bos[0].rw_rule_list == []
    assert registry.custom_bos[0].query_capability.naming_sqls == []
