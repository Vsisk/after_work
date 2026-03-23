from billing_dsl_agent.schema_provider import SchemaProvider


def test_schema_provider_load_all() -> None:
    provider = SchemaProvider()

    loaded = provider.load_all(site_id="site_a", project_id="project_a")

    assert loaded.bo_registry.all_bos()
    assert loaded.context_registry.global_root is not None
    assert loaded.function_registry.functions
