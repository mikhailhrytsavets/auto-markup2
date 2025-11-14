from pathlib import PurePosixPath
from urllib.parse import quote

import httpx
from loguru import logger
from lxml import etree

from core.config import Settings


class NextcloudError(Exception):
    """Base exception for Nextcloud utility errors."""


class NextcloudPublicLinkError(NextcloudError):
    """Raised when a public link cannot be created."""


class NextcloudNotFoundError(NextcloudError):
    """Raised when a resource not found."""


class NextcloudUtils:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def create_public_link(
        self,
        *,
        path: str,
        label: str | None = "Public view",
        share_type: int = 3,
        permissions: int = 1,
        timeout_s: float = 10.0,
    ) -> str:
        """Создает публичную ссылку на ресурс через OCS API."""
        share_api_url = f"{self.settings.NEXTCLOUD_OCS_URL}/files_sharing/api/v1/shares"
        data: dict[str, str] = {
            "path": path,
            "shareType": str(share_type),
            "permissions": str(permissions),
        }
        if label is not None:
            data["label"] = label
        headers = {
            "OCS-APIRequest": "true",
            "Accept": "application/xml",
        }

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(
                share_api_url,
                headers=headers,
                data=data,
                auth=self.settings.NEXTCLOUD_AUTH,
            )
        response.raise_for_status()

        try:
            xml_root = etree.fromstring(response.content)
        except etree.XMLSyntaxError as xml_err:
            logger.error("Некорректный XML при создании публичной ссылки {}: {}", path, xml_err)
            raise

        status_code_text = xml_root.findtext("meta//statuscode")
        if status_code_text != "200":
            message = xml_root.findtext("meta//statuscode") or "Не удалось создать публичную ссылку"
            error_text = f"Nextcloud вернул статус {status_code_text} при создании публичной ссылки: {message}"
            logger.error(error_text, status_code_text, path, message)
            raise NextcloudPublicLinkError(error_text)

        return xml_root.findtext("data//url")

    async def path_is_directory(self, *, path: PurePosixPath, timeout_s: float = 10.0) -> bool:
        """Проверяет по WebDAV (PROPFIND), является ли ресурс директорией."""
        webdav_url = f"{self.settings.NEXTCLOUD_WEBDAV_URL}{path}"
        headers = {"Depth": "0"}
        body = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.request(
                method="PROPFIND",
                url=webdav_url,
                content=body,
                headers=headers,
                auth=self.settings.NEXTCLOUD_AUTH,
            )
        if resp.status_code == 404:
            error_text = "Path-resource not found"
            raise NextcloudNotFoundError(error_text)
        resp.raise_for_status()

        try:
            xml_root = etree.fromstring(resp.content, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError as xml_err:
            logger.error("Некорректный XML при PROPFIND: {}", xml_err)
            return False

        nodes = xml_root.xpath("//d:resourcetype", namespaces={"d": "DAV:"})
        if not nodes:
            return False

        resourcetype = nodes[0]
        is_collection = resourcetype.find("{DAV:}collection") is not None
        return bool(is_collection)

    async def download_nc_files(self, file_urls_to_fetch: list[str], timeout_s: float = 10.0) -> dict[str, bytes]:
        files_content: dict[str, bytes] = {}
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            for file_url in file_urls_to_fetch:
                response = await client.get(file_url, auth=self.settings.NEXTCLOUD_AUTH)
                response.raise_for_status()
                file_name = file_url.rsplit("/", 1)[-1]
                files_content[file_name] = response.content
        return files_content

    async def create_folder(
        self,
        path: str,
        new_folder: str,
    ) -> None:
        """Создаёт новую папку new_folder внутри parent_path на Nextcloud через
        WebDAV."""
        if not path.endswith("/"):
            path += "/"
        if not new_folder.endswith("/"):
            new_folder += "/"
        folder_url = f"{self.settings.NEXTCLOUD_WEBDAV_URL}{path}{new_folder}"

        async with httpx.AsyncClient(auth=self.settings.NEXTCLOUD_AUTH) as client:
            response = await client.request("MKCOL", folder_url)

        match response.status_code:
            case 201 | 200:
                logger.debug(f"Директория '{new_folder}' создана успешно")
                return
            case 405:
                logger.debug(f"️Директория '{new_folder}' уже существует")
                return
            case 409:
                logger.debug("Родительская директория не существует")
            case _:
                logger.debug(f"Ошибка: {response.status_code} — {response.text[:200]}")
        response.raise_for_status()

    async def is_directory_empty(self, path: str) -> bool:
        """Проверяет, пуста ли директория в Nextcloud через WebDAV.

        Возвращает True, если директория пуста.
        """
        if not path.endswith("/"):
            path += "/"

        body = """<?xml version="1.0"?>
        <d:propfind xmlns:d="DAV:">
        <d:prop><d:displayname/></d:prop>
        </d:propfind>"""

        async with httpx.AsyncClient(auth=self.settings.NEXTCLOUD_AUTH) as client:
            response = await client.request(
                "PROPFIND",
                f"{self.settings.NEXTCLOUD_WEBDAV_URL}{path}",
                headers={
                    "Depth": "1",
                    "Content-Type": "application/xml; charset=utf-8",
                },
                content=body,
            )
        response.raise_for_status()

        doc = etree.fromstring(response.content)
        responses = doc.xpath("//d:response", namespaces={"d": "DAV:"})
        return len(responses) <= 1

    async def copy_directory(self, src_dir: str, dst_dir: str) -> None:
        """Копирует директорию src_dir в dst_dir на сервере Nextcloud через
        WebDAV COPY."""
        base = self.settings.NEXTCLOUD_WEBDAV_URL.rstrip("/")

        src_url = f"{base}/{self._encode_path(src_dir, ensure_trailing_slash=True)}"
        dst_url = f"{base}/{self._encode_path(dst_dir, ensure_trailing_slash=True)}"

        async with httpx.AsyncClient(auth=self.settings.NEXTCLOUD_AUTH) as client:
            resp = await client.request(
                "COPY",
                src_url,
                headers={
                    "Destination": dst_url,
                    "Depth": "infinity",
                    "Overwrite": "T",
                },
            )
        resp.raise_for_status()

    def _encode_path(self, path: str, *, ensure_trailing_slash: bool = False) -> str:
        p = path.replace("\\", "/")
        if ensure_trailing_slash and not p.endswith("/"):
            p += "/"
        return quote(p, safe="/%")
