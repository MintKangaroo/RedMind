import pytest

from redmind.runtime import PolicyConfig, PolicyEngine, PolicyViolation, RunRequest


def engine() -> PolicyEngine:
    return PolicyEngine(
        PolicyConfig(
            allowed_targets=frozenset({"lab-host", "10.0.0.4"}),
            allowed_tools=frozenset({"asset_inventory"}),
            max_steps=3,
            max_timeout_seconds=30,
        )
    )


def test_policy_accepts_scoped_low_risk_request():
    request = RunRequest(objective="inspect", max_steps=3, timeout_seconds=30,
                         target_ids=("lab-host",), tool_names=("asset_inventory",))
    assert engine().check(request) is True


@pytest.mark.parametrize(
    "run_request",
    [
        RunRequest(objective="inspect", target_ids=("unknown",)),
        RunRequest(objective="inspect", target_ids=("8.8.8.8",)),
        RunRequest(objective="inspect", tool_names=("shell",)),
        RunRequest(objective="inspect", max_steps=4),
        RunRequest(objective="inspect", timeout_seconds=31),
        RunRequest(objective="inspect", risk_level="high"),
    ],
)
def test_policy_rejects_unsafe_requests(run_request: RunRequest):
    with pytest.raises(PolicyViolation):
        engine().check(run_request)


def test_high_risk_requires_explicit_approval():
    request = RunRequest(objective="inspect", max_steps=3, timeout_seconds=30,
                         risk_level="high", approval_requested=True)
    assert engine().check(request) is True
