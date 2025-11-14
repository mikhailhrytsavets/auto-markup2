from aiogram import Bot
from aiogram.types import BotCommand
from aiogram.types.bot_command_scope_default import BotCommandScopeDefault


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="task", description="Запросить исследование"),
    ]
    await bot.set_my_commands(commands, BotCommandScopeDefault())
