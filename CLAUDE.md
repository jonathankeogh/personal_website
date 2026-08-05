# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Communication

Always talk in ASD-STE100 Simplified Technical English.

## Architecture

This is a personal website running on a VPS with Nginx, PHP, and Python. The system has three distinct layers:

- **Nginx** — serves `frontend/` as static files, routes `/api/*` requests to PHP-FPM
- **PHP (`api/`)** — lightweight HTTP request/response layer; reads/writes SQLite, returns JSON
- **Python (`src/`)** — offline analytics/batch jobs plus external API clients that PHP shells out to; never serves HTTP itself

Persistent data lives at `/var/data/site.db` (SQLite), outside the app directory. Python scripts may also write JSON outputs to `frontend/` for the browser to fetch directly.

## Key Constraint

Python must NOT serve HTTP. It runs via cron or manually and writes results to SQLite or `frontend/*.json`. All HTTP is handled by PHP.

## Commands

### Test the running site
```bash
curl localhost          # frontend
curl localhost/api      # PHP API health check
```

### Python (single `uv` project at the repo root, Python 3.12)
One `pyproject.toml` / `uv.lock` / `.venv` at the root cover all Python. Run from the repo root:
```bash
uv run python src/electricity_gdp.py   # run a script
uv add <package>                       # add dependency
uv sync                                # install from lockfile
```
PHP invokes the API clients directly via `/srv/personal_website/.venv/bin/python src/markets.py`, so keep that root `.venv` in sync.

### Reload Nginx (after config changes)
```bash
sudo nginx -s reload
```

### Deploy
No CI/CD. Workflow: edit → test → commit → reload nginx if needed.

## PHP API Pattern

Keep PHP endpoints minimal — one endpoint per file or a simple router. Each endpoint: parse input → query SQLite → return JSON.

## Python Analytics Pattern

Scripts live in `src/`, read raw inputs from `data/`, and read/write `/var/data/site.db` or write outputs into `frontend/`. `src/electricity_gdp.py` is a representative offline job; `src/fred.py` + `src/markets.py` are the external API clients PHP calls.
