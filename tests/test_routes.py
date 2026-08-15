"""HTTP surface: PDFs, roster, logos, webhook, and access control."""

from __future__ import annotations

import io

import pytest
from eventkit.testing.plugin import STRONG_TEST_TOKEN
from eventkit.webhook import WEAK_TOKENS
from pypdf import PdfReader

from nametag_press.models import BrandingAsset, Registrant

PROTECTED = [
    "/api/registrants",
    "/api/tallies",
    "/api/badges.pdf",
    "/api/badges/blank.pdf",
    "/api/webhook/status",
    "/api/admin/db-backup",
]

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


class TestProtection:
    @pytest.mark.parametrize("path", PROTECTED)
    def test_anonymous_is_refused(self, anon_client, path):
        assert anon_client.get(path).status_code != 200

    def test_page_redirects_anonymous(self, anon_client):
        res = anon_client.get("/")
        assert res.status_code in (302, 307)
        assert "/.auth/login" in res.headers.get("location", "")

    def test_healthz_is_open(self, anon_client):
        assert anon_client.get("/healthz").json() == {"status": "ok"}


class TestWebhookAndRoster:
    def test_creates_a_registrant(self, webhook_post, session):
        assert webhook_post().status_code == 200
        r = session.query(Registrant).one()
        assert r.first_name == "Ada"
        assert r.attendee_status == "Speaker"

    def test_is_idempotent(self, webhook_post, session):
        webhook_post()
        webhook_post()
        session.expire_all()
        assert session.query(Registrant).count() == 1

    def test_affiliation_is_normalised_from_the_profile(self, webhook_post, session):
        """The rule that existed in six copies across the predecessors."""
        webhook_post(data={"home_institution_or_organization": "", "email": "x@example.edu"})
        assert session.query(Registrant).one().home_institution == "Example University"

    def test_no_swag_field_exists(self):
        """Swag belongs to ticket-reconciler. Two apps counting shirts is how you
        oversell mediums."""
        cols = set(Registrant.__table__.columns.keys())
        assert not any("shirt" in c or "swag" in c for c in cols)

    def test_roster_and_tallies(self, webhook_post, client):
        webhook_post()
        assert len(client.get("/api/registrants").json()) == 1
        t = client.get("/api/tallies").json()
        assert t["total"] == 1
        assert t["by_role"].get("Speaker") == 1


class TestBadgePdf:
    def _pdf(self, res):
        assert res.status_code == 200, res.text
        assert res.headers["content-type"] == "application/pdf"
        assert res.content.startswith(b"%PDF")
        return PdfReader(io.BytesIO(res.content))

    def test_renders_for_the_whole_roster(self, webhook_post, client):
        webhook_post()
        pdf = self._pdf(client.get("/api/badges.pdf"))
        assert len(pdf.pages) == 1

    def test_empty_roster_still_produces_a_valid_pdf(self, client):
        pdf = self._pdf(client.get("/api/badges.pdf"))
        assert len(pdf.pages) == 1

    @pytest.mark.parametrize(("sku", "per_page"), [("5392", 6), ("74541", 6), ("5395", 8)])
    def test_page_count_matches_the_stock(self, client, session, sku, per_page):
        for i in range(per_page + 1):
            session.add(Registrant(person_key=f"k{i}", first_name="A", last_name=f"B{i}"))
        session.commit()
        res = client.get(f"/api/badges.pdf?template={sku}")
        assert self._pdf(res).pages.__len__() == 2
        assert res.headers["X-Page-Count"] == "2"

    def test_selection_by_key(self, client, session):
        session.add(Registrant(person_key="a", first_name="A", last_name="One"))
        session.add(Registrant(person_key="b", first_name="B", last_name="Two"))
        session.commit()
        res = client.get("/api/badges.pdf?keys=a")
        assert res.headers["X-Badge-Count"] == "1"

    def test_a_very_long_name_does_not_crash_the_renderer(self, client, session):
        session.add(Registrant(person_key="l", first_name="Wolfeschlegelsteinhausenberger",
                               last_name="Dorffvoralternwaren" * 3,
                               home_institution="A very long institution name " * 6))
        session.commit()
        self._pdf(client.get("/api/badges.pdf"))

    def test_run_cap_is_enforced(self, app, client, session):
        app.state.deps.settings.max_badges_per_run = 2
        for i in range(3):
            session.add(Registrant(person_key=f"c{i}", first_name="A", last_name=str(i)))
        session.commit()
        res = client.get("/api/badges.pdf")
        assert res.status_code == 400
        assert "cap" in res.json()["detail"]

    def test_blank_calibration_sheets(self, client):
        res = client.get("/api/badges/blank.pdf?sheets=3")
        assert len(self._pdf(res).pages) == 3

    def test_blank_sheet_count_is_bounded(self, client):
        assert client.get("/api/badges/blank.pdf?sheets=999").status_code == 422

    def test_layouts_endpoint_matches_the_module(self, client):
        from nametag_press.layout import to_json_dict

        assert client.get("/api/layouts").json() == to_json_dict()


class TestLogos:
    def test_upload_download_delete(self, client):
        res = client.put("/api/branding/primary",
                         files={"file": ("logo.png", PNG, "image/png")})
        assert res.status_code == 200
        assert res.json()["bytes"] == len(PNG)

        got = client.get("/api/branding/primary")
        assert got.status_code == 200
        assert got.content == PNG

        assert client.delete("/api/branding/primary").status_code == 204
        assert client.get("/api/branding/primary").status_code == 404

    def test_logo_survives_in_the_database_not_the_filesystem(self, client, session):
        """The predecessor wrote these to a path that was not the Azure Files
        mount, so they vanished on container restart."""
        client.put("/api/branding/primary", files={"file": ("l.png", PNG, "image/png")})
        session.expire_all()
        assert session.get(BrandingAsset, "primary").data == PNG

    def test_rejects_an_unknown_slot(self, client):
        assert client.put("/api/branding/nope",
                          files={"file": ("l.png", PNG, "image/png")}).status_code == 400

    def test_rejects_an_unsupported_type(self, client):
        assert client.put("/api/branding/primary",
                          files={"file": ("x.exe", b"MZ", "application/x-msdownload")}
                          ).status_code == 400

    def test_rejects_an_empty_upload(self, client):
        assert client.put("/api/branding/primary",
                          files={"file": ("e.png", b"", "image/png")}).status_code == 400

    def test_a_corrupt_logo_degrades_rather_than_500ing(self, client, session):
        """The predecessor swallowed this with a bare `except: pass` and silently
        drew nothing."""
        session.add(BrandingAsset(slot="primary", filename="broken.png",
                                  content_type="image/png", data=b"not really a png"))
        session.add(Registrant(person_key="r", first_name="A", last_name="B"))
        session.commit()
        res = client.get("/api/badges.pdf")
        assert res.status_code == 200
        assert res.content.startswith(b"%PDF")


class TestBackup:
    def test_backup_excludes_logo_bytes(self, client, webhook_post):
        """A backup is a data export staff download and email around."""
        webhook_post()
        client.put("/api/branding/primary", files={"file": ("l.png", PNG, "image/png")})
        body = client.get("/api/admin/db-backup").json()
        assert "registrants" in body["tables"]
        assert "branding_assets" not in body["tables"]


class TestSettingsFailClosed:
    def test_defaults(self):
        from nametag_press.settings import Settings

        f = Settings.model_fields
        assert f["enable_restore"].default is False
        assert f["authorized_principals"].default == ""
        assert f["drupal_webhook_token"].is_required()

    @pytest.mark.parametrize("weak", sorted(WEAK_TOKENS))
    def test_placeholder_tokens_rejected(self, weak):
        from eventkit.errors import ConfigError

        from nametag_press.settings import Settings

        with pytest.raises(ConfigError, match="placeholder"):
            Settings(drupal_webhook_token=weak)

    def test_strong_token_is_accepted(self):
        from nametag_press.settings import Settings

        assert Settings(drupal_webhook_token=STRONG_TEST_TOKEN)
