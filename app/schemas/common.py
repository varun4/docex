"""Shared Pydantic models used across multiple API endpoints."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error envelope returned by all error handlers."""
    code: str
    message: str
    detail: str = ""
