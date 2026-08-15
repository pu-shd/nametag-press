"""Database models."""

from __future__ import annotations

import datetime as _dt

from eventkit.db import declarative_base
from eventkit.identity import IdentityMixin
from sqlalchemy import DateTime, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

Base = declarative_base()


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class Registrant(IdentityMixin, Base):
    """The roster this application prints from.

    Note what is **absent**: there is no ``t_shirt_size``. Swag belongs to
    ticket-reconciler, which has the check-in desk and the inventory. The
    predecessor stored a size here, backed it up, and never rendered it anywhere;
    two applications counting shirts independently is how you oversell mediums.
    """

    __tablename__ = "registrants"

    home_institution: Mapped[str | None] = mapped_column(String(255), default=None)
    attendee_status: Mapped[str | None] = mapped_column(String(64), default=None)
    student: Mapped[bool] = mapped_column(default=False, nullable=False)
    presenting_poster: Mapped[bool] = mapped_column(default=False, nullable=False)
    registered_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class BrandingAsset(Base):
    """An uploaded logo, stored as bytes in the database.

    The predecessor wrote these to ``frontend/static/images/``, which is not the
    Azure Files mount — so they vanished on container restart, after which the
    renderer silently drew nothing because the failure path was a bare
    ``except: pass``.
    """

    __tablename__ = "branding_assets"

    #: "primary" or "sponsor".
    slot: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    uploaded_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
