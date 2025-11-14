from typing import Any, Protocol, TypeVar, runtime_checkable

from sqlalchemy import Integer, delete, func, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.schema import Column

from core.models.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


@runtime_checkable
class RepositoryProtocol(Protocol[ModelType]):
    @property
    def model(self) -> type[ModelType]: ...

    @property
    def model_pk(self) -> Column[Integer]: ...

    def create(self, obj_data: dict[str, Any]) -> ModelType: ...

    async def get_by_id(self, obj_id: int) -> ModelType | None: ...

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelType]: ...

    async def update(self, obj_id: int, obj_data: dict[str, Any]) -> ModelType | None: ...

    async def delete(self, obj_id: int) -> bool: ...

    async def count(self) -> int: ...

    def bulk_create(self, objects_data: list[dict[str, Any]]) -> list[ModelType]: ...


class BaseSQLAlchemyRepository[ModelType: BaseModel](RepositoryProtocol[ModelType]):
    def __init__(self, model: type[ModelType], session: AsyncSession) -> None:
        self._model = model
        self.session = session

    @property
    def model(self) -> type[ModelType]:
        return self._model

    @property
    def model_pk(self) -> Column[Integer]:
        return inspect(self.model).primary_key[0]

    def create(self, obj_data: dict[str, Any]) -> ModelType:
        obj = self.model(**obj_data)
        self.session.add(obj)
        return obj

    async def get_by_id(self, obj_id: int) -> ModelType | None:
        q = select(self.model).where(self.model_pk == obj_id).limit(1)
        res = await self.session.execute(q)
        return res.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelType]:
        q = select(self.model).limit(limit).offset(offset)
        res = await self.session.execute(q)
        return list(res.scalars().all())

    async def update(self, obj_id: int, obj_data: dict[str, Any]) -> ModelType | None:
        await self.session.execute(
            update(self.model).where(self.model_pk == obj_id).values(**obj_data),
        )
        return await self.get_by_id(obj_id)

    async def delete(self, obj_id: int) -> bool:
        res = await self.session.execute(delete(self.model).where(self.model_pk == obj_id))
        return (res.rowcount or 0) > 0

    async def count(self) -> int:
        res = await self.session.execute(select(func.count()).select_from(self.model))
        return int(res.scalar() or 0)

    def bulk_create(self, objects_data: list[dict[str, Any]]) -> list[ModelType]:
        objects = [self.model(**obj_data) for obj_data in objects_data]
        self.session.add_all(objects)
        return objects
