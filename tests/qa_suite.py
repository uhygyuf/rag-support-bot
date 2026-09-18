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
        {'Child': {'ai_languageModel': [[{'node': parent, ...}]]}} — so the
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
        check("T3.6", "safety", "Prompt also escalates an explicit human request",
              "asks for a human" in sp)

    # --- deterministic escalation branch: ticket insert + notification + reply
    ins = N.get("Insert Ticket")
    if ins:
        p = ins["parameters"]
        check("T4.1", "workflow", "Ticket insert uses a plain string table name "
                                  "(a resource-locator object becomes '[object Object]' at runtime)",
              isinstance(p.get("tableId"), str) and p.get("tableId") == "tickets",
              "tableId=%r" % (p.get("tableId"),))
        check("T4.5", "workflow", "Ticket insert targets the row/create operation",
              p.get("resource") == "row" and p.get("operation") == "create")
        check("T4.6", "workflow", "Ticket insert has the Supabase credential",
              bool(ins.get("credentials")))
    ntf = N.get("Notify Telegram")
    if ntf:
        check("T4.7", "workflow", "Notification failure cannot break the ticket "
                                  "(onError=continue)",
              ntf.get("onError") == "continueRegularOutput", ntf.get("onError"))
        check("T4.8", "workflow", "Notification node is a Telegram sendMessage",
              "telegram" in ntf["type"] and ntf["parameters"].get("operation") == "sendMessage")
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
        prompts = (p.get("suggestedPrompts") or {}).get("prompts") or []
        check("T6.6", "ux", "Chat trigger offers >= 4 quick-start options",
              len(prompts) >= 4, "found %d" % len(prompts))
        check("T6.7", "ux", "Assistant identity set (name/description/icon)",
              bool(p.get("agentName") and p.get("agentDescription") and p.get("agentIcon")),
              "name=%r" % p.get("agentName"))

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

    # --- embed URL must match the real chat endpoint of this workflow
    m = re.search(r'data-webhook="([^"]+)"', html)
    url = m.group(1) if m else ""
    check("T11.1", "integration", "index.html declares a widget webhook URL",
          bool(url), url)
    check("T11.2", "integration", "Embed URL uses the n8n chat endpoint "
                                  "shape /webhook/<id>/chat",
          bool(re.search(r"/webhook/[A-Za-z0-9_-]+/chat$", url)), url)

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
    secret_pat = re.compile(r"sk-[A-Za-z0-9]{16,}|sb_secret_|sbp_[A-Za-z0-9]{20,}"
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
    test_repo()

    failed = [r for r in RESULTS if r["status"] == "FAIL"]
    width = max(len(r["desc"]) for r in RESULTS)
    print("=" * (width + 26))
    print("QA SUITE — RAG support bot            %d checks, %d failed"
          % (len(RESULTS), len(failed)))
    print("=" * (width + 26))
    for area in ("workflow", "integration", "safety", "security", "content",
                 "a11y", "ux", "reliability", "release", "docs"):
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
