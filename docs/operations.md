# Operations guide

How to run, expose and monitor this bot. Written for whoever operates the instance day to day.

---

## 1. The two services, and the switches that drive them

The demo runs as two Windows services. Both start with Windows and are restarted by Windows if they
stop, so there is no watchdog script, no scheduled repair task and no address to refresh.

| Service | What it is | Where it is defined |
|---|---|---|
| **n8n support bot** | the workflow server on `http://127.0.0.1:5678` | `D:\Tools\n8n\service\n8n-service.xml` (WinSW wrapper around `node ...\n8n start`) |
| **ngrok** | the tunnel that publishes that port under the permanent hostname `flyable-rekindle-disobey.ngrok-free.dev` | `D:\Tools\ngrok\ngrok.yml` |

| What you double-click | What you get | When to use it |
|---|---|---|
| `switches\bot-on.bat` | both services set to Automatic and started; waits until n8n really answers, then verifies the public address from the outside | before a demo |
| `switches\bot-off.bat` | both services stopped **and** set to Disabled, so a reboot does not bring the demo back | end of session |
| `switches\bot-status.bat` | a report; changes nothing and needs no administrator rights | any time |

`WEBHOOK_URL` belongs to the service definition and points at the permanent hostname. That variable is
what makes n8n tell Telegram (and any other webhook provider) the right public callback URL. Without
it n8n registers `http://127.0.0.1:5678/...` and Telegram refuses with
`Bad Request: bad webhook: An HTTPS URL must be provided for webhook`. That failure is invisible from
the browser — it only shows up in Telegram's API or through the error-alert workflow.

A local-only run is still possible: stop the services (`bot-off.bat`), then start
`D:\Tools\n8n\n8n-serve.bat` by hand. It runs n8n on `127.0.0.1:5678` without the tunnel, which is
what the build and test loop uses.

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
| Website (hosted copy) | **https://uhygyuf.github.io/rag-support-bot/** → backend from `site/backend.json` | live while the tunnel is up (section 3.2) |
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

### 3.2 Hosting the demo page (GitHub Pages)

`site/` is published to **https://uhygyuf.github.io/rag-support-bot/** by
`.github/workflows/pages.yml` on every push that touches `site/` (manual run: *Actions → Deploy demo
site to GitHub Pages → Run workflow*).

The page no longer hardcodes a backend. `site/widget.js` resolves its target in this order:

1. `data-webhook` on the script tag — explicit, wins over everything;
2. `site/backend.json` — the live tunnel address sitting next to the page (what the hosted copy uses);
3. `data-local-webhook` — only for a page opened straight from disk (`file://`).

`site/backend.json` names the backend once. The hostname in it is permanent — it is the account's
tunnel name, configured in `D:\Tools\ngrok\ngrok.yml` — so the file only changes if the demo moves to
another machine or another tunnel. Nothing republishes it, and the widget no longer needs to re-read
the address after a restart, because nothing changes it any more. While the machine is off the page
still loads; the widget answers with its offline line instead of hanging.

### 3.3 Why there is no watchdog any more

The first deployment used a free Cloudflare quick tunnel. Those hostnames are random and change on
every start, so the project grew a watchdog: a scheduled task that noticed a dead tunnel, started a
new one, restarted n8n with the new address, and republished the address to the hosted page. It
worked, and it was the wrong shape — application code was compensating for a moving address.

What actually went wrong (2026-09-23): the local proxy's TUN mode left a stale DNS mapping that broke
`cloudflared`'s handshake with the Cloudflare edge. Every tunnel it started was announced and then
refused by the edge (HTTP 530), the watchdog correctly refused to publish an address nobody could
reach, and then sat out its own anti-flapping cooldown while the public page pointed at nothing. A
reboot did not help, because the proxy starts with Windows.

What replaced it, in the order the problems disappear:

1. **A permanent hostname.** The tunnel is the ngrok agent, and the hostname lives in its config file,
   so it is identical after every start, crash and reboot.
2. **The operating system supervises the processes.** n8n runs under a WinSW service wrapper, ngrok
   under its own service installer. Both are Automatic, both have restart-on-failure, and both are
   visible in `services.msc`.
3. **Therefore nothing has to be republished.** `site/backend.json` was written once.

The retired pieces (watchdog script, hook, republish script, quick tunnel) are gone from this
repository. The generic version of the watchdog lives on as a public repository,
**github.com/uhygyuf/service-tunnel-watchdog**, which is the honest home for "keep a tunnel and a
service alive and republish an address that changes".

### 3.4 Knowledge base: how a document gets in

```powershell
python tools/ingest.py --dry-run                 # chunk plan, nothing is sent
python tools/ingest.py --replace                 # every *.md in knowledge/
python tools/ingest.py --replace knowledge/faq.md
```

The script splits each file into blocks of at most 900 characters, embeds them with the same model the
workflow uses (`BAAI/bge-m3`, SiliconFlow, 1024 dimensions) and writes rows into Supabase `documents`
with `metadata = {source: "<file>.md", loc: {lines: {from, to}}, blobType}`. Answers are grounded in
those rows, and the `source` value is what the agent cites, so a correct label is what makes a citation
mean anything.

Credentials come from a local JSON file (`D:\Tools\n8n\demo-secrets.json`, `--secrets` to point
elsewhere) with four fields: `supabaseUrl`, `serviceKey`, `siliconflowUrl`, `siliconflowKey`. Keep it
outside the repository. Two header traps are handled inside the script: Supabase wants the service key
in **both** the `apikey` and the `Authorization` header (a bearer-only request is answered 401 "No API
key found in request"), and the embedding call needs its own headers: reusing the Supabase header
builder (which sends the service key as the bearer token) against the embedding endpoint is answered
`401` with no explanation, which is exactly what a careless refactor produces.

**The workflow's upload form cannot label chunks.** n8n 2.38.7's binary data loader hardcodes
`metadata.source = "blob"` for binary input, and version 1.1 of that node has no metadata parameter
(inspected in `node_modules/@n8n/n8n-nodes-langchain/.../DocumentDefaultDataLoader.node.js`; the
`metadata` field exists only in the sub-node schema, not in the node's own parameters). Evidence: three
files uploaded through the form on 2026-09-22 produced executions 195/196/197 where the binary carried
`fileName="policies.md"` and the loader still stored `"source": "blob"`. Uploads through the form are
therefore fine for experiments and wrong for anything a customer reads; use the script, or replace the
loader with a node that can set metadata.

---

## 4. Known limitations

1. **Email channel — IMAP path is retired.** The old IMAP trigger failed to activate intermittently
   on Gmail (`Connection ended unexpectedly`, widely reported upstream). It is replaced by the
   Gmail-API channel (section 3.1), which is verified end-to-end. The OAuth app itself lives in the
   **client's** Google Cloud project, so each customer needs the four setup steps once; treat that
   as part of onboarding, not as a defect.
2. **Availability is bounded by the machine being awake.** n8n and the tunnel are Windows services on
   one laptop, so they restart themselves after a crash or a reboot, but nothing answers while that
   machine is off or asleep. A permanently hosted instance needs a real host (a small VPS running
   n8n's own Docker image, or n8n Cloud) — that is the Premium deployment tier and is not part of
   this repository.
3. **Exposing n8n exposes the chat endpoint.** While the tunnel is up, anyone who knows the URL can
   send messages and consume the configured LLM quota. Stop the tunnel when you are done.
4. **No ticket dashboard.** Tickets live in the Supabase `tickets` table; there is no UI yet.
5. **The workflow's upload form stores an unusable source label** (`metadata.source = "blob"`, see
   section 3.4). Documents that customers will be answered from must be loaded with
   `tools/ingest.py`, otherwise the answer cannot name the file it came from.

---

## 5. Availability (what the operating system does now)

| Mechanism | What it does |
|---|---|
| Windows service **n8n support bot** (WinSW wrapper, Automatic) | starts n8n at boot; if the process fails, WinSW restarts it after 10 s, then 30 s, then 60 s, and resets the failure count after an hour without failures |
| Windows service **ngrok** (Automatic; its installer also set the Windows recovery options) | starts the tunnel at boot with the permanent hostname and restarts it if it stops |
| scheduled task **"n8n zombie cleanup"** (every 15 min) | legacy janitor for the old `n8n-serve.bat` launcher path: it only looks at console windows whose title mentions n8n, so it stays quiet while the services run. Kept because the manual local run still uses that launcher |
| the workflow's own error-alert trigger | posts workflow failures to Telegram (n8n's native error workflow pattern) |

The old out-of-band alerting went away with the watchdog. A separate script used to report n8n's death
through the Telegram Bot API, because a dead n8n cannot report anything. With the service model there
is no script to fail: a dead n8n is a stopped service, visible in `services.msc`, in `bot-status.bat`
and in `D:\Tools\n8n\logs\n8n-service.*.log`.

Verified on 2026-09-23, on the machine that runs it:

| Check | Evidence |
|---|---|
| n8n runs as a service and loads the same database | installed from `n8n-service.xml`; `service state: Running / Automatic`; a question sent through the public address afterwards answered from `products.md`, which only exists in the existing workflow database |
| the hostname is stable | two consecutive agent starts announced the same `https://flyable-rekindle-disobey.ngrok-free.dev` |
| a visitor's request works through the permanent address | `POST https://flyable-rekindle-disobey.ngrok-free.dev/webhook/b45b0144-.../chat` returned `Yes! We ship to Canada — … [faq.md]`, with `Access-Control-Allow-Origin: https://uhygyuf.github.io` |
| the page and the tunnel agree | `site/backend.json` holds the same hostname; `bot-status.bat` reports `published page points at the live tunnel` |
| the switches really stop it | `bot-off.bat` set both services to `Disabled`, and port 5678 stopped answering; `bot-on.bat` brought them back |

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
