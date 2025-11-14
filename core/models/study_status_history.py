from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel
from core.models.study import StudyStatusEnum

if TYPE_CHECKING:
    from core.models.study import Study


class StudyStatusHistory(BaseModel):
    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("study.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[StudyStatusEnum | None] = mapped_column(
        Enum(StudyStatusEnum, name="study_status"),
        nullable=True,
    )
    to_status: Mapped[StudyStatusEnum] = mapped_column(
        Enum(StudyStatusEnum, name="study_status"),
        nullable=False,
        index=True,
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    iteration_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    study: Mapped["Study"] = relationship(backref="status_history")
