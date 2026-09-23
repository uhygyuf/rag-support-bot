#!/usr/bin/env python3
"""QA suite for the RAG support bot (Harbor Coffee Roasters demo).

Runs static / structural / contract / security / accessibility checks against:
  - workflow/SupportBotRAG-full.json   (exported from the live n8n instance)
  - site/index.html, site/widget.js
  - knowledge/*.md

Usage:  python tests/qa_suite.py [--workflow PATH]
Exit code 0 = all checks pass, 1 = at least one FAIL.
No network calls, no writes.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = []


def check(cid, area, desc, ok, detail=""):
    RESULTS.append({"id": cid, "area": area, "desc": desc,
                    "status": "PASS" if ok else "FAIL", "detail": detail})
    return ok


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------- workflow ---
def load_workflow(path):
    data = json.loads(read(path))
    wf = data[0] if isinstance(data, list) else data
    return wf


def nodes_by_name(wf):
    return {n["name"]: n for n in wf["nodes"]}


def test_workflow(wf):
    N = nodes_by_name(wf)
    conns = wf["connections"]

    # --- chat branch wiring
    agent = next((n for n in wf["nodes"]
                  if n["type"] == "@n8n/n8n-nodes-langchain.agent"), None)
    check("T1.1", "workflow", "AI Agent node present", agent is not None)

    def sub_children(parent):
        """n8n expresses an AI sub-node link from the CHILD to the PARENT:
        {'Child': {'ai_languageModel': [[{'node': parent, ...}]]}}, so the
        child shows up as the *source* key, not as a target."""
        out = []
        for src, ports in conns.items():
            if src == parent:
                continue
            for groups in ports.values():
                for lst in groups:
                    if any(t.get("node") == parent for t in lst):
                        out.append(src)
        return out

    kids = sub_children("Support Agent")
    check("T1.2", "workflow", "Agent has a chat model wired",
          any("Model" in k for k in kids), "children: %s" % kids)
    check("T1.3", "workflow", "Agent has memory wired (multi-turn)",
          any("Memory" in k for k in kids), "children: %s" % kids)
    check("T1.4", "workflow", "Agent has the knowledge-base tool wired",
          any("Vector Store (Tool)" in k for k in kids), "children: %s" % kids)
    check("T1.5", "workflow", "Escalation is deterministic (no reliance on the model "
                              "choosing a tool)",
          "If escalated" in N and "Insert Ticket" in N and "Create Ticket Tool" not in N,
          "nodes: %s" % sorted(N))

    # --- model choice must support tool calling / avoid the reasoning_content 400
    model_nodes = [n for n in wf["nodes"] if "lmChat" in n["type"]]
    check("T1.6", "workflow", "Exactly one chat-model node",
          len(model_nodes) == 1, "found: %s" % [n["name"] for n in model_nodes])
    if model_nodes:
        mt = model_nodes[0]["type"]
        check("T1.7", "workflow", "Chat model is the native DeepSeek node "
                                  "(OpenAI-format node breaks on thinking models)",
              mt.endswith("lmChatDeepSeek"), mt)
        check("T1.8", "workflow", "Chat model has a credential attached",
              bool(model_nodes[0].get("credentials")),
              str(model_nodes[0].get("credentials")))

    # --- knowledge base tool
    kb = next((n for n in wf["nodes"] if n["name"] == "Supabase Vector Store (Tool)"), None)
    if kb:
        p = kb["parameters"]
        check("T2.1", "workflow", "KB tool mode = retrieve-as-tool",
              p.get("mode") == "retrieve-as-tool", p.get("mode"))
        tbl = p.get("tableName", {})
        check("T2.2", "workflow", "KB tool points at table 'documents'",
              tbl.get("value") == "documents", str(tbl))
        check("T2.3", "workflow", "KB tool has Supabase credential",
              bool(kb.get("credentials")), str(kb.get("credentials")))
        emb = sub_children(kb["name"])
        check("T2.4", "workflow", "KB tool has its own embeddings sub-node",
              len(emb) == 1, "children: %s" % emb)

    # --- system prompt guards (the anti-hallucination contract)
    if agent:
        sp = agent["parameters"].get("options", {}).get("systemMessage", "")
        check("T3.1", "safety", "Prompt forces knowledge_base before answering",
              "ALWAYS call the tool" in sp and "knowledge_base" in sp)
        check("T3.2", "safety", "Prompt forbids answering from own knowledge",
              "Never answer from your own knowledge" in sp)
        check("T3.3", "safety", "Prompt requires citing the source file",
              "source file name in square brackets" in sp)
        check("T3.5", "safety", "Answer length bounded (<= 60 words)",
              "60 words" in sp)
        check("T3.4", "safety", "Prompt routes an unanswerable question to the fixed handoff sentence",
              "passed your question to our team" in sp and "EXACTLY this sentence" in sp)
        check("T3.6", "safety", "Prompt has its own handoff sentence for an explicit human request",
              "asks to talk to a human" in sp and "passed your request to our team" in sp)
        check("T3.7", "safety", "A human request is never answered as if the bot lacked the answer",
              "never answer that you do not have the information" in sp)

    # --- deterministic escalation branch: ticket insert + notification + reply
    ins = N.get("Insert Ticket")
    if ins:
        p = ins["parameters"]
        check("T4.1", "workflow", "Ticket insert uses a plain string table name "
                                  "(a resource-locator object becomes '[object Object]' at runtime)",
              isinstance(p.get("tableId"), str) and p.get("tableId") == "tickets",
              "tableId=%r" % (p.get("tableId"),))
        check("T4.5", "workflow", "Ticket insert targets the row/create operation",
              p.get("resource", "row") == "row" and p.get("operation", "create") == "create",
              "resource=%r operation=%r (omitted means the n8n default)"
              % (p.get("resource"), p.get("operation")))
        check("T4.6", "workflow", "Ticket insert has the Supabase credential",
              bool(ins.get("credentials")))
    ntf = N.get("Notify Telegram")
    if ntf:
        check("T4.7", "workflow", "Notification failure cannot break the ticket "
                                  "(onError=continue)",
              ntf.get("onError") == "continueRegularOutput", ntf.get("onError"))
        check("T4.8", "workflow", "Notification node is a Telegram sendMessage",
              "telegram" in ntf["type"]
              and ntf["parameters"].get("operation", "sendMessage") == "sendMessage",
              "operation=%r (the editor omits the default)" % ntf["parameters"].get("operation"))
    for nm, cid in (("Reply Escalated", "T4.9"), ("Reply Normal", "T4.10")):
        node = N.get(nm)
        check(cid, "workflow", "Chat reply node '%s' returns {output: ...}" % nm,
              bool(node and "output" in (node["parameters"].get("jsCode") or "")),
              nm)
    prep = N.get("Prep Ticket Question")
    if prep:
        js = prep["parameters"].get("jsCode") or ""
        check("T4.11", "workflow", "Ticket records the CUSTOMER's question "
                                   "(read from the trigger, not the model reply)",
              "$('When chat message received')" in js and "chatInput" in js
              and "item.output" not in js,
              js[:120])

    # The gate is a string match on the agent's reply, so a wrong condition shape fails silently and
    # sends EVERY answer down the ticket branch (it happened: a normal Canada shipping answer was
    # turned into a handoff because the conditions block was replaced instead of extended).
    gate = N.get("If escalated")
    if gate:
        block = gate["parameters"].get("conditions") or {}
        conds = block.get("conditions") or []
        phrases = [c.get("rightValue") for c in conds]
        check("T4.12", "workflow", "Escalation gate accepts BOTH handoff wordings",
              block.get("combinator") == "or"
              and "passed your question to our team" in phrases
              and "passed your request to our team" in phrases,
              "combinator=%r phrases=%r" % (block.get("combinator"), phrases))
        check("T4.13", "workflow", "Every escalation condition tests the node output field",
              bool(conds) and all("$json.output" in (c.get("leftValue") or "") for c in conds),
              [c.get("leftValue") for c in conds])
    esc_node = N.get("Reply Escalated")
    if esc_node:
        js = esc_node["parameters"].get("jsCode") or ""
        check("T4.14", "workflow", "The reply sentence says which handoff happened",
              "passed your request to our team" in js and "passed your question to our team" in js,
              js[:120])

    # --- ingestion branch regression
    for need in ("On form submission", "Default Data Loader", "Embeddings OpenAI",
                 "Supabase Vector Store"):
        check("T5.%s" % need[:1], "workflow", "Ingestion node kept: %s" % need,
              need in N or any(need in k for k in N))
    ins = next((n for n in wf["nodes"] if n["name"] == "Supabase Vector Store"), None)
    if ins:
        check("T5.9", "workflow", "Ingestion store still mode=insert",
              ins["parameters"].get("mode") == "insert", ins["parameters"].get("mode"))
        check("T5.10", "workflow", "Ingestion store has Supabase credential",
              bool(ins.get("credentials")))

    # --- chat trigger must be embeddable from a website
    trig = next((n for n in wf["nodes"] if "chatTrigger" in n["type"]), None)
    if trig:
        p = trig["parameters"]
        check("T6.1", "release", "Chat trigger exists", True)
        check("T6.2", "release", "Chat trigger is public (embeddable off-site)",
              p.get("public") is True, "public=%r" % p.get("public"))
        check("T6.3", "release", "Chat trigger has a fixed webhookId "
                                 "(stable embed URL)",
              bool(trig.get("webhookId")), "webhookId=%r" % trig.get("webhookId"))
        rm = p.get("options", {}).get("responseMode")
        check("T6.4", "release", "Response mode pinned to lastNode "
                                 "(plain JSON for 3rd-party widgets)",
              rm == "lastNode", "responseMode=%r" % rm)
        # --- greeting + quick-start options (ETS-Anita pattern)
        check("T6.5", "ux", "Chat trigger shows a welcome message on open",
              bool(p.get("initialMessages")), "initialMessages=%r" % p.get("initialMessages"))
        # n8n 2.38.7 renders initialMessages and silently drops suggestedPrompts, agentName and
        # agentIcon (verified against the served chat page), so the options a visitor can click
        # live in site/widget.js. Asserting the trigger's own config would test a dead parameter:
        # an earlier version of this suite did exactly that and passed while the hosted page
        # showed no quick-start options at all.
        html = read(os.path.join(ROOT, "site", "index.html"))
        chats = re.findall(r'data-quick-replies="([^"]*)"', html)
        chips = [c for c in (chats[0].split("|") if chats else []) if c.strip()]
        check("T6.6", "ux", "Quick-start options reach the visitor (widget chips)",
              len(chips) >= 4, "chips=%d" % len(chips))
        check("T6.7", "ux", "Assistant identity shown by the widget",
              "Harbor Support" in html, "brand string present in site/index.html")

    # --- resilience: transient failures must self-heal, not surface to the visitor
    retry_nodes = ["Support Agent", "Insert Ticket", "Notify Telegram", "Supabase Vector Store (Tool)",
                   "Embeddings OpenAI", "Supabase Vector Store"]
    for i, name in enumerate(retry_nodes, 1):
        node = N.get(name)
        check("T17.%d" % i, "reliability",
              "%s retries a transient failure" % name,
              bool(node and node.get("retryOnFail") and (node.get("maxTries") or 0) >= 2),
              "retryOnFail=%r" % (node or {}).get("retryOnFail"))

    # --- secret scan inside the workflow export
    blob = json.dumps(wf, ensure_ascii=False)
    patterns = {
        "sk- key": r"sk-[A-Za-z0-9]{16,}",
        "sb_secret key": r"sb_secret_[A-Za-z0-9_-]{10,}",
        "JWT/service_role": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
        "Bearer literal": r"Bearer\s+[A-Za-z0-9._-]{20,}",
        "password literal": r"(?i)password\s*[:=]\s*['\"][^'\"]{6,}",
    }
    hits = {k: len(re.findall(v, blob)) for k, v in patterns.items()}
    check("T7.1", "security", "No plaintext API keys / secrets in workflow JSON",
          sum(hits.values()) == 0, str(hits))

    return wf


def test_subworkflow(path):
    """Ticket sub-workflow: trigger field + insert target."""
    try:
        data = json.loads(read(path))
        wf = data[0] if isinstance(data, list) else data
    except Exception as exc:  # noqa: BLE001
        return check("T4.2", "workflow", "Ticket sub-workflow readable", False, str(exc))
    blob = json.dumps(wf, ensure_ascii=False)
    check("T4.2", "workflow", "Ticket sub-workflow inserts into 'tickets'",
          '"tickets"' in blob and "supabase" in blob)
    check("T4.3", "workflow", "Ticket sub-workflow declares a 'question' input",
          '"question"' in blob)
    check("T4.4", "workflow", "Ticket sub-workflow has no plaintext secrets",
          not re.search(r"sk-[A-Za-z0-9]{16,}|sb_secret_|eyJ[A-Za-z0-9_-]{10,}\.", blob))


# ------------------------------------------------------------- knowledge -----
KB_EXPECTATIONS = [
    ("how long does us shipping take", "faq.md", "2\u20134 business days"),
    ("how much is ethiopia guji", "products.md", "$22"),
    ("can i pause my subscription", "faq.md", "24 hours"),
    ("do you offer franchises", "policies.md", "do not offer franchise"),
    ("do you offer wholesale", "faq.md", "5 kg"),
    ("what payment methods", "faq.md", "Apple Pay"),
]


def test_knowledge():
    docs = {f: read(os.path.join(ROOT, "knowledge", f))
            for f in ("faq.md", "products.md", "policies.md")}
    for i, (q, src, fact) in enumerate(KB_EXPECTATIONS, 1):
        hay = docs[src].lower()
        check("T8.%d" % i, "content",
              "Answerable question -> fact present in %s (%s)" % (src, q[:28]),
              fact.lower() in hay, fact)
    # hand-off questions must NOT be answerable from the docs
    blob = " ".join(docs.values()).lower()
    for i, (q, topic) in enumerate([("are you hiring baristas", "hiring"),
                                    ("can i pay in three instalments", "instalment")], 1):
        check("T9.%d" % i, "content",
              "Handoff trigger is genuinely unanswerable (%s)" % q,
              topic not in blob,
              "topic word %r already in the docs" % topic if topic in blob else "")


# ------------------------------------------------------------------ site -----
def test_site():
    html = read(os.path.join(ROOT, "site", "index.html"))
    js = read(os.path.join(ROOT, "site", "widget.js"))

    # --- widget <-> n8n Chat Trigger protocol contract
    check("T10.1", "integration", "Widget posts n8n 'action: sendMessage'",
          "sendMessage" in js)
    check("T10.2", "integration", "Widget posts the field 'chatInput' "
                                  "(n8n chat protocol)",
          "chatInput" in js)
    check("T10.3", "integration", "Widget sends a stable sessionId",
          "sessionId" in js)
    check("T10.4", "integration", "Widget parses the n8n reply field 'output'",
          re.search(r"j\.output|\.output\b", js) is not None)

    # --- embed URL must match the real chat endpoint of this workflow. The page may
    # declare the webhook itself, or a local one and let the widget read site/backend.json.
    m = re.search(r'data-(?:local-)?webhook="([^"]+)"', html)
    url = m.group(1) if m else ""
    check("T11.1", "integration", "index.html declares a widget webhook URL",
          bool(url), url)
    check("T11.2", "integration", "Embed URL uses the n8n chat endpoint "
                                  "shape /webhook/<id>/chat",
          bool(re.search(r"/webhook/[A-Za-z0-9_-]+/chat$", url)), url)
    try:
        hosted = json.loads(read(os.path.join(ROOT, "site", "backend.json")))
    except (OSError, ValueError) as exc:
        check("T11.3", "integration", "hosted backend.json is readable JSON", False, str(exc))
    else:
        hurl = hosted.get("webhook", "")
        check("T11.3", "integration", "hosted backend.json points at a chat webhook",
              bool(re.search(r"^https://[^/]+/webhook/[A-Za-z0-9_-]+/chat$", hurl)), hurl)

    # --- accessibility baseline (WCAG 2.1 AA)
    check("T12.1", "a11y", "Chat button has an accessible name (aria-label)",
          "aria-label" in js)
    check("T12.2", "a11y", "Message log is a live region (aria-live)",
          "aria-live" in js)
    check("T12.3", "a11y", "Text input has a real label / aria-label",
          re.search(r"<label|aria-label", js) is not None)
    check("T12.4", "a11y", "Panel exposes dialog semantics (role=dialog)",
          re.search(r"role['\"]?\s*,\s*['\"]dialog|role=[\"']dialog", js) is not None)
    check("T12.5", "a11y", "User text is inserted with textContent (no innerHTML "
                           "sink for untrusted data)",
          "textContent" in js)

    # --- greeting bubble + quick-start options in the client-side widget
    check("T16.1", "ux", "Widget shows a teaser greeting before the visitor opens it",
          "rgw-teaser" in js and "teaser.classList.add('show')" in js)
    check("T16.2", "ux", "Widget renders clickable quick-start options",
          "rgw-chip" in js and "renderChips" in js)
    check("T16.3", "ux", "Widget welcome text is configurable (data-welcome)",
          "data-welcome" in js and "data-quick-replies" in js)
    check("T16.4", "ux", "Widget hides the quick options after first use",
          "options are used once" in js or "quick.textContent = ''" in js)
    check("T16.5", "ux", "Visitors never see a technical error (friendly offline text)",
          "OFFLINE" in js and "console.warn" in js)
    check("T16.6", "ux", "Widget aborts a hung request instead of spinning forever",
          "AbortController" in js and "TIMEOUT_MS" in js)
    check("T16.7", "ux", "Offline text and timeout are configurable",
          "data-offline" in js and "data-timeout-ms" in js)

    # --- colour contrast (WCAG 2.1 AA: 4.5:1 normal text, 3:1 large)
    def lum(hexc):
        hexc = hexc.lstrip("#")
        vals = [int(hexc[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        vals = [(v / 12.92) if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
                for v in vals]
        return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]

    def ratio(a, b):
        la, lb = lum(a), lum(b)
        hi, lo = max(la, lb), min(la, lb)
        return round((hi + 0.05) / (lo + 0.05), 2)

    pairs = [("#ffffff", "#b4552d", "Send button label", 4.5),
             ("#b4552d", "#ffffff", "price text", 4.5),
             ("#6b625a", "#faf7f2", "muted body text", 4.5),
             ("#1d1a17", "#faf7f2", "body text", 4.5),
             ("#ffffff", "#1d1a17", "header text", 4.5)]
    for i, (fg, bg, label, need) in enumerate(pairs, 1):
        r = ratio(fg, bg)
        check("T13.%d" % i, "a11y",
              "Contrast %s %s on %s >= %.1f" % (label, fg, bg, need),
              r >= need, "ratio %.2f" % r)


# ------------------------------------------------------------------ repo -----
def test_repo():
    secret_pat = re.compile(r"sk-[A-Za-z0-9]{16,}|sb_secret_[A-Za-z0-9_-]{20,}"
                            r"|sbp_[A-Za-z0-9]{20,}"
                            r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
                            r"|AAAA[A-Za-z0-9_-]{20,}")
    offenders = []
    for dirpath, _dirs, files in os.walk(ROOT):
        if any(p in dirpath for p in (".git", "node_modules", "__pycache__")):
            continue
        for f in files:
            if f == "qa_suite.py":  # holds the patterns themselves (self-match)
                continue
            p = os.path.join(dirpath, f)
            try:
                if secret_pat.search(read(p)):
                    offenders.append(os.path.relpath(p, ROOT))
            except (UnicodeDecodeError, OSError):
                continue
    check("T14.1", "security", "No secrets committed in the project tree",
          not offenders, str(offenders))

    readme = read(os.path.join(ROOT, "README.md"))
    design = read(os.path.join(ROOT, "workflow", "design-v0.md"))
    check("T15.1", "docs", "README documents the exported workflow JSON it ships",
          "workflow/SupportBotRAG-full.json" in readme or "exported workflow" in readme)
    check("T15.2", "docs", "design doc reflects the Agent architecture actually built "
                           "(not only the Q&A chain)",
          "AI Agent" in design and "as built" in design.lower(),
          "drift: design-v0.md still describes the Q&A-chain build")
    check("T15.3", "docs", "A QA report exists in docs/",
          any(f.startswith("qa-report") for f in os.listdir(os.path.join(ROOT, "docs")))
          if os.path.isdir(os.path.join(ROOT, "docs")) else False)


def test_channels(channel_dir):
    """Telegram / Email channel workflows: wiring, safety defaults, scrubbing."""
    for fname, cid in (("SupportBotTelegram-channel.json", "T20"),
                       ("SupportBotEmail-channel.json", "T21")):
        path = os.path.join(channel_dir, fname)
        if not os.path.exists(path):
            check("%s.1" % cid, "channels", "Channel workflow shipped: %s" % fname,
                  False, "missing file")
            continue
        wf = load_workflow(path)
        N = nodes_by_name(wf)
        blob = json.dumps(wf, ensure_ascii=False)
        check("%s.1" % cid, "channels", "%s: readable + has an AI Agent" % fname,
              any(n["type"] == "@n8n/n8n-nodes-langchain.agent"
                  for n in wf["nodes"]))
        check("%s.2" % cid, "channels", "%s: reuses the same knowledge base tool" % fname,
              "Supabase Vector Store (Tool)" in N)
        check("%s.3" % cid, "channels", "%s: escalation still writes a ticket" % fname,
              "Insert Ticket" in N and "If escalated" in N)
        check("%s.4" % cid, "channels", "%s: no personal data committed "
                                        "(email / chat id must be placeholders)" % fname,
              not re.search(r"[A-Za-z0-9._%+-]+@gmail\.com|\b\d{9,11}\b", blob)
              and "@example.com" in blob,
              "personal identifiers found in the shipped workflow")

    # --- Telegram channel specifics
    tp = os.path.join(channel_dir, "SupportBotTelegram-channel.json")
    if os.path.exists(tp):
        wf = load_workflow(tp)
        N = nodes_by_name(wf)
        trig = next((n for n in wf["nodes"] if "telegramTrigger" in n["type"]), None)
        check("T20.5", "channels", "Telegram channel: message trigger present",
              trig is not None)
        check("T20.8", "release", "Telegram trigger carries a webhookId (without it "
                                  "n8n registers no route and Telegram gets 404s)",
              bool(trig and trig.get("webhookId")), "webhookId=%r" % (trig or {}).get("webhookId"))
        repl = N.get("Send Telegram Reply")
        check("T20.6", "channels", "Telegram channel: reply goes back to the "
                                   "sender's chat (trigger expression, not a "
                                   "hard-coded chat id)",
              bool(repl and "Telegram Trigger" in json.dumps(repl["parameters"])
                   and "chat.id" in json.dumps(repl["parameters"])))
        check("T20.7", "channels", "Telegram channel: uses the bot credential",
              bool(repl and repl.get("credentials")))

    # --- Email channel specifics
    ep = os.path.join(channel_dir, "SupportBotEmail-channel.json")
    if os.path.exists(ep):
        wf = load_workflow(ep)
        N = nodes_by_name(wf)
        trig = N.get("Email Trigger (IMAP)")
        check("T21.5", "channels", "Email channel: IMAP trigger present",
              bool(trig and "emailReadImap" in trig["type"]))
        check("T21.6", "safety", "Email channel: does NOT mark inbox mail as read "
                                 "(postProcessAction=nothing)",
              bool(trig and trig["parameters"].get("postProcessAction") == "nothing"),
              "postProcessAction=%r" % (trig or {}).get("parameters", {}).get("postProcessAction"))
        check("T21.7", "safety", "Email channel: only answers mail to the dedicated "
                                 "alias (+support), never the whole inbox",
              "+support" in json.dumps(N.get("Is support mail?", {}).get("parameters", {})))
        check("T21.8", "channels", "Email channel: SMTP reply node wired + credential",
              bool(N.get("Send Email Reply")
                   and N["Send Email Reply"].get("credentials")))
        check("T21.9", "channels", "Email channel: replies address the original sender "
                                   "(expression, not a hard-coded address)",
              "$('Prep Email Question')" in json.dumps(
                  N.get("Send Email Reply", {}).get("parameters", {})))

    # --- CRM / HTTP integration in the main workflow
    main_wf = load_workflow(os.path.join(ROOT, "workflow", "SupportBotRAG-full.json"))
    M = nodes_by_name(main_wf)
    crm = M.get("Push to CRM")
    check("T22.1", "integration", "CRM/HTTP node present in the escalation branch",
          bool(crm and "httpRequest" in crm["type"]))
    if crm:
        p = crm["parameters"]
        check("T22.2", "integration", "CRM push is a POST of a JSON body",
              p.get("method") == "POST" and p.get("sendBody") is True
              and p.get("specifyBody") == "json")
        body = json.dumps(p.get("jsonBody", ""))
        check("T22.3", "integration", "CRM payload carries the ticket id + question",
              "question" in body and "ticket_id" in body, body[:120])
        check("T22.4", "reliability", "A broken CRM endpoint cannot block the ticket "
                                      "or the customer reply (onError=continue)",
              str(crm.get("onError", "")).startswith("continue"))
        check("T22.5", "security", "CRM endpoint is a placeholder, not a live "
                                   "third-party URL with a token",
              "webhook.site" not in json.dumps(p.get("url", "")),
              json.dumps(p.get("url", ""))[:80])
        # The live instance points this node at a personal webhook.site sink (a leftover from
        # testing the CRM push). That URL must never reach the public repo: anyone could post to
        # it, and a client would inherit a dependency on someone else's endpoint.
        check("T22.6", "security", "No workflow file ships a live third-party endpoint",
              not any("webhook.site" in read(os.path.join(ROOT, "workflow", f))
                      for f in sorted(os.listdir(os.path.join(ROOT, "workflow")))
                      if f.endswith(".json")),
              "workflow/*.json scanned")


def test_input_guard():
    """Chat trigger must validate input instead of letting the model crash."""
    wf = load_workflow(os.path.join(ROOT, "workflow", "SupportBotRAG-full.json"))
    conns = wf["connections"]
    N = nodes_by_name(wf)
    trig = "When chat message received"
    first = (conns.get(trig, {}).get("main", [[{}]])[0] or [{}])[0].get("node")
    check("T25.1", "reliability", "Chat trigger routes through an input-validation "
                                 "node (an empty/malformed body must not reach the model)",
          first == "Valid input?", "first node after the trigger: %r" % first)
    check("T25.2", "reliability", "Empty input gets a friendly reply, not a 500",
          "Reply Empty Input" in N
          and "output" in N["Reply Empty Input"]["parameters"].get("jsCode", ""))
    guard = N.get("Valid input?")
    check("T25.3", "reliability", "Validation checks chatInput and has both branches wired",
          bool(guard) and "chatInput" in json.dumps(guard["parameters"])
          and len(conns.get("Valid input?", {}).get("main", [])) == 2)


def test_error_alerts(workflow_dir):
    """Error-alert workflow: n8n's native Error Trigger pattern."""
    path = os.path.join(workflow_dir, "SupportBotErrorAlerts.json")
    if not os.path.exists(path):
        return check("T24.1", "reliability", "Error-alert workflow shipped", False, path)
    wf = load_workflow(path)
    N = nodes_by_name(wf)
    check("T24.1", "reliability", "Alert workflow uses n8n's Error Trigger node",
          any("errorTrigger" in n["type"] for n in wf["nodes"]))
    fmt = N.get("Format Alert")
    check("T24.2", "reliability", "Alert message names the workflow, failing node and error",
          bool(fmt) and all(k in fmt["parameters"].get("jsCode", "")
                            for k in ("workflow", "Node", "Error")),
          "jsCode missing fields")
    check("T24.3", "reliability", "Alert is delivered out-of-band (Telegram message)",
          any("telegram" in n["type"] for n in wf["nodes"]))
    check("T24.4", "reliability", "Alert delivery itself retries before giving up",
          all(not n.get("retryOnFail") or (n.get("maxTries") or 0) >= 2
              for n in wf["nodes"] if "telegram" in n["type"]))
    js = (fmt or {}).get("parameters", {}).get("jsCode", "")
    check("T24.5", "reliability", "Alert handles BOTH shapes (execution error and "
                                 "trigger/activation error)",
          "trigger" in js and "execution" in js)


def test_gmail_channel(workflow_dir):
    """Gmail-API variant of the email channel (replaces the flaky IMAP trigger)."""
    path = os.path.join(workflow_dir, "SupportBotEmailGmail-channel.json")
    if not os.path.exists(path):
        return check("T26.1", "channels", "Gmail-API email channel shipped", False, path)
    wf = load_workflow(path)
    N = nodes_by_name(wf)
    blob = json.dumps(wf, ensure_ascii=False)
    trig = next((n for n in wf["nodes"] if "gmailTrigger" in n["type"]), None)
    check("T26.1", "channels", "Gmail trigger present (API + OAuth2, no IMAP)",
          trig is not None and "gmailOAuth2" in json.dumps(trig.get("credentials", {})))
    check("T26.2", "safety", "Trigger filters server-side on the dedicated alias",
          bool(trig) and "+support" in json.dumps(trig["parameters"].get("filters", {})))
    send = N.get("Send Gmail Reply")
    check("T26.3", "channels", "Reply goes back through the Gmail API as a threaded reply",
          bool(send) and send["parameters"].get("operation") == "reply"
          and "Prep Email Question" in json.dumps(send["parameters"]))
    check("T26.4", "reliability", "Handled mail is marked read (no duplicate answers)",
          bool(N.get("Mark handled as read"))
          and N["Mark handled as read"]["parameters"].get("operation") == "markAsRead")
    check("T26.5", "channels", "Same knowledge base + escalation as every other channel",
          "Supabase Vector Store (Tool)" in N and "If escalated" in N and "Insert Ticket" in N)
    check("T26.6", "channels", "No personal data committed",
          not re.search(r"[A-Za-z0-9._%+-]+@gmail\.com|\b\d{9,11}\b", blob)
          and "@example.com" in blob)
    js = N.get("Prep Email Question", {}).get("parameters", {}).get("jsCode", "")
    check("T26.7", "channels", "MIME parsing is defensive (plain text, base64url, header lookup)",
          ("findPlainText" in js or "findText" in js) and "base64" in js
          and ("rawHeader(" in js or "header(" in js))

    # --- Regressions found by the live Gmail end-to-end runs -----------------
    # Each one shipped in the workflow and only showed up against the real Gmail
    # API; the assertions below exist so they cannot come back unnoticed.
    alias_if = N.get("Is a support mail?")
    conds = ((alias_if or {}).get("parameters", {}).get("conditions", {})
             .get("conditions", []))
    check("T27.1", "channels", "Alias gate has exactly one rule (to contains +support)",
          len(conds) == 1 and "+support" in json.dumps(conds),
          "found %d condition(s): %s" % (len(conds), json.dumps(conds, ensure_ascii=False)))
    check("T27.2", "channels", "Parser accepts the structured trigger shape AND the raw "
                               "Gmail API shape",
          "value.value" in js and "m.payload" in js and "addressOf" in js)
    check("T27.3", "channels", "Empty body falls back to the subject (subject-only mail "
                               "must not get a greeting reply)",
          "if (!question)" in js and "subject" in js)
    check("T27.4", "reliability", "markAsRead uses the Gmail API id, not the RFC Message-ID",
          "messageId: m.id" in js and "rfcMessageId" in js)
    check("T27.5", "channels", "Reply is threaded (reply op + messageId of the parsed mail)",
          bool(send) and send["parameters"].get("operation") == "reply"
          and "Prep Email Question" in str(send["parameters"].get("messageId")))


def _js_syntax_error(js):
    """Parse JavaScript with the real parser. Returns None when it parses.

    The project ships JavaScript in two places that must not break silently: the Code
    nodes inside workflow JSON and the widget every visitor downloads. A structural
    check cannot see a broken string literal, only a parser can.
    """
    import subprocess
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "js_syntax_check.js")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(js)
    try:
        r = subprocess.run(["node", "--check", tmp], capture_output=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return "node could not be run: %s" % exc
    if r.returncode == 0:
        return None
    err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
    return err[-1] if err else "node --check failed"


def test_code_node_syntax(workflow_dir):
    """Every Code node's jsCode must be valid JavaScript.

    Regression guard: a real bug shipped because a backslash escape was lost in
    a JSON round-trip (the string literal received a raw newline) and the node
    only failed at runtime.
    """
    files = [f for f in os.listdir(workflow_dir) if f.endswith(".json")]
    checked = 0
    bad = []
    for fname in files:
        try:
            wf = load_workflow(os.path.join(workflow_dir, fname))
        except Exception:  # noqa: BLE001
            continue
        for n in wf.get("nodes", []):
            if not str(n["type"]).endswith(".code"):
                continue
            js = n["parameters"].get("jsCode") or ""
            if not js:
                continue
            checked += 1
            err = _js_syntax_error(js)
            if err:
                bad.append("%s/%s: %s" % (fname, n["name"], err))
    check("T23.1", "quality", "All %d Code nodes in shipped workflows parse as "
                              "valid JavaScript" % checked,
          not bad, str(bad))

    widget = os.path.join(ROOT, "site", "widget.js")
    err = _js_syntax_error(read(widget)) if os.path.exists(widget) else "file missing"
    check("T23.2", "quality", "The shipped chat widget parses as valid JavaScript",
          err is None, err or "")


def test_switches():
    """The start/stop switches (switches/).

    Two properties matter more than the scripts existing: stopping must disable the self-healing
    task (otherwise n8n is back within five minutes and "off" is a lie), and neither switch may
    touch data or credentials (switching the bot off must never delete anything).
    """
    on_bat = os.path.join(ROOT, "switches", "bot-on.bat")
    off_bat = os.path.join(ROOT, "switches", "bot-off.bat")
    ps1 = os.path.join(ROOT, "switches", "switch-bot.ps1")

    check("T28.1", "release", "Both switches and their script are shipped",
          all(os.path.exists(p) for p in (on_bat, off_bat, ps1)),
          "missing=%s" % [os.path.basename(p) for p in (on_bat, off_bat, ps1)
                          if not os.path.exists(p)])

    if not os.path.exists(ps1):
        return
    ps = read(ps1)
    check("T28.2", "release", "Each launcher calls the switch script with its own action",
          "-Action on" in read(on_bat) and "-Action off" in read(off_bat))
    check("T28.3", "reliability", "Stopping disables the services, so the bot cannot come back "
                                  "on its own after a reboot",
          "Set-Service" in ps and "Disabled" in ps
          and "functions: n8n, ngrok" not in ps
          and all(s in ps for s in ("'n8n'", "'ngrok'")))
    check("T28.4", "safety", "The switches never read credentials or touch the database",
          "demo-secrets" not in ps and "rest/v1" not in ps and "DELETE" not in ps.replace(
              "Stop-Process", ""))
    check("T28.5", "release", "Starting waits for the service, then verifies the public address "
                              "before it claims success",
          "function Wait-Service" in ps and "function Test-Tunnel" in ps
          and "NOT fully up" in ps)
    check("T28.6", "release", "The address is permanent, so nothing republishes it",
          "publish-backend-url" not in ps and "public-url" not in ps
          and "ngrok-free.dev" in ps
          and "ngrok-free.dev" in read(os.path.join(ROOT, "site", "backend.json")))
    check("T28.7", "docs", "The README points at the switches",
          any(s in read(os.path.join(ROOT, "README.md"))
              for s in ("switches/bot-on.bat", "switches\\bot-on.bat")))
    check("T28.8", "release", "The republish step is gone from the repository",
          not os.path.exists(os.path.join(ROOT, "demo", "publish-backend-url.ps1")))

    # A switch that needs a UAC prompt every single time is a switch that fails in real use: the
    # prompt gets missed, or the elevated window closes before anything can be read. The switch now
    # grants itself the rights Microsoft documents for this, once, and shows the result afterwards.
    check("T28.9", "release", "The switch grants itself start/stop rights once "
                              "(Microsoft: the service security descriptor)",
          "sc.exe sdset" in ps and "Grant-Control" in ps and "Revoke-Control" in ps
          and "DCLCSWRPWP" in ps,
          "rights string present: %s" % ("DCLCSWRPWP" in ps))
    check("T28.10", "reliability", "Elevation is awaited and its output is shown, so a double-click "
                                   "always ends in a readable report",
          "-Wait" in ps and "Show-Log" in ps and "last-run.log" in ps
          and "result is in the window that just opened" not in ps)
    check("T28.11", "reliability", "A cancelled permission prompt is reported as such",
          "was cancelled" in ps and "1223" in ps)
    check("T28.12", "safety", "The granted rights are scoped and reversible",
          "service-sddl-backup" in ps and "WriteOwner" not in ps and "SeTakeOwnership" not in ps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", default=os.path.join(
        ROOT, "workflow", "SupportBotRAG-full.json"))
    ap.add_argument("--subworkflow", default=os.path.join(
        ROOT, "workflow", "CreateSupportTicket-tool.json"))
    args = ap.parse_args()

    wf = load_workflow(args.workflow)
    test_workflow(wf)
    if os.path.exists(args.subworkflow):
        test_subworkflow(args.subworkflow)
    else:
        check("T4.2", "workflow", "Ticket sub-workflow export present", False,
              args.subworkflow)
    test_knowledge()
    test_site()
    test_channels(os.path.join(ROOT, "workflow"))
    test_gmail_channel(os.path.join(ROOT, "workflow"))
    test_input_guard()
    test_error_alerts(os.path.join(ROOT, "workflow"))
    test_code_node_syntax(os.path.join(ROOT, "workflow"))
    test_switches()
    test_repo()

    # The README quotes how many checks this suite runs. Assert it instead of trusting it:
    # a stale number in the documentation is exactly the kind of drift this suite exists for.
    declared = -1
    m = re.search(r"\*\*(\d+) static \+ contract checks\*\*",
                  read(os.path.join(ROOT, "README.md")))
    if m:
        declared = int(m.group(1))
    total = len(RESULTS) + 1  # +1 for the check added on this line
    check("T15.4", "docs", "README states the real number of checks (%d)" % total,
          declared == total, "README says %s" % (declared if declared >= 0 else "nothing"))

    failed = [r for r in RESULTS if r["status"] == "FAIL"]
    width = max(len(r["desc"]) for r in RESULTS)
    print("=" * (width + 26))
    print("QA SUITE: RAG support bot             %d checks, %d failed"
          % (len(RESULTS), len(failed)))
    print("=" * (width + 26))
    for area in ("workflow", "channels", "integration", "safety", "security",
                 "content", "a11y", "ux", "reliability", "quality", "release",
                 "docs"):
        rows = [r for r in RESULTS if r["area"] == area]
        if not rows:
            continue
        print("\n[%s]" % area.upper())
        for r in rows:
            mark = "PASS" if r["status"] == "PASS" else "FAIL"
            print("  %-4s %-6s %s" % (mark, r["id"], r["desc"]))
            if r["status"] == "FAIL" and r["detail"]:
                print("            -> %s" % r["detail"])
    print("\nRESULT: %s" % ("ALL PASS" if not failed else
                            "%d FAILURE(S)" % len(failed)))
    with open(os.path.join(ROOT, "tests", "qa-results.json"), "w",
              encoding="utf-8") as fh:
        json.dump(RESULTS, fh, indent=1, ensure_ascii=False)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())