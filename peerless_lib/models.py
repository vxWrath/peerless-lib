from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional
from uuid import uuid4

from discord import Permissions
from pydantic import BaseModel as PydanticBaseModel
from pydantic import (
    ConfigDict,
    Field,
    PrivateAttr,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from .namespace import Namespace

if TYPE_CHECKING:
    from .database import Database


class DataModel(PydanticBaseModel, Mapping):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    def __getattribute__(self, key: str) -> Any:
        if (
            key in super().__getattribute__('__pydantic_fields__').keys()
            and key not in super().__getattribute__('__pydantic_fields_set__')
        ):
            raise ValueError(f"'{self.__class__.__name__}.{key}' is not currently available")
        
        return super().__getattribute__(key)
    
    def __setitem__(self, key: str, val: Any) -> None:
        setattr(self, key, val)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)
    
    def __len__(self) -> int:
        return len(self.model_dump())

class LeagueData(DataModel):
    id: int
    teams: Namespace[str, 'Team'] = Field(default_factory=Namespace)

    _db: 'Database' = PrivateAttr(init=False)

class Team(PydanticBaseModel):
    token: str = Field(default_factory=lambda : str(uuid4()))

    role_name: str
    role_id: Optional[int] = None
    emoji_id: Optional[int] = None

class PlayerData(DataModel):
    id: int
    blacklisted: bool = False
    leagues: Namespace[int, 'PlayerLeagueData'] = Field(default_factory=Namespace)

    _db: 'Database' = PrivateAttr(init=False)

    def __getattribute__(self, key: str) -> Any:
        return super(PydanticBaseModel, self).__getattribute__(key)
    
class PlayerLeagueData(DataModel):
    player_id: int
    league_id: int
    demands: int = 3

    _db: 'Database' = PrivateAttr(init=False)

class PartialUser(PydanticBaseModel):
    id: int
    username: str
    avatar: str
    global_name: str

    @computed_field
    def avatar_url(self) -> str:
        if not self.avatar:
            return 'https://cdn.discordapp.com/embed/avatars/1.png'
        
        animated = self.avatar.startswith('a_')
        image_format = 'gif' if animated else 'png'

        return f'https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}.{image_format}?size=1024'

class PartialGuild(PydanticBaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    name: str
    icon: Optional[str]
    banner: Optional[str]
    owner: bool
    permissions: Permissions

    @field_validator('permissions', mode='wrap')
    @classmethod
    def perm_validator(cls, value: str | int, handler):
        if isinstance(value, int):
            v = Permissions._from_value(value)
        elif value.isdigit():
            v = Permissions._from_value(int(value))
        return handler(v)
    
    @field_serializer('permissions')
    def perm_serializer(self, permissions: Permissions) -> int:
        return permissions.value
    
    @model_validator(mode='before')
    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> Any:  
        data['permissions'] = data.pop('permissions_new', None) or data['permissions']
        return data
    
    @computed_field
    def icon_url(self) -> str:
        if not self.icon:
            return 'https://cdn.discordapp.com/embed/avatars/1.png'
        
        animated = self.icon.startswith('a_')
        image_format = 'gif' if animated else 'png'
        
        return f'https://cdn.discordapp.com/icons/{self.id}/{self.icon}.{image_format}?size=1024'