"""Digest-backed bearer authentication and role checks for the observer API."""

from __future__ import annotations

import hashlib
import hmac

from pydantic import BaseModel, ConfigDict

from redmind.runtime.models import StrEnum


class AccessRole(StrEnum):
    VIEWER = "viewer"
    AUDITOR = "auditor"


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    role: AccessRole


class AuthenticationError(ValueError):
    """Raised when no configured credential matches a bearer token."""


class AuthorizationError(ValueError):
    """Raised when an authenticated principal lacks the required role."""


class StaticTokenAuthorizer:
    """Stores only SHA-256 token digests and compares them in constant time."""

    def __init__(self, viewer_token: str, auditor_token: str) -> None:
        if not viewer_token or not auditor_token:
            raise ValueError("viewer and auditor tokens are required")
        if hmac.compare_digest(viewer_token, auditor_token):
            raise ValueError("viewer and auditor tokens must be different")
        self._credentials = (
            (
                self._digest(viewer_token),
                Principal(subject="observer-viewer", role=AccessRole.VIEWER),
            ),
            (
                self._digest(auditor_token),
                Principal(subject="observer-auditor", role=AccessRole.AUDITOR),
            ),
        )

    def authenticate(self, token: str) -> Principal:
        candidate = self._digest(token)
        for expected, principal in self._credentials:
            if hmac.compare_digest(candidate, expected):
                return principal
        raise AuthenticationError("invalid bearer credential")

    def authorize(self, token: str, required: AccessRole) -> Principal:
        principal = self.authenticate(token)
        if required is AccessRole.AUDITOR and principal.role is not AccessRole.AUDITOR:
            raise AuthorizationError("auditor role is required")
        return principal

    @staticmethod
    def _digest(token: str) -> bytes:
        return hashlib.sha256(token.encode("utf-8")).digest()
