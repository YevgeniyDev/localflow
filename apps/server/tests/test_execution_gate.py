from types import SimpleNamespace

from localflow.services.execution_service import ExecutionService


def _draft_with_plan(plan_obj: dict):
    return SimpleNamespace(tool_plan=SimpleNamespace(json_canonical=__import__("json").dumps(plan_obj)))


def test_tool_input_must_match_approved_params_exactly():
    svc = ExecutionService(db=None, tools=None)  # type: ignore[arg-type]
    draft = _draft_with_plan(
        {
            "actions": [
                {
                    "tool": "open_links",
                    "params": {"urls": ["https://example.com"]},
                }
            ]
        }
    )

    assert svc._is_tool_input_approved(draft, "open_links", {"urls": ["https://example.com"]})
    assert not svc._is_tool_input_approved(draft, "open_links", {"urls": ["https://evil.com"]})
    assert not svc._is_tool_input_approved(draft, "search_web", {"query": "x"})


def test_no_tool_plan_only_allows_empty_input():
    svc = ExecutionService(db=None, tools=None)  # type: ignore[arg-type]
    draft = SimpleNamespace(tool_plan=None)

    assert svc._is_tool_input_approved(draft, "open_links", {})
    assert not svc._is_tool_input_approved(draft, "open_links", {"urls": ["https://example.com"]})


def test_medium_high_policy_requires_confirmation_payload():
    class MediumTool:
        risk = "MEDIUM"

    class HighTool:
        risk = "HIGH"

    class FakeTools:
        def get(self, name: str):
            if name == "medium":
                return MediumTool()
            return HighTool()

    svc = ExecutionService(db=None, tools=FakeTools())  # type: ignore[arg-type]

    try:
        svc._enforce_tool_policy("medium", {"actions": [{"id": "a1"}]}, None)
        assert False, "expected confirmation requirement"
    except ValueError as e:
        assert "confirmation payload" in str(e).lower()

    svc._enforce_tool_policy(
        "medium",
        {"actions": [{"id": "a1"}]},
        {"approved_actions": ["a1"]},
    )

    try:
        svc._enforce_tool_policy(
            "high",
            {"actions": [{"id": "a1"}]},
            {"approved_actions": ["a1"]},
        )
        assert False, "expected high risk allow flag requirement"
    except ValueError as e:
        assert "allow_high_risk" in str(e)
