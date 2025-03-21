from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from .cache import B, Cache

__all__ = (
    'RedisMessage',
    'RedisRequest',
    'RedisResponse',
    'RedisCommand',
)

class RedisMessage(BaseModel):
    type: str
    pattern: Optional[str]
    channel: str
    data: int | Dict[str, Any]

    @field_validator('data', mode='before')
    @classmethod
    def wrap_data(cls, data: int | str, handler: Any):
        if isinstance(data, str):
            return json.loads(data)
        return data
    
class RedisRequest(BaseModel):
    identifier: Optional[int]
    nonce: str = Field(default_factory=lambda : str(uuid4()))
    data: Dict[str, Any]

class RedisResponse(BaseModel):
    identifier: int
    data: Optional[Dict[str, Any]]

class RedisCommand[T: BaseModel]:
    CHANNEL: str
    MODEL: T

    def __init__(self, cache: Cache[B]) -> None:
        self.cache = cache

    async def handle(self, context: T) -> Optional[Dict[str, Any]]:
        raise NotImplementedError()