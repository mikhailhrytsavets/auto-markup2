import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Column, DateTime, Enum, ForeignKey, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.project import Project


user_project_association = Table(
    "user_project",
    BaseModel.metadata,
    Column("user_id", ForeignKey("user.tg_id", ondelete="CASCADE"), primary_key=True),
    Column("project_id", ForeignKey("project.id", ondelete="CASCADE"), primary_key=True),
)


class UserRoleEnum(enum.Enum):
    ADMIN = "admin"
    ANNOTATOR = "annotator"
    VALIDATOR = "validator"


class User(BaseModel):
    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    role: Mapped[UserRoleEnum] = mapped_column(Enum(UserRoleEnum, name="user_role"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    cvat_login: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    tg_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    projects: Mapped[list["Project"]] = relationship(
        secondary=user_project_association,
        back_populates="users",
    )
