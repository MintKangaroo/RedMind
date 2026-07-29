import asyncio

import pytest
from pydantic import Field, ValidationError

from redmind.runtime import ToolCategory, ToolPermission, ToolRegistry, ToolSpec
from redmind.runtime.tools import ToolInput


class AssetInput(ToolInput):
    target: str = Field(min_length=1)


def test_registry_validates_input_and_audits_calls():
    records = []

    async def audit(record):
        records.append(record)

    async def handler(arguments: AssetInput):
        return {"target": arguments.target}

    registry = ToolRegistry(audit_hook=audit)
    registry.register(
        ToolSpec(
            "asset_inventory", ToolCategory.READ_ONLY, ToolPermission.READ, AssetInput, handler
        )
    )
    result = asyncio.run(registry.execute("asset_inventory", {"target": "lab-host"}))
    assert result == {"target": "lab-host"}
    assert records[0].outcome == "completed"


def test_registry_rejects_disabled_categories_and_unknown_tools():
    async def handler(arguments):
        return None

    registry = ToolRegistry()
    with pytest.raises(ValueError):
        registry.register(
            ToolSpec(
                "mutate", ToolCategory.STATE_CHANGING, ToolPermission.WRITE, AssetInput, handler
            )
        )
    with pytest.raises(KeyError):
        asyncio.run(registry.execute("missing", {}))


def test_registry_rejects_extra_arguments_and_shell_names():
    async def handler(arguments):
        return None

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "observe_asset", ToolCategory.OBSERVATION, ToolPermission.OBSERVE, AssetInput, handler
        )
    )
    with pytest.raises(ValidationError):
        asyncio.run(registry.execute("observe_asset", {"target": "x", "command": "ls"}))
    with pytest.raises(ValueError):
        ToolSpec(
            "shell_exec", ToolCategory.OBSERVATION, ToolPermission.OBSERVE, AssetInput, handler
        )


def test_registry_rejects_invalid_timeout_duplicates_and_audits_failures():
    records = []

    async def audit(record):
        records.append(record)

    async def failing_handler(arguments):
        raise RuntimeError("tool failed")

    with pytest.raises(ValueError, match="positive"):
        ToolSpec(
            "invalid_timeout",
            ToolCategory.READ_ONLY,
            ToolPermission.READ,
            AssetInput,
            failing_handler,
            timeout_seconds=0,
        )

    registry = ToolRegistry(audit_hook=audit)
    spec = ToolSpec(
        "asset_reader",
        ToolCategory.READ_ONLY,
        ToolPermission.READ,
        AssetInput,
        failing_handler,
    )
    registry.register(spec)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(spec)
    with pytest.raises(RuntimeError, match="tool failed"):
        asyncio.run(registry.execute("asset_reader", AssetInput(target="lab-host")))
    assert records[0].outcome == "failed"
