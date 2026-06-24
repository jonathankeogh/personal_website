# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

This is a personal website running on a VPS with Nginx, PHP, and Python. The system has three distinct layers:

- **Nginx** — serves `frontend/` as static files, routes `/api/*` requests to PHP-FPM
- **PHP (`api/`)** — lightweight HTTP request/response layer; reads/writes SQLite, returns JSON
- **Python (`python/`)** — offline analytics and batch jobs only; never serves HTTP

Persistent data lives at `/var/data/site.db` (SQLite), outside the app directory. Python scripts may also write JSON outputs to `frontend/` for the browser to fetch directly.

## Key Constraint

Python must NOT serve HTTP. It runs via cron or manually and writes results to SQLite or `frontend/*.json`. All HTTP is handled by PHP.

## Commands

### Test the running site
```bash
curl localhost          # frontend
curl localhost/api      # PHP API health check
```

### Run a Python script
```bash
cd python
uv run python src/main.py
```

### Python dependency management (uses `uv`, Python 3.12)
```bash
cd python
uv add <package>        # add dependency
uv sync                 # install from lockfile
```

### Reload Nginx (after config changes)
```bash
sudo nginx -s reload
```

### Deploy
No CI/CD. Workflow: edit → test → commit → reload nginx if needed.

## PHP API Pattern

Keep PHP endpoints minimal — one endpoint per file or a simple router. Each endpoint: parse input → query SQLite → return JSON.

## Python Analytics Pattern

Scripts read/write `/var/data/site.db` or write JSON to `frontend/`. Entry point convention follows `python/src/main.py`.
