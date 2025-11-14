import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from dishka.integrations.aiogram import setup_dishka as setup_dishka_aiogram
from dishka.integrations.fastapi import setup_dishka as setup_dishka_fastapi
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from bot.register_handlers import register_handlers
from bot.utils.commands import set_commands
from core.config import Settings
from core.di import container
from core.utils.logging_config import setup_logging
from web_api import routes

_settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(_settings)

    logger.info("Starting telegram bot..")
    bot_properties = DefaultBotProperties(parse_mode="html", link_preview_is_disabled=True)
    bot = Bot(token=_settings.BOT_TOKEN, default=bot_properties)
    storage = RedisStorage.from_url(str(_settings.REDIS_URI), key_builder=DefaultKeyBuilder(with_destiny=True))
    dp = Dispatcher(storage=storage)
    dp.callback_query.middleware(CallbackAnswerMiddleware())
    register_handlers(dp)
    await set_commands(bot)
    polling_task = asyncio.create_task(
        dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            settings=_settings,
            handle_signals=False,
        ),
    )
    setup_dishka_aiogram(container=container, router=dp, auto_inject=True)

    try:
        yield
    finally:
        if polling_task and not polling_task.done():
            polling_task.cancel()
            with suppress(asyncio.CancelledError):
                await polling_task
        await bot.session.close()
        await dp.storage.close()
        await app.state.dishka_container.close()


app = FastAPI(
    title="Nextcloud Webhook Service",
    description="Сервис для обработки вебхуков от Nextcloud",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes.router, prefix="/api/v1")

setup_dishka_fastapi(container=container, app=app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level=_settings.LOG_LEVEL.lower(),
        workers=1,
    )
