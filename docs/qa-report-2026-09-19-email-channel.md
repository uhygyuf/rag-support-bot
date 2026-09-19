# QA report — Gmail API email channel (live, 2026-09-19)

Third QA round for this project, and the first one that exercises a channel against a **real
mailbox instead of fixtures**. Everything below was observed in n8n execution data and
independently cross-checked against the Gmail API; nothing is inferred.

## Scope

The `Support Bot — Email channel (Gmail API)` workflow (18 nodes): Gmail trigger on the `+support`
alias → parser → alias gate → shared Agent/knowledge base → escalation branch (ticket → CRM push →
Telegram alert) → threaded reply → mark handled as read.

Out of scope: website widget, Telegram channel, error alerts (covered in
`qa-report-2026-09-18-rev2.md`).

## Method

1. Real messages sent from a normal Gmail account to the `+support` alias.
2. After each run: the execution record read from the n8n database (node-by-node outputs).
3. Independent cross-check through the Gmail API (thread membership, labels, message body) using
   the same OAuth credential — the workflow's own claim is never the evidence.
4. Every fix re-tested with a fresh inbound mail; the QA suite extended so each defect stays fixed.

## Evidence

| Exec | Mode | Result | What it proved |
|---|---|---|---|
| 110 | manual | error | `Credential with ID "PUT_GMAIL_OAUTH_CRED" does not exist` — the shipped JSON still carried the placeholder id |
| 111 | trigger | success | Trigger + parser ran, then the alias gate dropped the mail (owner's own address) |
| 112 | trigger | success | Escalation path end-to-end: ticket + CRM push + Telegram + reply |
| 113 | trigger | success | Parser/gate fixed, but question empty (subject-only mail) and reply opened a new thread |
| 114 | trigger | success | **Full happy path**: KB answer with citation, threaded reply, original marked read |

## Defects

| ID | Sev | Defect | Root cause | Fix |
|---|---|---|---|---|
| B11 | P1 | Alias gate silently ignored legitimate mail from the owner's address | Gate had a second rule `from notContains <owner>` left over from an anti-loop attempt | Rule removed; the server-side `to:+support` filter already prevents loops |
| B12 | P1 | Every parsed field empty (`question`, `from`, `to`, `subject`) | Parser read the raw Gmail API shape (`payload.headers`, base64 parts); the trigger returns a structured item (`from: {value:[{address}]}`, `text`) | Parser accepts both shapes; regression guard T27.2 |
| B13 | P2 | Reply created a **new** thread instead of answering in the customer's | Node used `message: send`; the send operation has no `threadId` parameter (`options.threadId` only exists for drafts) | Switched to `message: reply` with the parsed `messageId` — Gmail adds `In-Reply-To`/`References`; guard T27.5 |
| B14 | P2 | `Mark handled as read` failed with `Bad request - please check your parameters` | The field carried the RFC header id (`<...@mail.gmail.com>`); the API needs the Gmail message id | Parser returns `messageId: m.id` and keeps the RFC id separately; guard T27.4 |
| B15 | P3 | Subject-only mail got a useless greeting reply ("I'm ready to help…") | Parser used the body only; an empty body produced an empty question | Empty body falls back to the subject; guard T27.3 |

## Verification of the final state (exec 114)

| Requirement | Evidence |
|---|---|
| Question parsed from the mail | `question: "Do you ship to Canada?"` |
| Answer grounded in the knowledge base | `"Yes! We ship to Canada (plus the EU, UK and Australia), with delivery in 7–14 business days. Customs duties are paid by the customer. [faq.md]"` |
| Reply in the customer's thread | reply `threadId 1a0ba041…` = the inbound thread; Gmail API shows 2 messages in that thread |
| Original marked handled | message returned with labels `['SENT','INBOX']` — `UNREAD` removed, no error |
| No false escalation | ticket/CRM/Telegram nodes did not run |
| Escalation still works (exec 112) | ticket row + CRM push + Telegram alert + "passed to our team" reply |

## Suite status

`python tests/qa_suite.py` → **127/127 PASS** (was 122). New checks T27.1–T27.5 pin each fix;
T26.3 and T26.7 were updated because the threaded-reply change and the new parser helper names made
their original assertions stale — a passing suite that asserts the old behaviour would have hidden
B13 and B12.

## Residual risks

- Delivery depends on the client's own Google Cloud project staying valid (test users list, or the
  app published); an expired/revoked OAuth grant stops the channel silently until the alerting
  workflow reports the failing run.
- Only mail newer than the last check is handled (anti-duplicate), and only **unread** mail: reading
  a customer mail manually before the poll can skip it. Documented in `docs/operations.md` §3.1.
- No ticket dashboard yet: escalations are visible as Supabase rows plus the Telegram message.
