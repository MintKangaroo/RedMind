"""Privacy-conscious OpenTelemetry spans and metrics for the observer API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from importlib import import_module
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Request, Response
from opentelemetry import metrics, trace
from opentelemetry.metrics import Counter, Histogram, Meter
from opentelemetry.trace import SpanKind, Tracer


class ObserverTelemetry:
    """Instrument HTTP requests without recording credentials or payloads."""

    def __init__(self, *, tracer: Tracer | None = None, meter: Meter | None = None) -> None:
        self.tracer = tracer or trace.get_tracer("redmind.observer")
        resolved_meter = meter or metrics.get_meter("redmind.observer")
        self.request_counter: Counter = resolved_meter.create_counter(
            "redmind.observer.http.requests",
            unit="{request}",
            description="Observer HTTP requests",
        )
        self.duration_histogram: Histogram = resolved_meter.create_histogram(
            "redmind.observer.http.duration",
            unit="ms",
            description="Observer HTTP request duration",
        )

    def instrument(self, app: FastAPI) -> None:
        @app.middleware("http")
        async def observe_request(
            request: Request,
            call_next: Callable[[Request], Awaitable[Response]],
        ) -> Response:
            started = perf_counter()
            method = request.method
            status_code = 500
            with self.tracer.start_as_current_span(
                f"HTTP {method}",
                kind=SpanKind.SERVER,
                attributes={"http.request.method": method},
            ) as span:
                try:
                    response = await call_next(request)
                    status_code = response.status_code
                    return response
                except Exception as exc:
                    span.record_exception(exc)
                    raise
                finally:
                    route = request.scope.get("route")
                    route_path = getattr(route, "path", "unmatched")
                    attributes = {
                        "http.request.method": method,
                        "http.route": route_path,
                        "http.response.status_code": status_code,
                    }
                    span.set_attributes(attributes)
                    self.request_counter.add(1, attributes)
                    self.duration_histogram.record(
                        (perf_counter() - started) * 1_000,
                        attributes,
                    )


@dataclass(frozen=True)
class TelemetryRuntime:
    observer: ObserverTelemetry
    tracer_provider: Any | None = None
    meter_provider: Any | None = None

    def shutdown(self) -> None:
        if self.meter_provider is not None:
            self.meter_provider.shutdown()
        if self.tracer_provider is not None:
            self.tracer_provider.shutdown()


def create_otlp_runtime(service_name: str, endpoint: str) -> TelemetryRuntime:
    """Create isolated OTLP providers; optional production extras are imported lazily."""

    try:
        metric_exporter_module = import_module(
            "opentelemetry.exporter.otlp.proto.http.metric_exporter"
        )
        trace_exporter_module = import_module(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter"
        )
        metrics_module = import_module("opentelemetry.sdk.metrics")
        metrics_export_module = import_module("opentelemetry.sdk.metrics.export")
        resources_module = import_module("opentelemetry.sdk.resources")
        trace_module = import_module("opentelemetry.sdk.trace")
        trace_export_module = import_module("opentelemetry.sdk.trace.export")
    except ImportError as exc:  # pragma: no cover - depends on optional installation
        raise RuntimeError("OTLP export requires the redmind production dependency group") from exc

    OTLPMetricExporter = metric_exporter_module.OTLPMetricExporter
    OTLPSpanExporter = trace_exporter_module.OTLPSpanExporter
    MeterProvider = metrics_module.MeterProvider
    PeriodicExportingMetricReader = metrics_export_module.PeriodicExportingMetricReader
    Resource = resources_module.Resource
    TracerProvider = trace_module.TracerProvider
    BatchSpanProcessor = trace_export_module.BatchSpanProcessor

    resource = Resource.create({"service.name": service_name})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{endpoint.rstrip('/')}/v1/metrics")
            ),
        ),
    )
    return TelemetryRuntime(
        observer=ObserverTelemetry(
            tracer=tracer_provider.get_tracer("redmind.observer"),
            meter=meter_provider.get_meter("redmind.observer"),
        ),
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
