# M1 build checklist — RAG support bot (Supabase + forced retrieval)

Goal: a website support bot that **always retrieves**, answers **only** from the client's docs,
**cites the source file**, **refuses when the docs don't answer**, and **escalates to a human**.

> Test target: `knowledge/faq.md`, `knowledge/products.md`, `knowledge/policies.md` (Harbor Coffee Roasters).

---

## Step 0 — Supabase (once, ~15 min)

1. Create a project at supabase.com (free tier). Region: pick **Singapore** (closest to China).
2. SQL Editor → run:

```sql
create extension if not exists vector;

create table if not exists documents (
  id bigserial primary key,
  content text,
  metadata jsonb,
  embedding vector(1024)          -- BGE-M3 = 1024 dims. Do NOT use 1536.
);

create or replace function match_documents (
  query_embedding vector(1024),
  match_count int default 5,
  filter jsonb default '{}'
) returns table (id bigint, content text, metadata jsonb, similarity float)
language plpgsql as $$
begin
  return query
  select d.id, d.content, d.metadata,
         1 - (d.embedding <=> query_embedding) as similarity
  from documents d
  where d.metadata @> filter
  order by d.embedding <=> query_embedding
  limit match_count;
end;
$$;
```

3. Note from **Project Settings → API**: `Project URL`, `anon public` key (and the service key if you prefer).

## Step 1 — Embeddings provider (SiliconFlow)

1. Register at siliconflow.cn → API Keys → create key.
2. In n8n: **Credentials → Add → OpenAI**; Base URL `https://api.siliconflow.cn/v1`, paste the key.
3. Embedding model to use later: `BAAI/bge-m3` (1024 dims, multilingual — handles Chinese + English docs).

## Step 2 — Ingestion branch (same workflow, branch 1)

| # | Node | Configuration |
|---|---|---|
| 1 | **On form submission** | Add a field `document`, type **File**. (Optional: a `label` text field.) |
| 2 | **Default Data Loader** | Data Type: **Binary**; Input Data Field Name: the binary field from the form (`document`) |
| 3 | **Recursive Character Text Splitter** | Chunk Size `1000`, Chunk Overlap `100` |
| 4 | **Embeddings OpenAI** (credential = SiliconFlow) | Model `BAAI/bge-m3` |
| 5 | **Supabase Vector Store** (mode: **Insert Documents**) | Credential: Supabase (URL + key); Table `documents`; Query Name `match_documents` |

**Metadata trick:** in Default Data Loader → *Metadata* → add `source` = the uploaded file name.
(This is what makes "answer + source file" possible later.)

## Step 3 — Chat branch (same workflow, branch 2)

| # | Node | Configuration |
|---|---|---|
| 1 | **When chat message received** | Mode: **Embedded Chat**; toggle **Make Chat Publicly Available** (needed for the website embed) |
| 2 | **Question and Answer Chain** | Retrieval is **forced** by design — no Agent, so the model cannot skip the lookup |
| 3 | ↳ **Vector Store Retriever** → **Supabase Vector Store** (mode: **Retrieve Documents**) | Table `documents`, query `match_documents`, Top K `5` |
| 4 | ↳ **Chat Model** = **OpenAI Chat Model** (DeepSeek credential) | Base URL `https://api.deepseek.com/v1`, model `deepseek-flash` |
| 5 | ↳ **Simple Memory** | Session key = chat session id (short-term only; persistent session log = Standard tier) |

**System prompt (paste into the Q&A chain):**

```
You are the support assistant for Harbor Coffee Roasters.
Use ONLY the retrieved CONTEXT to answer. Never use your own knowledge, never guess.
If the context does not contain the answer, reply exactly:
IDK_HANDOFF: <one-line summary of what the customer asked>
and nothing else.
When you do answer, end with the source in square brackets, e.g. [faq.md].
Maximum 60 words. Friendly, concrete, no marketing fluff.
```

## Step 4 — Human handoff

After the chain, add an **IF** node:
- condition A: the reply contains `IDK_HANDOFF` → **true**
- condition B: the user message matches `human|agent|support|manager|refund|complaint` (case-insensitive) → **true**
- true → **Google Sheets: append row** (timestamp, sessionId, question, summary, full transcript)
  + **Gmail/Slack: notify** → reply "I've passed this to our team; they'll follow up by email."
- false → return the normal answer.

(Score-threshold gating — decide handoff by retrieval similarity — is an M2 refinement; it needs the
explicit *retrieve → filter → LLM* pattern instead of the canned Q&A chain.)

## Step 5 — Acceptance tests (these three ARE the product)

| # | Test | Pass condition |
|---|---|---|
| 1 | "How long does US shipping take?" | answers 2–4 business days **and shows [faq.md]** |
| 2 | "What's your cheapest espresso machine?" | **refuses** (IDK_HANDOFF) — never invents a product |
| 3 | "Can I pause a subscription?" then "and what about shipping to Canada?" | keeps context across both turns; then "I want to talk to a human" → **ticket row contains the full transcript** |

## Step 6 — Website embed (M4)

Chat Trigger → copy the **Chat URL** → embed via the `@n8n/chat` CDN snippet (or point
`site/widget.js` at the Chat URL). Keep the branded/self-hosted widget as a paid extra.

---

## What to sell (positioning, from the market scan)

Not "I will build an AI chatbot" (commodity). Sell the five guarantees:
1. answers **with sources**, 2. **refuses** instead of hallucinating, 3. low-confidence / human request
→ **auto ticket with full transcript**, 4. client can **upload and update** the knowledge base,
5. **branded embed + deployment + delivery docs**.

Tiers: Basic $90–120 (≤20 FAQ, 1 channel) · Standard $250 (site+PDF RAG, Supabase persistence,
branded widget, handoff) · Premium $500 (multi-channel, CRM/email integration, VPS deploy + backup).
