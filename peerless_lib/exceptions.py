from __future__ import annotations

from typing import TYPE_CHECKING, List

import discord

if TYPE_CHECKING:
    from .models import Team

class PeerlessException(Exception):
    """Base exception for all peerless errors"""
    pass

class PeerlessDown(Exception):
    pass

class CheckFailure(discord.app_commands.CheckFailure):
    def __init__(self, check: str):
        self.check = check

class RolesNotAssignable(PeerlessException):
    def __init__(self, roles: List[discord.Role]):
        self.roles = roles
        
class RolesAlreadyManaged(PeerlessException):
    def __init__(self, roles: List[discord.Role]):
        self.roles = roles
        
class RolesAlreadyUsed(PeerlessException):
    def __init__(self, roles: List[discord.Role]):
        self.roles = roles

class NotEnoughTeams(PeerlessException):
    def __init__(self, required: int):
        self.required = required

class TeamWithoutRole(PeerlessException):
    def __init__(self, team: Team):
        self.team = team