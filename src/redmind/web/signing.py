"""Canonical HMAC signatures for server-generated audit exports."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from redmind.web.auth import Principal
from redmind.web.timeline import RunTimeline

Clock = Callable[[], datetime]
UTC = timezone.utc  # noqa: UP017


def utc_now() -> datetime:
    return datetime.now(UTC)


class SignedAuditExport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal["redmind.signed-audit.v1"] = "redmind.signed-audit.v1"
    algorithm: Literal["HMAC-SHA256"] = "HMAC-SHA256"
    key_id: str = Field(min_length=12, max_length=12)
    run_id: UUID
    issued_at: datetime
    issued_to: str
    payload: RunTimeline
    signature: str = Field(pattern=r"^[a-f0-9]{64}$")


class AuditSigner:
    """Signs immutable timeline snapshots without exposing the signing key."""

    def __init__(self, signing_key: str, *, clock: Clock = utc_now) -> None:
        if len(signing_key) < 32:
            raise ValueError("audit signing key must contain at least 32 characters")
        self._key = signing_key.encode("utf-8")
        self._clock = clock
        self.key_id = hashlib.sha256(self._key).hexdigest()[:12]

    def sign(self, timeline: RunTimeline, principal: Principal) -> SignedAuditExport:
        draft = SignedAuditExport(
            key_id=self.key_id,
            run_id=timeline.run.id,
            issued_at=self._clock(),
            issued_to=principal.subject,
            payload=timeline,
            signature="0" * 64,
        )
        unsigned = draft.model_dump(mode="json", exclude={"signature"})
        signature = hmac.new(self._key, self._canonical(unsigned), hashlib.sha256).hexdigest()
        return draft.model_copy(update={"signature": signature})

    def verify(self, export: SignedAuditExport) -> bool:
        unsigned = export.model_dump(mode="json", exclude={"signature"})
        expected = hmac.new(self._key, self._canonical(unsigned), hashlib.sha256).hexdigest()
        return hmac.compare_digest(export.signature, expected)

    @staticmethod
    def _canonical(payload: object) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
