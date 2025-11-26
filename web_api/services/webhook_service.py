import csv
import io
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

import yaml
from loguru import logger

from core.config import Settings
from core.models.study import StudyStatusEnum
from core.unit_of_work import IUnitOfWork
from core.utils.nextcloud import NextcloudUtils
from web_api.schemas import IncomingPayload
from web_api.services.exceptions import (
    ConfigStructureError,
    InvalidNodePathError,
    MappingDecodeError,
    MappingMissingColumnError,
    MetadataDownloadError,
    ProjectNotFountError,
    UnknownWebhookEventError,
)


class WebhookService:
    def __init__(self, uow: IUnitOfWork, nc_util: NextcloudUtils, settings: Settings) -> None:
        self.uow = uow
        self.nc_util = nc_util
        self.settings = settings

    async def process_nextcloud_webhook(self, webhook_payload: IncomingPayload) -> None:
        if webhook_payload.event.class_.endswith("NodeCreatedEvent"):
            await self._handle_node_created(webhook_payload)
        else:
            error_message = f"Unknown event type: {webhook_payload.event.class_}"
            logger.debug(error_message)
            raise UnknownWebhookEventError(error_message)

    async def _handle_node_created(self, webhook_payload: IncomingPayload) -> None:
        path = webhook_payload.event.node.path
        if not await self.nc_util.path_is_directory(path=path):
            error_message = f"{webhook_payload.event.node.path} is not a directory"
            logger.debug(error_message)
            raise InvalidNodePathError(error_message)
        logger.debug("{} is directory", path)

        await self._process_batch(webhook_payload)

    async def _process_batch(self, webhook_payload: IncomingPayload) -> None:
        path = webhook_payload.event.node.path
        files_content = await self._download_metadata_files(path)
        parsed_config = self._parse_config(files_content.get("config.yaml", b""))
        parsed_mapping = self._parse_mapping(path, files_content.get("Mapping.csv", b""))

        async with self.uow:
            project = await self.uow.projects.get_by_name(name=parsed_config["project"])
            if not project:
                error_text = f"The project {parsed_config['project']} was not found in the database"
                logger.debug(error_text)
                raise ProjectNotFountError(error_text)
            batch = self.uow.batches.create({"name": path.name, "project_id": project.id})
            batch.studies.extend(
                self.uow.studies.bulk_create(
                    [
                        {
                            "study_iuid": study_data[1],
                            "study_path": study_data[0],
                            "status": StudyStatusEnum.NEW,
                        }
                        for study_data in parsed_mapping
                    ],
                ),
            )
            batch.categories.extend(
                await self.uow.categories.get_or_create_many(parsed_config["categories"]),
            )
            await self.uow.commit()

        logger.info("Batch {} succesfully processed", path.name)

    async def _download_metadata_files(self, path: PurePosixPath) -> dict[str, bytes]:
        directory = path.as_posix().strip("/")
        base_url = self.settings.NEXTCLOUD_WEBDAV_URL.rstrip("/")

        def build_file_url(filename: str) -> str:
            segments = [segment for segment in (directory, filename) if segment]
            encoded_subpath = "/".join(quote(segment) for segment in segments)
            return f"{base_url}/{encoded_subpath}"

        files_to_fetch = ("Mapping.csv", "config.yaml")
        file_urls_to_fetch = [build_file_url(file) for file in files_to_fetch]
        logger.debug("Downloading files: {}", file_urls_to_fetch)
        try:
            files_content = await self.nc_util.download_nc_files(file_urls_to_fetch)
        except Exception as e:
            error_text = f"Downloading error from {path}: {e}"
            logger.debug(error_text)
            raise MetadataDownloadError(error_text) from e
        return files_content

    def _parse_config(self, config_content: bytes) -> dict[str, Any]:
        with io.BytesIO(config_content) as config:
            data = yaml.safe_load(config)
        try:
            project = data["project"]["pathology"]
        except KeyError as e:
            detail = "Structure error for config.yaml - missing project->pathology"
            logger.debug(detail)
            raise ConfigStructureError(detail) from e
        categories = data.get("classes", [])
        categories = categories if isinstance(categories, list) else []
        return {"project": project, "categories": categories}

    def _parse_mapping(self, batch_path: PurePosixPath, mapping_content: bytes) -> list[tuple[str, str]]:
        if not mapping_content:
            return []
        try:
            csv_text = mapping_content.decode()
        except UnicodeDecodeError as e:
            detail = "Не удалось декодировать Mapping.csv как UTF-8"
            logger.error(detail)
            raise MappingDecodeError(detail) from e

        reader = csv.DictReader(io.StringIO(csv_text))
        if (
            not reader.fieldnames
            or "batch" not in reader.fieldnames
            or "foldername" not in reader.fieldnames
            or "StudyID" not in reader.fieldnames
        ):
            detail = "Отсутствует необходимый столбец в Mapping.csv"
            logger.error(detail)
            raise MappingMissingColumnError(detail)

        parsed_rows: list[tuple[str, str]] = []
        for row in reader:
            batch = (row.get("batch") or "").strip()
            foldername = (row.get("foldername") or "").strip()
            study_iuid = (row.get("StudyID") or "").strip()
            if not all((batch, foldername, study_iuid)):
                continue
            foldername = foldername.zfill(3)
            study_path = batch_path / "1-original-data" / batch / foldername
            parsed_rows.append((str(study_path), study_iuid))
        return parsed_rows
