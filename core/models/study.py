import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import BaseModel
from core.models.study_category import study_category_study_association

if TYPE_CHECKING:
    from core.models.study_category import StudyCategory


class StudyStatusEnum(enum.Enum):
    ASSIGNED = "assigned"
    NEW = "new"
    WAITING_REVIEW = "waiting_review"
    IN_REVIEW = "in_review"
    WAITING_REWORK = "waiting_rework"
    REWORK = "rework"
    APPROVED = "approved"
    APPROVED_F = "approved_f"
    PENDING_CONFIRMATION = "pending_confirmation"
    CLOSED_N = "closed_n"
    CLOSED_I = "closed_i"
    CLOSED_OP = "closed_op"
    CLOSED_F = "closed_f"


class Study(BaseModel):
    id: Mapped[int] = mapped_column(primary_key=True)
    study_iuid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id", ondelete="RESTRICT"), nullable=False, index=True)
    study_path: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[StudyStatusEnum] = mapped_column(
        Enum(StudyStatusEnum, name="study_status"),
        nullable=False,
        index=True,
    )
    iteration_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    annotator_id: Mapped[int | None] = mapped_column(ForeignKey("user.tg_id"), nullable=True, index=True)
    expert_id: Mapped[int | None] = mapped_column(ForeignKey("user.tg_id"), nullable=True, index=True)
    nc_share_link: Mapped[str | None] = mapped_column(nullable=True)
    nc_upload_link: Mapped[str | None] = mapped_column(nullable=True)
    nc_last_upload_link: Mapped[str | None] = mapped_column(nullable=True)
    reject_comment_msg_id: Mapped[int | None] = mapped_column(nullable=True)
    categories: Mapped[list["StudyCategory"]] = relationship(
        secondary=study_category_study_association,
        back_populates="studies",
    )
