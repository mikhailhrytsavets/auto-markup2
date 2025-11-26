from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel

if TYPE_CHECKING:
    from core.models.batch import Batch
    from core.models.study import Study


study_category_batch_association = Table(
    "study_category_batch",
    BaseModel.metadata,
    Column("study_category_id", ForeignKey("study_category.id", ondelete="CASCADE"), primary_key=True),
    Column("batch_id", ForeignKey("batch.id", ondelete="CASCADE"), primary_key=True),
)

study_category_study_association = Table(
    "study_category_study",
    BaseModel.metadata,
    Column("study_category_id", ForeignKey("study_category.id", ondelete="CASCADE"), primary_key=True),
    Column("study_id", ForeignKey("study.id", ondelete="CASCADE"), primary_key=True),
)


class StudyCategory(BaseModel):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False, unique=True)
    batches: Mapped[list["Batch"]] = relationship(
        secondary=study_category_batch_association,
        back_populates="categories",
    )
    studies: Mapped[list["Study"]] = relationship(
        secondary=study_category_study_association,
        back_populates="categories",
    )
