"""Validated environment settings for local and production observer deployments."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class ObserverSettings(BaseModel):
    """Fail-closed production settings loaded from explicit REDMIND variables."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: Literal["local", "production"] = "local"
    database_url: str = "sqlite+aiosqlite:///:memory:"
    viewer_token: SecretStr | None = None
    auditor_token: SecretStr | None = None
    audit_signing_key: SecretStr | None = None
    otel_service_name: str = Field(default="redmind-observer", min_length=1, max_length=100)
    otlp_endpoint: str | None = None

    @model_validator(mode="after")
    def validate_environment_boundary(self) -> ObserverSettings:
        secrets = (self.viewer_token, self.auditor_token, self.audit_signing_key)
        if self.environment == "production":
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("production requires a postgresql+asyncpg database URL")
            if any(secret is None or len(secret.get_secret_value()) < 32 for secret in secrets):
                raise ValueError(
                    "production tokens and signing key must contain at least 32 characters"
                )
        provided_tokens = tuple(
            secret.get_secret_value()
            for secret in (self.viewer_token, self.auditor_token)
            if secret is not None
        )
        if len(provided_tokens) == 1:
            raise ValueError("viewer and auditor tokens must be configured together")
        if len(provided_tokens) == 2 and provided_tokens[0] == provided_tokens[1]:
            raise ValueError("viewer and auditor tokens must be different")
        if self.otlp_endpoint is not None:
            parsed = urlparse(self.otlp_endpoint)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("OTLP endpoint must be an HTTP(S) origin without credentials")
        return self

    @property
    def authentication_enabled(self) -> bool:
        return self.viewer_token is not None and self.auditor_token is not None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ObserverSettings:
        values = environ if environ is not None else os.environ
        raw: dict[str, str] = {}
        mapping = {
            "environment": "REDMIND_ENVIRONMENT",
            "database_url": "REDMIND_DATABASE_URL",
            "viewer_token": "REDMIND_VIEWER_TOKEN",
            "auditor_token": "REDMIND_AUDITOR_TOKEN",
            "audit_signing_key": "REDMIND_AUDIT_SIGNING_KEY",
            "otel_service_name": "REDMIND_OTEL_SERVICE_NAME",
            "otlp_endpoint": "REDMIND_OTLP_ENDPOINT",
        }
        for field, variable in mapping.items():
            if value := values.get(variable):
                raw[field] = value
        return cls.model_validate(raw)
