"""Standardized error codes returned in all API error responses."""

from enum import Enum


class ErrorCode(str, Enum):
    """Enumerates all application-level error codes used in the error response envelope."""
    MISSING_TENANT = "MISSING_TENANT"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class EventStatus(str, Enum):
    """Processing status for outbox document events."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class EventType(str, Enum):
    """Types of document events published to Kafka / stored in outbox."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
