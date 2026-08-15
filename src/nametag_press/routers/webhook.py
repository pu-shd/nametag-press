"""Drupal Remote Post ingest for the roster."""

from __future__ import annotations

import logging
from typing import Any

from eventkit.drupal import parse_submission
from eventkit.identity import IdentityError
from eventkit.identity import person_key as derive_person_key
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from ..deps import ProfileDep, SessionDep, deps, webhook_guard
from ..models import Registrant

logger = logging.getLogger("nametag_press.webhook")

router = APIRouter()


def upsert_registrant(session: Session, submission: Any, profile: Any) -> tuple[Registrant | None, str]:
    """Create or update one roster row. Shared with the bulk importer."""
    try:
        key = derive_person_key(uuid=submission.get("uuid"), email=submission.email)
    except IdentityError:
        return None, "skipped"

    affiliation = submission.get("home_institution_or_organization")
    # Normalise "" / "n/a" and fill in from the email domain where the profile
    # knows it. Six copies of this rule existed across the predecessors.
    normalised = profile.affiliation.normalize(
        email=submission.email or "", declared=affiliation
    )

    fields = {
        "email_address": submission.email,
        "first_name": submission.first_name,
        "last_name": submission.last_name,
        "drupal_uuid": submission.get("uuid"),
        "drupal_sid": submission.get("sid"),
        "serial_number": submission.get("serial"),
        "home_institution": normalised,
        "attendee_status": submission.get("attendee_status"),
    }
    student = bool(submission.get("student"))
    presenting = bool(submission.get("presenting_poster"))

    existing = session.get(Registrant, key)
    if existing is None:
        session.add(
            Registrant(
                person_key=key, student=student, presenting_poster=presenting, **fields
            )
        )
        return session.get(Registrant, key) or existing, "created"

    for name, value in fields.items():
        if value is not None:
            setattr(existing, name, value)
    existing.student = student
    existing.presenting_poster = presenting
    existing.row_version += 1
    return existing, "updated"


@router.post(
    "/api/drupal-webhook",
    dependencies=[Depends(webhook_guard("registration"))],
    status_code=status.HTTP_200_OK,
)
async def drupal_webhook(request: Request, session: Session = SessionDep, profile=ProfileDep):
    d = deps(request)
    body = await request.json()
    submission = parse_submission(body, d.field_map)

    mapped = set(d.field_map.element_keys())
    payload_keys = set((body.get("data") or body).keys()) if isinstance(body, dict) else set()
    d.counters.record(authenticated=True, unmapped=sorted(payload_keys - mapped))

    registrant, outcome = upsert_registrant(session, submission, profile)
    if registrant is None and outcome == "skipped":
        logger.warning("submission carried no usable identity; ignored")
        return {"status": "ignored"}

    session.commit()
    logger.info("webhook %s", outcome)
    return {"status": outcome}
