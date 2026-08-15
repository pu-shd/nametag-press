"""Application settings.

Lazy by design. ``get_settings()`` is cached rather than instantiated at import,
which is what lets ``create_app()`` have no import-time side effects and lets an
app's ``conftest.py`` be empty. Both predecessor repositories ran
``settings = Settings()`` and ``Base.metadata.create_all()`` at module import, so
every test file had to set environment variables *before* importing the app.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    #: SQLite on the App Service persistent share by default. Postgres opt-in.
    database_url: str = "sqlite:///./data/nametag-press.db"

    #: No default. A placeholder default ships a publicly-known shared secret to
    #: every deployment that forgets to set it.
    drupal_webhook_token: SecretStr

    #: Comma-separated Easy Auth principals. Empty means DENY ALL, not allow all.
    authorized_principals: str = ""

    #: Destructive endpoints are opt-in.
    enable_restore: bool = False

    #: Path to event-profile.yaml. None falls back to eventkit's search paths.
    event_profile: str | None = None

    #: Local development only; inert on Azure (eventkit.auth refuses the bypass
    #: when WEBSITE_SITE_NAME is set).
    allow_local_dev_admin: bool = False
    local_dev_admin_principal: str | None = None

    #: Cap on one print run. A slip in a selection should not silently spool
    #: hundreds of sheets.
    max_badges_per_run: int = Field(default=600, ge=1, le=5000)

    @model_validator(mode="after")
    def _check_token(self) -> Settings:
        from eventkit.webhook import assert_strong

        assert_strong(self.drupal_webhook_token, name="DRUPAL_WEBHOOK_TOKEN")
        return self

    @property
    def dev_principal(self) -> str | None:
        if not self.allow_local_dev_admin:
            return None
        return self.local_dev_admin_principal


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
