from pathlib import PurePosixPath
from typing import Any

from loguru import logger
from pydantic import Field, SecretStr, computed_field
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Nextcloud Webhook Service"

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    ALLOWED_ORIGINS: list[str] = ["*"]

    NEXTCLOUD_WEBHOOK_TOKEN: str

    LOG_LEVEL: str = "INFO"

    NEXTCLOUD_WEBDAV_URL: str
    NEXTCLOUD_AUTH: tuple[str, str]
    NEXTCLOUD_DIRECTORIES: list[PurePosixPath]
    NEXTCLOUD_OCS_URL: str

    DATABASE_HOST: str
    DATABASE_PORT: int = 5432
    DATABASE_USER: str
    DATABASE_PASSWORD: str = ""
    DATABASE_NAME: str = ""
    DATABASE_SCHEMA: str = "public"
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_PRE_PING: bool = False
    DATABASE_ADDITIONAL_CONNECTION_PARAMS: dict[str, Any] = {}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> MultiHostUrl:  # noqa: N802
        additional_connection_params = "&".join(
            f"{key}={value}" for key, value in self.DATABASE_ADDITIONAL_CONNECTION_PARAMS.items()
        )
        logger.info(f"Additional connection params: {additional_connection_params}")
        return MultiHostUrl.build(
            scheme="postgresql+asyncpg",
            host=self.DATABASE_HOST,
            port=self.DATABASE_PORT,
            username=self.DATABASE_USER,
            password=self.DATABASE_PASSWORD,
            path=self.DATABASE_NAME,
            query=additional_connection_params,
        )

    BOT_TOKEN: str
    BOT_SECRET: SecretStr
    BOT_DEEP_LINK_TTL: int = 300
    BOT_DEEP_LINK_TAG_LEN: int = 8

    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: SecretStr = SecretStr("")
    REDIS_DB: int = Field(default=0, description="Database index")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def REDIS_URI(self) -> MultiHostUrl:  # noqa: N802
        return MultiHostUrl.build(
            scheme="redis",
            password=self.REDIS_PASSWORD.get_secret_value(),
            host=self.REDIS_HOST,
            port=self.REDIS_PORT,
            path=f"{self.REDIS_DB}",
        )

    ITERATION_LIMIT: int = 3
    SHARE_LINK_TTL_HOURS: int = 24

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )
