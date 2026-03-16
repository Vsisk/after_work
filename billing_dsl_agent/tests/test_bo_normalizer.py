from billing_dsl_agent.normalize.bo_normalizer import normalize_bo_registry


def test_normalize_bo_registry_handles_system_and_custom_lists() -> None:
    raw = {
        "sys_bo_list": [
            {
                "bo_id": "1",
                "bo_name": "SYS_BE",
                "bo_desc": "system be",
                "is_virtual_bo": False,
                "is_monthly": True,
                "or_mapping_list": [
                    {
                        "param_name": "beId",
                        "data_type": "basic",
                        "data_type_name": "LONG",
                        "is_list": False,
                        "naming_sql_list": [
                            {
                                "naming_sql_id": "sql1",
                                "sql_name": "Q_BE",
                                "sql_command": "select * from t",
                                "param_list": [
                                    {
                                        "param_name": "be_id",
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
        "custom_bo_list": [{"bo_name": "CUST_BO", "bo_desc": "custom"}],
    }

    registry = normalize_bo_registry(raw)

    assert len(registry.system_bos) == 1
    assert len(registry.custom_bos) == 1
    sys_bo = registry.system_bos[0]
    assert sys_bo.name == "SYS_BE"
    assert sys_bo.fields[0].name == "beId"
    assert sys_bo.query_capability.naming_sqls[0].name == "Q_BE"
    assert sys_bo.query_capability.naming_sqls[0].params[0].name == "be_id"
    assert sys_bo.metadata["is_monthly"] is True
