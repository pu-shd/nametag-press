# nametag-press

Avery-format badge PDFs, generated server-side.

One of five applications in the
[event-management stack](https://github.com/pu-shd/event-stack), built on
[eventkit](https://github.com/pu-shd/eventkit).

## What it does

- Renders badges for a selected roster onto Avery 5392, 74541 or 5395.
- Auto-shrinks long names and affiliations per line.
- Role labels and colours come from the event profile.
- Blank calibration sheets, and an in-browser PDF preview.
- Logos are stored in the database, so they survive a container restart.

## Quickstart

```sh
docker-compose up            # http://localhost:8000
docker-compose run --rm test
```

## Routes

| Route | Auth | |
|---|---|---|
| `GET /` | user | roster and selection |
| `GET /api/badges.pdf?template=&keys=` | user | the sheet |
| `GET /api/badges/blank.pdf?sheets=` | user | calibration |
| `GET/PUT /api/branding/{slot}` | user | logos |
| `POST /api/drupal-webhook` | token | upsert |
| `GET /healthz` | none | liveness |

## Configuration

| Setting | Default | Notes |
| --- | --- | --- |
| `DRUPAL_WEBHOOK_TOKEN` | **required** | No default; placeholders rejected. |
| `AUTHORIZED_PRINCIPALS` | `""` | **Empty means deny all.** |
| `DATABASE_URL` | `sqlite:///./data/nametag-press.db` | |
| `ENABLE_RESTORE` | `False` | |
| `MAX_BADGES_PER_RUN` | `600` | A slip in a selection should not spool hundreds of sheets. |
| `EVENT_PROFILE` | unset | Supplies role labels and colours, the default stock, and whether to show affiliation. |

## Drupal wiring

Add a Remote Post handler on your registration webform pointing at
`https://<app>.azurewebsites.net/api/drupal-webhook`, Completed and Updated,
method POST, type JSON. Custom options:

```yaml
headers:
  X-Drupal-Webhook-Token: <the token the toolkit printed>
```

**The nesting matters** — a flat key is ignored and every call 403s while the
registrant still sees success. Confirm with `GET /api/webhook/status`, which
reports counters and `unmapped_keys` and no attendee data.

Field keys are declared in
[drupal-event-forms](https://github.com/pu-shd/drupal-event-forms/blob/main/contracts/).

## Calibrate before printing a box

Print one blank sheet on plain paper and hold it against a real Avery sheet, up
to the light. Printer margins drift. One sheet, and it saves a box.

## One renderer

ReportLab produces the PDF; the browser previews that same PDF. There is no
separate print-CSS path, so what you preview is what prints.

## This application does not own swag

Sizes live in `ticket-reconciler`. Two applications counting shirts is how you
oversell mediums.

## Deploying

```zsh
eventkit azure deploy --event my-event-2027 --dry-run   # prints every az command
eventkit azure deploy --event my-event-2027
```

Idempotent and resumable; it joins the event's existing resource group, plan and
registry or creates them. `deploy/app.conf` declares the settings and gates.
Every route is behind Easy Auth.

CI/CD templates:

```zsh
TPL="$(python -c 'import eventkit.azure as a; print(a.templates_path())')"
cp "$TPL"/workflows/{deploy,test,backup}.yml .github/workflows/
```

Without Azure, the container runs anywhere:

```sh
docker build --target runtime -t nametag-press .
docker run -p 8000:8000 \
  -v "$PWD/event-profile.yaml:/app/event-profile.yaml:ro" \
  -e DRUPAL_WEBHOOK_TOKEN="$(openssl rand -hex 32)" \
  -e AUTHORIZED_PRINCIPALS="you@example.edu" \
  -e DATABASE_URL="sqlite:////data/nametag-press.db" \
  nametag-press
```

→ [Deployment guide](https://github.com/pu-shd/eventkit/blob/main/docs/azure/README.md)

## Licence

MIT. Copyright (c) 2026 The Trustees of Princeton University.
