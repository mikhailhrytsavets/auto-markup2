import enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel
from core.models.user import user_project_association

if TYPE_CHECKING:
    from core.models.user import User


class ProductEnum(enum.Enum):
    CHEST_CT = "chest_ct"
    HEAD_CT = "head_ct"
    DX = "dx"
    MMG = "mmg"
    DENTAL = "dental"
    SKIN = "skin"


class Project(BaseModel):
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    tg_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    product: Mapped[ProductEnum] = mapped_column(
        Enum(ProductEnum, name="product_name"),
        nullable=False,
    )
    users: Mapped[list["User"]] = relationship(
        secondary=user_project_association,
        back_populates="projects",
    )
