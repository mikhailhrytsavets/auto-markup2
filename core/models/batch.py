from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.schema import ForeignKey

from core.models.base import BaseModel
from core.models.study_category import study_category_batch_association

if TYPE_CHECKING:
    from core.models.study import Study
    from core.models.study_category import StudyCategory


class Batch(BaseModel):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    studies: Mapped[list["Study"]] = relationship()
    categories: Mapped[list["StudyCategory"]] = relationship(
        secondary=study_category_batch_association,
        back_populates="batches",
    )
