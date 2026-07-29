"""Fail-closed production application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from redmind.web.app import create_app
from redmind.web.auth import StaticTokenAuthorizer
from redmind.web.repository import SQLRepository
from redmind.web.settings import ObserverSettings
from redmind.web.signing import AuditSigner
from redmind.web.telemetry import ObserverTelemetry, TelemetryRuntime, create_otlp_runtime


def create_app_from_env() -> FastAPI:
    settings = ObserverSettings.from_env()
    if settings.environment != "production":
        raise RuntimeError("production app factory requires REDMIND_ENVIRONMENT=production")

    viewer_token = settings.viewer_token
    auditor_token = settings.auditor_token
    signing_key = settings.audit_signing_key
    if viewer_token is None or auditor_token is None or signing_key is None:
        raise RuntimeError("validated production credentials are unavailable")

    repository = SQLRepository.from_url(settings.database_url)
    authorizer = StaticTokenAuthorizer(
        viewer_token.get_secret_value(),
        auditor_token.get_secret_value(),
    )
    signer = AuditSigner(signing_key.get_secret_value())
    telemetry_runtime = (
        create_otlp_runtime(settings.otel_service_name, settings.otlp_endpoint)
        if settings.otlp_endpoint is not None
        else TelemetryRuntime(observer=ObserverTelemetry())
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await repository.initialize()
        try:
            yield
        finally:
            telemetry_runtime.shutdown()
            await repository.close()

    return create_app(
        repository,
        authorizer=authorizer,
        audit_signer=signer,
        telemetry=telemetry_runtime.observer,
        readiness=repository.ready,
        lifespan=lifespan,
        environment=settings.environment,
    )
