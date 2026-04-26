# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WodPlanner is a custom frontend for WodApp (app.wodapp.nl), a CrossFit class scheduling app. It wraps the reverse-engineered `ws.paynplan.nl` API to provide:
- **Friends tracking**: See which friends are signed up for classes
- **Browser-based authentication**: Users log in with their WodApp credentials

## Commands

```bash
# Install (with API server support)
pip install -e ".[api]"

# Install test dependencies (needed to run tests)
pip install -e ".[api,dev]"

# Run server
uvicorn wodplanner.app.main:app --reload

# Run tests
pytest

# Run tests with coverage
pytest --cov=wodplanner --cov-report=term-missing

# Run e2e tests
pytest tests/e2e/ --browser chromium

# Lint
ruff check .

# Type check
mypy src

# Import workout schedule from PDF (--dry-run to preview)
import-schedule schedule.pdf --year 2026 --gym-id 2495
import-schedule schedule.pdf --year 2026 --gym-id 2495 --dry-run

# Manage 1RM exercise list (fuzzy-match, add new, rename)
add-1rm --exercise "Back Squat"
add-1rm  # interactive: shows existing list, prompts for name

# Backup database (safe during live writes, keeps 7 by default)
backup-db
backup-db --db-path /data/wodplanner.db --backup-dir /data/backups --keep 7
```

## Architecture

```
src/wodplanner/
├── api/client.py          # WodApp API client (ws.paynplan.nl)
├── app/                   # FastAPI application
│   ├── main.py            # App entry point
│   ├── config.py          # Settings (session expiry, cookie config)
│   ├── dependencies.py    # Session-based auth dependencies
│   ├── routers/           # API endpoints (prefixed /api) and views
│   └── templates/         # Jinja2 HTML templates with HTMX
├── cli/import_schedule.py # PDF parser for workout schedules
├── cli/backup_db.py       # SQLite Online Backup API wrapper
├── models/                # Pydantic models
└── services/
    ├── session.py         # Cookie-based session encoding (itsdangerous)
    ├── schedule.py        # Workout schedule storage + class name mapping
    ├── friends.py         # Friends list persistence
    └── api_cache.py       # Short TTL in-memory cache for non-user-specific API responses
```

## Configuration

Environment variables (all optional for web usage):
- `ENVIRONMENT` — `development` (default) or `production`; production enables `COOKIE_SECURE` automatically
- `SESSION_EXPIRE_DAYS` — session lifetime in days (default: unset = never expire; browser max_age capped at 400 days)
- `COOKIE_SECURE` — override cookie secure flag; auto-enabled when `ENVIRONMENT=production`
- `SECRET_KEY` — cookie signing key; random default invalidates sessions on restart; set in production
- `WODAPP_USERNAME` / `WODAPP_PASSWORD` — only needed for CLI tools, not web
- `API_CACHE_TTL_SECONDS` — TTL for non-user-specific API response cache (default: 600 = 10 min); set lower for faster refresh, higher to reduce API load
- `LOG_LEVEL` — logging verbosity: `DEBUG`, `INFO` (default), `WARNING`, `ERROR`; applies to all wodplanner loggers

## Further Reading

- [docs/api.md](docs/api.md) — external API, API client, auth dependencies, auto-signup flow
- [docs/frontend.md](docs/frontend.md) — HTMX patterns, OOB swap gotcha, schedule import
- [docs/database.md](docs/database.md) — SQLite schema and tables
