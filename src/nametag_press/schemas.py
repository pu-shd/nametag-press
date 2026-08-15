"""Request and response shapes."""

from __future__ import annotations

import datetime as _dt

from eventkit.drupal import DrupalSubmissionModel
from pydantic import BaseModel, ConfigDict


class RosterSubmission(DrupalSubmissionModel):
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    uuid: str | None = None
    sid: int | None = None
    serial: int | None = None
    home_institution_or_organization: str | None = None
    attendee_status: str | None = None
    student: bool = False
    presenting_poster: bool = False


class RegistrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    person_key: str
    first_name: str | None = None
    last_name: str | None = None
    email_address: str | None = None
    home_institution: str | None = None
    attendee_status: str | None = None
    presenting_poster: bool = False
    serial_number: int | None = None


class Tallies(BaseModel):
    total: int = 0
    by_role: dict[str, int] = {}
    presenting: int = 0


class WebhookStatus(BaseModel):
    received_total: int
    authenticated_total: int
    rejected_total: int
    last_received_at: _dt.datetime | None = None
    unmapped_keys: list[str] = []
