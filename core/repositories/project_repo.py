from typing import Protocol, runtime_checkable

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.batch import Batch
from core.models.project import Project
from core.models.user import user_project_association
from core.repositories.base import BaseSQLAlchemyRepository, RepositoryProtocol


@runtime_checkable
class ProjectRepositoryProtocol(RepositoryProtocol[Project], Protocol):
    async def get_by_name(self, name: str) -> Project | None: ...

    async def exists(self, name: str) -> bool: ...

    async def get_by_batch_id(self, batch_id: int) -> Project | None: ...

    async def get_all_without_user(self, user_id: int, limit: int = 100, offset: int = 0) -> list[Project]: ...


class ProjectSQLAlchemyRepository(BaseSQLAlchemyRepository[Project], ProjectRepositoryProtocol):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Project, session)

    async def get_by_name(self, name: str) -> Project | None:
        q = select(self.model).where(self.model.name == name).limit(1)
        res = await self.session.execute(q)
        return res.scalar_one_or_none()

    async def exists(self, name: str) -> bool:
        q = select(exists().where(self.model.name == name))
        res = await self.session.execute(q)
        return bool(res.scalar())

    async def get_by_batch_id(self, batch_id: int) -> Project | None:
        q = select(self.model).join(Batch, self.model_pk == Batch.project_id).where(Batch.id == batch_id).limit(1)
        res = await self.session.execute(q)
        return res.scalar_one_or_none()

    async def get_all_without_user(self, user_id: int, limit: int = 100, offset: int = 0) -> list[Project]:
        user_link_exists = exists().where(
            user_project_association.c.project_id == self.model_pk,
            user_project_association.c.user_id == user_id,
        )
        q = select(self.model).where(~user_link_exists).limit(limit).offset(offset)
        res = await self.session.execute(q)
        return list(res.scalars().all())
