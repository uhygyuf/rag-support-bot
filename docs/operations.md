# Operations guide

How to run, expose and monitor this bot. Written for whoever operates the instance day to day.

---

## 1. The three start/stop modes

| Mode | What you double-click | What you get | When to use it |
|---|---|---|---|
| **Local** | `D:\Tools\n8n\n8n-serve.bat` | editor + site widget on `http://127.0.0.1:5678` only | building, testing |
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
| Email | IMAP `INBOX` → `+support` alias → SMTP reply | **not production-ready** — see limitations |

All channels share the same knowledge base (Supabase `documents`), the same Agent and the same
escalation branch (ticket → CRM push → Telegram alert → reply), so a fix in one place benefits
every channel.

---

## 4. Known limitations

1. **Email channel — trigger reliability.** n8n's IMAP trigger for Gmail fails to activate
   intermittently (`Connection ended unexpectedly`, widely reported upstream) and n8n deactivates
   the workflow when that happens. The mailbox credentials themselves are fine (a plain IMAP client
   logs in and reads the inbox). Production options: switch to the Gmail node with OAuth2, or use a
   provider with stable IDLE support. Do not sell this channel until it is resolved.
2. **Quick-tunnel URLs are not permanent.** `*.trycloudflare.com` names change on every start, so the
   Telegram webhook registration changes with them. `start-public.bat` handles this automatically,
   but for a permanently hosted instance use a real host (VPS + a named Cloudflare tunnel or the
   client's own domain) — that is the Premium deployment tier.
3. **Exposing n8n exposes the chat endpoint.** While the tunnel is up, anyone who knows the URL can
   send messages and consume the configured LLM quota. Stop the tunnel when you are done.
4. **No ticket dashboard.** Tickets live in the Supabase `tickets` table; there is no UI yet.

---

## 5. Console-window hygiene (automatic)

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
