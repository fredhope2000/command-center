# Command Center Agent Notes

Durable context for future Codex sessions. Keep this stable; do not add session changelog notes.

## Product Intent

Command Center is a private household web app, initially focused on food inventory, grocery purchase tracking and receipt capture, recipes, recipe suggestions, and prepared-meal inventory. Later themes may include restaurant notes, budgeting, spending analysis, finance/investment news, and AI-assisted workflows.

This is not a multi-tenant SaaS app. Practical household usability matters more than generalized product architecture. Barebones auth is acceptable later; early local/dev use may run without auth.

## Stack And Layout

- FastAPI backend with server-rendered Jinja templates
- SQLite via SQLAlchemy; no Alembic yet
- Static CSS and vanilla JavaScript
- pytest route tests with `TestClient`
- Gunicorn + Uvicorn workers behind nginx on EC2

Prefer existing server-rendered patterns unless there is a strong reason to add a frontend framework.

Key files: `app/main.py`, `app/config.py`, `app/db.py`, `app/models/food.py`, `app/routes/`, `app/services/`, `app/templates/`, `app/static/css/site.css`, `app/static/js/app.js`, `scripts/seed_dev.py`, `tests/test_routes.py`, and `deploy/env/`.

## Data And Commands

SQLite DB files are not committed; `instance/` is ignored.

Default local settings:

```bash
APP_ENV=development
DATABASE_URL=sqlite:///instance/dev.sqlite
```

Common databases: Mac dev `sqlite:///instance/dev.sqlite`; Mac production-like smoke `sqlite:///instance/prod-local.sqlite`; EC2 dev `sqlite:////var/lib/command-center/dev.sqlite`; EC2 prod `sqlite:////var/lib/command-center/prod.sqlite`.

The app runs `Base.metadata.create_all()` on startup and has lightweight schema updates in `app/db.py`. If dev data can be discarded, deleting/reseeding SQLite is acceptable.

Install and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8021
```

Seed dev data:

```bash
APP_ENV=development DATABASE_URL=sqlite:///instance/dev.sqlite .venv/bin/python scripts/seed_dev.py
```

Test and syntax-check:

```bash
.venv/bin/python -m pytest
python3 -m py_compile app/routes/groceries.py app/routes/recipes.py app/models/food.py
node --check app/static/js/app.js
```

## Deployment And UI

The app runs on an existing EC2 instance with multiple Python web apps. Production has used port `8020`; dev has used `8021`; other apps may use `8000` or `8010`. Use systemd to run Gunicorn with Uvicorn workers bound to `127.0.0.1:<port>`. nginx handles hostnames/TLS and proxies to the local port. Keep dev and prod on separate SQLite files. Public dev hostnames should usually have nginx basic auth until app auth exists.

This is a practical household operations app, not a marketing site. Prefer compact, readable, utilitarian layouts:

- Use server-rendered pages with forms and progressive JavaScript.
- Keep the left sidebar navigation.
- Use panels for real tool surfaces and repeated items.
- Detail pages are read-only by default; `Edit` becomes `Done`.
- `Done` saves when dirty; if unchanged, it exits edit mode.
- Destructive deletes use inline confirmation or staged remove/undo saved as a batch.
- Placeholder text should be faint enough not to look like default values.
- Keep mobile layouts from overflowing; prefer responsive list/card rows over wide tables.
- Avoid large explanatory text blocks inside the app; build direct controls.

## Food, Grocery, And Recipe Behavior

Food inventory tracks `FoodItem` name, quantity, unit, location, category, expiration, and notes.

Grocery purchases have purchase details and line items. Purchase detail editing is batched: one `Done` saves purchase fields and line-item changes; existing removals are staged with `Remove` -> `Undo`; new line items can be added inline. Adding line items to inventory is idempotent through `inventory_item_id` / `added_to_inventory_at`.

Inventory reconciliation is intentionally simple: exact normalized item-name match, merge only compatible unit families, and create separate inventory items for incompatible units. Supported families include count, volume, and weight; `gal` and `gals` are aliases.

Recipes have structured ingredients: name, quantity, unit, and notes. Recipe detail editing is batched like groceries; `Make it` is hidden while editing.

Making a recipe creates a prepared-meal `FoodItem` with quantity set to recipe servings, unit `servings`, location `fridge`, optional shelf-life expiration, and ingredient subtraction from matching inventory when possible.

Recipe suggestions are local/deterministic, not AI-backed yet. Compare structured ingredients to inventory, use quantity/unit compatibility when possible, bucket by readiness, and mark insufficient inventory as not enough. Longer term AI can improve fuzzy matching, substitutions, adaptation, and receipt interpretation, but current logic should remain useful without AI.

## Receipt Parsing

Receipt upload is AWS Textract only. Do not add local OCR/OpenCV/Tesseract unless explicitly asked; prior local parsing was not useful.

Users upload a receipt image from the Add Purchase form. The backend parses through `app/services/receipt_parser/`, populates the form for review, and does not submit automatically. AWS credentials/role and region are configured outside the app.

## Testing And Git

Run pytest after backend/template behavior changes. Add focused route tests for meaningful workflows, especially batch edit/save, staged remove, inventory reconciliation, and recipe make/suggestion behavior. Run `node --check app/static/js/app.js` after JS edits.

The working tree may contain user or previous-agent changes. Do not revert unrelated changes. Use `git status --short` before commits. Only commit or push when asked. Use `apply_patch` for manual file edits.
