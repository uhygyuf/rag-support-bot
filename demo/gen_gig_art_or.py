"""Generate the three gig hero illustrations through OpenRouter (image-output model).

Cost note: google/gemini-2.5-flash-image bills image tokens at ~$0.0000003 each and one
image is ~1300 tokens, i.e. well under one cent per image.
"""
import base64
import glob
import json
import os
import urllib.request
import urllib.error

OUT = r"F:\Fiverr\Image"
os.makedirs(OUT, exist_ok=True)

key = None
for p in glob.glob(r"C:\Users\leo wang\AppData\Local\hermes\.env"):
    for line in open(p, encoding="utf-8", errors="replace"):
        if line.strip().startswith("OPENROUTER_API_KEY"):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
if not key:
    raise SystemExit("no OPENROUTER_API_KEY")

HDR = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
       "HTTP-Referer": "https://github.com/uhygyuf/rag-support-bot", "X-Title": "gig art"}


def credits():
    try:
        r = json.loads(urllib.request.urlopen(
            urllib.request.Request("https://openrouter.ai/api/v1/key", headers=HDR), timeout=30).read().decode())
        d = r.get("data", {})
        print("key 额度: limit=%s usage=%s remaining=%s" % (
            d.get("limit"), d.get("usage"), d.get("limit_remaining")))
    except Exception as e:
        print("查额度失败:", type(e).__name__, str(e)[:120])


STYLE = ("flat vector illustration, minimal geometric shapes, corporate tech style, "
         "dark navy background (#0B1220), warm amber accent (#D4AC7A), soft shadows, "
         "wide 16:9 banner composition, no text, no letters, no words, no numbers, no logos")

PROMPTS = {
    "art1.png": "A friendly AI assistant chat bubble rising out of a clean minimal website page, "
                "a chat window with a small round robot avatar beside a coffee cup. " + STYLE,
    "art2.png": "An AI assistant handing a paper ticket across a desk to a human support agent, "
                "concept of passing a customer question to a person. " + STYLE,
    "art3.png": "Three connected devices - a laptop showing a website, a smartphone showing a chat app, "
                "and an envelope - all linked by thin glowing lines to one hub in the middle. " + STYLE,
}

MODELS = ["google/gemini-2.5-flash-image", "google/gemini-3.1-flash-lite-image"]


def generate(prompt, model):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
    }).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                 data=body, headers=HDR)
    return json.loads(urllib.request.urlopen(req, timeout=240).read().decode())


credits()
for name, prompt in PROMPTS.items():
    done = False
    for model in MODELS:
        try:
            r = generate(prompt, model)
            msg = (r.get("choices") or [{}])[0].get("message", {})
            imgs = msg.get("images") or []
            if not imgs:
                print("%s / %s -> 无图返回; 文本: %s" % (name, model, str(msg.get("content"))[:120]))
                continue
            url = imgs[0]["image_url"]["url"]
            raw = base64.b64decode(url.split(",", 1)[1])
            open(os.path.join(OUT, name), "wb").write(raw)
            usage = r.get("usage") or {}
            print("%s 由 %s 生成 -> %.0f KB (tokens: %s)" % (name, model, len(raw) / 1024, usage.get("total_tokens")))
            done = True
            break
        except urllib.error.HTTPError as e:
            print("%s / %s -> HTTP %s %s" % (name, model, e.code, e.read().decode()[:150].replace("\n", " ")))
        except Exception as e:
            print("%s / %s -> %s %s" % (name, model, type(e).__name__, str(e)[:150]))
    if not done:
        print("%s 全部模型失败" % name)
