from billing_dsl_agent.environment import NodeContextResolver
from billing_dsl_agent.schema_provider import SchemaProvider


def test_node_context_resolver_basic() -> None:
    provider = SchemaProvider()
    loaded = provider.load_all(site_id="site_a", project_id="project_a")
    resolver = NodeContextResolver()
    node_info = {
        "node_path": "invoice.customer.title",
        "parent_path": "invoice.customer",
        "node_name": "title",
        "description": "客户称谓",
    }

    env = resolver.resolve(node_info=node_info, loaded_schemas=loaded)

    assert env.node_path == "invoice.customer.title"
    assert env.visible_global_context
    assert isinstance(env.visible_local_context, list)
    assert env.bo_schema
    assert env.function_schema
