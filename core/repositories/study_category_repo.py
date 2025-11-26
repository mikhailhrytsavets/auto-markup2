from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.study_category import StudyCategory
from core.repositories.base import BaseSQLAlchemyRepository, RepositoryProtocol


@runtime_checkable
class StudyCategoryRepositoryProtocol(RepositoryProtocol[StudyCategory], Protocol):
    async def get_by_ids(self, category_ids: list[int]) -> list[StudyCategory]: ...

    async def get_or_create_many(self, names: list[str]) -> list[StudyCategory]: ...


class StudyCategorySQLAlchemyRepository(
    BaseSQLAlchemyRepository[StudyCategory],
    StudyCategoryRepositoryProtocol,
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(StudyCategory, session)

    async def get_by_ids(self, category_ids: list[int]) -> list[StudyCategory]:
        if not category_ids:
            return []
        q = select(self.model).where(self.model_pk.in_(category_ids))
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def get_or_create_many(self, names: list[str]) -> list[StudyCategory]:
        if not names:
            return []

        existing = await self.session.execute(
            select(self.model).where(self.model.name.in_(names)),
        )
        existing_map = {c.name: c for c in existing.scalars().all()}

        result = []
        for name in names:
            if name in existing_map:
                result.append(existing_map[name])
            else:
                obj = self.model(name=name)
                self.session.add(obj)
                result.append(obj)
        return result
