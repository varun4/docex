"""Pydantic models for health check responses."""

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    """Status and latency for a single external dependency."""

    status: str
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    """Aggregated health status across all external dependencies."""

    status: str
    version: str
    dependencies: dict[str, DependencyStatus]
