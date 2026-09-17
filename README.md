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

## Status (2026-09-16)

| # | Milestone | State | Evidence |
|---|---|---|---|
| M1 | Ingestion + chat answers from real docs | **done** | 3 docs ingested into Supabase `documents` (vector 1024); live answers with `[faq.md]` / `[product-catalogue.md]` citations |
| M2 | Multi-turn memory | **done** | same-session follow-up "…What about Canada?" resolved to 7–14 business days |
| M3 | Human handoff (ticket) | **done** | out-of-KB question → `Create Ticket Tool` executed inside a successful run (n8n execution 23); the row itself was verified by the owner in Supabase |
| M4 | Website widget on the demo site | **code done, needs a published workflow** | widget protocol + embed URL fixed and verified over HTTP 200; site/ is not yet served |
| M5 | VPS deploy (Docker + Caddy + backups) | not started | Premium-tier add-on |
| — | Handoff notification (email/Telegram) | **open** | ticket lands in the DB but nobody is pinged yet |

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

It is static + contract only (no network, no writes). Live behaviour is covered by the end-to-end
tests in the QA report — POST the chat protocol to the published webhook.

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
