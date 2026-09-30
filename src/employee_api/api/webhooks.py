"""Webhook endpoints (HMAC SHA256 verified)."""

import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request

from employee_api.api.routes import get_employee_service
from employee_api.config import get_settings
from employee_api.schemas.common import MessageResponse
from employee_api.services.employee_service import EmployeeService
from employee_api.services.external_api_service import WebhookService
from employee_api.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def get_webhook_service(
    service: EmployeeService = Depends(get_employee_service),
) -> WebhookService:
    return WebhookService(secret=get_settings().webhook_secret, employee_service=service)


@router.post("/employee", response_model=MessageResponse, status_code=202)
async def receive_employee_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_signature_256: Optional[str] = Header(default=None),
    webhook_service: WebhookService = Depends(get_webhook_service),
) -> MessageResponse:
    """Accepts events: employee.created, employee.updated, employee.deleted.

    Signature header: ``X-Signature-256: sha256=<hex hmac of raw body>``.
    """
    if not webhook_service.secret_configured:
        logger.error("Webhook received but WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=503, detail="Webhook secret is not configured")

    body = await request.body()
    if not webhook_service.verify_signature(body, x_signature_256):
        logger.warning("Rejected webhook with invalid signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Body must be valid JSON") from exc

    if not isinstance(payload, dict) or not payload.get("event"):
        raise HTTPException(status_code=400, detail="Payload must include an 'event' field")

    background_tasks.add_task(webhook_service.process_event, payload)
    return MessageResponse(status="accepted", detail=f"Event '{payload['event']}' queued")