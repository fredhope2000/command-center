# Command Center

Private household command center for food inventory, grocery tracking, recipes, restaurant notes, budgeting, and finance workflows.

## Current Slice

- FastAPI app with server-rendered pages
- SQLite persistence
- Dashboard summary
- Food inventory add/list/delete flow
- Local seed script
- No authentication yet

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed_dev.py
uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000`.

By default, local data is stored at:

```text
instance/dev.sqlite
```

That file is ignored by git.

## Environment

Optional local overrides:

```bash
export APP_NAME="Command Center"
export APP_ENV="development"
export DATABASE_URL="sqlite:///instance/dev.sqlite"
```

Production on EC2 should point at a persistent path and run in production mode:

```bash
export APP_ENV="production"
export DATABASE_URL="sqlite:////var/lib/command-center/prod.sqlite"
```

Example env files live in `deploy/env/`.

Recommended environment/database combinations:

```text
Mac normal dev:
  APP_ENV=development
  DATABASE_URL=sqlite:///instance/dev.sqlite

Mac production-like smoke test:
  APP_ENV=production
  DATABASE_URL=sqlite:///instance/prod-local.sqlite

EC2 dev:
  APP_ENV=development
  DATABASE_URL=sqlite:////var/lib/command-center/dev.sqlite

EC2 prod:
  APP_ENV=production
  DATABASE_URL=sqlite:////var/lib/command-center/prod.sqlite
```

## EC2 Deployment Shape

Recommended production app command:

```bash
gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 127.0.0.1:8010 app.main:app
```

Recommended development app command on the same EC2 instance:

```bash
gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 127.0.0.1:8011 app.main:app
```

Use nginx/Caddy to terminate TLS and proxy hostnames to the right local port:

```text
command.example.com      -> 127.0.0.1:8010 -> prod.sqlite
command-dev.example.com  -> 127.0.0.1:8011 -> dev.sqlite
```

The dev site should be protected before exposing it publicly. Until app authentication is added, use nginx basic auth or keep the dev hostname inaccessible outside your network/VPN.

For the initial version, tables are created on startup if they do not exist. Once the schema settles into repeated changes, add Alembic migrations so deploys can evolve the production database deliberately.

## Development Seed Data

The seed script is meant for local/dev databases only:

```bash
APP_ENV=development DATABASE_URL=sqlite:///instance/dev.sqlite python scripts/seed_dev.py
```

It refuses to run when `APP_ENV=production`.

## Backups

Production SQLite backups should happen outside git:

```bash
sqlite3 /var/lib/command-center/prod.sqlite ".backup '/var/backups/command-center/prod-$(date +%Y%m%d).sqlite'"
```

Syncing `/var/backups/command-center/` to S3 is a good next step.

## Tests

```bash
pytest
```
