# Acceptance checklist — AI support chatbot

**How to use:** after setup, run these 8 checks with the client present (or record them once and attach
the video). When all 8 pass, the delivery is complete. Anything that fails is a defect under the
revision/tuning scope — send the exact question and the exact reply.

Test in the n8n **Chat** panel, or on the client's website once embedded.

| # | Check | How to test | Pass looks like |
|---|---|---|---|
| 1 | Answers from the documents | Ask a question your documents answer (e.g. *"How long does US shipping take?"*) | A correct answer, ending with the source file name in brackets, e.g. `… 2–4 business days. [faq.md]` |
| 2 | Uses the client's own facts, not general knowledge | Ask about a price or policy that only appears in the documents | The value from the documents — not a generic or invented figure |
| 3 | Says "I don't know" instead of guessing | Ask something the documents do not cover (e.g. *"Are you hiring baristas?"*) | It does **not** invent an answer; it replies that the question has been passed to a human |
| 4 | Creates a ticket for the unanswered question | After check 3, open Supabase → Table Editor → `tickets` | A new row whose `question` column contains that question |
| 5 | Multi-turn context works | Ask *"Do you ship to Canada?"* then, in the same chat session, *"How long does it take?"* | The second answer refers to Canada (7–14 business days), not to a generic shipping time and not "I don't know" |
| 6 | Chat window works on the website | Open the client's page, click the chat button, send any question | The window opens, shows the question and the bot's answer; no error text |
| 7 | Knowledge base can be updated by the client | Upload a new/edited document through the form, then ask a question answered only by the new text | The new answer comes back with the new file name as its source |
| 8 | Restart safety (persistence) | Restart n8n (or wait a day), then ask check 1's question again | The same correct answer — the knowledge base is in Supabase, not in memory |

**Also confirmed at handover**

- [ ] The client can open n8n, see the workflow, and find the `tickets` table
- [ ] The client knows where their API keys are and how to top up the DeepSeek balance
- [ ] The workflow is published, and the chat URL is embedded on the site
- [ ] The client knows: to change an answer, edit the document and re-upload it (and delete the old version's rows)
- [ ] Boundaries agreed in writing: what is included, revision limits, and what is quoted separately
      (hosting/VPS, extra channels such as WhatsApp, custom UI redesign)

**Not covered by this acceptance (state it explicitly to the client)**

- Answer accuracy for questions whose wording appears nowhere in the documents (the bot escalates instead)
- Traffic/abuse protection at scale (a reverse proxy with rate limiting belongs to the hosting add-on)
- Non-English documents, unless the documents themselves are non-English
- Behaviour on browsers other than the one used for the checks above
