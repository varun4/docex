from pydantic import BaseModel


class DependencyStatus(BaseModel):
    status: str
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    dependencies: dict[str, DependencyStatus]
