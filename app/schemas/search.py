"""Pydantic models for search request parameters and response payloads."""

from uuid import UUID

from pydantic import BaseModel


class SearchResult(BaseModel):
    """Single search hit with document id, title, and relevance score."""

    id: UUID
    title: str
    rank: float = 0.0


class SearchResponse(BaseModel):
    """Paginated search results with total hit count."""

    results: list[SearchResult]
    total: int
    page: int
    size: int
