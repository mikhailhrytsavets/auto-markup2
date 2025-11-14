from typing import Any

from sqlalchemy.ext.declarative import declared_attr

from core.database import Base


class BaseModel(Base):  # type: ignore[misc]
    __abstract__ = True

    @declared_attr.directive
    def __tablename__(self) -> str:
        """Автоматически генерирует имя таблицы из имени класса.

        Преобразует CamelCase в snake_case.
        """
        name = self.__name__
        return "".join(["_" + c.lower() if c.isupper() else c for c in name]).lstrip("_")

    def __repr__(self) -> str:
        """Представление объекта для отладки."""
        attrs = []
        for key, value in self.__dict__.items():
            if not key.startswith("_"):
                attrs.append(f"{key}={value!r}")
        return f"{self.__class__.__name__}({', '.join(attrs)})"

    def to_dict(self) -> dict[str, Any]:
        """Преобразование объекта в словарь."""
        return {
            column.name: getattr(self, column.name) for column in self.__table__.columns if hasattr(self, column.name)
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseModel":
        """Создание объекта из словаря."""
        return cls(**{key: value for key, value in data.items() if hasattr(cls, key)})
