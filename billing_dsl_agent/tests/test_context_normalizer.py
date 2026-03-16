from billing_dsl_agent.normalize.context_normalizer import normalize_context_registry


def test_normalize_context_registry_recursively_parses_children() -> None:
    raw = {
        "global_context": {
            "property_id": "g1",
            "property_name": "billStatement",
            "annotation": "global bill ctx",
            "property_type": "object",
            "data_type": "OBJECT",
            "allow_modify": False,
            "cdsl": "$ctx$.billStatement",
            "sub_properties": [
                {
                    "property_id": "g1_1",
                    "property_name": "prepareId",
                    "annotation": "prepare id",
                    "data_type": "LONG",
                }
            ],
            "return_sub_properties": [
                {
                    "property_id": "g1_2",
                    "property_name": "billCycleId",
                    "annotation": "cycle",
                    "data_type": "LONG",
                }
            ],
        }
    }

    registry = normalize_context_registry(raw)

    assert registry.global_root.name == "billStatement"
    assert registry.global_root.description == "global bill ctx"
    assert registry.global_root.value_type == "OBJECT"
    assert len(registry.global_root.children) == 2
    child_names = sorted([c.name for c in registry.global_root.children])
    assert child_names == ["billCycleId", "prepareId"]
