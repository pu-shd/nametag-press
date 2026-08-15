"""Role resolution: what appears at the bottom of a badge, and in what colour.

Driven entirely by ``profile.roles``. The predecessor defined this mapping twice
— once in Python for the PDF and once in JavaScript for the browser print path —
with the colours as hex literals in both.
"""

from __future__ import annotations

from eventkit.eventprofile import EventProfile


def role_for(profile: EventProfile, *, attendee_status: str | None,
             presenting_poster: bool = False) -> tuple[str | None, str | None]:
    """Return ``(label, colour)`` for a badge.

    A poster presenter with no other role is labelled as one: that is the thing a
    person walking up to their poster needs to be identifiable by.
    """
    for role in profile.roles.options:
        if attendee_status and role.key == attendee_status:
            return role.label, getattr(role, "color", None)

    if presenting_poster:
        return "Poster Presenter", _brand(profile)

    default = profile.roles.default
    if default:
        for role in profile.roles.options:
            if role.key == default:
                return role.label, getattr(role, "color", None)
    return None, None


def _brand(profile: EventProfile) -> str | None:
    return getattr(profile.branding, "brand_color", None)


def tally(profile: EventProfile, rows) -> dict[str, int]:
    """Count per configured role label, so the UI needs no vocabulary of its own."""
    counts: dict[str, int] = {}
    for row in rows:
        label, _ = role_for(
            profile,
            attendee_status=row.attendee_status,
            presenting_poster=row.presenting_poster,
        )
        if label:
            counts[label] = counts.get(label, 0) + 1
    return counts
