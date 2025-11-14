from typing import Annotated

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Header, HTTPException, status
from loguru import logger

from core.config import Settings
from core.unit_of_work import IUnitOfWork
from core.utils.nextcloud import NextcloudUtils
from web_api.schemas import IncomingPayload
from web_api.services.exceptions import WebhookServiceError
from web_api.services.webhook_service import WebhookService
from web_api.utils.path_filter import PathFilter

router = APIRouter(tags=["webhooks"], route_class=DishkaRoute)


@router.post(
    "/webhook/nextcloud",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def receive_nextcloud_webhook(
    webhook_payload: IncomingPayload,
    x_webhook_token: Annotated[str, Header(alias="X-Webhook-Token")],
    path_filter: Annotated[PathFilter, Depends(PathFilter)],
    uow: FromDishka[IUnitOfWork],
    nc_util: FromDishka[NextcloudUtils],
    settings: FromDishka[Settings],
) -> None:
    if x_webhook_token != settings.NEXTCLOUD_WEBHOOK_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if not path_filter.should_process_event(webhook_payload, settings.NEXTCLOUD_DIRECTORIES):
        return
    webhook_service = WebhookService(uow, nc_util, settings)
    logger.debug("Process webhook: {}", webhook_payload)
    try:
        await webhook_service.process_nextcloud_webhook(webhook_payload)
    except WebhookServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e}",
        ) from e


@router.get("/webhook/test")
async def webhook_status(
    path_filter: Annotated[PathFilter, Depends(PathFilter)],
    uow: FromDishka[IUnitOfWork],
    nc_util: FromDishka[NextcloudUtils],
    settings: FromDishka[Settings],
) -> None:
    webhook_service = WebhookService(uow, nc_util, settings)
    webhook_payload = IncomingPayload(
        **{
            "event": {
                "class": "NodeCreatedEvent",
                "node": {
                    "path": "/maksim.zhdanov/files/Exchange/tmp_diag_dev/Ishemic/"
                    "2025-10-21-ct-head-ishemic.3DSlicer.CheckReannotated_batch_4",
                    "id": 1,
                },
            },
            "user": {
                "uid": "1",
                "displayName": "maksim.zhdanov",
            },
            "time": 1727337600,
        },
    )
    logger.debug("Process webhook: {}", webhook_payload)
    if not path_filter.should_process_event(webhook_payload, settings.NEXTCLOUD_DIRECTORIES):
        return
    try:
        await webhook_service.process_nextcloud_webhook(webhook_payload)
    except WebhookServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
