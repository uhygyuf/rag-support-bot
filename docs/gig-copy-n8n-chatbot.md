# Fiverr gig copy — AI support chatbot (n8n + RAG), market-modeled 2026-09-17

Derived from a live scrape of the niche: **111 competing gigs** (start price, rating, reviews) plus
**full page extraction of the 12 best-selling ones** (package tables, FAQ, portfolio entries).

## Market evidence

| Comparable gig | Reviews | Basic | Standard | Premium | Days |
|---|---|---|---|---|---|
| AI customer support agent (Pro, "no monthly fees") | 47 | $450 | $1,500 | $3,200 | 7 / 14 / 21 |
| Customer support AI chatbot | 24 | $300 | $2,000 | $10,000 | 7 / 14 / 21 |
| RAG + AI agent system | 104 | $150 | $650 | $1,250 | 2 / 7 / 10 |
| n8n automation + AI agents | 37 | $150 | $750 | $1,500 | 5 / 14 / 21 |

- Start-price distribution over 111 gigs: 25th $30 · **median $90** · 75th $150.
- **Established sellers (≥50 reviews) median start $50; zero-review sellers median $90** — new sellers
  price higher and sell less. Credibility, not price, is the bottleneck.
- Market ratios: Standard ≈ 2.5–5× Basic, Premium ≈ 5–10× Basic.
- The rows buyers actually compare: **Delivery time (12/12), Revisions (10/12), Source code (5/12)**.

### What every top gig does (patterns to copy)

1. Title = deliverable + outcome ("build an AI customer support agent you own, no monthly fees").
2. Opening line names the **pain**, not the technology ("Most clients who find me already paid for an
   AI project that never reached production…").
3. **Ownership is the hook**: "runs on your server", "no monthly fees", "no vendor lock-in",
   "you own it" — repeated in the description *and* in the FAQ.
4. 5–6 FAQ entries answering exactly: what do I get · do I pay a subscription · what do you need from
   me · what about channels/integrations · how does human handoff work · what if the answer is wrong.
5. Portfolio entries are named projects with a one-paragraph description, tech tags, **project cost**
   and **project duration**.
6. They refuse bad-fit work in writing ("No demos, only real world systems", "I don't do homework") —
   it protects the review score.

---

## Description (≤1200 chars — 1003 used)

```
Your website loses customers every night and every weekend: the same questions sit unanswered until someone wakes up.

I build an AI support assistant that answers them 24/7 using ONLY your own documents - your FAQ, product pages, policies and PDFs. It shows the source of every answer, says "I don't know" instead of inventing one, and turns anything it cannot answer into a ticket for your team.

What you get:
- Answers from your documents, with the source file shown
- No guessing: unanswerable questions become tickets, never fiction
- Human handoff, so no customer is ever stuck
- You own it: the full n8n workflow is delivered as a file, no monthly fee to me
- Branded chat widget with a welcome message and one-click starting questions

Built with n8n + a vector database + your own AI key (DeepSeek or OpenAI), so you control the running cost: roughly 3-9 RMB per 1,000 questions.

Send me your website and the questions your customers ask most. I will confirm the exact scope before you order.
```

## FAQ (answer limit 400 chars — all pass)

1. **What exactly do I get?**
   A working AI chat assistant on your website, trained on your documents, plus the complete n8n
   workflow file, setup guide and an acceptance checklist. You own everything after delivery.
2. **Do I pay a monthly fee to you?**
   No. You pay once. The assistant runs in your n8n workspace with your own AI key and database, so
   there is no subscription to me and no lock-in.
3. **What do you need from me to start?**
   Your documents (FAQ, policies, product info or PDFs), your website address and an AI API key
   (DeepSeek or OpenAI). If you do not have a key yet, I send a 2-minute guide.
4. **What happens when it does not know the answer?**
   It never invents one. It says it cannot answer, saves the question as a ticket and tells the
   customer a human will follow up - so you keep the lead instead of letting it disappear.
5. **Can it be connected to WhatsApp, Slack or my CRM?**
   Website chat and ticket storage are in every package. Extra channels and CRM/email/Slack
   integration are available in the Premium package - tell me what you use.
6. **What if an answer is wrong?**
   Send me the question and the correct answer. Rules are tuned within your revision scope and the
   knowledge base updated. Unsure questions are never answered automatically.

## Requirements (modeled on the top gigs)

| # | Type | Text |
|---|---|---|
| R1 | Free text | What should the assistant know? Send your documents (FAQ, policies, product info) or the links. |
| R2 | Free text | Where will the chat window live? Give the website URL, plus the title and greeting you want. |
| R3 | Free text | Where should unanswered questions go? (email address or "tickets only") |
| R4 | Multiple choice | Do you have an AI API key? A) Yes, I will send it in the order chat. B) No, send me the 2-minute guide. |
| R5 | Free text | Anything the assistant must NEVER say or promise? (claims, prices, legal wording) |

## Row-by-row reference for the Scope & Pricing table (market evidence)

Evidence: raw HTML of the best-selling RAG/agent gig (`usman_choudhary`, **104 reviews**,
$150/$650/$1250, 2/7/10 days) showed its **Basic** package already includes *AI model integration,
Database integration, Source code, Detailed code comments* + *Unlimited revisions*. The other rows
come from the package tables of the 12 best-selling gigs (labels, values, days, revisions).
Fiverr rate-limits full-page fetches after the first one, so per-tier checkmarks could only be
verified for that gig.

| Fiverr row | What the popular gigs do (evidence) | Your value |
|---|---|---|
| Implementations | fixed AI-category row; top gigs express scale through package names (Basic `AI Starter Integration` → Standard `RAG + AI Agent System` → Premium `Enterprise AI Architecture`) | `1 / 2 / 3` |
| AI agents | same gig: "multi tool AI agent logic" only from Standard, "multi agent" at Premium — agent capability climbs with tier | `1 / 1 / 2` |
| Database integration | **Basic of the 104-review gig includes it** — in RAG gigs the database is baseline, not an upgrade | **tick all three** |
| Training | none of the 12 comparable gigs sells "training"; only adjacent-category gigs list "AI Model Fine-tuning" (2/12) | leave unticked |
| Documentation | top gigs differentiate on artefacts (Source code 5/12, Detailed code comments 1/12) | tick all three |
| Revisions | present in 10/12; n8n gigs use *Unlimited* on all tiers, RAG gigs use 1/2/3 | `1 / 2 / 3` (or Unlimited on Basic to win the first order) |
| Delivery time | RAG gigs 2/7/10 · chatbot gigs 3/7/14–21 · n8n gigs 5/14/21 | `4 / 7 / 14` |
| Price | see the market table above | `$149 / $390 / $750` |

Model to copy for the advertised inclusions (the 104-review gig's Basic): an AI-model integration,
a database/vector store, the source of the build, and detailed documentation. In your delivery those
map to: your model wired (DeepSeek/OpenAI) · Supabase knowledge base · the `workflow.json` · the
setup guide + acceptance checklist.

## Portfolio entry (market format)

- **Project name:** AI Support Chatbot for a Coffee Roastery (n8n + Supabase + DeepSeek)
- **Description:** Demo store with 30+ FAQ, product and policy pages. The assistant answers only from
  those documents, cites the source file of every answer, refuses instead of guessing, keeps
  multi-turn context, and creates a support ticket when it cannot answer. Includes a branded chat
  widget with a welcome message and one-click starting questions.
- **Tags:** n8n · RAG · Chatbot development · Supabase · AI integrations · Customer support
- **Project cost:** $150–$750 · **Project duration:** 4–14 days
