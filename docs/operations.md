# Operations guide

How to run, expose and monitor this bot. Written for whoever operates the instance day to day.

---

## 1. The three start/stop modes

| Mode | What you double-click | What you get | When to use it |
|---|---|---|---|
| **Local** | `%LOCALAPPDATA%\n8n\n8n-serve.bat` | editor + site widget on `http://127.0.0.1:5678` only | building, testing |
| **Public** | `D:\Tools\n8n\start-public.bat` | the same, plus a public HTTPS URL through a Cloudflare quick tunnel | Telegram channel, demo to a client, testing from a phone |
| **Stop** | `D:\Tools\n8n\stop-public.bat` | stops n8n **and** the tunnel | end of session |

`start-public.bat` does three things: starts `cloudflared`, waits for the assigned
`https://<random>.trycloudflare.com` address, then starts n8n **with `WEBHOOK_URL` set to that
address**. That environment variable is what makes n8n tell Telegram (and any other webhook
provider) the right public callback URL.

**Why it matters:** without `WEBHOOK_URL`, n8n writes `http://127.0.0.1:5678/...` into Telegram's
webhook registration. Telegram then refuses to deliver and answers `Bad Request: bad webhook: An
HTTPS URL must be provided for webhook`. That failure is invisible from the browser — it only shows
up in Telegram's API or through the error-alert workflow.

### Recording a demo (one command)

```
E:\Hermes\Projects\rag-support-bot\start-demo.bat
```

Starts n8n in public mode if it is not running (waiting until the editor really answers), reports
whether the tunnel is live, clears the QA rows from the Supabase `tickets` table so the escalation
shot shows exactly one row, opens `site/index.html`, and prints the 60-second shot list.

| Switch | Effect |
|---|---|
| `-KeepTickets` | leave the tickets table alone |
| `-NoBrowser` | do not open the page |

Secrets live outside the repo in `D:\Tools\n8n\demo-secrets.json`
(`{"supabaseUrl": "...", "serviceKey": "..."}`). Two practical notes learned from running it:
PowerShell 5.1's `Invoke-RestMethod` gets a 401 for the new-style `sb_secret_...` Supabase keys, so
the cleanup shells out to `curl.exe` and feeds it the key through a throwaway config file (never
argv); and the quick tunnel can be up but refused by the edge (`Unauthorized: Tunnel not found`) —
the watchdog's repair branch fixes it, and until it does, film that one shot from the alert already
sitting in the Telegram bot chat.

---

## 2. Error alerting (n8n's native pattern)

`workflow/SupportBotErrorAlerts.json` contains:

```
Error Trigger  →  Format Alert (Code)  →  Notify Telegram (error)
```

The `Error Trigger` node is n8n's built-in hook: whenever a workflow that has this alert workflow
attached fails — **including a trigger that fails to activate** — it fires and sends one Telegram
message:

```
Workflow: Support Bot — Telegram channel  [SupportBotTelegram01]
Node: Telegram Trigger
Error: Bad Request: bad webhook: An HTTPS URL must be provided for webhook
Exec id: activation   mode: internal
Open: http://127.0.0.1:5678/workflow/SupportBotTelegram01
```

### Wiring it up (once per workflow)

n8n → open the workflow → **⋯ (top right) → Settings → Error Workflow → `Support Bot — Error
Alerts`** → Save. Repeat for every workflow that must be monitored. Workflow ids differ per
instance, so this is a manual step after importing the JSON files — it cannot be shipped inside
the JSON.

### Testing it on purpose

`ZZ error-alert test` is a two-node workflow (webhook → HTTP request to a dead port). Open
`http://127.0.0.1:5678/webhook/zz-error-test` in a browser and you should receive an alert within
seconds. Keep it inactive except when testing.

---

## 3. Channels

| Channel | Entry point | State |
|---|---|---|
| Website widget | `site/index.html` → chat webhook | production-ready |
| Telegram | `@HarborSupport_bot` → Telegram trigger | works, **requires the public mode** (section 1) |
| Email | Gmail API (`+support` alias) → threaded reply | production-ready (verified end-to-end 2026-09-19) |

All channels share the same knowledge base (Supabase `documents`), the same Agent and the same
escalation branch (ticket → CRM push → Telegram alert → reply), so a fix in one place benefits
every channel.

### 3.1 Email channel (Gmail API) — setup and behaviour

One-time setup, once per Google account (client-side, because it is the client's own mailbox):

1. Google Cloud → new project → enable **Gmail API** → OAuth client type **Web application**.
2. Authorized redirect URI, exactly: `http://localhost:5678/rest/oauth2-credential/callback`
   (the n8n OAuth callback is derived from `N8N_EDITOR_BASE_URL`, **not** from the tunnel URL —
   a tunnel hostname changes on every restart and would break the redirect).
3. While the consent screen is in **Testing**, the mailbox owner must be listed under
   *Audience → Test users*; otherwise Google answers `403 access_denied` even for the owner.
4. n8n → Credentials → **Gmail OAuth2 API** → paste Client ID + Secret → *Sign in with Google*.

Behaviour worth knowing (both are intentional, not bugs):

- The trigger polls every minute and only handles mail **newer than the last check**. Re-sending an
  old mail you already sent will not be answered twice — that is the anti-duplicate mechanism.
- The trigger only looks at **unread** mail and the workflow marks handled mail as read afterwards,
  so opening a customer mail by hand *before* the poll can skip it.

---

## 4. Known limitations

1. **Email channel — IMAP path is retired.** The old IMAP trigger failed to activate intermittently
   on Gmail (`Connection ended unexpectedly`, widely reported upstream). It is replaced by the
   Gmail-API channel (section 3.1), which is verified end-to-end. The OAuth app itself lives in the
   **client's** Google Cloud project, so each customer needs the four setup steps once; treat that
   as part of onboarding, not as a defect.
2. **Quick-tunnel URLs are not permanent.** `*.trycloudflare.com` names change on every start, so the
   Telegram webhook registration changes with them. `start-public.bat` handles this automatically,
   but for a permanently hosted instance use a real host (VPS + a named Cloudflare tunnel or the
   client's own domain) — that is the Premium deployment tier.
3. **Exposing n8n exposes the chat endpoint.** While the tunnel is up, anyone who knows the URL can
   send messages and consume the configured LLM quota. Stop the tunnel when you are done.
4. **No ticket dashboard.** Tickets live in the Supabase `tickets` table; there is no UI yet.

---

## 5. Availability (crash recovery + out-of-band alerts)

Two mechanisms watch the instance while Windows is on. Neither starts anything at Windows boot — the
service only exists while the machine is running, and that is deliberate.

| Mechanism | What it does |
|---|---|
| `D:\Tools\n8n\watchdog-n8n.ps1` (scheduled task **"n8n watchdog"**, every 5 min) | if the tunnel died or stopped answering, starts a fresh tunnel and restarts n8n with the new public URL in `WEBHOOK_URL`; if n8n itself is down, starts it again (`autoStart: true`) |
| the same script's alerting (`notify.enabled`) | sends the alert **itself** to the Telegram Bot API — n8n cannot report its own death. Repeated alerts are rate-limited (`remindMinutes`, 60) |

Credentials for the alert live in `D:\Tools\n8n\watchdog-secrets.json` (restricted file, never inside
the workflow and never in the log); the shareable config keeps only the file path. Log:
`D:\Tools\n8n\watchdog.log` — one line per scan.

Verified by inducing both failures on purpose (2026-09-20):

| Failure | Result |
|---|---|
| n8n + tunnel killed | `repaired: service started again, tunnel <new url>` + alert `message_id 35`; local and public HTTP 200 afterwards |
| tunnel connected but unreachable at the edge | `repaired: tunnel <new url>, service restarted` + alert `message_id 36` |

The generic version of this tool is a public repo: **github.com/uhygyuf/service-tunnel-watchdog**
(21 sandbox tests, including "alert is delivered", "token never reaches the log", "recovery stays
opt-in").

---

## 6. Console-window hygiene (automatic)

Restarting n8n repeatedly used to leave a growing pile of console windows: `n8n-serve.bat` ends
with `pause`, so when the n8n process exits the window sits waiting for a keypress forever, and
nothing closes it.

Two automatic mechanisms now prevent that:

| Mechanism | What it does |
|---|---|
| `D:\Tools\n8n\cleanup-zombies.ps1` | kills launcher windows that no longer keep n8n or the tunnel alive |
| Scheduled task **"n8n zombie cleanup"** | runs that script every 15 minutes |
| both launchers (`n8n-serve.bat`, `start-public.bat`) | call the script once before starting, so restarts never accumulate |

Manual run: `D:\Tools\n8n\cleanup-zombies.bat` (log: `D:\Tools\n8n\cleanup.log`).

**Safety nets** (a cleanup script that force-kills processes must never take down the service):

1. the process listening on port 5678 **and every ancestor above it** form a keep-set that is never touched;
2. a window is only killed when nothing in its process tree is `node.exe` or `cloudflared.exe`.

Verified: a fabricated zombie launcher was removed while the live instance kept answering HTTP 200.

**Maintainer notes** (both cost real debugging time):

- Never name a PowerShell parameter `$pid` — it collides with PowerShell's automatic variable and the
  function silently receives the wrong process id (the first version of this script killed the live
  launcher chain because of exactly that).
- In a window started hidden/minimised, `timeout /t N` aborts immediately (stdin is redirected) — use
  a `ping`-based wait instead when you need to keep such a process alive for testing.
