# Talking to Hermes from the phone (Signal / WhatsApp)

Goal: message the Hermes agent that lives on the Windows box (D:\repo12, profile
`default`) from a phone, e.g. from Peru, and get replies + cron notifications
(auto-backup results, trip reminders) delivered there.

Source: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/
(Signal page + WhatsApp page, fetched 2026-09-13). Anything below that is not on
those pages is marked *[opinion]*.

## 0. Which channel

| | Signal | WhatsApp (Baileys bridge) | Anthropic / Claude app |
|---|---|---|---|
| Official Hermes support | yes | yes, but "unofficial API, ban risk" | no — it talks to Anthropic's servers, not to your Hermes |
| Needs a second phone number | no (links as a secondary device, like Signal Desktop) | recommended (bot mode); self-chat mode works with your own number | — |
| Extra runtime on the PC | signal-cli (Java 17+) | Node.js 18+ (bridge is auto-installed) | — |
| Media | images, files, audio in; images/voice/video/docs out; 100 MB | images, files; voice in (transcribed), TTS out | — |
| Hermes cron `deliver=` target | `signal` | `whatsapp` | — |

*[opinion]* Start with **Signal**: no second SIM, no ban risk, official
adapter, and the Hermes docs say it is the most privacy-focused. Add WhatsApp
later only if you want it as a second channel.

Both run inside the **Hermes gateway** — one background process on the Windows
host (NOT inside the docker sandbox) that owns all messaging platforms and also
runs cron jobs. The gateway must stay up while you are away, so the PC must stay
on and not sleep.

---

## 1. Signal (recommended)

### 1.1 On the Windows host — install signal-cli

signal-cli is a Java program. The Hermes docs give brew/Linux commands; on
Windows *[opinion]*:

    winget install EclipseAdoptium.Temurin.17.JRE      # Java 17+
    # download signal-cli-<ver>.tar.gz (or the Windows zip if present) from
    #   https://github.com/AsamK/signal-cli/releases/latest
    # extract to e.g. C:\tools\signal-cli\ and put C:\tools\signal-cli\bin on PATH
    signal-cli --version

If native Windows is painful, run signal-cli inside WSL2 (Ubuntu) instead — the
docs' Linux one-liner works there — and point Hermes at `http://127.0.0.1:8080`
(WSL2 localhost is forwarded to Windows).

### 1.2 Link the phone (Signal → Settings → Linked Devices → Link New Device)

    signal-cli link -n "HermesAgent"

It prints a QR code / `sgnl://linkdevice?...` URI. Scan it with the phone.
Your phone stays the primary device; the PC becomes a linked device (like
Signal Desktop).

### 1.3 Run the daemon (must stay running)

    signal-cli --account +358XXXXXXXXX daemon --http 127.0.0.1:8080
    # verify:
    curl http://127.0.0.1:8080/api/v1/check      # -> {"versions":{"signal-cli":...}}

Keep it alive: Task Scheduler "at logon" task, NSSM service, or a WSL
systemd unit. *[opinion]* NSSM is the simplest on Windows.

### 1.4 Configure Hermes

Wizard (preferred):

    hermes gateway setup        # pick Signal; it tests the daemon URL and asks for the account number + allowed users

Or manual, in `C:\Users\ernos\AppData\Local\hermes\.env` (docs say `~/.hermes/.env`;
on this machine the Hermes home is the AppData\Local\hermes folder):

    SIGNAL_HTTP_URL=http://127.0.0.1:8080
    SIGNAL_ACCOUNT=+358XXXXXXXXX
    SIGNAL_ALLOWED_USERS=+358XXXXXXXXX          # only your own number may talk to the agent
    SIGNAL_HOME_CHANNEL=+358XXXXXXXXX           # default delivery target for cron jobs
    # SIGNAL_GROUP_ALLOWED_USERS=<groupId>      # leave unset: groups ignored

Access rules (from docs): allowlist set → only those numbers; no allowlist →
unknown senders get a pairing code you approve with
`hermes pairing approve signal CODE`; `SIGNAL_ALLOW_ALL_USERS=true` → anyone
(don't).

### 1.5 Start the gateway

    hermes gateway                 # foreground, for the first test
    hermes gateway install         # then install as a user service
    hermes gateway status

Send yourself a Signal message from the phone (a DM to your own number = the
linked device receives it) — Hermes answers. Chat commands inside Signal:
`/new`, `/model`, `/status`, `/retry`, `/undo`, `/whoami`.

### 1.6 Make cron jobs reach the phone

Existing cron jobs in this profile were created from the CLI with
`deliver=origin`, which has no live channel. Edit them (or recreate) with
`deliver=signal` (or `all`). The `SIGNAL_HOME_CHANNEL` above is where they
land. Jobs to retarget: `VennsRabbitHole auto-backup`, `TravelGuide / peru-2027
auto-backup`.

---

## 2. WhatsApp (optional second channel)

Docs: Baileys bridge = emulated WhatsApp Web session; **no Meta business
account**, but "small risk of account restrictions". Their mitigation list:
dedicated number, conversational use only, no unsolicited outbound.

Prereq: Node.js 18+ on the Windows host (`winget install OpenJS.NodeJS.LTS`).

    hermes whatsapp            # wizard: choose mode (bot | self-chat), installs bridge, shows QR
    # phone: WhatsApp → Settings → Linked Devices → Link a Device → scan

Modes: **self-chat** = your own WhatsApp, you message yourself (quick, single
user). **bot** = separate number (needs a prepaid SIM or VoIP number that
WhatsApp accepts; Google Voice is US-only).

`.env`:

    WHATSAPP_ENABLED=true
    WHATSAPP_MODE=self-chat                   # or bot
    WHATSAPP_ALLOWED_USERS=358XXXXXXXXX       # country code, no +

config.yaml (recommended for a private number):

    whatsapp:
      unauthorized_dm_behavior: ignore

Session persists under `<hermes home>\platforms\whatsapp\session` — never commit
it; if it breaks after a WhatsApp update, run `hermes whatsapp` again and
rescan.

---

## 3. Things to be careful about

- The gateway is a **host** process. Do not try to run it inside the docker
  sandbox; the sandbox has no Java/Node and is recreated on config changes.
- Terminal width ≥ 60 cols for the WhatsApp QR; Signal prints a URI you can
  paste if the QR is garbled.
- Phone numbers: Signal wants E.164 with `+`; WhatsApp wants digits without `+`.
- Keep the PC awake (power plan: never sleep) or the gateway and signal-cli die
  with it. *[opinion]* Also set the router/DHCP so the PC keeps LAN; no inbound
  ports are needed for either adapter (both are outbound connections).
- Do not put the `.env` secrets or the WhatsApp session directory in any repo.
- Nothing here requires an API-key LLM provider; the gateway uses whatever model
  provider the profile already uses.

---

## 4. Paste-to-Grok instruction block

> On the Windows host (not in docker): install Java 17 + signal-cli, run
> `signal-cli link -n HermesAgent` and let me scan the QR with my phone; then run
> `signal-cli --account +358… daemon --http 127.0.0.1:8080` as a persistent
> service (NSSM or Task Scheduler at logon) and verify
> `curl http://127.0.0.1:8080/api/v1/check`. Then `hermes gateway setup` →
> Signal, HTTP URL http://127.0.0.1:8080, account +358…, allowed users = my
> number only, home channel = my number. `hermes gateway install` and confirm
> `hermes gateway status`. Retarget the two auto-backup cron jobs to
> `deliver=signal`. Send me a test message. Do not enable groups or
> allow-all. Skip WhatsApp for now. Docs:
> https://hermes-agent.nousresearch.com/docs/user-guide/messaging/signal
