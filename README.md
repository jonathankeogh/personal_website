# personal_website

The frontend and backend for [jonathankeogh.com](https://jonathankeogh.com) — a
personal site with a few writing and data projects.

No framework and no build step. Static HTML and CSS, a small PHP endpoint for
dynamic data, and Python for the analysis behind the posts.

## Layout

```
frontend/   static pages, stylesheet, self-hosted fonts and MathJax
api/        PHP endpoint — reads SQLite, returns JSON
src/        Python: offline analysis and external API clients
data/       raw inputs (OWID energy, World Bank GDP)
```

`src/energy_gdp.py` and `src/bohemian.py` build the project pages.
`src/fred.py` and `src/markets.py` fetch market data that the API serves.

## Stack

Nginx, PHP-FPM, SQLite, Python 3.12 (`uv`), behind Cloudflare. Runs on a VPS.

```bash
uv sync                        # install Python dependencies
uv run python src/energy_gdp.py
```

A `.env` with `FRED_API_KEY` is needed for the market scripts.
