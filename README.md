# WodPlanner

[![Python >=3.11](https://img.shields.io/badge/python-%3E%3D3.11-blue?logo=python)](https://python.org)
[![GitHub release](https://img.shields.io/github/v/release/sebastiaankok/wodplanner?logo=github)](https://github.com/sebastiaankok/wodplanner/releases)
[![CI](https://github.com/sebastiaankok/wodplanner/actions/workflows/ci.yml/badge.svg)](https://github.com/sebastiaankok/wodplanner/actions/workflows/ci.yml)
[![Docker](https://github.com/sebastiaankok/wodplanner/actions/workflows/docker.yml/badge.svg)](https://github.com/sebastiaankok/wodplanner/actions/workflows/docker.yml)
[![Ruff](https://img.shields.io/badge/ruff-checked-blueviolet)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/mypy-checked-blue)](http://mypy-lang.org)
[![Renovate](https://img.shields.io/badge/renovate-enabled-brightgreen?logo=renovate)](https://renovatebot.com)
[![Last commit](https://img.shields.io/github/last-commit/sebastiaankok/wodplanner)](https://github.com/sebastiaankok/wodplanner/commits/main)

Unofficial WodApp alternative for planning CrossFit classes. Uses the same credentials as WodApp — no separate account needed.

> **Privacy:** Your password is never stored. Login sends it directly to WodApp, which returns an auth token — only that token is kept in your browser cookie.

> **Disclaimer:** This is a personal experiment, not affiliated with or endorsed by WodApp. It uses a reverse-engineered, undocumented API. The API may change or break at any time. **For personal use only — do not run as a public service.**

## Features

- **Friend tracking** — see what classes your friends are joining
- **Exercises overview** — browse all programmed movements across the schedule
- **1RM tracker** — log and track your personal records per exercise


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
| `WODAPP_API_BASE_URL` | — | **Required.** Base URL for the WodApp API |
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

This project is not affiliated with or endorsed by WodApp. It uses a reverse-engineered, undocumented API and is intended for personal use only. It is experimental — the upstream API may change without notice. Do not run this as a public service or share access with others.
