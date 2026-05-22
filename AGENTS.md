# Command Center Agent Notes

This file is durable context for future Codex sessions. Keep it stable and avoid adding session-specific changelog notes.

## Product Intent

Command Center is a private household web app for one household, initially focused on food workflows:

- Food inventory and current stock
- Grocery purchase tracking and receipt capture
- Recipes, recipe suggestions, and prepared-meal inventory
- Later themes may include restaurant notes, budgeting, spending analysis, finance/investment news, and AI-assisted workflows

The app does not need multi-tenant behavior. Barebones authentication is acceptable later, but the current app may be run without auth during early development. Practical usability for the household is more important than generalized SaaS design.

## Tech Stack

- Python backend using FastAPI
- Server-rendered Jinja templates
- SQLite via SQLAlchemy
- Static CSS and vanilla JavaScript
- pytest route tests with `TestClient`
- Gunicorn + Uvicorn workers for EC2 deployment
- nginx handles hostnames/TLS in front of the app

Use the repo’s existing server-rendered patterns unless there is a strong reason to introduce a frontend framework.

## Project Layout

- `app/main.py`: FastAPI app setup, static/templates, startup DB init, Jinja filters
- `app/config.py`: env-driven settings
- `app/db.py`: SQLAlchemy engine/session/init and lightweight SQLite schema updates
- `app/models/food.py`: food, grocery, recipe models
- `app/routes/`: page route modules
- `app/services/`: domain services such as dashboard summaries, inventory reconciliation, receipt parsing, recipe suggestions
- `app/templates/`: Jinja templates
- `app/static/css/site.css`: global styles
- `app/static/js/app.js`: UI behavior for editing, staged deletes, dynamic rows, receipt upload
- `scripts/seed_dev.py`: development seed data only
- `tests/test_routes.py`: route-level behavior tests
- `deploy/env/`: example env files for local/EC2 dev/prod

## Data And Environments

SQLite DB files are intentionally not committed. `instance/` is ignored by git.

Default local app behavior with no env vars:

```bash
APP_ENV=development
DATABASE_URL=sqlite:///instance/dev.sqlite
```

Common env/database combinations:

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

The app uses `Base.metadata.create_all()` on startup and has lightweight SQLite schema updates in `app/db.py`. Alembic is not yet present. For now, if dev data can be discarded, deleting/reseeding the SQLite file is acceptable.

Seed dev data:

```bash
APP_ENV=development DATABASE_URL=sqlite:///instance/dev.sqlite .venv/bin/python scripts/seed_dev.py
```

The seed script refuses to run in production.

## Local Commands

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run locally, matching the EC2 dev port for easy memory:

```bash
.venv/bin/uvicorn app.main:app --reload --port 8021
```

Run tests:

```bash
.venv/bin/python -m pytest
```

Useful syntax checks:

```bash
python3 -m py_compile app/routes/groceries.py app/routes/recipes.py app/models/food.py
node --check app/static/js/app.js
```

## Deployment Shape

The app is intended to run on an existing EC2 instance with multiple Python web apps. Known port convention:

- Other apps may already use ports like `8000` and `8010`
- Command Center production has used `8020`
- Command Center dev has used `8021`

Use systemd to run Gunicorn with Uvicorn workers bound to `127.0.0.1:<port>`. nginx proxies public hostnames to the local ports. The user handles DNS and nginx/certbot details.

Dev and prod should use separate SQLite files. Public dev hostnames should be protected, typically with nginx basic auth until app auth exists.

## UI Conventions

The UI is a practical household operations app, not a marketing site. Prefer compact, readable, utilitarian layouts.

Existing conventions:

- Server-rendered pages with forms and progressive JavaScript
- Left sidebar navigation
- Panels for actual tool surfaces and repeated items
- Read-only detail pages by default, with an `Edit` button that becomes `Done`
- `Done` saves changes when dirty; if no changes, it exits edit mode
- Destructive deletes use inline confirmation or staged remove/undo where edits are saved as a batch
- Placeholder text should be faint enough not to look like default values
- Keep mobile layouts from overflowing; tables have mostly been replaced by responsive list/card rows

Avoid large explanatory text blocks inside the app. Build direct usable controls instead.

## Food And Grocery Behavior

Food inventory tracks `FoodItem` records with name, quantity, unit, location, category, expiration, and notes.

Grocery purchases have purchase details and line items. Purchase detail editing is batched:

- One `Done` action saves purchase fields and line-item changes together
- Existing line item removals are staged visually with `Remove` -> `Undo`
- New line items can be added inline during edit mode
- Line items can be added to inventory when not already added
- Adding a line item to inventory is idempotent via `inventory_item_id` / `added_to_inventory_at`

Inventory reconciliation is intentionally simple:

- Exact normalized item-name match
- Merge only compatible unit families
- Supported unit families include count, volume, and weight
- `gal` and `gals` are supported aliases
- If units are incompatible, create a separate inventory item rather than merging

## Recipe Behavior

Recipes have structured ingredients using the same broad idea as grocery line items:

- Ingredient name
- Quantity
- Unit
- Notes

Recipe detail editing is batched:

- One `Done` action saves all recipe fields and ingredient row changes
- Existing ingredient removals are staged visually with `Remove` -> `Undo`
- New ingredients can be added inline during edit mode
- `Make it` is hidden while editing

Making a recipe:

- Creates a prepared-meal `FoodItem`
- Quantity is recipe servings
- Unit is `servings`
- Location defaults to fridge
- Expiration can be calculated from recipe shelf life
- Structured ingredients are subtracted from matching inventory when possible

Recipe suggestions are local/deterministic, not AI-backed yet:

- Compare structured recipe ingredients to current inventory
- Use quantity/unit compatibility when possible
- Bucket recipes by readiness
- Mark insufficient inventory as not enough

Longer term, AI may improve fuzzy matching, substitutions, recipe adaptation, and receipt interpretation, but current logic should remain useful without AI.

## Receipt Parsing

Receipt upload is AWS Textract only. Do not add local OCR/OpenCV/Tesseract paths unless the user explicitly asks; prior local parsing was not useful.

Receipt parsing flow:

- User uploads receipt image from the Add Purchase form
- Backend parses through `app/services/receipt_parser/`
- Parsed data populates the form for review
- It does not submit automatically

AWS credentials/role and region must be configured outside the app.

## Testing Expectations

Run pytest after backend/template behavior changes. Add focused route tests for meaningful workflows, especially:

- Batch edit/save behavior
- Staged remove behavior
- Inventory reconciliation
- Recipe make/suggestion behavior

Run `node --check app/static/js/app.js` after JS edits.

## Git And Collaboration

The working tree may contain user or previous-agent changes. Do not revert unrelated changes. Use `git status --short` before commits. The user sometimes asks to push; only commit/push when asked.

Use `apply_patch` for manual file edits.
