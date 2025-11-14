from collections.abc import AsyncGenerator

from dishka import Provider, Scope, from_context, provide
from dishka.async_container import make_async_container
from loguru import logger

from bot.utils.deep_link_codec import DeepLinkCodec
from core.config import Settings
from core.database import DatabaseManager
from core.unit_of_work import IUnitOfWork, SqlAlchemyUnitOfWork
from core.utils.nextcloud import NextcloudUtils


class SQLARepoProvider(Provider):
    settings = from_context(provides=Settings, scope=Scope.APP)

    @provide(scope=Scope.APP)
    async def get_db_manager(
        self,
        settings: Settings,
    ) -> AsyncGenerator[DatabaseManager]:
        db_manager = DatabaseManager(settings)
        logger.debug("Created db_manager")
        yield db_manager
        logger.debug("Destroyed db_manager")
        await db_manager.close_db()

    @provide(scope=Scope.APP)
    async def get_deep_link_codec(
        self,
        settings: Settings,
    ) -> DeepLinkCodec:
        return DeepLinkCodec(
            secret=settings.BOT_SECRET.get_secret_value(),
            tag_len=settings.BOT_DEEP_LINK_TAG_LEN,
            ttl=settings.BOT_DEEP_LINK_TTL,
        )

    @provide(scope=Scope.APP)
    async def get_nextcloud_util(
        self,
        settings: Settings,
    ) -> NextcloudUtils:
        return NextcloudUtils(settings=settings)

    @provide(scope=Scope.REQUEST)
    async def get_sqla_unit_of_work(
        self,
        db_manager: DatabaseManager,
    ) -> IUnitOfWork:
        logger.debug("UoW creation...")
        return SqlAlchemyUnitOfWork(db_manager.async_session_maker)


container = make_async_container(
    SQLARepoProvider(),
    context={
        Settings: Settings(),
    },
)
