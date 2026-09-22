"""Free image generation via Pollinations (no API key, ~no cost) + compose the
same three 1280x769 gig images, so both routes can be compared side by side.
"""
import os
import urllib.parse
import urllib.request
from PIL import Image, ImageDraw, ImageFont

OUT = r"F:\Fiverr\Image"
WORK = r"E:\Hermes\Projects\rag-support-bot\demo\video"
os.makedirs(OUT, exist_ok=True)

HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0 Safari/537.36",
    "Referer": "https://pollinations.ai/",
    "Accept": "image/*,*/*",
}

STYLE = ("flat vector illustration, minimal geometric shapes, corporate tech style, "
         "dark navy background, warm amber accent, wide banner, no text, no letters, no words")

PROMPTS = {
    "art_p1.png": "A friendly AI assistant chat bubble rising out of a clean minimal website page, "
                  "a chat window with a small round robot avatar beside a coffee cup. " + STYLE,
    "art_p2.png": "An AI assistant handing a paper ticket across a desk to a human support agent. " + STYLE,
    "art_p3.png": "A laptop, a smartphone and an envelope connected by thin glowing lines to one hub. " + STYLE,
}

for name, prompt in PROMPTS.items():
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
           + "?model=flux&width=1280&height=769&nologo=true&referrer=hermes-agent&seed=17")
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers=HDRS), timeout=180).read()
        open(os.path.join(OUT, name), "wb").write(data)
        print("%s -> %.0f KB" % (name, len(data) / 1024))
    except Exception as e:
        print("%s 失败: %s %s" % (name, type(e).__name__, str(e)[:120]))

# --- compose three gig images from the free art ------------------------------
W, H = 1280, 769
FG, ACCENT, MUTED, BAND = (255, 255, 255), (228, 190, 138), (208, 218, 230), (10, 16, 28)
FB = os.path.join(WORK, "arialbd.ttf")
FR = os.path.join(WORK, "arial.ttf")
f_head = ImageFont.truetype(FB, 50)
f_sub = ImageFont.truetype(FR, 25)
f_bul = ImageFont.truetype(FR, 22)
f_tag = ImageFont.truetype(FR, 17)


def cover(path, w, h):
    im = Image.open(path).convert("RGB")
    s = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def scrim(img, top_frac=0.62, strength=232):
    grad = Image.new("L", (1, H))
    for y in range(H):
        if y < H * top_frac:
            v = strength - int(strength * (y / (H * top_frac)) * 0.55)
        else:
            v = int(strength * 0.45 * (1 - (y - H * top_frac) / (H * (1 - top_frac))))
        grad.putpixel((0, y), max(0, min(255, v)))
    img.paste(Image.new("RGB", (W, H), BAND), (0, 0), grad.resize((W, H)))
    return img


def build(name, art, headline, sub, bullets, tag):
    img = scrim(cover(os.path.join(OUT, art), W, H))
    d = ImageDraw.Draw(img)
    y = 54
    d.text((56, y), headline, font=f_head, fill=FG); y += 62
    d.text((56, y), sub, font=f_sub, fill=ACCENT); y += 46
    for b in bullets:
        d.text((60, y), "\u2022  " + b, font=f_bul, fill=MUTED); y += 34
    d.rectangle([0, H - 40, W, H], fill=(8, 12, 22))
    d.text((56, H - 32), tag, font=f_tag, fill=(150, 166, 188))
    img.save(os.path.join(OUT, name), quality=93)
    print("%s  %dx%d" % (name, img.width, img.height))


build("gig-free-1.jpg", "art_p1.png", "Answers from YOUR documents",
      "24/7 support - every answer shows where it came from",
      ["Cites the exact file, e.g. [faq.md]",
       'Says "I don\'t know" instead of inventing',
       "Unanswered questions become tickets"],
      "Set up on your own n8n + your own AI key - no monthly fee to me")

build("gig-free-2.jpg", "art_p2.png", "Never invents an answer",
      "No answer in your documents? It hands the question to your team",
      ["Saves the customer's exact words as a ticket",
       "Optional CRM / webhook push",
       "Your team is alerted in seconds"],
      "Harbor Support - RAG support bot on n8n + Supabase")

build("gig-free-3.jpg", "art_p3.png", "Website, Telegram and email",
      "One knowledge base, three channels your customers already use",
      ["Same answers everywhere, same source citations",
       "Escalations reach the team where they look",
       "You own the whole workflow"],
      "Harbor Support - RAG support bot on n8n + Supabase")

# --- comparison contact sheet: paid trio on top, free trio below -------------
rows = ["gig-1-answers-from-your-docs.jpg", "gig-2-never-invents.jpg", "gig-3-channels.jpg",
        "gig-free-1.jpg", "gig-free-2.jpg", "gig-free-3.jpg"]
tw, gap = 620, 16
tiles = []
for f in rows:
    im = Image.open(os.path.join(OUT, f)).convert("RGB")
    tiles.append(im.resize((tw, int(im.height * tw / im.width)), Image.LANCZOS))
sheet = Image.new("RGB", (tw + gap * 2, sum(t.height for t in tiles) + gap * (len(tiles) + 1)), (22, 26, 34))
y = gap
for t in tiles:
    sheet.paste(t, (gap, y)); y += t.height + gap
sheet.save(os.path.join(OUT, "_compare.jpg"), quality=88)
print("对比图:", os.path.join(OUT, "_compare.jpg"), sheet.size)
