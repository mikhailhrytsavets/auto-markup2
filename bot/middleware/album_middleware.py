import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import (
    Message,
    TelegramObject,
)


class MediaGroupMiddleware(BaseMiddleware):
    ALBUM_DATA: dict[str, list[Message]]

    def __init__(self, delay: float = 1) -> None:
        self.ALBUM_DATA = {}
        self.delay = delay

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401
        if not isinstance(event, Message) or not event.media_group_id:
            return await handler(event, data)

        try:
            self.ALBUM_DATA[event.media_group_id].append(event)
        except KeyError:
            self.ALBUM_DATA[event.media_group_id] = [event]
            await asyncio.sleep(self.delay)
            data["album"] = self.ALBUM_DATA.pop(event.media_group_id)
        else:
            return None

        return await handler(event, data)
