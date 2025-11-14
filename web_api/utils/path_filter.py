from pathlib import PurePosixPath

from loguru import logger

from web_api.schemas import IncomingPayload


class PathFilter:
    """Фильтер webhook событий по структуре директорий: разрешены только пути
    вида base_dir/level1/level2."""

    def should_process_event(self, webhook_payload: IncomingPayload, nc_directories: list[PurePosixPath]) -> bool:
        path = webhook_payload.event.node.path
        if not self._is_path_allowed(path, nc_directories):
            logger.debug("The path {} does not match the allowed directory structure", path)
            return False
        return True

    def _is_path_allowed(self, path: PurePosixPath, nc_directories: list[PurePosixPath]) -> bool:
        """Проверяет, соответствует ли путь разрешенной структуре директорий.

        Логика фильтрации:
        - Путь должен начинаться с одной из директорий из settings.NC_DIRECTORIES
        - После базовой директории должно быть ровно 2 дополнительных уровня

        Примеры для settings.NC_DIRECTORIES = ["Exchange/tmp_diag_dev"]:
        ✅ Exchange/tmp_diag_dev/Ishemic/test_dir       (2 уровня: Ishemic + test_dir)
        ❌ Exchange/tmp_diag_dev/Ishemic               (1 уровень: только Ishemic)
        ❌ Exchange/tmp_diag_dev/Ishemic/test_dir/sub  (3 уровня: Ishemic + test_dir + sub)
        ❌ Other/tmp_diag_dev/Ishemic/test_dir         (не начинается с разрешенной директории)
        """
        for base_path in nc_directories:
            # Проверяем, что наш путь начинается с базовой директории
            if len(path.parts) >= len(base_path.parts):
                path_prefix = PurePosixPath(*path.parts[: len(base_path.parts)])
                if path_prefix == base_path:
                    # Проверяем, что после базовой директории есть ровно 2 дополнительных уровня
                    remaining_parts = path.parts[len(base_path.parts) :]
                    if len(remaining_parts) == 2:
                        logger.debug("The path {} is allowed for the base directory {}", path, base_path)
                        return True
        return False
