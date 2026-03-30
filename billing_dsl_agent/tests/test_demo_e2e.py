from billing_dsl_agent.demo_e2e import (
    DEFAULT_REQUIREMENT,
    build_demo_dataset,
    build_demo_request,
    run_demo,
)


def test_demo_dataset_contains_virtual_resources() -> None:
    dataset = build_demo_dataset()

    assert ("demo-site", "demo-project") in dataset
    payload = dataset[("demo-site", "demo-project")]
    assert "context" in payload
    assert "bo" in payload
    assert "function" in payload
    assert "edsl" in payload


def test_demo_stub_mode_runs_end_to_end_successfully() -> None:
    response = run_demo(mode="stub", requirement=DEFAULT_REQUIREMENT)

    assert response.success is True
    assert response.dsl == "Customer.GetSalutation($ctx$.customer.gender)"
    assert response.debug is not None
    assert response.debug.resource_selection is not None
    assert "function:Customer.GetSalutation" in response.debug.resource_selection.function.selected_ids
    assert response.debug.plan_attempts


def test_demo_request_defaults_are_valid() -> None:
    request = build_demo_request()

    assert request.site_id == "demo-site"
    assert request.project_id == "demo-project"
    assert request.node_def.node_path == "$.children[0].children[0]"
