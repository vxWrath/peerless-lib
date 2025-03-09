import asyncio
import os
import sys
from typing import Any, List, Optional, Set

import colorlog
import discord
from discord.app_commands import Command, CommandTree
from discord.ext import commands

from .cache import Cache
from .database import Database
from .interaction import BeforeInteraction
from .namespace import Namespace

intents = discord.Intents.none()
intents.guilds  = True
intents.emojis  = True
intents.members = True

member_cache_flags = discord.MemberCacheFlags().none()
member_cache_flags.joined = True

class Bot(commands.AutoShardedBot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix = [],
            tree_cls = AppCommandTree,
            intents = intents,
            member_cache_flag = member_cache_flags,
            max_messages = None,
            chunk_guilds_at_startup = False,
        )

        self.cache: Cache
        self.database: Database

    async def setup_hook(self) -> None:
        await self.load_extensions()

        logger = colorlog.getLogger('bot')

        assert self.user
        
        logger.info(f"Logged in - {self.user.name} ({self.application_id})")
        logger.info(f"Loaded {len([x for x in self.tree.walk_commands() if isinstance(x, Command)])} Commands")

        self.tree.copy_global_to(guild=discord.Object(id=1258570200102469632))
        await self.tree.sync(guild=discord.Object(id=1258570200102469632))

    async def load_extensions(self) -> None:
        self._cogs_: List[str] = []
        
        for cog in self._cogs_:
            try:
                await self.reload_extension(cog)
            except commands.ExtensionNotLoaded:
                await self.load_extension(cog)
        
        dont_load: List[str] = []
        for dir_, _, files in os.walk('./commands'):
            for file in files:
                if not file.endswith('.py') or file in dont_load:
                    continue
                
                self._cogs_.append(dir_[2:].replace("\\" if sys.platform == 'win32' else '/', ".") + f".{file[:-3]}")
                
                try:
                    await self.reload_extension(self._cogs_[-1])
                except commands.ExtensionNotLoaded:
                    await self.load_extension(self._cogs_[-1])

        return None
                    
    async def unload_extensions(self) -> None:
        for i in range(0, len(self._cogs_)):
            try:
                await self.unload_extension(self._cogs_[i])
            except commands.ExtensionNotLoaded:
                pass

        return None

class AppCommandTree(CommandTree[Bot]):
    def _from_interaction(self, interaction: discord.Interaction[Bot]) -> None:
        async def wrapper():
            try:
                await self._call(interaction)
            except discord.app_commands.AppCommandError as e:
                await self._dispatch_error(interaction, e)

        self.client.loop.create_task(wrapper(), name='CommandTree-invoker')

    async def interaction_check(self, interaction: discord.Interaction[Bot]) -> bool:
        if interaction.guild and interaction.guild.unavailable:
            try:
                await interaction.response.send_message(
                    content = "<:fail:1136341671857102868>**| This server is unavailable. This is a discord issue.**", 
                    ephemeral = True
                )
            except discord.HTTPException:
                pass
            
            return False
        
        data: Namespace[str, Namespace[str, Any]] = Namespace(interaction.data) if interaction.data else Namespace() # type: ignore

        if interaction.command:
            before: BeforeInteraction = interaction.command.extras['before'] if 'before' in interaction.command.extras else BeforeInteraction()
        else:
            before: BeforeInteraction = interaction.extras['before'] if 'before' in interaction.extras else BeforeInteraction()

        if not before.modal_response and before.defer.defer:
            await interaction.response.defer(ephemeral=before.defer.ephemerally, thinking=before.defer.thinking)

        tasks: Namespace[str, Optional[asyncio.Task[Any]]] = Namespace(chunk_guild=None, fetch_league_data=None)

        if interaction.guild:
            if not interaction.guild.chunked:
                tasks.chunk_guild = self.client.loop.create_task(interaction.guild.chunk())

                if not before.modal_response and not before.defer.defer:
                    await interaction.response.defer(ephemeral=before.defer.ephemerally, thinking=before.defer.thinking)

            if before.league_data.retrieve:
                tasks.fetch_league_data = self.client.loop.create_task(
                    self.client.database.produce_league(interaction.guild.id, keys=before.league_data.keys)
                )

        player_ids: Set[int] = set()
        if before.player_data.retrieve:
            player_ids.add(interaction.user.id)

            if data.has('resolved'):
                for user_id, discord_user_data in (data.resolved.get('members') or data.resolved.get('users', {})).items():
                    if interaction.user.id == int(user_id) or discord_user_data.get('bot', False) or discord_user_data.get('user', {}).get('bot', False):
                        continue

                    player_ids.add(int(user_id))

        if any(tasks.values()) or player_ids:
            try:
                async with asyncio.timeout(15 if interaction.response.is_done() else 2):
                    if tasks.fetch_league_data:
                        fetch_league_data_task, _ = await asyncio.wait([tasks.fetch_league_data], timeout=None)
                        interaction.extras['league'] = fetch_league_data_task.pop().result()
                        
                    if player_ids:
                        results, _ = await asyncio.wait([
                            self.client.loop.create_task(
                                self.client.database.produce_player(x, interaction.extras['league'])) 
                                for x in player_ids
                        ], timeout=None, return_when=asyncio.ALL_COMPLETED)

                    if tasks.chunk_guild:
                        await asyncio.wait([tasks.chunk_guild], timeout=None)

                if player_ids:
                    for player_task in results:
                        player = player_task.result()
                        interaction.extras['players'][player.id] = player

            except asyncio.TimeoutError:
                #dead_keys = [x for x, y in self.client.guilds_erroring.items() if y < discord.utils.utcnow() - datetime.timedelta(minutes=5)]
                #for dead_key in dead_keys:
                #    self.client.guilds_erroring.pop(dead_key)

                #if interaction.guild and self.client.guilds_erroring[interaction.guild.id] < discord.utils.utcnow() - datetime.timedelta(seconds=20):
                #    await respond(interaction, content=(
                #        "### ❌ Possible reasons for this server having continuous errors when trying to run commands:\n"
                #        "- This server is being chunked *(Chunking is basically the bot loading up the server)*\n"
                #        "- Database issues\n"
                #        "- Discord issues\n"
                #        "- The bot simply needs a restart\n"
                #    ), ephemeral=True)
                #else:
                #    await respond(interaction, content="❌ **Please try again in a few seconds**", ephemeral=True)
                return False

        return True