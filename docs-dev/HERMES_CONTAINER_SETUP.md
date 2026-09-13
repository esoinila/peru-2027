# Instructions for Grok: make the Hermes docker sandbox survive rebuilds

Context: Hermes (the agent working in `D:\repo12\VennsRabbitHole` and now
`D:\repo12\TravelGuide`) runs its terminal inside a Docker container
(`terminal.backend: docker`, Debian 13 "trixie", Python 3.11). The container's
root filesystem is an ephemeral overlay — anything installed with `apt`/`pip`
is lost whenever the container is recreated (which happened when the
`TravelGuide` mount was added). Only the bind mounts persist:

    D:\repo12\VennsRabbitHole  -> /workspace                 (rw)
    D:\repo12\TravelGuide      -> /workspace/TravelGuide     (rw)
    <hermes docker home>       -> /root                      (rw)
    (sandboxes\docker\default\home on the Windows side)

Today the container came up with NO `git` binary, so the VennsRabbitHole
2-hour auto-backup cron (`bash scripts/auto_backup.sh`) was silently failing,
and the credentials Grok wrote had Windows CRLF line endings, which made git's
`credential.helper=store` fail with "could not read Username for
'https://github.com'". Both are fixed in the live container, but they will
regress on the next rebuild unless the following is baked in.

## 1. Bake tools into the sandbox image (required)

Wherever Hermes's docker sandbox image is defined (Dockerfile or
`terminal.docker.*` in `C:\Users\ernos\AppData\Local\hermes\config.yaml`),
make sure these are installed at image build time, not at runtime:

    apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates ffmpeg
    pip install --no-cache-dir yt-dlp pytest

- `git`     — needed by scripts/auto_backup.sh and all repo work
- `ffmpeg`  — needed by scripts/ingest_youtube.py for keyframes
- `yt-dlp`  — YouTube ingest
- `pytest`  — `pytest` is the verify step for both repos

If the Hermes config only allows an image name (no Dockerfile), build a
derived image, e.g.

    FROM <current-hermes-sandbox-image>
    RUN apt-get update && apt-get install -y --no-install-recommends \
            git ca-certificates ffmpeg \
        && rm -rf /var/lib/apt/lists/* \
        && pip install --no-cache-dir yt-dlp pytest

and point `terminal.docker.image` at it.

## 2. Git identity/credentials in the persistent home (already done — keep it)

These files live in the mounted home
(`sandboxes\docker\default\home\` on Windows = `/root` in the container) so
they survive rebuilds. Rules when (re)writing them:

- Write with LF line endings only. CRLF breaks `credential.helper=store`.
  From PowerShell use `-NoNewline` + "`n", or write via WSL/bash, never
  Notepad/`Set-Content` defaults.
- `~/.git-credentials` : one line, `https://<user>:<token>@github.com`
  (or `https://<token>@github.com`), chmod 600 if possible.
- `~/.gitconfig` should contain exactly:

        [user]
            name  = esoinila
            email = esoinila@users.noreply.github.com
        [credential]
            helper = store
        [core]
            fileMode = false
        [safe]
            directory = /workspace
            directory = /workspace/TravelGuide

  Do NOT append `safe.directory` repeatedly — the file had ~110 duplicate
  `directory = /workspace` lines from `git config --global --add` running on
  every backup. Set it once; the backup script should use
  `git config --global --get-all safe.directory | grep -qx /workspace ||
  git config --global --add safe.directory /workspace`.

- Token: currently the `gho_` OAuth token from `gh auth`. Preferred: a
  fine-grained PAT scoped to `esoinila/VennsRabbitHole` and
  `esoinila/peru-2027` (contents: read/write) with an expiry, swapped into
  `~/.git-credentials`. The same token can go in
  `C:\Users\ernos\AppData\Local\hermes\.env` as `GITHUB_TOKEN=` for Hermes's
  own `gh`/GitHub tools (that one needs a Hermes restart to take effect;
  the in-container git does not).

## 3. Verify after any rebuild

Run inside the container (Hermes can do it):

    which git ffmpeg && python -c "import yt_dlp" && pytest --version
    cd /workspace            && git ls-remote --heads origin   # VennsRabbitHole
    cd /workspace/TravelGuide && git ls-remote --heads origin  # peru-2027
    bash /workspace/scripts/auto_backup.sh                     # must print nothing or one OK line

If `ls-remote` says "could not read Username", the credentials file has CRLF
or is missing — see §2.

## 4. Nice-to-have

- Add a TravelGuide equivalent of `scripts/auto_backup.sh` (same script with
  `REPO=/workspace/TravelGuide`) and a second Hermes cron entry, so peru-2027
  gets pushed automatically too.
- Keep the mount list in `config.yaml` as the source of truth; if another
  repo is added, remember it also needs a `safe.directory` line.
