# OSRS Flipping

A self-hosted [Grand Exchange](https://oldschool.runescape.wiki/w/Grand_Exchange) flip screener for Old School RuneScape. It records price history from the [OSRS Wiki real-time prices API](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices) and ranks items by how much you could realistically make flipping them, after tax.

## How it works

A single Python process, built on FastAPI and SQLite, does two jobs.

**Collector.** Keeps a local copy of the price API:
- latest instabuy/instasell prices, every minute;
- 5-minute average prices and trade volumes, every 5 minutes;
- item names and buy limits, daily;
- after downtime, backfill of up to 24h of missing history, at 5-minute or hourly resolution.

**Screener and dashboard.** Ranks items by estimated profit per 4-hour buy-limit window, and scores how *stable* each margin has been. Margins that only appeared a few minutes ago rank low.

### What the columns mean

| Column | Meaning |
|---|---|
| Buy / Sell | Latest instasell / instabuy price. A patient buy offer fills near Buy; a patient sell offer near Sell. |
| Tax | 2% of Sell, rounded down, capped at 5M. Free under 50gp, and bonds plus some tools are exempt ([tax.py](src/flipping/tax.py)). |
| Margin | Sell − Tax − Buy |
| 1h vol | min(units bought, units sold) per hour, measured over the last hour |
| Qty | min(buy limit, what your budget affords, 1h vol). One hour of real volume is a deliberately conservative guess at how much you can actually fill. |
| Profit / 4h | Margin × Qty. Optimistic: assumes the current margin holds. |
| Stable | Share of price windows in the lookback (default 6h) where the item had a positive post-tax margin |
| Med. margin | Median post-tax margin across those windows |
| Real / 4h | Med. margin × Qty, floored at 0. The default sort: steady flips rise and one-off spikes sink. |

**How to read it:** a big margin with low Stable or a negative Med. margin is usually noise, such as a single odd trade. Prefer items with Stable above about 70%. Click a row to see its 24h price chart.

**Favorites (★):** starred items always appear at the top of the table, sorted by the current column, even when the filters would hide them. They're saved in your browser, so each browser or device keeps its own list.

## Running locally

You need [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run flipping          # http://127.0.0.1:8000, DB at ./data/flipping.db
uv run pytest
```

Data starts collecting as soon as the app runs. Volume and stability numbers become useful once there's an hour or more of history.

### Being kind to the API

The OSRS Wiki provides the price API for free, so this project tries to keep its requests to a minimum:

- **Bulk endpoints only.** It never loops over items one at a time.
- **Hourly backfill by default.** Outside Docker, a fresh database is backfilled with hourly windows (`FLIPPING_BACKFILL_STEP=1h`), which takes about 40 requests for 24h of history instead of about 290.
- **Gaps only.** After a restart, only periods with no stored data are fetched, so restarting often costs almost nothing.
- **UI-only mode.** For dashboard work against an existing database, `FLIPPING_COLLECTOR=0` makes no API requests at all.

**Running your own copy?** Set `FLIPPING_USER_AGENT` to something that identifies *you*. The wiki asks clients for a descriptive User-Agent with a way to contact the operator.

### Settings

All settings are environment variables:

| Var | Default | |
|---|---|---|
| `FLIPPING_USER_AGENT` | the maintainer's contact string | Set your own; see above |
| `FLIPPING_DB` | `data/flipping.db` (`/data/flipping.db` in Docker) | SQLite database path |
| `FLIPPING_HOST` / `FLIPPING_PORT` | `127.0.0.1` / `8000` (`0.0.0.0` in Docker) | |
| `FLIPPING_BACKFILL_HOURS` | `24` | How far back to fill gaps after downtime |
| `FLIPPING_BACKFILL_STEP` | `1h` | Gap-filling resolution: `1h` uses about 12x fewer requests; `5m` gives full-resolution history and is recommended for long-running deployments |
| `FLIPPING_RETENTION_DAYS` | `30` | History kept; about 20 MB/day |
| `FLIPPING_LATEST_INTERVAL` | `60` | Seconds between latest-price polls |
| `FLIPPING_COLLECTOR` | `1` | `0` = serve the UI only, no API requests |

## Deploying

The app is meant to run around the clock, so that history keeps building up. It ships as a single Docker container.

### Container image

On every push to `main`, the [image workflow](.github/workflows/image.yml):
1. runs the tests;
2. builds a multi-arch (`amd64` + `arm64`) image;
3. pushes it to GitHub's container registry as `ghcr.io/<owner>/flipping`, tagged `latest` and `sha-<short commit>`.

To use it from a fork:
1. Push the repo to GitHub.
2. Set the package's visibility to Public (profile → Packages → `flipping` → Package settings), or log your Docker host into `ghcr.io`.

### Running the container

Any Docker host works. Keep `/data` on persistent storage:

```yaml
services:
  flipping:
    image: ghcr.io/<owner>/flipping:latest
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      FLIPPING_USER_AGENT: "flipping (self-hosted) - contact: <you>"
      FLIPPING_BACKFILL_STEP: 5m
    volumes:
      - ./data:/data
```

To update, pull the new image and recreate the container, for example with `docker compose pull && docker compose up -d`. To roll back, pin a `sha-…` tag instead of `latest`.

Platform guides:
- [Synology NAS (Container Manager)](docs/synology.md)

### Testing the image locally

`compose.yaml` at the repo root builds the image from source:

```bash
docker compose up --build
```

### Backups

The database is a single SQLite file in WAL mode. Copy `flipping.db` together with `flipping.db-wal` if that file exists, or back up the whole data directory.

## License

[MIT](LICENSE)
