import discord

__all__ = (
    'is_managed',
)

def is_managed(role: discord.Role) -> bool:
    if role.managed:
        return True
    elif role.is_default():
        return True
    elif not role.tags:
        return False
    
    elif role.tags.is_bot_managed():
        return True
    elif role.tags.is_premium_subscriber():
        return True
    elif role.tags.is_integration():
        return True
    elif role.tags.is_available_for_purchase():
        return True
    elif role.tags.is_guild_connection():
        return True
    
    else:
        return False