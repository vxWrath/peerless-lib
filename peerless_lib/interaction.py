from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Self, Set, Union

import discord
from discord.ui.select import BaseSelect
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field

if TYPE_CHECKING:
    from .bot import Bot

__all__ = (
    'Defer',
    'DataRetrieval',
    'BeforeInteraction',
    'BeforeView',
    'BaseView',
    'response',
)

class Defer(PydanticBaseModel):
    defer: bool = False
    ephemerally: bool = False
    thinking: bool = False

class DataRetrieval(PydanticBaseModel):
    retrieve: bool = False
    keys: Set[str] = Field(default_factory=set)

class BeforeInteraction(PydanticBaseModel):
    defer: Defer = Field(default_factory=Defer)
    modal_response: bool = False
    
    league_data: DataRetrieval = Field(default_factory=DataRetrieval)
    player_data: DataRetrieval = Field(default_factory=DataRetrieval)

class BeforeView(PydanticBaseModel):
    before_all: Optional[BeforeInteraction] = None
    before_components: Optional[Dict[str, BeforeInteraction]] = None

class BaseView(discord.ui.View):
    children: List[discord.ui.Button[Self] | BaseSelect[Self]]
    checks: List[Callable[[Self, discord.Interaction[Bot]], bool]] = []

    def __init__(self, 
            timeout: Optional[int]=120,
            *,
            interaction: Optional[discord.Interaction[Bot]] = None,
            before: Optional[BeforeView] = None
        ):
        super().__init__(timeout=timeout)
        
        self.interaction = interaction
        self.before = before

        self.message: Optional[Union[discord.Message, discord.WebhookMessage, discord.InteractionMessage]] = None

        self.format_custom_ids()

    def __init_subclass__(cls) -> None:
        cls.checks = []
        super().__init_subclass__()

    def format_custom_ids(self) -> None:
        if not self.before or not self.before.before_components:
            return
        
        keys  = self.before.before_components.keys()
        names = [(i, self.children[i].callback.callback.__name__) for i in range(len(self.children))]

        for index, name in names:
            if name in keys:
                self.children[index].custom_id = f"{name}:{self.children[index].custom_id}"

    async def interaction_check(self, interaction: discord.Interaction[Bot]) -> bool:
        interaction.extras['before'] = None

        if self.before and self.before.before_components:
            name, *_ = interaction.data['custom_id'].split(':') # type: ignore
            interaction.extras['before'] = self.before.before_components.get(name)

        if self.before and self.before.before_all and not interaction.extras['before']:
            interaction.extras['before'] = self.before.before_all

        if not interaction.extras['before']:
            interaction.extras['before'] = BeforeInteraction()

        if not await interaction.client.tree.interaction_check(interaction):
            return False
        
        if interaction.channel and interaction.channel.type == discord.ChannelType.private:
            return True
        
        if not self.checks:
            if self.interaction and self.interaction.user != interaction.user:
                await response.send(interaction, content="❌ **You don't have permission**", ephemeral=True)
                return False
        else:
            for check in self.checks:
                if not await discord.utils.maybe_coroutine(check, self, interaction):
                    return False

        return True
    
    async def on_timeout(self) -> None:
        if not self.interaction and not self.message:
            return
                
        for child in self.children:
            child.disabled = True
            
        try:
            if self.message:
                await self.message.edit(content="**This message has expired**", view=self)
            elif self.interaction:
                await self.interaction.edit_original_response(content="**This message has expired**", view=self)
        except discord.HTTPException:
            pass

    async def on_error(self, interaction: discord.Interaction[Bot], error: discord.app_commands.AppCommandError, _) -> None:
        return await interaction.client.tree.on_error(interaction, error)
    
    async def cancel_view(self, message: str="❌ **Canceled**"):
        self.stop()

        if not self.interaction:
            return
                
        try:
            await self.interaction.edit_original_response(content=message, view=None, embed=None)
        except discord.HTTPException:
            pass
    
    @classmethod
    def check(cls, func: Callable[[Self, discord.Interaction[Bot]], bool]) -> Callable[[Self, discord.Interaction[Bot]], bool]:
        cls.checks.append(func)
        return func
    
class response:
    @staticmethod
    async def send(interaction: discord.Interaction[Bot], **kwargs) -> Union[discord.InteractionCallbackResponse, discord.WebhookMessage]:
        if interaction.response.is_done():
            return await interaction.followup.send(**kwargs)
        else:
            return await interaction.response.send_message(**kwargs)
        
    @staticmethod
    async def edit(interaction: discord.Interaction[Bot], **kwargs) -> Union[discord.InteractionCallbackResponse[Bot], discord.InteractionMessage, None]:
        if interaction.response.is_done():
            return await interaction.edit_original_response(**kwargs)
        else:
            return await interaction.response.edit_message(**kwargs)