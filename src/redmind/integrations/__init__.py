"""External integration adapters."""

from redmind.integrations.autopentest import (
    AssetRecord,
    AutoPentestAdapter,
    AutoPentestAPIError,
    AutoPentestConfig,
    FindingRecord,
    ObservationResult,
    Transport,
    TransportResponse,
    UrllibTransport,
)

__all__ = [
    "AssetRecord",
    "AutoPentestAdapter",
    "AutoPentestAPIError",
    "AutoPentestConfig",
    "FindingRecord",
    "ObservationResult",
    "Transport",
    "TransportResponse",
    "UrllibTransport",
]
