from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import os
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Generic,
    Iterable,
    List,
    Literal,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from pydantic import BaseModel as PydanticBaseModel
from redis.asyncio.client import PubSub, Redis

from .ipcmodels import RedisCommand, RedisMessage, RedisRequest, RedisResponse
from .models import LeagueData, PlayerData, PlayerLeagueData

if TYPE_CHECKING:
    from .bot import Bot

__all__ = (
    'Cache',
)

B = TypeVar('B', None, 'Bot')

class Cache(Generic[B]):
    def __init__(self, bot: B, identifier: int) -> None:
        self.bot = bot
        self.identifier = identifier
        self.loop = asyncio.get_running_loop()

        self.redis: Redis
        self.pubsub: PubSub

        self.responses: Dict[str, List[RedisResponse]] = {}
        self.futures: Dict[str, asyncio.Future[RedisResponse]] = {}
        self.endpoints: List[RedisCommand[PydanticBaseModel]] = []

        self._task: asyncio.Task[None]

    async def start(self, endpoint_directory: str='endpoints') -> None:
        self.redis = Redis(
            host = os.getenv("REDISHOST", "localhost"), 
            password = os.getenv("REDISPASSWORD"), 
            decode_responses = True,
            health_check_interval = 60,
            retry_on_timeout = True,
        )
        self.pubsub = self.redis.pubsub()

        await self.redis.initialize()
        await self.pubsub.connect()

        self.load_endpoints(endpoint_directory)
        self._task = asyncio.create_task(self.listen())
    
    async def stop(self) -> None:
        if hasattr(self, '_task') and not self._task.done():
            self._task.cancel()

        await self.pubsub.unsubscribe()
        await self.pubsub.aclose()
        await self.redis.aclose()

    async def set(self, *path: str | int, model: Union[Dict[str, Any], PydanticBaseModel], nx: bool=False) -> bool:
        name = ":".join([str(x) for x in path])
        data = model.model_dump() if isinstance(model, PydanticBaseModel) else model

        res = await self.redis.set(name, json.dumps(data), ex=604800, nx=nx)

        if res:
            return True
        return False
    
    async def get[T](self, *path: str | int, model_cls: Type[T]) -> Optional[T]:
        name = ":".join([str(x) for x in path])
        item = await self.redis.get(name)

        if not item:
            return None
        
        data = json.loads(item)
        if isinstance(model_cls, PydanticBaseModel):
            return model_cls.model_validate(data)
        return model_cls(**data)
    
    async def delete(self, *paths: Union[Tuple[str], str]) -> None:
        path_dict: Dict[Optional[int], List[str]] = {None: []}

        for i, path in enumerate(paths):
            if isinstance(path, (list, tuple)):
                path_dict[i] = list(path)
            else:
                path_dict[None].append(path)

        await self.redis.delete(*[":".join(map(str, path)) for path in path_dict.values()])
    
    async def hash_set(self, model: Union[LeagueData, PlayerData, PlayerLeagueData], *, identifier: str, keys: Iterable[str]) -> None:
        necessary_keys = {'league_id', 'player_id'} if isinstance(model, PlayerLeagueData) else {'id'}
        necessary_keys.update(keys)

        name = f"{model.__class__.__name__}:{identifier}"
        dump = model.model_dump(mode="json", include=necessary_keys)

        await self.redis.hset(name, mapping={
            k: json.dumps(v)
            for k, v in dump.items()
        }) # type: ignore
        await self.redis.hexpire(name, 60 * 60, *necessary_keys)

    async def hash_get[T: Union[LeagueData, PlayerData, PlayerLeagueData]](self, model_cls: Type[T], *, identifier: str, keys: Iterable[str]) -> Tuple[Optional[T], Set[str]]:
        necessary_keys = {'league_id', 'player_id'} if issubclass(model_cls, PlayerLeagueData) else {'id'}
        necessary_keys.update(keys)

        name = f"{model_cls.__name__}:{identifier}"

        if not await self.redis.exists(name):
            return (None, necessary_keys)
        
        necessary_keys = list(necessary_keys)
        data = await self.redis.hmget(name, necessary_keys) # type: ignore

        mapping: Dict[str, Any] = {}
        unretrieved: Set[str] = set()

        for i, key in enumerate(necessary_keys):
            loaded = json.loads(data[i])

            if data[i] is not None:
                mapping[key] = loaded
            else:
                unretrieved.add(key)

        return (model_cls.model_validate(mapping, strict=True), unretrieved)
    
    def load_endpoints(self, folder_path: str) -> None:
        for dirpath, _, files in os.walk(folder_path):
            for file in files:
                if not file.endswith('.py'):
                    continue
                
                module_path = os.path.join(dirpath, file).replace(os.sep, '.').replace('/', '.')[:-3]

                spec = importlib.util.find_spec(module_path)
                if not spec:
                    raise FileNotFoundError(f"Couldn't find '{module_path}'")

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module) # type: ignore

                commands: List[Type[RedisCommand[PydanticBaseModel]]] = [
                    obj for obj in module.__dict__.values() if isinstance(obj, type) and issubclass(obj, RedisCommand) and obj is not RedisCommand
                ]

                for cmd in commands:
                    self.endpoints.append(cmd(self)) # type: ignore

    async def listen(self) -> None:
        channels = [x.CHANNEL for x in self.endpoints]
        if channels:
            await self.pubsub.subscribe(*channels)

        while True:
            message_data = await self.pubsub.get_message(ignore_subscribe_messages=True)

            if message_data is None:
                await asyncio.sleep(0.1)
                continue
            
            message = RedisMessage.model_validate(message_data)
            
            if 'reply' in message.channel.lower():
                resp = RedisResponse.model_validate(message.data)

                if message.channel in self.responses:
                    self.responses[message.channel].append(resp)
                elif message.channel in self.futures:
                    future = self.futures.pop(message.channel)
                    future.set_result(resp)
            else:
                asyncio.create_task(self.handle(message))

    async def handle(self, message: RedisMessage) -> None:
        request = RedisRequest.model_validate(message.data)

        if request.identifier is not None and request.identifier != self.identifier:
            return
        
        command = next((x for x in self.endpoints if x.CHANNEL == message.channel), None)

        if command:
            response_data = await command.handle(command.MODEL.model_validate(request.data))
            response = RedisResponse(identifier=self.identifier, data=response_data)
        else:
            response = RedisResponse(identifier=self.identifier, data=None)

        await self.redis.publish(
            channel = f"reply:{request.nonce}",
            message = response.model_dump_json()
        )
    
    async def send_message(self, channel: str, data: Dict[str, Any], wait_for: float=1.5, return_when: Literal['all', 'first']='all') -> List[RedisResponse]:
        request = RedisRequest(identifier=None, data=data)

        await self.pubsub.subscribe(f"reply:{request.nonce}")
        await self.redis.publish(
            channel = channel,
            message = request.model_dump_json()
        )

        if return_when == 'first':
            return [await self.wait_for_reply(request, timeout=wait_for)]
        return await self.wait_for_replies(request, wait_for=wait_for)
    
    async def send_message_to(self, identifier: int, channel:str, data: Dict[str, Any], timeout: float=1.5) -> RedisResponse:
        request = RedisRequest(identifier=identifier, data=data)

        await self.pubsub.subscribe(f"reply:{request.nonce}")
        await self.redis.publish(
            channel = channel,
            message = request.model_dump_json()
        )

        return await self.wait_for_reply(request, timeout=timeout)

    async def wait_for_replies(self, request: RedisRequest, wait_for: float) -> List[RedisResponse]:
        self.responses[f"reply:{request.nonce}"] = []

        await asyncio.sleep(wait_for)
        responses = self.responses[f"reply:{request.nonce}"]

        self.responses.pop(f"reply:{request.nonce}")
        await self.pubsub.unsubscribe(f"reply:{request.nonce}")

        return responses
    
    async def wait_for_reply(self, request: RedisRequest, timeout: float) -> RedisResponse:
        future: asyncio.Future[RedisResponse] = self.loop.create_future()
        self.futures[f"reply:{request.nonce}"] = future

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self.futures.pop(f"reply:{request.nonce}")
            return RedisResponse(identifier=-1, data=None)
        finally:
            future.cancel()
            await self.pubsub.unsubscribe(f"reply:{request.nonce}")