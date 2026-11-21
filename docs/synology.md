# Deploying on a Synology NAS

This guide runs the app as a **Container Manager** project. Updates are a few clicks in DSM, and you don't need SSH or root.

- Requires DSM 7.2+ with Container Manager installed from Package Center.
- The image is multi-arch, so it runs on both x86 and ARM models.

How it fits together:
1. Pushing to `main` builds `ghcr.io/<owner>/flipping:latest` (see the [README](../README.md#container-image)).
2. Container Manager pulls that image and runs it.
3. The database lives in `data/` inside the project folder, so it survives updates and Hyper Backup can cover it.

## One-time setup

1. **Publish the image.** Push the repo to GitHub, and wait for the **image** workflow under the Actions tab to go green:
   ```bash
   git remote add origin git@github.com:<you>/flipping.git
   ```
   ```bash
   git push -u origin main
   ```
2. **Make the image pullable.** On GitHub, go to your profile → Packages → `flipping` → Package settings → Change visibility → **Public**. The source repo can stay private.

   If you'd rather keep the image private, add GHCR under Container Manager → Registry → Settings → Add instead:
   - URL: `https://ghcr.io`
   - username: your GitHub username
   - password: a classic personal access token with `read:packages`
3. **Create the folder.** In File Station, create `docker/flipping` on the share that holds your `docker` folder, then create a `data` subfolder inside it.
4. **Create the project.** Container Manager → Project → Create:
   - Name: `flipping`
   - Path: the `docker/flipping` folder
   - Source: *Create docker-compose.yml*, then paste [deploy/synology/compose.yaml](../deploy/synology/compose.yaml). Set the `image:` line to your own GitHub user or org, and add your `FLIPPING_USER_AGENT`.
   - Skip the Web Station portal step, then click Done. Container Manager pulls the image and starts the container.
5. **Open the dashboard** at `http://synology.local:8000`, or your NAS's own hostname or IP. Port 8000 doesn't clash with DSM's 5000/5001.

## Updating

1. Push your changes to `main` and wait for the image workflow to finish, about 3–5 minutes.
2. In Container Manager → Project → `flipping`, choose **Action → Stop**, then **Action → Build**. Build pulls the new `:latest` image and recreates the container. Then choose **Action → Start** if it didn't start by itself.

Container Manager can also show **Update available** on the Image page, but its check can take up to 12 hours, so Project → Build is the reliable route.

Logs are under Container Manager → Container → `flipping` → Log.

**Changing settings:** edit the YAML under Project → `flipping` → YAML Configurations → Edit, then rebuild. The project keeps its own copy of the compose file, so changes to `deploy/synology/compose.yaml` in the repo don't apply until you paste them in.

## Rolling back

Each build is also tagged `sha-<short commit>`, and the repo's package page lists them. To roll back:

1. In the project's YAML, change `:latest` to a known-good tag such as `:sha-1a2b3c4`.
2. Rebuild.

Remember to switch back to `:latest` afterwards.

## Backups and local copies

`docker/flipping/data/` holds the whole database. Back it up with Hyper Backup.

For local development against real history, copy the database down with File Station or over SMB. Copy `flipping.db` together with `flipping.db-wal` if that file exists; the newest data may still be sitting in the `-wal` file. Put them in your local `data/` folder, then run:

```bash
FLIPPING_COLLECTOR=0 uv run flipping
```
