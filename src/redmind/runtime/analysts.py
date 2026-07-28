"""Deterministic evidence-gap analysts that emit safe observation proposals."""

from __future__ import annotations

from redmind.runtime.agents import Agent, AgentContext
from redmind.runtime.models import AgentResult, EvidenceDraft, MessageDraft, MessageRole


def _proposal(action_type: str, purpose: str, target: str) -> MessageDraft:
    return MessageDraft(
        role=MessageRole.AGENT,
        sender=action_type,
        content=purpose,
        metadata={
            "action_type": action_type,
            "target_id": target,
            "required_evidence": ["authorized_scope", "source_observation"],
            "expected_observation": purpose,
            "risk_level": "low",
            "approval_required": False,
            "tool_name": "",
            "structured_arguments": {},
        },
    )


class ReconAnalystAgent:
    name = "recon_analyst"

    async def execute(self, context: AgentContext) -> AgentResult:
        if context.evidence:
            return AgentResult(complete=True)
        target = str(context.run.metadata.get("target_id", "approved-scope"))
        return AgentResult(
            messages=(_proposal("recon_observation", "Review existing asset inventory and identify missing ownership metadata.", target),),
            evidence=(EvidenceDraft(evidence_type="gap", source=self.name, summary="No prior evidence is available; asset inventory is required."),),
            complete=True,
        )


class EnumerationAnalystAgent:
    name = "enumeration_analyst"

    async def execute(self, context: AgentContext) -> AgentResult:
        summaries = {item.summary for item in context.evidence}
        if any("service" in summary.lower() or "port" in summary.lower() for summary in summaries):
            return AgentResult(complete=True)
        target = str(context.run.metadata.get("target_id", "approved-scope"))
        return AgentResult(
            messages=(_proposal("service_observation", "Collect approved service and technology observations; do not infer versions without evidence.", target),),
            evidence=(EvidenceDraft(evidence_type="gap", source=self.name, summary="Service and version evidence is unavailable."),),
            complete=True,
        )
