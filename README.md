# WodPlanner

Unofficial WodApp alternative for planning CrossFit classes. Uses the same credentials as [app.wodapp.nl](https://app.wodapp.nl) — no separate account needed.

> **Privacy:** Your credentials are never stored. They are passed directly to WodApp on login and discarded.

## Features

- **Friend tracking** — see which friends are signed up for the same class
- **Exercises overview** — browse all programmed movements across the schedule
- **1RM tracker** — log and track your personal records per exercise
- **Auto-signup queue** — automatically sign up when registration opens (7 days before)

## Using the app

Log in with your existing WodApp credentials (email + password). No registration required.

Questions or issues? [Open an issue on GitHub](https://github.com/sebastiaankok/wodplanner/issues).

## Self-hosting

### Requirements

- Python 3.11+
- A WodApp account

### Install & run

```bash
git clone https://github.com/sebastiaankok/wodplanner.git
cd wodplanner

python -m venv .venv
source .venv/bin/activate

pip install -e ".[api]"

uvicorn wodplanner.app.main:app --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) and log in with your WodApp credentials.

### Configuration

All settings are optional. Set via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | random | Cookie signing key — set this in production or sessions reset on restart |
| `ENVIRONMENT` | `development` | Set to `production` to enable secure cookies |
| `SESSION_EXPIRE_DAYS` | never | Session lifetime in days |
| `API_CACHE_TTL_SECONDS` | `600` | Cache TTL for schedule data |

### Import workout schedule

Schedules can be imported from a PDF file:

```bash
import-schedule schedule.pdf --year 2026 --gym-id 2495
```

Use `--dry-run` to preview without writing to the database.

### Backup database

```bash
backup-db
backup-db --db-path /data/wodplanner.db --backup-dir /data/backups --keep 7
```

## Disclaimer

This project is not affiliated with or endorsed by WodApp or Paynplan. It uses a reverse-engineered API (`ws.paynplan.nl`) for personal use only.
