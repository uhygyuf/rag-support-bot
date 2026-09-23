# Architecture

## What runs where

| Piece | Runs on | Always available |
|---|---|---|
| Demo page | GitHub Pages (static files) | yes, even when the project owner's machine is off |
| `backend.json` | GitHub Pages, next to the page | yes |
| n8n workflow | the project owner's Windows machine | only while that machine is on |
| Postgres + pgvector | Supabase (hosted) | yes |
| Embedding API | SiliconFlow (`BAAI/bge-m3`) | yes |
| Chat API | DeepSeek | yes |

The page carries no key and no server logic of its own. It reads `backend.json` at load time and
sends questions to the single address in that file, so the address can change without touching
the page.

## Request path

    visitor browser
      |  GET index.html, widget.js, backend.json        (GitHub Pages, static)
      |  POST { question }                              (the assistant address)
      v
    tunnel with a fixed hostname
      |
      v
    n8n webhook  ->  embed the question  ->  vector search  ->  prompt  ->  DeepSeek
                                                                              |
    visitor browser  <-  answer + the source file names it came from  <--------

When the machine is off, the page still opens; the widget shows the offline sentence instead of
an answer.

## Inside the n8n workflow

1. `Webhook` receives the visitor message.
2. The message is normalized and guarded (length, empty input, prompt-injection patterns).
3. `Embeddings OpenAI` calls SiliconFlow for a 1024-dimension vector of the question.
4. `Supabase Vector Store` runs the `match_documents` function over the `documents` table.
5. The retrieved passages are formatted into a single context block.
6. `DeepSeek Chat Model` answers using only that context.
7. A `Code` node appends the source file names of the passages that were used, so every answer
   ends with a citation the visitor can check.
8. `Insert Ticket` stores the exchange (question, answer, sources) in Postgres.
9. The answer goes back to the browser.

`Push to CRM` exists but is disabled and points at a placeholder URL: an external system must not
receive customer questions unless the operator decides to wire one up.

## Knowledge base

`knowledge/faq.md`, `knowledge/policies.md` and `knowledge/products.md` are the only sources.
`tools/ingest.py` splits them into 900-character chunks, embeds each chunk with `bge-m3` (1024
dimensions) and writes them to the `documents` table, with the real file name stored in
`metadata.source`. Re-running it with `--replace` is idempotent. The citation a visitor sees is
that stored file name, never a value the model made up.

## Why these choices

| Choice | Reason |
|---|---|
| Page on GitHub Pages | static hosting is free, has no runtime, and stays up when the machine is off |
| Address kept in `backend.json` | one file decides where questions go; the page never hardcodes a URL |
| n8n | the flow is inspectable and editable as a graph, and the workflow JSON can be versioned next to the code |
| Supabase + pgvector | vector search without running Postgres locally; the schema is one table and one function |
| `bge-m3` via SiliconFlow | multilingual, 1024 dimensions, and cheap enough for a demo |
| DeepSeek | low cost per answer, and answers stay grounded because the prompt forbids outside knowledge |
| Citations appended by code | a model cannot be trusted to name its sources; the names come from the rows that were retrieved |
| Tests as files in the repo | `tests/qa_suite.py` (138 checks), `tests/e2e_live.py`, `tests/widget_dom_test.js`, `tests/test_ingest.py`, `tests/kb_live_check.py`. Every claim in `TEST_REPORT.md` maps to one of them |

## What this design does not have

- A server of its own: the backend is a laptop, so the assistant answers only while that laptop is
  awake. Static hosting hides this from the visitor, it does not remove it.
- Any secret in the repository: keys live in n8n credentials and in a local file outside the repo.
  `tests/qa_suite.py` scans the tree for key-shaped strings and fails the build if one appears.
- Multi-user isolation: one shared knowledge base, one workflow, one token budget.
