"""Generate three hero illustrations with Gemini image models (no text in the art),
then compose 1280x769 Fiverr gig images: art background + our own crisp text overlay.
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
        if line.strip().startswith("GOOGLE_API_KEY"):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
if not key:
    raise SystemExit("no GOOGLE_API_KEY")

BASE_STYLE = ("flat vector illustration, minimal geometric shapes, corporate tech style, "
              "dark navy background #0B1220, warm amber accent #D4AC7A, soft shadows, "
              "wide 16:9 composition, no text, no letters, no words, no numbers, no logos")

PROMPTS = {
    "art1.png": "A friendly AI assistant chat bubble rising from a website page, "
                "chat window with a small robot avatar, a coffee cup next to it. " + BASE_STYLE,
    "art2.png": "An AI assistant passing a paper ticket to a human support agent across a desk, "
                "concept of handing over a customer question to a person. " + BASE_STYLE,
    "art3.png": "Three connected screens: a laptop with a website, a smartphone with a chat app "
                "and an envelope, all linked to one glowing knowledge base hub in the middle. " + BASE_STYLE,
}

MODELS = ["gemini-3-pro-image", "gemini-3.1-flash-image", "gemini-2.5-flash-image"]


def generate(prompt, model):
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s" % (model, key)
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read().decode())


for name, prompt in PROMPTS.items():
    saved = False
    for model in MODELS:
        try:
            r = generate(prompt, model)
            parts = r["candidates"][0]["content"]["parts"]
            data = None
            for p in parts:
                if "inlineData" in p or "inline_data" in p:
                    data = (p.get("inlineData") or p.get("inline_data"))["data"]
                    break
            if not data:
                print("%s / %s -> no image in response" % (name, model))
                continue
            raw = base64.b64decode(data)
            path = os.path.join(OUT, name)
            open(path, "wb").write(raw)
            print("%s generated with %s -> %.0f KB" % (name, model, len(raw) / 1024))
            saved = True
            break
        except urllib.error.HTTPError as e:
            print("%s / %s -> HTTP %s %s" % (name, model, e.code, e.read().decode()[:120].replace("\n", " ")))
        except Exception as e:
            print("%s / %s -> %s %s" % (name, model, type(e).__name__, str(e)[:120]))
    if not saved:
        print("%s FAILED on every model" % name)
