from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Node(BaseModel):
    id: int
    path: PurePosixPath

    @field_validator("path", mode="after")
    @classmethod
    def validate_path(cls, v: PurePosixPath) -> PurePosixPath:
        # Убираем две верхние директории, так как Nextcloud приписывает
        # к отслеживаемому вебхуком пути /<username>/files/
        return PurePosixPath(*v.parts[3:])


class Event(BaseModel):
    node: Node
    class_: str = Field(alias="class")


class User(BaseModel):
    uid: str
    display_name: str = Field(alias="displayName")


class IncomingPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    event: Event
    user: User
    time: int
