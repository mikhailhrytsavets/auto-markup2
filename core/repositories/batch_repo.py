from typing import Protocol, runtime_checkable

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from core.models.batch import Batch
from core.repositories.base import BaseSQLAlchemyRepository, RepositoryProtocol


@runtime_checkable
class BatchRepositoryProtocol(RepositoryProtocol[Batch], Protocol):
    async def get_by_name(self, name: str) -> Batch | None: ...

    async def get_with_categories(self, batch_id: int) -> Batch | None: ...

    async def exists(self, name: str) -> bool: ...


class BatchSQLAlchemyRepository(BaseSQLAlchemyRepository[Batch], BatchRepositoryProtocol):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Batch, session)

    async def get_by_name(self, name: str) -> Batch | None:
        q = select(self.model).where(self.model.name == name).limit(1)
        res = await self.session.execute(q)
        return res.scalar_one_or_none()

    async def get_with_categories(self, batch_id: int) -> Batch | None:
        q = select(self.model).where(self.model_pk == batch_id).options(joinedload(self.model.categories))
        res = await self.session.execute(q)
        return res.unique().scalar_one_or_none()

    async def exists(self, name: str) -> bool:
        q = select(exists().where(self.model.name == name))
        res = await self.session.execute(q)
        return bool(res.scalar())
