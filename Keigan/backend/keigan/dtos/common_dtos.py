"""Base DTO and shared response beans. All JSON is camelCase; Python attributes stay snake_case."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

ItemType = TypeVar("ItemType")


class ApiModel(BaseModel):
    """Base for every request and response body."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class PagedResult(ApiModel, Generic[ItemType]):
    items: list[ItemType]
    total_count: int
    page: int = 1
    page_size: int = 50


class JobAcceptedResponse(ApiModel):
    job_id: str
    status: str = "queued"
    message: str | None = None


class MessageResponse(ApiModel):
    message: str


class IdentifierResponse(ApiModel):
    identifier: str
