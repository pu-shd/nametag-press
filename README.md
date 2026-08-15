# nametag-press

Print-ready Avery badge sheets from the registrant roster.

One of five applications in the [event-management stack](https://github.com/pu-shd/eventkit).

## What it does

- **Badge PDFs** on three Avery stocks, with per-badge text fitting.
- **Selection**: search, filter by role, tick the people you want.
- **In-browser preview** of the actual PDF — not a CSS approximation of it.
- **Calibration sheets**: outlined but empty, for aligning a printer.
- **Logo upload** for the badge header, stored in the database.

## Supported stock

| SKU | Card | Per sheet | Margins | Gaps |
| --- | --- | --- | --- | --- |
| `5392` (default) | 4 × 3 in | 6 | 0.25 in sides, 1.0 in top/bottom | none |
| `74541` | 4 × 3 in | 6 | identical to 5392 | none |
| `5395` | 3⅜ × 2⅓ in | 8 | 0.75 in sides, 0.5 in top/bottom | 0.25 × 0.1 in |

`74541` and `5392` are the same physical sheet under two part numbers. Both are
listed so you can pick whichever is printed on the box in front of you.

## Calibrate before you print a box

```
Download a blank sheet → print on plain paper → hold it against real stock
```

A passing test suite and a misaligned sheet are entirely compatible. The geometry
tests assert that every layout fits on Letter and that no card escapes the page,
which catches an arithmetic slip — they cannot catch your printer's margins.

## One renderer

Geometry lives in `layout.py` and nowhere else. `layouts.json`, which the browser
uses to draw the selection grid, is **generated** from it and asserted equal in CI.

The predecessor defined the geometry twice — once in ReportLab and once in a print
CSS grid — and the CSS version could not reproduce per-line autoshrink, so a long
name printed differently depending on which path you used. There is now one path,
and the preview is the output.

## This application does not own swag

There is no `t_shirt_size` column. Inventory, replacement sizes and issuance all
live in `ticket-reconciler`, which has the check-in desk. The predecessor stored a
size here, backed it up, and never rendered it anywhere. Two applications counting
shirts independently is how you oversell mediums.

## Quickstart

```sh
docker-compose run --rm test     # the whole suite, same command as CI
docker-compose up app            # http://localhost:8000
```

## Configuration

| Setting | Default | Notes |
| --- | --- | --- |
| `DRUPAL_WEBHOOK_TOKEN` | **required** | No default; placeholders rejected. |
| `AUTHORIZED_PRINCIPALS` | `""` | **Empty means deny all.** |
| `DATABASE_URL` | `sqlite:///./data/nametag-press.db` | |
| `ENABLE_RESTORE` | `False` | |
| `MAX_BADGES_PER_RUN` | `600` | A slip in a selection should not spool hundreds of sheets. |
| `EVENT_PROFILE` | unset | Supplies role labels and colours, the default stock, and whether to show affiliation. |

## Roles come from the profile

`profile.roles` supplies the label and colour printed at the bottom of each badge.
Someone presenting a poster with no other role is labelled a poster presenter,
because that is what makes them identifiable at their poster.

## Logos

`PUT /api/branding/primary` with a PNG, JPEG or SVG under 2 MB. Stored as bytes in
the database — the predecessor wrote them to a path that was not the Azure Files
mount, so they vanished on container restart, after which the renderer silently drew
nothing because the failure path was a bare `except: pass`. A corrupt logo here logs
a warning and still prints the badges.

Backups deliberately exclude logo bytes: a backup is a data export staff download
and email around, and it should not carry megabytes of image.

## Licence

MIT. Copyright (c) 2026 The Trustees of Princeton University.
