from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base

from core.config import Settings

_POSTGRES_INDEXES_NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}
metadata = MetaData(naming_convention=_POSTGRES_INDEXES_NAMING_CONVENTION)
Base = declarative_base(metadata=metadata)


class DatabaseManager:
    async_session_maker: async_sessionmaker[AsyncSession]

    def __init__(self, settings: Settings) -> None:
        self.engine = create_async_engine(
            str(settings.SQLALCHEMY_DATABASE_URI),
            connect_args={"server_settings": {"search_path": settings.DATABASE_SCHEMA}},
            echo=settings.DATABASE_ECHO,
        )
        self.async_session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

    async def close_db(self) -> None:
        await self.engine.dispose()
