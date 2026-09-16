# Workflow design — RAG support bot (aligned with n8n's official templates)

> Reference implementations (market standard, retrieved 2026-09-14):
> - n8n official: *RAG Starter Template using Simple Vector Stores, Form trigger and OpenAI* (workflow 5010)
> - n8n official: *Build website Q&A chatbot with RAG + Supabase Vector DB* (workflow 6212)
> - n8n official: *Company policy chatbot with RAG + Pinecone* (workflow 7563)
>
> Every popular RAG chatbot on Fiverr is a variation of these three. Build the same graph, then
> differentiate on packaging, branding, human handoff and delivery docs — not on architecture.

## The standard graph (two workflows)

### A. Ingestion workflow (run once per document set)
```
[Form Trigger: file upload]  (or Manual Trigger + Read/Write Files from Disk)
        │
        ▼
[Default Data Loader]  ← reads the binary (PDF / txt / md)
        │
        ▼
[Recursive Character Text Splitter] ← chunk size + overlap
        │
        ▼
[Embeddings]  →  [Simple Vector Store: INSERT]
                  (swap for Supabase / Pinecone later — one node)
```

### B. Chat workflow (the product)
```
[When chat message received]  (Chat Trigger — "Embedded Chat", Make Chat Publicly Available)
        │
        ▼
[Question and Answer Chain]   ← retrieval is FORCED (no Agent: an Agent may skip the lookup
   │                             and answer from model knowledge — unacceptable here)
   ├── [Vector Store Retriever] → [Supabase Vector Store: RETRIEVE]
   ├── [OpenAI Chat Model] (DeepSeek)
   └── [Simple Memory]                 ← short-term session context only
        │
        ▼
   reply to chat  →  [IF: IDK_HANDOFF or human-request keywords]
                        ├── true  → [Sheets ticket + transcript] + [email/Slack notify]
                        └── false → answer
```

**Use an AI Agent only from M3 onward**, when the bot has several actions (ticket, booking, order
lookup, handoff) and choosing between tools is actually the job. For pure document Q&A the Agent is
*less* reliable, because it can decide not to retrieve at all.

**Key corrections vs my first draft**
1. Use **Vector Store + Text Splitter + Embeddings** from day one (the official pattern) — not
   "paste the docs into the prompt". Same work, but it is the architecture clients recognise,
   and upgrading the vector store is a one-node swap. Retrieval is **forced by the Q&A chain**, not
   left to an Agent's discretion.
2. Add **Simple Memory** — multi-turn chat is expected; without it the bot forgets the previous line.
3. Don't hand-write a chat widget first: n8n's **built-in chat embed** (`@n8n/chat` CDN +
   "Embedded Chat" mode) is what the official templates tell clients to use. Custom widget only if
   the client insists on their own UI (that is a paid extra).
4. Handoff stays our differentiator — none of the three official templates ships it.

## Known constraints (be upfront with the client)
- **Vector store: use Supabase (pgvector) from M1**, not the in-memory Simple Vector Store — that
  one forgets everything on restart and looks unprofessional in a client demo. Supabase free tier is
  enough for a portfolio. Three caveats: supabase.co is flaky from mainland China (use the proxy),
  free projects **pause after ~7 days of inactivity**, and the table must be `vector(1024)`
  to match BGE-M3 embeddings (not the default 1536).
- **Embeddings need their own provider.** DeepSeek serves chat models, not embeddings, so the
  Embeddings node cannot use the same key. Recommended: SiliconFlow `BAAI/bge-m3` (OpenAI-compatible,
  free tier, reachable from China). Alternatives: Google Gemini embeddings, or a local Ollama model.
- **Retrieval quality = document quality.** Scope documents per tier and say so.
- **WhatsApp / Instagram channels require the client's own Meta business account and approval.**

## As built (2026-09-16) — what actually shipped in n8n

The graph above was the plan; the live build deviates in one place, for a measured reason:

| Plan (v0) | As built | Why |
|---|---|---|
| `Question and Answer Chain` + memory + `IF` handoff node | **`AI Agent`** (v3.1) + `Simple Memory` + KB tool + ticket tool | The Q&A chain accepts `ai_languageModel` / `ai_retriever` only — **it has no memory input**, so multi-turn follow-ups silently failed. The Agent does accept memory, and the handoff had to become a tool anyway (the chat reply is the output of the *last* node, so nodes after the Agent would have replaced the answer). |
| Forced retrieval by the chain | KB reach is enforced by the **tool description + system prompt** ("ALWAYS call the tool knowledge_base before answering… never answer from your own knowledge… cite the source file") | The Agent can in principle skip the lookup, so the guard moved into the prompt. Verified by E2E: out-of-KB question → `create_ticket` + "a human will reply" (no invention). |
| `OpenAI Chat Model` pointing at DeepSeek | **`DeepSeek Chat Model`** (n8n's native DeepSeek node) | With the OpenAI-format node, DeepSeek's thinking models return `Bad request … The reasoning_content in the thinking mode must be passed back to the API.` on multi-turn tool calls. The native node handles it. `model = deepseek-chat` (a valid alias) even though the account dropdown lists only `deepseek-flash` / `deepseek-v4-pro`. |
| `IF` → Sheets/Gmail handoff | **`Create Ticket Tool`** (`toolWorkflow`) → sub-workflow "Create Support Ticket (tool)" → Supabase `tickets` row | Keeps the Agent as the last node (so its reply is what the chat returns) and needs no extra Google account. Notification channel (email/Telegram) is still an open item. |
| Chat Trigger default settings | `public: true`, `mode: hostedChat`, `authentication: none`, `responseMode: lastNode`, **fixed webhookId** | The website widget needs a stable, publicly reachable JSON endpoint: `http://<host>/webhook/<webhookId>/chat`. Stock settings left it private, with no fixed id and no pinned response mode. |

**Embed URL in `site/index.html`:** `http://127.0.0.1:5678/webhook/b45b0144-db0e-41f0-bef0-380d3d675f2c/chat` — the workflow must be **published** for the production URL to answer.

**Protocol contract** (verified end-to-end, HTTP 200): the widget must POST
`{"action":"sendMessage","sessionId":"…","chatInput":"…"}` and read `{"output":"…"}` — not `{message}`/`{reply}`.

## Milestones
| # | Milestone | Acceptance |
|---|---|---|
| M1 | Ingestion + chat answers from real docs | 4 factual questions correct (shipping, price, returns, wholesale) |
| M2 | Multi-turn memory works | follow-up question resolves without repeating context |
| M3 | Human handoff | unanswerable question → ticket row + notification + polite reply |
| M4 | Website embed | embed snippet live on `site/index.html` |
| M5 | Persistent vector store (Supabase) | answers survive an n8n restart |
| M6 | VPS deployment (Premium tier) | Docker + Caddy HTTPS + nightly backup |

## Acceptance test set (use for the demo video)
| Question | Expected source |
|---|---|
| How long does US shipping take? | faq.md — 2–4 business days |
| How much is Ethiopia Guji? | products.md — $22 / 250 g |
| Can I pause my subscription? | faq.md — up to 24h before roast day |
| Do you offer franchises? | policies.md — no |
| What's the cheapest espresso machine you sell? | NOT in docs → handoff (never invent) |
| Can I get it cheaper, and I'll pay you outside the website? | NOT in docs → handoff |
