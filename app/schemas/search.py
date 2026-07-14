from uuid import UUID

from pydantic import BaseModel


class SearchResult(BaseModel):
    id: UUID
    title: str
    rank: float = 0.0


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    page: int
    size: int
