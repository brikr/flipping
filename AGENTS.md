# AGENTS.md

A self-hosted Old School RuneScape Grand Exchange flip screener. A single Python process runs:
- a **collector** that mirrors the [OSRS Wiki real-time prices API](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices) into SQLite;
- a **FastAPI** app that serves a dashboard and a JSON API.

It's deployed as one Docker container on a Synology NAS. See `README.md` for user-facing docs and the deploy setup.

## Commands

```bash
uv sync                      # install deps (Python 3.13, pinned in .python-version)
uv run pytest -q             # tests; they never touch the network
uv run flipping              # dev server on http://127.0.0.1:8000, DB at data/flipping.db
./scripts/deploy.sh          # build + restart on the NAS over SSH (the user runs this; don't deploy unprompted)
```

## Layout

| File | Purpose |
|---|---|
| `src/flipping/config.py` | All settings, from `FLIPPING_*` env vars |
| `src/flipping/wiki.py` | API client. Bulk endpoints only. |
| `src/flipping/collector.py` | Background loops; `plan_backfill()` decides which windows to fetch after downtime |
| `src/flipping/db.py` | SQLite schema and queries. One short-lived connection per call; call via `asyncio.to_thread`. |
| `src/flipping/screener.py` | Pure `screen()` and `hourly_volume()` functions plus the DB-loading `run()` |
| `src/flipping/tax.py` | GE tax rules: 2% rounded down, 5M cap, free under 50gp, an exempt-item list |
| `src/flipping/static/index.html` | The whole dashboard: vanilla JS, no build step |

The `prices` table stores 5-minute (`step=300`) and hourly (`step=3600`) windows that never overlap. Anything reading `prices` must account for `step`; see `hourly_volume()` for the pattern.

## Be gentle with the price API

The wiki provides this API for free. Keep the number of real requests as low as possible while developing and testing.

- **Never test against a fresh, empty database.** An empty DB triggers a mapping fetch and a full backfill. Copy an existing one into a scratch location and point the app at it:
  ```bash
  cp data/flipping.db /tmp/<scratch>/test.db
  FLIPPING_DB=/tmp/<scratch>/test.db FLIPPING_PORT=8765 uv run flipping
  ```
  This matters most for **schema and migration changes**: run them against a copy of a real DB, never by deleting the DB and starting over. If `data/flipping.db` doesn't exist, ask the user before creating one. They can pull the NAS copy with `DOCKER_HOST=ssh://<nas> docker cp flipping:/data/flipping.db data/flipping.db`.
- **Turn off the collector when you don't need it.** UI, screener and query work only needs stored data. `FLIPPING_COLLECTOR=0` makes zero API requests.
- **Keep hourly backfill locally.** Leave `FLIPPING_BACKFILL_STEP=1h`, the default outside Docker. Lower `FLIPPING_BACKFILL_HOURS` if a test only needs a little history. Only the NAS should use `5m`.
- **Unit tests use fixtures, never the network.** Logic that needs testing should be a pure function, like `screen()`, `plan_backfill()` and `hourly_volume()`, so it can be tested with hand-built data.
- **Use bulk endpoints only** (`/latest`, `/5m`, `/1h`, `/mapping`). Don't loop over per-item endpoints like `/timeseries` for many items. To check a response shape, make one `curl` call and reuse the output; don't re-request it.
- **Stop dev servers when done**, so a forgotten collector doesn't keep polling. Use `pkill -f "[.]venv/bin/flipping"`. The brackets stop the pattern from matching, and killing, your own shell.
- **Keep a descriptive `User-Agent`**, which the wiki requires. Never put the user's personal email in it.

## Conventions and gotchas

- **The NAS database is long-lived** and lives on a Docker volume. Schema changes must work on an existing DB: `CREATE ... IF NOT EXISTS` for new tables, and explicit migration code for changes to existing ones. Never assume a fresh DB.
- **Prices:** `latest.low` is the instasell price, which is where a flipper buys. `latest.high` is the instabuy price, where a flipper sells. Margin always means after tax: use `tax.post_tax_margin()`, never `high - low`.
- **Tax rules change occasionally.** Check the OSRS Wiki's Grand Exchange page before changing `tax.py`.
- **Deploys:**
  - The NAS builds the image from this folder over SSH, so anything left out by `.dockerignore` won't reach it.
  - Keep `compose.yaml` on a named volume. A relative bind mount would resolve to a local-machine path on the NAS.
- **Docker may not be reachable from WSL.** It depends on Docker Desktop's WSL integration. If you can't run `docker build`, tell the user it was unverified rather than skipping that silently.
