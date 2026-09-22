"""Compose the three 1280x769 Fiverr gig images: AI-generated hero art + our own text.

Text is always drawn by PIL, never by the image model (models misspell words), and a
gradient scrim keeps the headline readable over the artwork.
"""
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ART = r"F:\Fiverr\Image"
OUT = r"F:\Fiverr\Image"
WORK = r"E:\Hermes\Projects\rag-support-bot\demo\video"

W, H = 1280, 769
FG = (255, 255, 255)
ACCENT = (228, 190, 138)
MUTED = (208, 218, 230)
BAND = (10, 16, 28)

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
    x = (im.width - w) // 2
    y = (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def scrim(img, top_frac=0.62, strength=232):
    """dark gradient from the top so white text stays readable"""
    grad = Image.new("L", (1, H))
    for y in range(H):
        if y < H * top_frac:
            v = strength - int(strength * (y / (H * top_frac)) * 0.55)
        else:
            v = int(strength * 0.45 * (1 - (y - H * top_frac) / (H * (1 - top_frac))))
        grad.putpixel((0, y), max(0, min(255, v)))
    mask = grad.resize((W, H))
    img.paste(Image.new("RGB", (W, H), BAND), (0, 0), mask)
    return img


def build(name, art, headline, sub, bullets=(), tag=""):
    img = scrim(cover(os.path.join(ART, art), W, H))
    d = ImageDraw.Draw(img)
    y = 54
    d.text((56, y), headline, font=f_head, fill=FG)
    y += 62
    d.text((56, y), sub, font=f_sub, fill=ACCENT)
    y += 46
    for b in bullets:
        d.text((60, y), "\u2022  " + b, font=f_bul, fill=MUTED)
        y += 34
    if tag:
        d.rectangle([0, H - 40, W, H], fill=(8, 12, 22))
        d.text((56, H - 32), tag, font=f_tag, fill=(150, 166, 188))
    img.save(os.path.join(OUT, name), quality=93)
    print("%s  %dx%d" % (name, img.width, img.height))


build("gig-1-answers-from-your-docs.jpg", "art1.png",
      "Answers from YOUR documents",
      "24/7 support - every answer shows where it came from",
      ["Cites the exact file, e.g. [faq.md]",
       'Says "I don\'t know" instead of inventing',
       "Unanswered questions become tickets"],
      "Set up on your own n8n + your own AI key - no monthly fee to me")

build("gig-2-never-invents.jpg", "art2.png",
      "Never invents an answer",
      "No answer in your documents? It hands the question to your team",
      ["Saves the customer's exact words as a ticket",
       "Optional CRM / webhook push",
       "Your team is alerted in seconds"],
      "Harbor Support - RAG support bot on n8n + Supabase")

build("gig-3-channels.jpg", "art3.png",
      "Website, Telegram and email",
      "One knowledge base, three channels your customers already use",
      ["Same answers everywhere, same source citations",
       "Escalations reach the team where they look",
       "You own the whole workflow"],
      "Harbor Support - RAG support bot on n8n + Supabase")

for f in sorted(os.listdir(OUT)):
    if f.startswith("gig-") and f.endswith(".jpg"):
        print("  %-42s %.0f KB" % (f, os.path.getsize(os.path.join(OUT, f)) / 1024))
