from typing import Protocol, runtime_checkable

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from core.models.user import User
from core.repositories.base import BaseSQLAlchemyRepository, RepositoryProtocol


@runtime_checkable
class UserRepositoryProtocol(RepositoryProtocol[User], Protocol):
    async def get_by_tg_id_with_projects(self, tg_id: int) -> User | None: ...

    async def exists(self, tg_id: int) -> bool: ...


class UserSQLAlchemyRepository(BaseSQLAlchemyRepository[User], UserRepositoryProtocol):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_tg_id_with_projects(self, tg_id: int) -> User | None:
        q = select(self.model).where(self.model.tg_id == tg_id).options(joinedload(self.model.projects))
        res = await self.session.execute(q)
        return res.unique().scalar_one_or_none()

    async def exists(self, tg_id: int) -> bool:
        q = select(exists().where(self.model.tg_id == tg_id))
        res = await self.session.execute(q)
        return bool(res.scalar())
