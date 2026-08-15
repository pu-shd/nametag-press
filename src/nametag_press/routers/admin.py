"""Operational status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..deps import deps, require_principal
from ..schemas import WebhookStatus

router = APIRouter(dependencies=[Depends(require_principal)])


@router.get("/api/webhook/status", response_model=WebhookStatus)
def webhook_status(request: Request) -> WebhookStatus:
    c = deps(request).counters
    return WebhookStatus(
        received_total=c.received_total,
        authenticated_total=c.authenticated_total,
        rejected_total=c.rejected_total,
        last_received_at=c.last_received_at,
        unmapped_keys=sorted(c.unmapped_keys),
    )
