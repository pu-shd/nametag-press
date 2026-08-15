"""Application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from eventkit.auth import AllowList, DeniedTheme, EasyAuth
from eventkit.auth import install as install_auth
from eventkit.backup import BackupSpec, TableSpec, make_backup_router
from eventkit.db import Database
from eventkit.drupal import resolve_field_map
from eventkit.eventprofile import EventProfile
from eventkit.eventprofile.load import load_profile
from eventkit.logging import configure_logging
from eventkit.ui import static_path
from eventkit.webhook import WebhookTokens
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .deps import AppDeps, WebhookCounters, get_db, require_principal
from .models import Base, Registrant
from .routers import admin, badges, webhook
from .settings import Settings, get_settings

logger = logging.getLogger("nametag_press")

REQUIRED_FIELDS = ["email", "name"]
OPTIONAL_FIELDS = [
    "uuid", "sid", "serial", "home_institution_or_organization",
    "attendee_status", "student", "presenting_poster",
]

BACKUP_SPEC = BackupSpec(
    app_name="nametag-press",
    app_version="1.0.0",
    tables=[
        TableSpec(model=Registrant, key="registrants", order=0),
        # Logo bytes are deliberately excluded: a backup is a data export staff
        # download and email around, and it should not carry megabytes of image.
    ],
    required_keys={"registrants"},
)


def build_deps(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    profile: EventProfile | None = None,
) -> AppDeps:
    settings = settings or get_settings()
    profile = profile or load_profile(settings.event_profile)
    profile.validate_for_app("nametag-press", require=["event", "branding", "roles"])

    database = database or Database(settings.database_url)
    field_map = resolve_field_map(profile, want=REQUIRED_FIELDS + OPTIONAL_FIELDS)

    auth = EasyAuth(
        AllowList.parse(settings.authorized_principals),
        dev_principal=settings.dev_principal,
        page_paths=("/",),
        theme=DeniedTheme.from_profile(profile),
    )
    tokens = WebhookTokens({"registration": settings.drupal_webhook_token})
    tokens.assert_all_strong()

    return AppDeps(
        settings=settings,
        database=database,
        profile=profile,
        auth=auth,
        tokens=tokens,
        field_map=field_map,
        counters=WebhookCounters(),
    )


def create_app(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    profile: EventProfile | None = None,
    create_schema: bool = True,
) -> FastAPI:
    configure_logging()
    app_deps = build_deps(settings=settings, database=database, profile=profile)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if create_schema:
            Base.metadata.create_all(app_deps.database.engine)
        logger.info(
            "nametag-press ready event=%s template=%s",
            app_deps.profile.event.slug,
            app_deps.profile.nametags.avery_template,
        )
        yield

    app = FastAPI(
        title="nametag-press",
        version="1.0.0",
        summary="Print-ready Avery badge sheets from the registrant roster.",
        lifespan=lifespan,
    )
    app.state.deps = app_deps
    app.state.database = app_deps.database
    app.state.auth = app_deps.auth
    app.state.profile = app_deps.profile

    install_auth(app, app_deps.auth)

    app.include_router(badges.router)
    app.include_router(admin.router)
    app.include_router(webhook.router)
    app.include_router(
        make_backup_router(
            BACKUP_SPEC,
            db=get_db,
            principal=require_principal,
            enable_restore=lambda: app_deps.settings.enable_restore,
            database=app_deps.database,
        )
    )

    app.mount("/ui", StaticFiles(directory=static_path()), name="ui")

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
