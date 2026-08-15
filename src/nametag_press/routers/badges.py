"""Badge PDFs, the roster, and logo upload."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import ProfileDep, SessionDep, deps, require_principal
from ..layout import get as get_layout
from ..layout import page_count, to_json_dict
from ..models import BrandingAsset, Registrant
from ..render_pdf import Badge, render_badges, render_blank
from ..roles import role_for, tally
from ..schemas import RegistrantOut, Tallies
from ..templating import render_page

router = APIRouter(dependencies=[Depends(require_principal)])

ALLOWED_LOGO_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
}
MAX_LOGO_BYTES = 2_000_000


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def page(profile=ProfileDep) -> HTMLResponse:
    return HTMLResponse(render_page("index.html", profile))


@router.get("/api/layouts", include_in_schema=False)
def layouts() -> dict:
    """Geometry for the on-screen selection grid.

    Generated from ``layout.py`` so the browser can describe the sheet without
    owning its dimensions.
    """
    return to_json_dict()


@router.get("/api/registrants", response_model=list[RegistrantOut])
def roster(session: Session = SessionDep) -> list[Registrant]:
    stmt = select(Registrant).order_by(
        Registrant.last_name.asc(), Registrant.first_name.asc()
    )
    return list(session.execute(stmt).scalars())


@router.get("/api/tallies", response_model=Tallies)
def tallies(session: Session = SessionDep, profile=ProfileDep) -> Tallies:
    rows = list(session.execute(select(Registrant)).scalars())
    return Tallies(
        total=len(rows),
        by_role=tally(profile, rows),
        presenting=sum(1 for r in rows if r.presenting_poster),
    )


def _badges_for(session: Session, profile, keys: list[str] | None) -> list[Badge]:
    stmt = select(Registrant).order_by(
        Registrant.last_name.asc(), Registrant.first_name.asc()
    )
    rows = list(session.execute(stmt).scalars())
    if keys:
        wanted = set(keys)
        rows = [r for r in rows if r.person_key in wanted]

    out: list[Badge] = []
    for r in rows:
        label, colour = role_for(
            profile,
            attendee_status=r.attendee_status,
            presenting_poster=r.presenting_poster,
        )
        out.append(
            Badge(
                first_name=r.first_name,
                last_name=r.last_name,
                affiliation=r.home_institution if profile.nametags.show_affiliation else None,
                role_label=label if profile.nametags.show_role_badge else None,
                role_color=colour,
            )
        )
    return out


@router.get("/api/badges.pdf", include_in_schema=False)
def badges_pdf(
    request: Request,
    session: Session = SessionDep,
    profile=ProfileDep,
    template: str | None = Query(default=None),
    keys: str | None = Query(default=None, description="Comma-separated person keys"),
    outline: bool = Query(default=False),
) -> Response:
    layout = get_layout(template or profile.nametags.avery_template)
    selected = [k for k in (keys or "").split(",") if k.strip()] or None
    badges = _badges_for(session, profile, selected)

    cap = deps(request).settings.max_badges_per_run
    if len(badges) > cap:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{len(badges)} badges exceeds the {cap}-badge cap for one run. "
            "Select fewer, or raise MAX_BADGES_PER_RUN deliberately.",
        )

    logo = session.get(BrandingAsset, "primary")
    pdf = render_badges(
        badges,
        layout=layout,
        header_text=profile.event.title,
        logo_bytes=logo.data if logo else None,
        show_outline=outline,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="badges-{layout.sku}.pdf"',
            "X-Badge-Count": str(len(badges)),
            "X-Page-Count": str(page_count(len(badges), layout)),
        },
    )


@router.get("/api/badges/blank.pdf", include_in_schema=False)
def blank_pdf(
    profile=ProfileDep,
    template: str | None = Query(default=None),
    sheets: int = Query(default=1, ge=1, le=20),
) -> Response:
    """Calibration sheets. Print one on plain paper and hold it against the stock."""
    layout = get_layout(template or profile.nametags.avery_template)
    return Response(
        content=render_blank(layout, sheets=sheets),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="calibration-{layout.sku}.pdf"'},
    )


@router.put("/api/branding/{slot}")
async def upload_logo(slot: str, session: Session = SessionDep, file: UploadFile = File(...)):
    if slot not in ("primary", "sponsor"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Slot must be primary or sponsor.")
    if file.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported type {file.content_type!r}. Allowed: {sorted(ALLOWED_LOGO_TYPES)}",
        )

    data = await file.read()
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Logo exceeds 2 MB.")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty upload.")

    existing = session.get(BrandingAsset, slot)
    if existing is None:
        session.add(
            BrandingAsset(
                slot=slot, filename=file.filename or slot,
                content_type=file.content_type, data=data,
            )
        )
    else:
        existing.filename = file.filename or slot
        existing.content_type = file.content_type
        existing.data = data
    session.commit()
    return {"slot": slot, "bytes": len(data), "content_type": file.content_type}


@router.get("/api/branding/{slot}", include_in_schema=False)
def get_logo(slot: str, session: Session = SessionDep) -> Response:
    asset = session.get(BrandingAsset, slot)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No logo in that slot.")
    return Response(content=asset.data, media_type=asset.content_type)


@router.delete("/api/branding/{slot}", status_code=status.HTTP_204_NO_CONTENT)
def delete_logo(slot: str, session: Session = SessionDep) -> None:
    asset = session.get(BrandingAsset, slot)
    if asset is not None:
        session.delete(asset)
        session.commit()
