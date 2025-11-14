import sys

from loguru import logger

from core.config import Settings


def setup_logging(settings: Settings) -> None:
    """Настраивает логирование с помощью loguru на основе объекта settings.

    Конфигурация:
    - Убирает стандартный handler
    - Добавляет цветной вывод в консоль
    - Добавляет ротируемый файловый вывод (если включен)
    - Устанавливает уровень логирования из settings
    """
    logger.remove()

    log_format: str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level> | <yellow>{extra}</yellow>"
    )
    logger.add(
        sink=sys.stdout,
        format=log_format,
        level=settings.LOG_LEVEL,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    logger.info(f"loglevel={settings.LOG_LEVEL}")
