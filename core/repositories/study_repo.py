from typing import Protocol, runtime_checkable

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from core.models.batch import Batch
from core.models.study import Study, StudyStatusEnum
from core.repositories.base import BaseSQLAlchemyRepository, RepositoryProtocol


@runtime_checkable
class StudyRepositoryProtocol(RepositoryProtocol[Study], Protocol):
    async def get_by_iuid(self, iuid: str) -> Study | None: ...

    async def exists(self, iuid: str) -> bool: ...

    async def get_with_categories(self, study_id: int) -> Batch | None: ...

    async def get_assigned_for_annotator(self, user_id: int) -> Study | None: ...

    async def get_in_review_for_expert(self, user_id: int) -> Study | None: ...

    async def assign_to_user(
        self,
        project_id: int,
        user_id: int,
    ) -> Study | None: ...


class StudySQLAlchemyRepository(BaseSQLAlchemyRepository[Study], StudyRepositoryProtocol):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Study, session)

    async def get_by_iuid(self, iuid: str) -> Study | None:
        q = select(self.model).where(self.model.study_iuid == iuid).limit(1)
        res = await self.session.execute(q)
        return res.scalar_one_or_none()

    async def exists(self, iuid: str) -> bool:
        q = select(exists().where(self.model.study_iuid == iuid))
        res = await self.session.execute(q)
        return bool(res.scalar())

    async def get_with_categories(self, study_id: int) -> Batch | None:
        q = select(self.model).where(self.model_pk == study_id).options(joinedload(self.model.categories))
        res = await self.session.execute(q)
        return res.unique().scalar_one_or_none()

    async def get_assigned_for_annotator(self, user_id: int) -> Study | None:
        q = (
            select(self.model)
            .where(
                self.model.annotator_id == user_id,
                self.model.status.in_(
                    (StudyStatusEnum.ASSIGNED, StudyStatusEnum.WAITING_REWORK, StudyStatusEnum.REWORK),
                ),
            )
            .limit(1)
            .order_by(self.model.status)
        )
        res = await self.session.execute(q)
        return res.scalar_one_or_none()

    async def get_in_review_for_expert(self, user_id: int) -> Study | None:
        q = (
            select(self.model)
            .where(
                self.model.expert_id == user_id,
                self.model.status.in_((StudyStatusEnum.WAITING_REVIEW, StudyStatusEnum.IN_REVIEW)),
            )
            .limit(1)
        )
        res = await self.session.execute(q)
        return res.scalar_one_or_none()

    async def assign_to_user(
        self,
        project_id: int,
        user_id: int,
    ) -> Study | None:
        # Locks the next available NEW study for the project and assigns it to the annotator in a single statement.
        c = (
            select(self.model.id)
            .join(Batch, self.model.batch_id == Batch.id)
            .where(
                Batch.project_id == project_id,
                self.model.status == StudyStatusEnum.NEW,
            )
            .order_by(self.model_pk)
            .limit(1)
            .with_for_update(skip_locked=True)
            .cte("c")
        )
        stmt = (
            update(self.model)
            .where(self.model.id == select(c.c.id).scalar_subquery())
            .values(
                annotator_id=user_id,
                status=StudyStatusEnum.ASSIGNED,
                iteration_count=self.model.iteration_count + 1,
            )
            .returning(self.model)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()
