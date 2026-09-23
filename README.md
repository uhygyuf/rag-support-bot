# Harbor Support Bot — grounded RAG customer support on n8n

A self-hosted customer-support assistant for a small online store. It answers **only** from the
company's own documents (FAQ, product pages, policies), shows the document each answer came from,
says "I don't know" instead of guessing — and turns every unanswered question into a ticket with a
notification so a human can follow up.

One knowledge base, one agent, **three customer channels**: website chat widget · email (Gmail,
threaded reply) · Telegram.

The demo business is a fictional coffee roaster (Harbor Coffee Roasters); its FAQ, catalogue and
policies in `knowledge/` are the only facts the bot is allowed to use.

## Live demo

| Where | How to reach it |
|---|---|
| **Web** | **https://uhygyuf.github.io/rag-support-bot/** — the storefront with the assistant in the corner. Ask something the FAQ does not cover and you get the handoff to a human instead of a guess. |
| Email | write to the demo mailbox's `+support` alias — the bot answers inside the customer's thread |
| Telegram | `@HarborSupport_bot` |

The hosted page finds its backend at runtime through `site/backend.json`, which holds the tunnel
hostname. That hostname is permanent — it is the account's tunnel name, set in
`D:\Tools\ngrok\ngrok.yml` — so nothing has to be republished. While the machine that runs n8n is off,
the page still loads and the widget says the assistant is offline; the storefront itself never breaks.

---

## What the product does

| Behaviour | What the customer / operator sees |
|---|---|
| Answers from the company's documents, not from model memory | every answer ends with its source file, e.g. `… 7–14 business days. [faq.md]` |
| Admits ignorance in one fixed sentence | `I don't have that information - I've passed your question to our team and a human will reply within 24 hours.` |
| Never lets that sentence be an empty promise | the same turn writes a row into Supabase `tickets`, pushes it to a CRM webhook and sends the operator a Telegram alert (the CRM node ships disabled with a placeholder URL — point it at your own endpoint and enable it) |
| Follows a conversation | same-session follow-ups ("…what about Canada?") resolve against the earlier turn |
| Same behaviour on every channel | the widget, Gmail and Telegram all run the same agent, knowledge base and escalation branch |
| Degrades safely | if the backend is down the visitor gets one plain sentence, never an HTTP code or a stack trace |

## Why the answers can be trusted (grounding, in three layers)

1. **Retrieval is a mandatory tool call.** The agent's system prompt requires calling the
   `knowledge_base` tool before answering and forbids answering from its own knowledge.
2. **Answers are constrained, not paraphrased.** The prompt forbids inventing prices, dates or
   policies, caps answers at 60 words and requires the source file name in square brackets.
3. **Escalation is a deterministic graph branch, not a model decision.** The agent must reply with
   one verbatim handoff sentence; the workflow matches that sentence (`If escalated`) and then runs
   `Insert Ticket → Notify Telegram → Push to CRM → Reply`. Even if the model forgets the ticket
   tool, the question still lands in the ticket table.

*Known hardening items:*

- the vector store runs in `retrieve-as-tool` mode with default options — **no similarity-score
  threshold** is wired in yet. Grounding today is enforced by the prompt and the escalation branch;
  a score threshold is the next change that makes retrieval itself stricter.
- the Gmail filter (`to:…+support`, unread only) also matches the bot's **own** replies, because
  Gmail keeps the alias on the `To` header of a reply. Those are rejected today by the alias check on
  the parsed `to` field, but depending on that field's order is fragile — the filter should also
  exclude own sent mail (`-from:me`).

## How it works

```
 visitor ──► website chat widget ─┐
 customer ─► email  (Gmail API)   ┼──► n8n ──► Support Agent
 customer ─► Telegram             ┘                │  (system prompt: call the KB first)
                                                   ▼
                              Supabase pgvector knowledge base  ◄── 3 documents, loaded by
                              (bge-m3 embeddings, 1024 dims)         tools/ingest.py
                                                   │
                        grounded answer + [source] ◄┘
                                                   │  can't answer / customer asks for a human
                                                   ▼
             Insert Ticket (Supabase) ─► Notify Telegram ─► Push to CRM ─► fixed handoff reply
```

| Component | Role |
|---|---|
| **n8n** (self-hosted, 2.38) | the whole orchestration: triggers, agent node, branching, retries |
| **DeepSeek** (OpenAI-compatible) | the conversational model behind the agent |
| **Supabase pgvector** | knowledge base (`documents`) and the ticket queue (`tickets`) |
| **SiliconFlow bge-m3** | embeddings for ingestion and for the query |
| **ngrok** (permanent hostname) | makes the local instance reachable for the widget and the Telegram webhooks; runs as a Windows service |
| **Telegram bot** | the operator's alert channel (tickets, workflow errors, crash recovery) |

What runs where (GitHub Pages, the tunnel, the workflow, the database), why each piece was chosen,
and what the design deliberately does not have: `docs/architecture.md`.

## Channels — state and evidence

| Channel | Entry point | Verified |
|---|---|---|
| Website widget | `site/index.html` + `site/widget.js` → Chat Trigger webhook | happy path, real citations, multi-turn, escalation, injection refusal — 11/11 live E2E cases |
| Email | Gmail Trigger on the `+support` alias → threaded reply | live runs 2026-09-19 and re-verified 2026-09-22: question parsed, answer returned with a `[faq.md]` citation, reply delivered **inside the customer's thread**, original marked read |
| Telegram | Telegram Trigger on `@HarborSupport_bot` | live run: message received → same agent answered → reply delivered (`message_id` 9) |
| Operator alerts | escalation branch + `Error Trigger` workflow | live ticket alert and live workflow-error alert both delivered to the phone |

## Verification

| Suite | What it covers | Last run |
|---|---|---|
| `tests/qa_suite.py` | **139 static + contract checks** (workflow shape 29, channels 23, reliability 18, ux 10, a11y 10, integration 10, safety 10, release 10, content 8, docs 5, security 4, quality 2) — no network, no writes | 139 / 139 PASS |
| `tests/widget_dom_test.js` | 12 DOM-level cases for the widget's backend resolution (`data-webhook` → `backend.json` → local n8n), its offline behaviour, its retry after a stale address, and its refusal to render an answer as HTML, in a stubbed DOM | 12 / 12 PASS |
| `tests/test_ingest.py` | 13 offline cases for the loader: chunk boundaries, an oversized block, CRLF, a whitespace-only file, and the rule that the two APIs never share headers | 13 / 13 PASS |
| `tests/kb_live_check.py` | reads the live knowledge base and compares it with `knowledge/`: every chunk names a file, every file is loaded, no stray source, chunk counts match the plan (needs credentials; skipped without them) | 5 / 5 PASS |
| `tests/e2e_live.py` | **11 live cases** against a running instance: `happy_path_answer`, `citation_is_a_real_source`, `policy_document_reachable`, `memory_followup`, `escalation_reply`, `injection_refused`, `malformed_body_survives`, `empty_input_survives`, `long_input_survives`, `concurrent_3_visitors`, `public_tunnel_reachable` | 11 / 11 PASS |
| crash recovery | both processes are Windows services (`n8n support bot` under a WinSW wrapper, `ngrok` with recovery options); Windows starts them at boot and restarts them on failure | services come back, `bot-status.bat` reports them running, the public address answers again (evidence in `docs/operations.md` §5) |

Results are machine-readable: `tests/qa-results.json`, `tests/e2e-results.json`.

### Real defects found and fixed by this testing

1. **The agent skipped the ticket tool.** A live run replied "I've passed your question to our team"
   *without* calling `create_ticket` — the question was lost. Escalation is now a deterministic graph
   branch driven by the verbatim handoff sentence, not a model decision.
2. **The Supabase node's `tableId` was an object, not a string** → `Could not find the table
   'public.[object Object]'`. Every earlier "ticket created" claim was wrong; nothing had been
   written. Fixed, and execution output now returns the inserted row. Regression guards: `T4.1`,
   `T1.5`, `T4.7`.
3. **Five defects in the email channel** (threading, quoting, poll window, alias matching, marking
   read) — found by the first live Gmail run and fixed; details in
   `docs/qa-report-2026-09-19-email-channel.md`.

## Run it locally

1. Import the workflows into n8n and attach your own credentials (exports never carry secrets):
   ```bash
   npx n8n import:workflow --input=workflow/SupportBotRAG-full.json
   npx n8n import:workflow --input=workflow/SupportBotEmailGmail-channel.json
   npx n8n import:workflow --input=workflow/SupportBotTelegram-channel.json
   npx n8n import:workflow --input=workflow/SupportBotErrorAlerts.json
   ```
   Credentials needed: Supabase (pgvector), DeepSeek (chat model), SiliconFlow or OpenAI
   (embeddings), Gmail OAuth2, Telegram bot. Setup detail: `docs/client-setup-guide.md`.
2. Ingest the knowledge base: `python tools/ingest.py --replace` (chunks the files in `knowledge/`,
   calls the embedding model, and writes rows with a real `source` label). The **On form submission**
   trigger in the RAG workflow also ingests a file, but n8n 2.38.7's binary loader stamps every chunk
   `metadata.source = "blob"` and the node has no parameter to change it, so uploads through the form
   produce answers that cannot name their source. Use the form for quick text experiments, the script
   for anything a customer will see.
3. Publish the workflows (top-right **Publish**, or `npx n8n publish:workflow --id=<id>` **while n8n
   is stopped** — the CLI cannot register a webhook into a running instance). The widget URL is
   `http://<host>:5678/webhook/<chat-trigger-webhookId>/chat`.
4. Open the demo store: double-click `site/index.html`, then click **"Need coffee help?"**.

### Daily start / stop

| I want to… | Do this |
|---|---|
| **Start the bot** (the two services) | double-click **`switches\bot-on.bat`** — sets n8n and ngrok to Automatic, starts them, waits until n8n answers, then checks the public address |
| **Really stop it** | double-click **`switches\bot-off.bat`** — stops both services and sets them to Disabled, so a reboot does not bring the demo back |
| Check the state without changing anything | `switches\bot-status.bat` |
| Start everything and open the demo page (clears QA tickets) | double-click `start-demo.bat` (add `-KeepTickets` to keep them) |
| Start only n8n, no public access | stop the services (`bot-off.bat`), then `D:\Tools\n8n\start-n8n.bat` (keep the "n8n server" window open) |
| Open the bot editor | browser → `http://127.0.0.1:5678` → workflow **Support Bot (RAG) — full** |
| Check whether n8n is up | `curl -s -o NUL -w "%{http_code}" http://127.0.0.1:5678/healthz` → `200` = up, `000` = down (20–60 s to boot) |

Details, and what a visitor sees in each state: `switches/README.md`.

## Operations

Both processes are Windows services now, so the operating system keeps them alive:

| Mechanism | What it does |
|---|---|
| Windows service **n8n support bot** (WinSW wrapper, Automatic) | starts n8n at boot and restarts it after a failure (10 s / 30 s / 60 s backoff, counter reset after an hour without failures) |
| Windows service **ngrok** (Automatic, recovery options set by its installer) | starts the tunnel at boot and restarts it if it stops; the hostname lives in `ngrok.yml`, so it never changes |
| scheduled task **"n8n zombie cleanup"** (every 15 min) | legacy janitor for the manual `n8n-serve.bat` path; silent while the services run |

Built-in resilience (covered by tests `T16.x` / `T17.x`):

| Risk | Defence |
|---|---|
| transient network / API hiccup | agent, KB tool, ticket tool, embeddings and the Supabase write each retry twice before failing |
| the model takes too long | the widget aborts after 45 s and shows its offline line instead of spinning forever |
| n8n restarts | the workflows stay published (that state lives in the database), so the webhook answers as soon as n8n is back |
| a knowledge document is wrong or outdated | the bot escalates instead of guessing — fix the document and run `python tools/ingest.py --replace knowledge/<file>.md` |
| a dead CRM endpoint | `Push to CRM` runs with `onError: continue` and ships disabled with a placeholder URL, so it can never break the ticket or the reply |

Operational rules while the bot is in use:

1. Do not import/replace a workflow while it is serving — an import *deactivates* it; re-publish after.
2. Do not restart n8n during a demo — answers fail for about a minute.
3. Keep the machine awake: sleep or hibernation stops everything. "Always available" needs real
   hosting (VPS + named tunnel), which this repository does not include.
4. Supabase free projects pause after ~7 days without activity — open the dashboard before a demo.
5. The Gmail trigger polls once a minute and only handles **unread** mail newer than its last check;
   opening a customer mail by hand before the poll can skip it (deliberate anti-duplicate behaviour).

## Repository layout

```
rag-support-bot/
├── site/            demo storefront (index.html) + embeddable chat widget (widget.js)
├── knowledge/       the "company documents" the bot is allowed to answer from
├── tools/           ingest.py — loads knowledge/ into Supabase with a real source label
├── workflow/        design notes + exported n8n workflows
│   ├── SupportBotRAG-full.json             website channel + KB ingestion (20 nodes)
│   ├── SupportBotEmailGmail-channel.json   Gmail channel, threaded replies (18 nodes)
│   ├── SupportBotTelegram-channel.json     Telegram channel (13 nodes)
│   ├── SupportBotErrorAlerts.json          Error Trigger → operator alert (3 nodes)
│   ├── SupportBotEmail-channel.json        earlier IMAP-based email channel (retired)
│   └── CreateSupportTicket-tool.json       earlier tool-based ticket node (kept for reference)
├── tests/           static QA suite + live E2E suite (+ JSON results)
├── switches/        bot-on.bat / bot-off.bat / bot-status.bat — start and really stop the bot
├── demo/            one-command demo launcher (demo-start.ps1) + the subtitle/render pipeline used
│                    for the 60-second walkthrough video
└── docs/            architecture, operations, setup guide, QA reports, acceptance checklist
```

## Scope and honest limits

- **Runs on one laptop.** Availability is bounded by the machine being awake. The address itself is
  permanent, so uptime is the only thing that limits the demo.
- **No ticket UI.** The Supabase `tickets` table *is* the queue; a dashboard is not built.
- **The chat endpoint is unauthenticated** while the tunnel is up — anyone with the URL can consume
  the configured model quota. The tunnel is meant to be stopped when not in use.
- **Doc accuracy is the customer's job, not the bot's.** The product's promise is *answer from the
  documents · admit ignorance · escalate* — never "always correct".
- **Demo data is fictional.** Harbor Coffee Roasters, its products, prices in `knowledge/` and
  `support@harborcoffee.example` do not exist.

## Design rules

- Never promise accuracy; promise *answer from your documents / admit ignorance / escalate*.
- Every "I don't know" is a logged ticket — that log is the follow-up queue.
- No secret ever lives in a workflow export, a report or a log.
- The customer keeps their own accounts and API keys.

MIT licensed — see `LICENSE`.
