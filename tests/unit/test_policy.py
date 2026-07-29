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
    request = RunRequest(
        objective="inspect",
        max_steps=3,
        timeout_seconds=30,
        target_ids=("lab-host",),
        tool_names=("asset_inventory",),
    )
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
    request = RunRequest(
        objective="inspect",
        max_steps=3,
        timeout_seconds=30,
        risk_level="high",
        approval_requested=True,
    )
    assert engine().check(request) is True


def test_each_policy_budget_and_network_boundary_is_enforced():
    policy = engine()
    bounded = {
        "objective": "inspect",
        "max_steps": 3,
        "timeout_seconds": 30,
    }
    unsafe_requests = (
        RunRequest(**(bounded | {"timeout_seconds": 31})),
        RunRequest(**bounded, target_ids=tuple(f"lab-{index}" for index in range(11))),
        RunRequest(**bounded, target_ids=("unknown",)),
        RunRequest(**bounded, tool_names=("shell",)),
        RunRequest(**bounded, risk_level="critical"),
    )
    for request in unsafe_requests:
        with pytest.raises(PolicyViolation):
            policy.check(request)

    public_policy = PolicyEngine(
        PolicyConfig(
            allowed_targets=frozenset({"8.8.8.8"}),
            max_steps=3,
            max_timeout_seconds=30,
        )
    )
    with pytest.raises(PolicyViolation, match="public IP"):
        public_policy.check(RunRequest(**bounded, target_ids=("8.8.8.8",)))
