# OSRS Flipping

A self-hosted Grand Exchange flip screener for Old School RuneScape. One process does two things:

- **Collector**: keeps a local SQLite copy of the [OSRS Wiki real-time prices API](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices).
  - Fetches instabuy/instasell prices every minute.
  - Fetches 5-minute volume and average prices every 5 minutes.
  - Refreshes item names and buy limits daily.
  - After a restart, backfills any missing history (up to 24h back), either as 5-minute windows or as gentler hourly windows (`FLIPPING_BACKFILL_STEP`).
- **Screener + dashboard**: ranks items by estimated profit per 4-hour buy-limit window and scores how *stable* each margin has been.

## How the screener scores items

| Column | Meaning |
|---|---|
| Buy / Sell | Latest instasell / instabuy price. A patient buy offer fills near Buy; a patient sell offer near Sell. |
| Tax | 2% of Sell, rounded down, capped at 5M. Free under 50gp, and bonds plus some tools are exempt ([tax.py](src/flipping/tax.py)). |
| Margin | Sell − Tax − Buy |
| 1h vol | min(units bought, units sold) over the last hour |
| Qty | min(buy limit, what your budget affords, 1h vol). One hour of real volume is a deliberately conservative guess at how much you can actually fill. |
| Profit / 4h | Margin × Qty |
| Stable | Share of price windows in the lookback (default 6h) where the item had a positive post-tax margin. Windows are 5 minutes, or 1 hour where history was backfilled hourly. |
| Med. margin | Median post-tax margin across those windows |

**How to read it:** a big margin with low Stable or a negative Med. margin is usually noise, such as a single odd trade. Prefer items with Stable above about 70%. Click a row to see its 24h price chart.

## Local development

You need [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run flipping          # http://127.0.0.1:8000, DB at ./data/flipping.db
uv run pytest
```

Locally, the backfill defaults to hourly windows (`FLIPPING_BACKFILL_STEP=1h`), so a fresh database gets 24h of history in about 40 requests instead of about 290:

- one request per hour of history from the API's hourly endpoint;
- plus up to about 20 five-minute windows. The hourly data runs about 2 hours behind, and these close that gap.

Restarting often during development costs almost nothing, because only periods with no data at all get fetched. The NAS deploy sets `5m` for full detail. Live collection is always every 5 minutes.

To work on the UI against real history without running a second collector, copy the NAS database down. Then set `FLIPPING_COLLECTOR=0` so your dev copy only serves the UI:

```bash
DOCKER_HOST=ssh://$NAS_SSH docker cp flipping:/data/flipping.db ./data/flipping.db
FLIPPING_COLLECTOR=0 uv run flipping
```

### Settings (env vars)

| Var | Default | |
|---|---|---|
| `FLIPPING_USER_AGENT` | `osrs-flipping-dashboard (personal, self-hosted)` | The wiki asks for a descriptive UA; adding a Discord handle is polite |
| `FLIPPING_DB` | `data/flipping.db` (`/data/flipping.db` in Docker) | |
| `FLIPPING_HOST` / `FLIPPING_PORT` | `127.0.0.1` / `8000` | |
| `FLIPPING_BACKFILL_HOURS` | `24` | How far back to fill gaps after downtime |
| `FLIPPING_BACKFILL_STEP` | `1h` locally, `5m` in `compose.yaml` | Granularity of gap filling: `1h` is about 12x fewer API requests, `5m` gives full-resolution history |
| `FLIPPING_RETENTION_DAYS` | `30` | 5m history kept, about 20 MB/day (about 600 MB at 30 days) |
| `FLIPPING_LATEST_INTERVAL` | `60` | Seconds between latest-price polls |
| `FLIPPING_COLLECTOR` | `1` | `0` = UI only |

## Deploying to the Synology

`scripts/deploy.sh` points your local Docker CLI at the Synology's Docker over SSH and runs `docker compose up -d --build`. The Synology builds the image itself, so:

- no image registry or GitHub repo is needed;
- it doesn't matter whether the model is ARM or x86;
- the database is on a named Docker volume (`flipping_flipping-data`), so it survives redeploys.

The container shows up in **Container Manager → Container** as `flipping`. It's deployed from the CLI, so it won't be listed under Container Manager's *Projects*.

### One-time setup

The steps assume DSM 7.2+ with **Container Manager** installed from Package Center. Your DSM user must be in the **administrators** group, since only admins can SSH in.

1. **Enable SSH:** Control Panel → Terminal & SNMP → *Enable SSH service*.
2. **Enable home folders** so `~/.ssh` exists: Control Panel → User & Group → Advanced → *Enable user home service*.
3. **Install your SSH key** from WSL:
   ```bash
   ssh-keygen -t ed25519
   ```
   ```bash
   ssh-copy-id you@synology.local
   ```
   DSM gives home folders permissions that sshd rejects, so key login usually fails until you fix them. SSH in with your password and run:
   ```bash
   chmod 755 ~ && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys
   ```
4. **Let your user run docker without sudo.** SSH in and run:
   ```bash
   sudo synogroup --add docker $USER
   ```
   ```bash
   sudo chown root:docker /var/run/docker.sock
   ```
   DSM resets the socket's owner on reboot and when Container Manager restarts. To make the fix permanent, add a task in Control Panel → Task Scheduler → Create → Triggered Task → User-defined script:
   - user: `root`
   - event: Boot-up
   - script: `sleep 60 && chown root:docker /var/run/docker.sock`
5. **Put `docker` on the SSH PATH.** Remote Docker runs `docker` over a non-interactive SSH session, but Synology installs it to `/usr/local/bin`, which isn't on that PATH:
   ```bash
   sudo ln -sf /usr/local/bin/docker /usr/bin/docker
   ```
   Big DSM updates can remove this symlink. If a deploy suddenly fails with `docker: command not found`, run it again.
6. **Check from WSL.** This must print the container list with no password prompt:
   ```bash
   ssh you@synology.local docker ps
   ```
7. **Install a Linux Docker CLI in WSL.** Your current `docker` is Docker Desktop's Windows binary, and its SSH uses your *Windows* SSH keys. You can either:
   - turn on Docker Desktop → Settings → Resources → WSL integration for this distro, or
   - install `docker-ce-cli` and `docker-compose-plugin` from Docker's apt repo. You only need the CLI.
8. `cp .deploy.env.example .deploy.env` and set `NAS_SSH`.

### Each deploy

```bash
./scripts/deploy.sh
```

Then open `http://synology.local:8000`. Port 8000 doesn't clash with DSM's 5000/5001. To tail the logs:

```bash
DOCKER_HOST=ssh://you@synology.local docker compose -p flipping logs -f
```

### Troubleshooting

- **`permission denied ... docker.sock`:** the socket owner was reset; rerun the `chown` from step 4, and check the boot-up task exists.
- **`docker: command not found`:** a DSM update removed the symlink; redo step 5.
- **Key login falls back to a password prompt:** fix the home folder permissions from step 3.
- **Back up the database:**
  ```bash
  DOCKER_HOST=ssh://you@synology.local docker cp flipping:/data/flipping.db ./backup.db
  ```

## Possible next step: push-to-deploy

If you later put this on GitHub, you can deploy by pushing instead of running a script:

1. A GitHub Action builds a multi-arch image and pushes it to GHCR.
2. [Watchtower](https://containrrr.dev/watchtower/) on the NAS pulls the new image automatically.

`compose.yaml` would then use `image: ghcr.io/<you>/flipping:latest` instead of `build: .`. Until you want that, the SSH script has fewer moving parts.
