# Personal Website VPS Architecture (Simple + Robust)

This document defines the structure, responsibilities, and workflow for the personal website running on a VPS with Nginx, PHP, Python, and SQLite.

---

# 1. Directory Structure

All application code lives in one workspace:

/srv/personal_website/
    frontend/        # HTML / CSS / JavaScript (static site)
    api/             # PHP backend (request/response layer)
    analytics/       # Python scripts (batch + computations)
    scripts/         # utilities (backup, maintenance)
    data/            # optional generated outputs

Persistent data lives outside the app:

/var/data/site.db   # SQLite database (single source of truth)

---

# 2. System Roles

## Nginx
- Serves static frontend files
- Routes `/api` requests to PHP-FPM
- Entry point for all HTTP traffic

## PHP (API layer)
- Handles HTTP requests
- Reads/writes SQLite
- Returns JSON responses
- Must stay lightweight (no heavy computation)

## Python (analytics layer)
- Runs offline (NOT via HTTP)
- Used for:
  - data processing
  - analytics
  - scheduled jobs
- Writes results to SQLite or frontend-readable files

## SQLite (data layer)
- Single file database
- No server process
- Accessed by PHP and Python

---

# 3. Request Flow

## Frontend
Browser → Nginx → /frontend/index.html

## API
Browser → Nginx → PHP-FPM → /api/*.php → SQLite

## Analytics
Cron / manual run → Python scripts → SQLite / JSON outputs

---

# 4. Development Workflow

## Step 1: Enter project
cd /srv/personal_website

---

## Step 2: Edit code
- Use Claude Code or Vim
- Modify frontend, API, or scripts directly

---

## Step 3: Test locally

Frontend:
curl localhost

API:
curl localhost/api

Python scripts:
python3 analytics/script.py

---

## Step 4: Commit changes
git add .
git commit -m "describe change"

---

## Step 5: (Optional) Push to GitHub
git push

---

# 5. Python Analytics Pattern

Python must NOT serve HTTP.

Instead:

- Run manually or via cron
- Write results to:
  - /var/data/site.db, or
  - /srv/personal_website/frontend/*.json

Example:
python3 analytics/build_stats.py

---

# 6. PHP API Pattern

Keep PHP minimal:

- One endpoint per file OR simple router
- Focus on:
  - input parsing
  - SQLite queries
  - JSON output

Example endpoints:
/api/stats
/api/users
/api/data

---

# 7. Design Rules

## Separation of concerns
- PHP = request handling
- Python = computation
- Nginx = routing
- Frontend = UI
- SQLite = state

## Do NOT:
- Mix Python with HTTP serving (initially)
- Put business logic in frontend
- Couple analytics to request flow

---

# 8. Deployment Model

No CI/CD required initially.

Workflow:
edit → test → commit → reload nginx (if needed)

---

# 9. Mental Model

Browser
  ↓
Nginx
  ├── Frontend (static)
  └── PHP API

Python (offline jobs)
  ↓
SQLite / JSON outputs

---

# 10. Goal

Keep the system:

- minimal
- explicit
- easy to reason about
- incrementally extensible
