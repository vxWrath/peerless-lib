from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from .cache import Cache


class RedisMessage(BaseModel):
    type: str
    pattern: Optional[str]
    channel: str
    data: int | Dict[str, Any]

    @field_validator('data', mode='before')
    @classmethod
    def wrap_data(cls, v: int | str, handler):
        if isinstance(v, str):
            return json.loads(v)
        return v
    
class RedisRequest(BaseModel):
    nonce: str = Field(default_factory=lambda : str(uuid4()))
    data: Dict[str, Any]

class RedisResponse(BaseModel):
    data: Dict[str, Any]

class RedisCommand[T: BaseModel]:
    CHANNEL: str
    MODEL: T

    def __init__(self, cache: 'Cache') -> None:
        self.cache = cache

    async def handle(self, context: T) -> Dict[str, Any]:
        raise NotImplementedError()