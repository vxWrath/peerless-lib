from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, Optional, Set, Union

import asyncpg

from .cache import Cache
from .models import LeagueData, PlayerData, PlayerLeagueData

if TYPE_CHECKING:
    from .bot import Bot

async def postgres_initializer(con):
    await con.set_type_codec(
        'jsonb',
        schema='pg_catalog',
        encoder=json.dumps,
        decoder=json.loads,
        format='text',
    )

class Database:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool
        self.cache: Cache

    @classmethod
    async def create(cls, bot: Bot):
        self = cls()
        
        self.pool  = await asyncpg.create_pool(init=postgres_initializer)
        self.cache = bot.cache

        return self
    
    async def close(self) -> None:
        if hasattr(self, 'pool'):
            await self.pool.close()
    
    async def insert(self, table: str, model: Union[LeagueData, PlayerData, PlayerLeagueData], excluded: Set[str]) -> None:
        dump: Dict[str, Any] = {
            k: json.dumps(v) if isinstance(v, (dict, list)) else v 
            for k, v in model.model_dump(exclude=excluded).items()
        }

        await self.pool.execute(f"""
            INSERT INTO {table} ({', '.join(dump.keys())}) 
            VALUES ({', '.join(f'${i}' for i in range(1, len(dump.values())+1))});
        """, *dump.values())

    async def update(self, table: str, model: Union[LeagueData, PlayerData, PlayerLeagueData], *, keys: Set[str]) -> None:
        dump: Dict[str, Any] = {
            k: json.dumps(v) if isinstance(v, (dict, list)) else v 
            for k, v in model.model_dump(include=set(keys)).items()
        }

        if isinstance(model, PlayerLeagueData):
            await self.pool.execute(f"""
                UPDATE {table} 
                SET {', '.join(f"{key}=${i}" for i, key in enumerate(dump.keys(), 1))} 
                WHERE player_id={len(dump.keys())+1} AND league_id={len(dump.keys())+2};
            """, *dump.values(), model.player_id, model.league_id)
        else:
            await self.pool.execute(f"""
                UPDATE {table} 
                SET {', '.join(f"{key}=${i}" for i, key in enumerate(dump.keys(), 1))} 
                WHERE id={len(dump.keys())+1};
            """, *dump.values(), model.id)

    async def delete(self, table: str, model: Union[LeagueData, PlayerData, PlayerLeagueData]) -> None:
        if isinstance(model, PlayerLeagueData):
            await self.pool.execute(f"""
                DELETE FROM {table} WHERE player_id=$1 AND league_id=$2
            """, model.player_id, model.league_id)
        else:
            await self.pool.execute(f"""
                DELETE FROM {table} WHERE id=$1
            """, model.id)

    async def create_league(self, league_id: int) -> LeagueData:
        league_data = LeagueData(id=league_id)
        league_data._db = self

        await self.insert(
            table = "leagues",
            model = league_data,
            excluded = set()
        )

        return league_data

    async def create_player(self, player_id: int) -> PlayerData:
        player_data = PlayerData(id=player_id)
        player_data._db = self

        await self.insert(
            table = "players",
            model = player_data,
            excluded = {'leagues'}
        )

        return player_data

    async def create_player_league(self, player_data: PlayerData, league_data: LeagueData) -> PlayerLeagueData:
        player_league_data = PlayerLeagueData(player_id=player_data.id, league_id=league_data.id)
        player_league_data._db = self

        await self.insert(
            table = "player_leagues",
            model = player_league_data,
            excluded = set()
        )

        return player_league_data

    async def fetch_league(self, league_id: int, *, keys: Set[str]) -> Optional[LeagueData]:
        necessary_keys = {'id'}
        necessary_keys.update(keys)
        
        league_data, missing = await self.cache.hash_get(LeagueData, identifier=str(league_id), keys=keys)

        if league_data and missing:
            data = await self.pool.fetchrow(f"SELECT {', '.join(missing)} FROM leagues WHERE id=$1", league_id)

            league_data.model_copy(update=dict(data))
            await self.cache.hash_set(league_data, identifier=str(league_id), keys=necessary_keys)

        elif not league_data:
            data = await self.pool.fetchrow(f"SELECT {', '.join(necessary_keys)} FROM leagues WHERE id=$1", league_id)

            if not data:
                return

            league_data = LeagueData.model_validate(dict(data), strict=True)
            await self.cache.hash_set(league_data, identifier=str(league_id), keys=missing)

        league_data._db = self
        return league_data

    async def fetch_player(self, player_id: int, league_id: int, *, keys: Set[str]) -> Optional[PlayerData]:
        necessary_keys = {'player_id', 'league_id'}
        necessary_keys.update(keys)
        
        player_data, _ = await self.cache.hash_get(PlayerData, identifier=str(league_id), keys={'id', 'blacklisted'})
        player_league_data, missing = await self.cache.hash_get(PlayerLeagueData, identifier=f"{player_id}:{league_id}", keys=necessary_keys)

        if not player_data or missing:
            async with self.pool.acquire() as con:
                if not player_data:
                    data = await con.fetchrow(f"SELECT * FROM players WHERE id=$1", player_id)

                    if not data:
                        return None
                    
                    player_data = PlayerData.model_validate(dict(data) | {"leagues": {}}, strict=True)
                    await self.cache.hash_set(player_data, identifier=str(player_id), keys={'id', 'blacklisted'})

                if not player_league_data:
                    data = await con.fetchrow(f"SELECT {', '.join(necessary_keys)} FROM player_leagues WHERE player_id=$1 AND league_id=$2", player_id, league_id)
                
                    if data:
                        player_league_data = PlayerLeagueData.model_validate(dict(data), strict=True)
                        await self.cache.hash_set(player_league_data, identifier=f"{player_id}:{league_id}", keys=necessary_keys)
                
                elif player_league_data and missing:
                    data = await con.fetchrow(f"SELECT {', '.join(missing)} FROM player_leagues WHERE player_id=$1 AND league_id=$2", player_id, league_id)

                    if data:
                        player_league_data = player_league_data.model_copy(update=dict(data))
                        await self.cache.hash_set(player_league_data, identifier=f"{player_id}:{league_id}", keys=missing)
                    else:
                        player_league_data = None

        player_data._db = self

        if player_league_data:
            player_league_data._db = self
            player_data.leagues[player_league_data.league_id] = player_league_data

        return player_data

    async def update_league(self, league_data: LeagueData, *, keys: Set[str]) -> None:
        await self.update("leagues", league_data, keys=keys)
        await self.cache.hash_set(league_data, identifier=str(league_data.id), keys=keys)

    async def update_player_league(self, player_league_data: PlayerLeagueData, *, keys: Set[str]):
        await self.update("player_leagues", player_league_data, keys=keys)
        await self.cache.hash_set(player_league_data, identifier=f"{player_league_data.player_id}:{player_league_data.league_id}", keys=keys)

    async def produce_league(self, league_id: int, *, keys: Set[str]) -> LeagueData:
        league_data = await self.fetch_league(league_id, keys=keys)

        if not league_data:
            league_data = await self.create_league(league_id)

        return league_data
    
    async def produce_player(self, player_id: int, league_data: Optional[LeagueData]=None, *, keys: Optional[Set[str]]=None) -> PlayerData:
        player_data = await self.fetch_player(player_id, league_data.id if league_data else 0, keys=keys or set())

        if not player_data:
            player_data = await self.create_player(player_id)

        if league_data and not player_data.leagues.get(league_data.id):
            player_league_data = await self.create_player_league(player_data, league_data)
            player_data.leagues[player_league_data.league_id] = player_league_data

        return player_data