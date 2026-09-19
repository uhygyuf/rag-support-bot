# Release-gate QA report — 2026-09-19 (after the email channel went live)

Scope: the whole shipped product (3 channels, escalation chain, alerting, watchdogs), tested against
the running local instance and the live public tunnel. Evidence is execution data, HTTP responses and
API responses; nothing here is inferred or claimed without a run behind it.

## A. Executive summary

**Conditional release.** All automated and live functional tests pass (127/127 static, 10/10 live E2E),
but the round exposed one **P0 operational gap**: the service had died silently and nothing noticed.
Functionally the product is releasable; for anything client-facing the availability gap must be closed
first (one config flag on the existing watchdog — see D1).

## B. Environment, commands, scope

| Item | Value |
|---|---|
| n8n | 2.38.7, npm-local `D:\Tools\n8n`, SQLite `C:\Users\leo wang\.n8n` |
| Public entry | Cloudflare quick tunnel (name changes per start: `https://jail-identifying-letting-routine.trycloudflare.com` at test time) |
| Static suite | `python tests/qa_suite.py` → **127 checks, 0 failed** |
| Live E2E | `python tests/e2e_live.py --tunnel <url>` → **10/10 passed** |
| Data stores | Supabase `documents` (vector 1024) + `tickets`; Gmail mailbox for the email channel |
| Out of scope | VPS/Docker deployment (not built), Slack channel (not built) |

Critical journeys covered: web chat answer with citation, multi-turn memory, escalation reply,
prompt-injection refusal, malformed/empty/oversized input, concurrent visitors, public reachability,
email answer with citation in the customer's thread, mark-as-read, ticket + CRM push + Telegram alert.

## C. Results

| Area | Status | Evidence |
|---|---|---|
| Static workflow/QA suite | PASS | 127/127 |
| Live web chat E2E | PASS | 10/10, latency median 3.7 s, max 7.7 s |
| Public tunnel reachability | PASS | HTTP 200 on `/home` |
| Telegram channel wiring | PASS | `getWebhookInfo` → URL matches the current tunnel, `pending 0`, no error |
| Email channel (Gmail API) | PASS | exec 114: KB answer + `[faq.md]`, threaded reply, original marked read |
| Escalation chain | PASS | exec 112: ticket + CRM push + Telegram alert + escalated reply |
| Error alerting | PASS | fired on real failures earlier (exec 51, `message_id` 8/12/13) |
| Availability / liveness | **FAIL** | service had stopped (no 5678 listener, tunnel gone); first E2E run: 10/10 FAILED, HTTP 000/530 |

## D. Defects

**D1 — P0 — Silent service death, nobody notified.**
Reproduction: let the n8n window/process end (crash, closing the console, reboot). Actual: all channels
stop; `watchdog.log` records `service is not running - nothing to watch (no autostart by design)`
repeatedly; the tunnel dies with it; n8n's own error alerting cannot fire because n8n *is* the failed
component. Detected only because the live E2E suite was run. Expected: the operator learns within
minutes and the service comes back. Root cause: the watchdog's "never start anything" rule (added to
honour "no autostart at boot") also suppresses **crash recovery**, and nothing checks liveness from
outside n8n. Recommended fix: add an opt-in `autoStart: true` to the watchdog — it restarts the
service and the tunnel when they are down (still nothing at Windows boot), and send the alert
out-of-band through the Telegram Bot API from the script itself, since n8n cannot report its own death.
Not applied: it changes runtime behaviour the user explicitly configured, so it is proposed, not assumed.

**D2 — P2 — Demo page can only talk to a local instance.**
`site/index.html` ships `data-webhook="http://127.0.0.1:5678/webhook/<id>/chat"`. Actual: fine on the
operator's machine (and fine for a screen recording), silently broken for anyone opening the page
elsewhere. Expected: one documented value to switch per deployment. Recommended fix: document the two
values (local for the video, tunnel URL for a shared live demo) and warn that a public URL must be
followed by stopping the tunnel, since anyone with the link can spend LLM quota.

**D3 — P3 — Unhelpful trigger error in the log.**
`There was a problem in 'Gmail Trigger (support alias)' node in workflow 'SupportBotEmailGmail01': 'undefined'`.
Observed once at startup; the channel then polled and handled mail correctly (exec 113/114). No action
beyond watching for recurrence; if it returns, capture the poll context before changing anything.

## E. Files changed in this round

| File | Why |
|---|---|
| `workflow/SupportBotEmailGmail-channel.json` | 5 fixes: structured-payload parser, single alias rule, subject fallback, API id for markAsRead, threaded `reply` |
| `tests/qa_suite.py` | T27.1–T27.5 pin those fixes; T26.3/T26.7 updated (their old assertions described the buggy behaviour) |
| `docs/qa-report-2026-09-19-email-channel.md` | Evidence for the live email round |
| `docs/operations.md` | Email channel marked live; §3.1 documents the Google Cloud setup and the two intentional behaviours |
| `README.md` | Status table reflects the verified email channel |

## F. Remaining risks and limitations

1. Availability (D1) — the one with real customer impact; everything else is cosmetic by comparison.
2. The Gmail channel depends on the client's own Google Cloud project (test users / published app).
   A revoked grant stops the channel until the alerting workflow reports a failing run.
3. Quick-tunnel hostnames are not permanent; a hosted client needs a named tunnel or a VPS.
4. No ticket dashboard: escalations are Supabase rows plus the Telegram message.
5. VPS deployment (the Premium tier's remaining promise) is not built, so Premium cannot be sold as-is.

## G. Release-readiness checklist

| Gate | State |
|---|---|
| Build/start, static checks, critical automated tests pass | PASS (127/127, 10/10) |
| No unresolved P0/P1 in *functionality* | PASS |
| Critical end-to-end journeys pass | PASS |
| No known high-severity security issue or secret leak | PASS (`/rest/login` requires auth; decrypted exports removed) |
| Rollback path, monitoring, operational docs | PARTIAL — alerting exists, but liveness monitoring does not (D1) |
| Remaining P2/P3 documented | PASS (D2, D3 + section F) |
