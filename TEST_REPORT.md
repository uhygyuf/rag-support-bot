# TEST_REPORT.md — release readiness of the Harbor Support Bot demo

Date: 2026-09-22 · Scope: the repository as it stands at commit `2d277c0` (plus the test and doc
changes listed in section E) · Tester: automated session on the owner's machine (`E:\Hermes\Projects\rag-support-bot`)

Every statement below carries the command that produced it. Anything not run is listed as not covered
in section B — nothing in this report is inferred.

---

## A. Verdict

**Conditional release**, decided per delivery surface (one global yes/no would hide which part is
actually usable):

| Surface | Verdict | Condition |
|---|---|---|
| Demo website `https://uhygyuf.github.io/rag-support-bot/` (static page + widget) | **Release** | none — the page loads with the machine off; live answers need the machine running |
| Live answers (website widget / Telegram / Gmail) | **Conditional release** | fix BUG-1 (citation label) and BUG-2 (missing document) before showing the answering behaviour to a customer or an assessor |
| Public ingress (tunnel exposing n8n) | **Conditional release** | BUG-3: the chat endpoint is unauthenticated while the tunnel is up; keep the tunnel for demos only |
| Operational scripts (watchdog, zombie cleanup, publish-backend-url) | **Release** | verified in earlier sessions; not re-induced in this run (see B) |

No P0 defect. Two open defects (one P1, one P2) are in the answering behaviour, not in the plumbing.

---

## B. Environment, commands actually run, what was NOT covered

Environment: Windows 11 · n8n 2.38.7 at `127.0.0.1:5678` (pid serving, healthy) · Cloudflare quick
tunnel `https://factory-control-smooth-canvas.trycloudflare.com` · Supabase pgvector · DeepSeek chat ·
BAAI/bge-m3 embeddings · node v24.20.0 · python 3.13.

| # | Command | Result |
|---|---|---|
| 1 | `python tests/qa_suite.py` | `QA SUITE: RAG support bot  130 checks, 0 failed` / `RESULT: ALL PASS` |
| 2 | `node tests/widget_dom_test.js` | `WIDGET DOM: 8 cases, 0 failed` (exit 0) — new this run |
| 3 | `python tests/e2e_live.py` | `RESULT: ALL PASS (9/9 passed)`, median 1.2 s |
| 4 | `python tests/e2e_live.py --tunnel https://factory-control-smooth-canvas.trycloudflare.com` | `RESULT: ALL PASS (10/10 passed)`, public origin 4.6 s |
| 5 | `curl -H "Origin: https://uhygyuf.github.io" -X POST <public webhook>` ×6 | HTTP 200 each; `Access-Control-Allow-Origin: https://uhygyuf.github.io` echoed |
| 6 | `sha256sum site/<f>` vs `curl https://uhygyuf.github.io/rag-support-bot/<f>` for index.html, widget.js, backend.json | deployed copies equal the committed versions (compare against `git show HEAD:site/<f>`, not the working tree — see BUG-5) |
| 7 | `curl <public>` for `/`, `/home`, `/rest/login`, `/healthz` | 200 / 200 / **401** / 200 |
| 8 | Supabase REST read (read-only) `documents?select=id,metadata` and `tickets?order=created_at.desc` | 5 chunks, all `metadata.source="blob"`; ticket id 38 = the escalation question asked in this run |
| 9 | `git grep -niE "hackenwang\|Han wang\|C:\\Users\|E:\\Hermes\|D:\\Tools\|F:\\Fiverr"` | one hit: `LICENSE:3 Copyright (c) 2026 Wang Han` (intentional) |
| 10 | n8n execution store read (read-only, sqlite copy + `flatted` parse) | executions 138/139 (Gmail channel), 144 (widget escalation, `Insert Ticket` → row id 30), list of today's runs |

Scope covered: workflow structure and wiring, channel contracts, knowledge-base content, security
(secret + PII scan, public endpoint probe), accessibility rules in the widget, the widget's runtime
backend resolution, live answering paths over the public origin, artifact/deployment agreement.

**Not covered (no evidence either way):**

- Telegram and Gmail channels were not re-run today; their last verified live runs are 2026-09-18/19.
- Mobile browsers, Safari, Firefox and Edge were not exercised; only HTTP-level checks and a stubbed
  DOM were used (no real browser was driven).
- No screen-reader pass; accessibility evidence is limited to automated rules (labels, live region,
  dialog semantics, contrast ratios).
- No load test beyond 3 concurrent requests (the `concurrent_3_visitors` case).
- The CRM webhook remains a placeholder (`PUT_YOUR_CRM_WEBHOOK_URL`), so `Push to CRM` was not verified.
- No penetration testing: the public probes were read-only GETs plus the intended chat POST.
- Watchdog and zombie-cleanup recovery were not re-induced in this run (last induced verification:
  2026-09-20, `message_id` 35/36).

**Side effects of this test run (disclosed):** live paid API calls to DeepSeek and the embedding
provider; three ticket rows created in Supabase by escalation tests (incl. id 38); no data deleted,
no configuration changed, the knowledge base was not written to.

---

## C. Results table

| Test area | Status | Evidence | Notes |
|---|---|---|---|
| Static + contract suite (130 checks) | PASS | command 1 | areas: workflow 29, channels 23, reliability 17, UX 10, a11y 10, integration 10, safety 9, content 8, release 5, docs 4, security 3, quality 3 |
| Widget backend resolution + offline behaviour (new) | PASS | command 2 | file:// → local webhook; hosted → `backend.json`; missing `backend.json` → falls back; unreachable backend → fixed offline sentence, no HTTP code |
| Live end-to-end, local origin | PASS | command 3 | happy path, citation present, memory, escalation, injection refused, malformed/empty/oversized input, 3 concurrent visitors |
| Live end-to-end, public origin | PASS | command 4 | the deployed page's path works end to end |
| Cross-origin behaviour from the Pages origin | PASS | command 5 | CORS echo verified, answers grounded in the knowledge base |
| Deployment agreement (repo vs Pages) | PASS | command 6 | all three published files identical to `HEAD` |
| Public ingress | CONDITIONAL | command 7 | `/rest/login` returns 401 (good); the editor login page and `/healthz` are public; the chat webhook is unauthenticated by design → BUG-3 |
| Knowledge base content | **FAIL** | command 8 + BUG-2 repro | 5 chunks from 2 of the 3 documents; `policies.md` absent |
| Answer citation contract | **FAIL** | command 5 + BUG-1 repro | citation label is `[blob]` or a copy of the prompt example, not retrieval metadata |
| Escalation side effect (row actually written) | PASS | command 8 | `tickets` id 38 matches the question asked through the public origin |
| Secret / PII scan of the tracked tree | PASS | command 9 | no keys, no machine paths; only the intentional license line |
| Documentation accuracy | PASS after fix | command 1 (`T15.4`) | README quoted 128 checks against a real 130; the new check caught it, README corrected |

---

## D. Bug list

### BUG-1 — P1 — Answer citations do not come from the knowledge base

- **Reproduction:** `POST <public webhook>` `{"action":"sendMessage","sessionId":"x","chatInput":"What is in the Night Watch blend?"}`
  - actual: `… works well for drip and moka, and comes in 340 g ($19.00) or 1 kg ($48). [blob]`
  - also actual: `… is $22 for 250 g. [blob]`
  - expected: the answer ends with the real source file name, e.g. `[products.md]`
- **Second manifestation:** FAQ-style answers end with `[faq.md]`, which is the literal example in the
  agent's system prompt (`End every real answer with the source file name in square brackets, e.g. [faq.md]`).
  The model is echoing the example; it is not reading metadata.
- **Root cause:** every chunk in `documents` carries `metadata.source = "blob"` (the binary property name
  used at ingestion, not the uploaded file's name). The citation is therefore a model choice with no
  data behind it, while the prompt+workflow make the citation look authoritative.
- **Fix (not applied — needs a knowledge-base re-ingest and a workflow re-publish):**
  1. at ingestion, write the real file name into the chunk metadata (`Default Data Loader` metadata /
     form field name instead of `blob`);
  2. make the citation mechanical: append the retrieved chunks' `source` to the reply instead of asking
     the model for it;
  3. add a regression assertion: a citation must match one of the three known file names, and `[blob]`
     must fail.
- **Detected by:** manual probe in this run. The `citation_present` E2E case passes on any bracketed
  string, so it did not catch this — see section F.

### BUG-2 — P2 — `knowledge/policies.md` was never ingested, so the bot refuses questions its own documents answer

- **Reproduction:** `POST <public webhook>` `{"chatInput":"Do you offer hiring or franchise?"}`
  - actual: `I don't have that information - I've passed your question to our team …`
  - expected: `We do not offer franchise opportunities. [policies.md]` (the fact is in
    `knowledge/policies.md` line 23)
- **Root cause:** the live `documents` table holds 5 chunks, from `faq.md` (lines 1-34) and
  `products.md` (lines 1-26) only. `policies.md` is missing, while `README.md` (line 68 and line 131)
  states that three documents are ingested.
- **Fix:** re-ingest `knowledge/policies.md` through the ingestion form trigger, then re-run
  `python tests/e2e_live.py` and this repro. Owner action (writes to the live knowledge base).

### BUG-3 — P2 — Public ingress exposes the n8n login page and an unauthenticated chat endpoint

- **Reproduction:** `curl -o /dev/null -w "%{http_code}" <public>/home` → `200`; `<public>/rest/login` → `401`;
  `<public>/healthz` → `200`; the chat webhook accepts a POST from any client.
- **Impact:** anyone with the URL can attempt the editor login, and can consume the paid DeepSeek /
  embedding quota through the chat webhook. Not a product defect — a deployment boundary that the
  documentation already states.
- **Fix options:** keep the tunnel up only while demoing (current practice); or front it with
  Cloudflare Access; or move n8n to a VPS with authentication when the demo needs 24/7 answers.

### BUG-4 — P3 — Documentation drift on the check count (fixed, now guarded)

- README quoted "128 static + contract checks" while the suite ran 130. The new `T15.4` check compares
  the README number with the suite's real total, so the drift fails the suite from now on.

### BUG-5 — P3 — Line endings make local/dev-deployed hash comparisons misleading

- `demo/publish-backend-url.ps1` writes LF; the git working tree checks files out as CRLF, so
  `sha256sum site/backend.json` differs from the published copy while the committed content is
  identical. Cosmetic; reported because it wastes debugging time. Fix: compare against `git show HEAD:`
  (as done in command 6).

### BUG-6 — P3 — Fixed during this run: suite assumptions vs. the new widget

- After the widget gained runtime backend resolution, `T11.1`/`T11.2` failed (`data-webhook` was
  renamed) and `T14.1` reported a false secret (`sb_secret_...` as a literal in the setup notes).
- Fixed: the webhook check accepts `data-webhook` or `data-local-webhook`; new `T11.3` validates
  `site/backend.json`; the secret pattern now requires a realistic key length.

---

## E. Files changed and why

| File | Change | Reason |
|---|---|---|
| `tests/qa_suite.py` | `T11.1`/`T11.2` accept both webhook attributes; new `T11.3` (hosted `backend.json`), `T23.2` (the widget parses), `T15.4` (README check count); `_js_syntax_error` helper; secret pattern length; plain-language comments | keep the suite true after the widget change; guard the new artifact; close the documented-count drift |
| `tests/widget_dom_test.js` | new file, 8 cases in a stubbed DOM | the widget's backend resolution and offline behaviour had no test |
| `tests/qa-results.json`, `tests/e2e-results.json`, `tests/widget_dom-results.json` | refreshed | machine-readable evidence for this report |
| `README.md` | check count 130, DOM suite row added | documentation accuracy (`T15.4` enforces it) |
| `site/widget.js`, `site/index.html` | earlier pass in this session: no em dashes/arrows, shorter comments, simpler `aria-label` | requested style pass; behaviour unchanged (re-verified by commands 2, 3, 4) |

---

## F. Remaining risks, limitations, next steps

1. **The citation case is too weak.** `tests/e2e_live.py::citation_present` accepts any bracketed text,
   which is why BUG-1 survived a green run. Replace it with "the citation equals one of the known
   document names" and let `[blob]` fail.
2. **The live knowledge base is not covered by the static suite** (it needs credentials and network).
   BUG-2 was only visible by reading the store. Either add an opt-in live check or verify the store
   before each demo.
3. **Availability is bounded by the machine being awake.** The hosted page always loads; answers stop
   when the laptop sleeps, and the tunnel hostname changes on every restart (`demo\publish-backend-url.bat`
   refreshes `site/backend.json`). 24/7 answers require a VPS.
4. **Telegram and Gmail were not re-run today.** Add them to the pre-demo checklist or to an opt-in
   E2E run.
5. **Accessibility evidence is automated only** (labels, live region, dialog role, contrast). Keyboard
   order and screen-reader behaviour were not exercised.
6. **No monitoring or error budget** beyond the Telegram alert from the `Error Trigger` workflow and
   the watchdog's own alerts.

Next actions, in order: (1) re-ingest `knowledge/policies.md`; (2) fix the citation metadata + make the
citation mechanical; (3) tighten the citation E2E case; (4) re-run commands 1-4 and confirm BUG-1 and
BUG-2 are gone.

---

## G. Release-readiness checklist

| Item | State |
|---|---|
| Static suite, lint-equivalent checks, JS parse gates | PASS (130 checks) |
| Critical journeys pass (website path, local + public) | PASS (8 DOM + 10 live cases) |
| No unresolved P0/P1 | **NO** — BUG-1 open (P1) |
| No known high-severity security issue or data leak | PASS for secrets/PII; ingress exposure documented as BUG-3 |
| Rollback / recovery path exists and is documented | PASS — watchdog + zombie cleanup + documented start/stop (`docs/operations.md`) |
| Operational documentation exists | PASS — `docs/operations.md`, `docs/client-setup-guide.md`, `docs/acceptance-checklist.md` |
| Deployment matches the repository | PASS (command 6) |
| Remaining P2/P3 documented with impact | PASS — this section and D |
| Knowledge base matches the documented content | **NO** — BUG-2 open (P2) |
