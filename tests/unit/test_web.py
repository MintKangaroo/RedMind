import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from redmind.web import InMemoryTimelineRepository, create_app, demo_timelines
from redmind.web.timeline import demo_timeline


def endpoints(app):
    return {route.path: route for route in app.routes if hasattr(route, "endpoint")}


def test_timeline_api_and_ui_are_read_only():
    timeline = demo_timeline()
    app = create_app(InMemoryTimelineRepository((timeline,)))
    routes = endpoints(app)
    assert asyncio.run(routes["/health/live"].endpoint()) == {"status": "ok"}
    runs = asyncio.run(routes["/api/v1/runs"].endpoint())
    assert runs[0].id == timeline.run.id
    detail = asyncio.run(routes["/api/v1/runs/{run_id}"].endpoint(timeline.run.id))
    assert detail.approvals[0].status == "approved"
    index = asyncio.run(routes["/"].endpoint())
    assert str(index.path).endswith("index.html")
    assert routes["/api/v1/runs"].methods == {"GET"}
    assert all(
        route.methods == {"GET"}
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/")
    )


def test_default_dashboard_exposes_sorted_demo_states():
    app = create_app()
    routes = endpoints(app)
    runs = asyncio.run(routes["/api/v1/runs"].endpoint())
    assert tuple(run.state for run in runs) == ("completed", "executing", "rejected")
    assert runs == tuple(timeline.run for timeline in demo_timelines())
    detail = asyncio.run(routes["/api/v1/runs/{run_id}"].endpoint(runs[-1].id))
    assert detail.failure is not None
    assert detail.failure.kind == "policy_denied"


def test_demo_timelines_cover_dashboard_trust_and_empty_states():
    completed, running, rejected = demo_timelines()
    assert completed.evidence[0].trust == "untrusted"
    assert running.run.progress_percent == 62
    assert running.approvals == ()
    assert rejected.tool_calls == ()
    assert rejected.approvals[0].status == "rejected"


def test_unknown_run_is_not_found():
    app = create_app(InMemoryTimelineRepository())
    route = endpoints(app)["/api/v1/runs/{run_id}"]
    with pytest.raises(HTTPException) as caught:
        asyncio.run(route.endpoint(uuid4()))
    assert caught.value.status_code == 404
