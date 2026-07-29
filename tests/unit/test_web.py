from uuid import uuid4

from fastapi.testclient import TestClient

from redmind.web import InMemoryTimelineRepository, create_app, demo_timelines
from redmind.web.timeline import demo_timeline


def test_timeline_api_and_ui_are_read_only():
    timeline = demo_timeline()
    app = create_app(InMemoryTimelineRepository((timeline,)))

    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").json() == {"status": "ready"}
        metadata = client.get("/api/v1/meta").json()
        assert metadata == {
            "version": "0.3.0",
            "environment": "local",
            "authentication_required": False,
            "signed_exports": False,
        }
        runs = client.get("/api/v1/runs")
        assert runs.status_code == 200
        assert runs.json()[0]["id"] == str(timeline.run.id)
        detail = client.get(f"/api/v1/runs/{timeline.run.id}")
        assert detail.json()["approvals"][0]["status"] == "approved"
        assert client.get("/").status_code == 200
        assert client.get("/assets/app.css").status_code == 200

    assert all(
        route.methods == {"GET"}
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/")
    )


def test_default_dashboard_exposes_sorted_demo_states():
    with TestClient(create_app()) as client:
        runs = client.get("/api/v1/runs").json()
        assert tuple(run["state"] for run in runs) == ("completed", "executing", "rejected")
        assert tuple(run["id"] for run in runs) == tuple(
            str(timeline.run.id) for timeline in demo_timelines()
        )
        detail = client.get(f"/api/v1/runs/{runs[-1]['id']}").json()
        assert detail["failure"]["kind"] == "policy_denied"


def test_demo_timelines_cover_dashboard_trust_and_empty_states():
    completed, running, rejected = demo_timelines()
    assert completed.evidence[0].trust == "untrusted"
    assert running.run.progress_percent == 62
    assert running.approvals == ()
    assert rejected.tool_calls == ()
    assert rejected.approvals[0].status == "rejected"


def test_unknown_and_unconfigured_audit_routes():
    with TestClient(create_app(InMemoryTimelineRepository())) as client:
        assert client.get(f"/api/v1/runs/{uuid4()}").status_code == 404
        response = client.get(f"/api/v1/runs/{uuid4()}/audit-export")
        assert response.status_code == 503


def test_readiness_failure_returns_service_unavailable():
    async def unavailable():
        return False

    with TestClient(create_app(readiness=unavailable)) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
