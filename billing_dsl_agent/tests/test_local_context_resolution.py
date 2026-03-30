from billing_dsl_agent.environment import EnvironmentBuilder
from billing_dsl_agent.local_context_normalizer import normalize_local_contexts
from billing_dsl_agent.local_context_resolver import resolve_node_chain, resolve_visible_local_contexts
from billing_dsl_agent.models import ContextResource, NodeDef, ResourceRegistry
from billing_dsl_agent.semantic_selector import MockSemanticSelector


def _edsl_tree() -> dict:
    return {
        "node_type": "parent",
        "id": "root",
        "local_context": [
            {
                "property_id": "lc_root_cycle",
                "property_name": "currentCycle",
                "property_type": "normal",
                "annotation": "root cycle",
            }
        ],
        "mapping_content": {
            "node_type": "parent",
            "id": "mapping",
            "children": [
                {
                    "node_type": "parent_list",
                    "id": "c0",
                    "local_context": [
                        {
                            "property_id": "lc_mid_1",
                            "property_name": "invoiceId",
                            "annotation": "mid value",
                        },
                        {
                            "property_id": "dup_id",
                            "property_name": "dupNameFar",
                            "annotation": "far value",
                        },
                    ],
                    "children": [
                        {
                            "node_type": "parent",
                            "id": "leaf_parent",
                            "local_context": [
                                {
                                    "property_id": "dup_id",
                                    "property_name": "dupNameNear",
                                    "annotation": "near value",
                                },
                                {
                                    "property_id": "lc_self",
                                    "property_name": "selfValue",
                                },
                            ],
                            "children": [
                                {"node_type": "leaf", "id": "target"},
                            ],
                        }
                    ],
                }
            ],
        },
    }


def test_jsonpath_chain_resolution_restores_root_to_target_chain() -> None:
    chain = resolve_node_chain(_edsl_tree(), "$.mapping_content.children[0].children[0]")
    assert [item[0] for item in chain] == [
        "$",
        "$.mapping_content",
        "$.mapping_content.children",
        "$.mapping_content.children[0]",
        "$.mapping_content.children[0].children",
        "$.mapping_content.children[0].children[0]",
    ]


def test_visible_local_context_aggregates_root_mid_and_target_node() -> None:
    resolved = resolve_visible_local_contexts(_edsl_tree(), "$.mapping_content.children[0].children[0]")
    normalized = normalize_local_contexts(resolved)
    assert [item.property_name for item in normalized.ordered_nodes] == [
        "currentCycle",
        "invoiceId",
        "dupNameNear",
        "selfValue",
    ]
    assert normalized.nodes_by_property_name["currentCycle"].source_node_path == "$"
    assert normalized.nodes_by_property_name["selfValue"].source_node_path.endswith("children[0]")


def test_local_access_path_and_resource_id_stable() -> None:
    resolved = resolve_visible_local_contexts(_edsl_tree(), "$.mapping_content.children[0].children[0]")
    normalized = normalize_local_contexts(resolved)
    node = normalized.nodes_by_property_name["invoiceId"]
    assert node.access_path == "$local$.invoiceId"
    assert node.resource_id == "local_context:lc_mid_1"


def test_same_property_id_prefers_nearer_definition() -> None:
    resolved = resolve_visible_local_contexts(_edsl_tree(), "$.mapping_content.children[0].children[0]")
    normalized = normalize_local_contexts(resolved)
    by_id = normalized.nodes_by_id["local_context:dup_id"]
    assert by_id.property_name == "dupNameNear"
    assert any("property_id_override:dup_id" in item for item in normalized.warnings)


def test_environment_keeps_local_context_outside_global_registry() -> None:
    registry = ResourceRegistry(
        contexts={
            "context:$ctx$.customer.id": ContextResource(
                resource_id="context:$ctx$.customer.id",
                name="id",
                path="$ctx$.customer.id",
                scope="global",
            )
        },
        edsl_tree=_edsl_tree(),
    )
    env = EnvironmentBuilder(semantic_selector=MockSemanticSelector(top_k=2)).build_filtered_environment(
        node_info=NodeDef(node_id="n1", node_name="target", node_path="$.mapping_content.children[0].children[0]"),
        user_query="query",
        registry=registry,
    )
    assert "local_context:lc_mid_1" in env.selected_local_context_ids
    assert "local_context:lc_mid_1" not in env.registry.contexts


def test_same_property_name_with_different_property_id_records_warning() -> None:
    tree = _edsl_tree()
    tree["mapping_content"]["children"][0]["local_context"].append(
        {"property_id": "x1", "property_name": "shadowName", "annotation": "far"}
    )
    tree["mapping_content"]["children"][0]["children"][0]["local_context"].append(
        {"property_id": "x2", "property_name": "shadowName", "annotation": "near"}
    )
    resolved = resolve_visible_local_contexts(tree, "$.mapping_content.children[0].children[0]")
    normalized = normalize_local_contexts(resolved)
    assert normalized.nodes_by_property_name["shadowName"].property_id == "x2"
    assert any("property_name_conflict:shadowName" in item for item in normalized.warnings)
