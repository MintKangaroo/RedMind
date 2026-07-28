import asyncio
from uuid import uuid4

from redmind.runtime import (
    AgentContext,
    AgentState,
    CancellationToken,
    EnumerationAnalystAgent,
    Evidence,
    ReconAnalystAgent,
    Run,
    Step,
)
from redmind.runtime.engine import utc_now


def context(evidence=()):
    run = Run(id=uuid4(), objective="inspect", max_steps=2, timeout_seconds=30, created_at=utc_now())
    step = Step(id=uuid4(), run_id=run.id, sequence=1, agent_name="analyst", created_at=utc_now())
    return AgentContext(run=run, step=step, evidence=evidence, cancellation=CancellationToken())


def test_recon_proposes_only_when_evidence_is_missing():
    result = asyncio.run(ReconAnalystAgent().execute(context()))
    assert result.messages[0].metadata["action_type"] == "recon_observation"
    assert result.evidence[0].evidence_type == "gap"
    evidence = Evidence(id=uuid4(), run_id=uuid4(), step_id=uuid4(), evidence_type="asset", source="tool", summary="asset inventory observed", collected_at=utc_now())
    result = asyncio.run(ReconAnalystAgent().execute(context((evidence,))))
    assert result.messages == ()


def test_enumeration_does_not_duplicate_service_observation():
    result = asyncio.run(EnumerationAnalystAgent().execute(context()))
    assert result.messages[0].metadata["action_type"] == "service_observation"
    evidence = Evidence(id=uuid4(), run_id=uuid4(), step_id=uuid4(), evidence_type="service", source="tool", summary="port 443 service observed", collected_at=utc_now())
    result = asyncio.run(EnumerationAnalystAgent().execute(context((evidence,))))
    assert result.messages == ()
