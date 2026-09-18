# RAG Support Bot — n8n + LLM (portfolio project)

**Goal:** a website support chatbot that answers from a company's own docs (FAQ / products / policies),
says "I don't know" when the docs don't cover it, and hands off to a human with a ticket.

**Business model (Fiverr gig):**
- Basic $90–120 — ≤20 FAQ entries, 1 channel, 3–4 days
- Standard $250 — site + PDF RAG, brand styling, human handoff, 6–7 days
- Premium $500 — RAG + handoff + CRM/email integration + VPS deployment, 10–14 days

**Stack:** n8n (self-hosted) · OpenAI-compatible LLM API (DeepSeek) · simple in-context retrieval (v0) → vector store (v1) · Caddy + Docker on VPS (v2)

## Why this demo is credible
The knowledge base is **real content** (a small business: Harbor Coffee Roasters), not dummy data:
products, shipping, returns, wholesale, FAQ. The demo site is a real page that loads the chat widget.

## Status (2026-09-18)

| # | Milestone | State | Evidence |
|---|---|---|---|
| M1 | Ingestion + chat answers from real docs | **done** | 3 docs ingested into Supabase `documents` (vector 1024); live answers with `[faq.md]` / `[product-catalogue.md]` citations |
| M2 | Multi-turn memory | **done** | same-session follow-up "…What about Canada?" resolved to 7–14 business days |
| M3 | Human handoff (ticket) | **done (fixed 2026-09-18)** | deterministic branch: unanswerable question → `Insert Ticket` runs and its execution output contains the inserted row (`id:1`); the earlier tool-based version silently wrote nothing |
| M4 | Website widget on the demo site | **code done, needs a published workflow** | widget protocol + embed URL fixed and verified over HTTP 200; site/ is not yet served |
| M5 | VPS deploy (Docker + Caddy + backups) | not started | Premium-tier add-on |
| — | Handoff notification (Telegram) | **done (verified 2026-09-18)** | escalation branch runs `Insert Ticket` → `Notify Telegram` → `Reply Escalated`; execution 40 is `success` with the inserted row (`created_at`) and Telegram's `message_id` in the output — the phone push was delivered |
| — | CRM / HTTP integration | **done (verified 2026-09-18)** | `Push to CRM` POSTs the ticket JSON to any endpoint; verified against a live webhook collector (HTTP 200, payload carries `question` + `ticket_id`); `onError: continue` so a dead endpoint can never break the ticket or the reply |
| — | Second channel — **email** (IMAP in / SMTP out) | **built, not release-ready** | `workflow/SupportBotEmail-channel.json`; answers only mail sent to the dedicated `+support` alias and never marks inbox mail as read. Blocked by an n8n/Gmail IMAP trigger defect — see QA report B4 |
| — | Second channel — **Telegram** | **done (verified 2026-09-18)** | `workflow/SupportBotTelegram-channel.json`; message received → same Agent answered → reply delivered (`message_id` 9) after exposing n8n through a Cloudflare quick tunnel with `WEBHOOK_URL` set. Start with `D:\Tools
8n\start-public.bat` |
| — | Error alerting | **done (verified 2026-09-18)** | `workflow/SupportBotErrorAlerts.json` (n8n `Error Trigger` → Telegram). Fired on a real failure and on a real trigger-activation failure; alert delivered (`message_id` 12/13) |

### 2026-09-18 — two real defects found and fixed

1. **The agent skipped the ticket tool.** On a live run it replied "I've passed your question to our
   team" **without calling `create_ticket`** — the question was lost. Escalation is now a deterministic
   graph branch (`If escalated` → `Insert Ticket` → `Notify Telegram` → `Reply Escalated`), driven by a
   verbatim handoff sentence in the system prompt.
2. **The Supabase node's `tableId` was an object, not a string** → `Could not find the table
   'public.[object Object]'`. Every earlier "ticket created" claim was wrong; nothing had been written.
   After the fix, execution 37 returns the inserted row (`id: 1`). Regression guards: `T4.1` (string
   table name), `T1.5` (deterministic escalation), `T4.7` (notification cannot break the ticket).

## Shipped artifacts

```
workflow/SupportBotRAG-full.json       exported chat + ingestion workflow (11 nodes) — import into n8n
workflow/CreateSupportTicket-tool.json exported ticket sub-workflow (2 nodes)
tests/qa_suite.py                      reproducible QA suite (60 checks: structure, contract, security, a11y)
tests/qa-results.json                  machine-readable results of the last run
docs/qa-report-2026-09-16.md           QA report: findings, fixes, release gate
```

Re-import into a fresh n8n: `npx n8n import:workflow --input=workflow/SupportBotRAG-full.json` and the
same for the ticket sub-workflow — then attach your own credentials (Supabase, SiliconFlow embeddings,
DeepSeek) in the node panels, because exports never carry secrets.

## Running the QA suite

```bash
python tests/qa_suite.py                 # exit 0 = all checks pass
python tests/qa_suite.py --workflow workflow/SupportBotRAG-full.json
```

```bash
python tests/qa_suite.py     # 115 static checks: structure, contracts, safety, security, docs
python tests/e2e_live.py     # 10 live cases against a running instance (writes tests/e2e-results.json)
python tests/e2e_live.py --tunnel https://<your-tunnel-host>   # also verifies the public origin
```

`qa_suite.py` is static + contract only (no network, no writes). `e2e_live.py` needs the workflow
published and n8n reachable; it covers the happy path, citations, multi-turn memory, escalation,
prompt injection, malformed/empty/oversized input, concurrency and the public origin.

## Publishing (needed before a website embed works)

The Chat Trigger only serves its production URL while the workflow is published:
publish it in the editor (top-right **Publish**, formerly the Active toggle) or
`npx n8n publish:workflow --id=<workflowId>` **while n8n is stopped** (the CLI cannot register a
webhook into an already-running instance). The embed URL is
`http://<host>:5678/webhook/<chat-trigger-webhookId>/chat`.

## Starting and stopping (daily use)

| I want to… | Do this |
|---|---|
| **Start everything** (n8n + demo page) | double-click `start-demo.bat` in this folder — it starts n8n if needed, waits ~30 s, then opens the demo website |
| Start only the server | double-click `D:\Tools\n8n\n8n-serve.bat` (a window titled "n8n server" stays open — keep it open) |
| Open the bot editor | browser → `http://127.0.0.1:5678` → workflow **Support Bot (RAG) — full** |
| Open the demo website | double-click `site\index.html`, then click the **"Need coffee help?"** button |
| **Stop n8n** | close the window titled "n8n server", or double-click `D:\Tools\n8n\stop-n8n.bat` |
| Check whether n8n is running | `curl -s -o NUL -w "%{http_code}" http://127.0.0.1:5678/home` → `200` = up, `000` = down (takes 20–60 s to boot after a start) |

Notes

- **n8n must be running for the bot to answer** — the widget on the website calls it at
  `http://127.0.0.1:5678/webhook/<id>/chat`. If n8n is down, the widget shows "not reachable".
- The workflow must also be **Published** (top-right of the editor) for that URL to answer.
- Supabase, DeepSeek and SiliconFlow are cloud services — nothing to start or stop there.
- n8n has died on its own repeatedly after long idle periods in this setup. If the bot stops
  answering, first check `http://127.0.0.1:5678`; if it is down, double-click `start-demo.bat`.

### Reliability — what is defended, and what is not

Built-in protections (added 2026-09-17, all covered by tests `T16.x` / `T17.x`):

| Risk | Defence |
|---|---|
| Transient network / API hiccup | the Agent, the KB tool, the ticket tool, the embeddings and the Supabase write each **retry** (2 tries) before failing |
| The model takes too long | the widget **aborts after 45 s** and shows its offline line instead of spinning forever |
| n8n is down or the request fails | the visitor sees one plain sentence ("our assistant is offline right now…"), never an HTTP code or stack trace; the details go to the browser console (`data-offline`, `data-timeout-ms` to customise) |
| n8n restarts | the workflow stays **published** (that state lives in the database), so the webhook answers again as soon as n8n is back at `http://127.0.0.1:5678` |
| A knowledge document is wrong/outdated | the bot escalates instead of guessing; fix the document and re-upload |

Operational rules while a client is using it:

1. **Do not import/replace the workflow while it is serving** — an import *deactivates* it. After any
   import you must re-publish (and restart n8n) before the widget answers again.
2. **Do not restart or stop n8n during a demo** — answers fail for ~1 minute.
3. Keep the machine awake (sleep/hibernate stops everything). "Always available" needs hosting: that
   is the VPS add-on (Docker + Caddy + auto-restart), not something a laptop can promise.
4. Supabase free projects **pause after ~7 days without activity** — with real traffic that never
   happens; for a demo, open the Supabase dashboard before showing it.
5. If the bot stops answering: open `http://127.0.0.1:5678`; if it is down, run `start-demo.bat`.

## Layout
```
rag-support-bot/
├── site/            demo business website + chat widget
├── knowledge/       the "client's docs" the bot must answer from
├── workflow/        node-by-node design + exported workflow JSON
└── docs/            scope notes, client-facing setup guide (later)
```

## Rules of engagement (delivery discipline)
- Client's own accounts and API keys; never host for a client long term.
- Never promise accuracy; promise *answer from docs / admit ignorance / escalate*.
- Every "I don't know" is logged — that log IS the ticket list.
