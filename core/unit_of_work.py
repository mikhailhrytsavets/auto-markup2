import abc
from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from core.repositories.batch_repo import BatchRepositoryProtocol, BatchSQLAlchemyRepository
from core.repositories.project_repo import ProjectRepositoryProtocol, ProjectSQLAlchemyRepository
from core.repositories.study_category_repo import (
    StudyCategoryRepositoryProtocol,
    StudyCategorySQLAlchemyRepository,
)
from core.repositories.study_repo import StudyRepositoryProtocol, StudySQLAlchemyRepository
from core.repositories.user_repo import UserRepositoryProtocol, UserSQLAlchemyRepository


class IUnitOfWork(abc.ABC):
    @property
    @abc.abstractmethod
    def projects(self) -> ProjectRepositoryProtocol: ...

    @property
    @abc.abstractmethod
    def batches(self) -> BatchRepositoryProtocol: ...

    @property
    @abc.abstractmethod
    def studies(self) -> StudyRepositoryProtocol: ...

    @property
    @abc.abstractmethod
    def users(self) -> UserRepositoryProtocol: ...

    @property
    @abc.abstractmethod
    def categories(self) -> StudyCategoryRepositoryProtocol: ...

    @abc.abstractmethod
    async def __aenter__(self) -> Self: ...

    @abc.abstractmethod
    async def __aexit__(
        self,
        typ: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    @abc.abstractmethod
    async def commit(self) -> None: ...

    @abc.abstractmethod
    async def rollback(self) -> None: ...


class SqlAlchemyUnitOfWork(IUnitOfWork):
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
    ) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self._tx: AsyncSessionTransaction | None = None
        self._projects: ProjectRepositoryProtocol | None = None
        self._batches: BatchRepositoryProtocol | None = None
        self._studies: StudyRepositoryProtocol | None = None
        self._users: UserRepositoryProtocol | None = None
        self._categories: StudyCategoryRepositoryProtocol | None = None

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        try:
            self._tx = await self.session.begin()
        except Exception:
            await self.session.close()
            self.session = None
            self._tx = None
            raise
        self._projects = ProjectSQLAlchemyRepository(self.session)
        self._batches = BatchSQLAlchemyRepository(self.session)
        self._studies = StudySQLAlchemyRepository(self.session)
        self._users = UserSQLAlchemyRepository(self.session)
        self._categories = StudyCategorySQLAlchemyRepository(self.session)
        return self

    async def __aexit__(
        self,
        typ: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if self._tx is not None and self._tx.is_active:
                # Если транзакция открыта и не был сделан commit
                await self._tx.rollback()
        finally:
            if self.session is not None:
                await self.session.close()
            self._tx = None
            self.session = None
            self._projects = None
            self._batches = None
            self._studies = None
            self._users = None
            self._categories = None

    @property
    def projects(self) -> ProjectRepositoryProtocol:
        if self._projects is None:
            msg = "UnitOfWork is closed; repositories are not available"
            raise RuntimeError(msg)
        return self._projects

    @property
    def batches(self) -> BatchRepositoryProtocol:
        if self._batches is None:
            msg = "UnitOfWork is closed; repositories are not available"
            raise RuntimeError(msg)
        return self._batches

    @property
    def studies(self) -> StudyRepositoryProtocol:
        if self._studies is None:
            msg = "UnitOfWork is closed; repositories are not available"
            raise RuntimeError(msg)
        return self._studies

    @property
    def users(self) -> UserRepositoryProtocol:
        if self._users is None:
            msg = "UnitOfWork is closed; repositories are not available"
            raise RuntimeError(msg)
        return self._users

    @property
    def categories(self) -> StudyCategoryRepositoryProtocol:
        if self._categories is None:
            msg = "UnitOfWork is closed; repositories are not available"
            raise RuntimeError(msg)
        return self._categories

    async def commit(self) -> None:
        if self._tx is None or self.session is None:
            msg = "UnitOfWork is not active or already closed"
            raise RuntimeError(msg)
        await self._tx.commit()

    async def rollback(self) -> None:
        if self._tx is None or self.session is None:
            return
        if self._tx.is_active:
            await self._tx.rollback()
