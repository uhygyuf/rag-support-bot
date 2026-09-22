"""Cleanup + a refined v2 of the three gig images (non-destructive: v1 files stay).

Review feedback addressed: image 1 felt empty in the middle (zoom in, push the subject
down), image 2's line art is thin (raise contrast + sharpen), image 3 felt cramped at the
bottom (lift the art, keep a bottom margin).
"""
import os
import shutil
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

IMG = r"F:\Fiverr\Image"
WORK = r"E:\Hermes\Projects\rag-support-bot\demo\video"

# ---------------------------------------------------------------- cleanup
victims = [
    os.path.join(IMG, "stock"),
    os.path.join(IMG, "art_p1.png"),
    os.path.join(IMG, "art_p2.png"),
    os.path.join(IMG, "art_p3.png"),
    os.path.join(IMG, "gig-free-1.jpg"),
    os.path.join(IMG, "gig-free-2.jpg"),
    os.path.join(IMG, "gig-free-3.jpg"),
    os.path.join(IMG, "_pollinations_test.jpg"),
    os.path.join(IMG, "_contact_sheet.jpg"),
]
for v in victims:
    if os.path.isdir(v):
        shutil.rmtree(v, ignore_errors=True)
        print("removed dir ", v)
    elif os.path.exists(v):
        os.remove(v)
        print("removed file", v)

# ---------------------------------------------------------------- refine
W, H = 1280, 769
FG, ACCENT, MUTED, BAND = (255, 255, 255), (228, 190, 138), (208, 218, 230), (10, 16, 28)
FB = os.path.join(WORK, "arialbd.ttf")
FR = os.path.join(WORK, "arial.ttf")
f_head = ImageFont.truetype(FB, 50)
f_sub = ImageFont.truetype(FR, 25)
f_bul = ImageFont.truetype(FR, 22)
f_tag = ImageFont.truetype(FR, 17)


def cover(path, w, h, zoom=1.0, focus=0.5):
    im = Image.open(path).convert("RGB")
    s = max(w / im.width, h / im.height) * zoom
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    x = max(0, (im.width - w) // 2)
    y = max(0, int((im.height - h) * focus))
    return im.crop((x, y, x + w, y + h))


def punch(im, contrast=1.0, sharp=0.0):
    if contrast != 1.0:
        im = ImageEnhance.Contrast(im).enhance(contrast)
    if sharp:
        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=int(sharp * 100), threshold=3))
    return im


def scrim(img, top_frac=0.60, strength=236):
    grad = Image.new("L", (1, H))
    for y in range(H):
        if y < H * top_frac:
            v = strength - int(strength * (y / (H * top_frac)) * 0.55)
        else:
            v = int(strength * 0.45 * (1 - (y - H * top_frac) / (H * (1 - top_frac))))
        grad.putpixel((0, y), max(0, min(255, v)))
    img.paste(Image.new("RGB", (W, H), BAND), (0, 0), grad.resize((W, H)))
    return img


def build(name, art, headline, sub, bullets, tag, zoom, focus, contrast=1.0, sharp=0.0):
    img = scrim(punch(cover(os.path.join(IMG, art), W, H, zoom, focus), contrast, sharp))
    d = ImageDraw.Draw(img)
    y = 54
    d.text((56, y), headline, font=f_head, fill=FG); y += 62
    d.text((56, y), sub, font=f_sub, fill=ACCENT); y += 46
    for b in bullets:
        d.text((60, y), "\u2022  " + b, font=f_bul, fill=MUTED); y += 34
    d.rectangle([0, H - 40, W, H], fill=(8, 12, 22))
    d.text((56, H - 32), tag, font=f_tag, fill=(150, 166, 188))
    img.save(os.path.join(IMG, name), quality=93)
    print("wrote", name)


build("gig-1-v2.jpg", "art1.png", "Answers from YOUR documents",
      "24/7 support - every answer shows where it came from",
      ["Cites the exact file, e.g. [faq.md]",
       'Says "I don\'t know" instead of inventing',
       "Unanswered questions become tickets"],
      "Set up on your own n8n + your own AI key - no monthly fee to me",
      1.18, 0.66)

build("gig-2-v2.jpg", "art2.png", "Never invents an answer",
      "No answer in your documents? It hands the question to your team",
      ["Saves the customer's exact words as a ticket",
       "Optional CRM / webhook push",
       "Your team is alerted in seconds"],
      "Harbor Support - RAG support bot on n8n + Supabase",
      1.12, 0.52, contrast=1.22, sharp=1.1)

build("gig-3-v2.jpg", "art3.png", "Website, Telegram and email",
      "One knowledge base, three channels your customers already use",
      ["Same answers everywhere, same source citations",
       "Escalations reach the team where they look",
       "You own the whole workflow"],
      "Harbor Support - RAG support bot on n8n + Supabase",
      1.06, 0.40, contrast=1.06)

# side-by-side: v1 then v2 for each
pairs = [("gig-1-answers-from-your-docs.jpg", "gig-1-v2.jpg"),
         ("gig-2-never-invents.jpg", "gig-2-v2.jpg"),
         ("gig-3-channels.jpg", "gig-3-v2.jpg")]
tw, gap = 600, 14
tiles = []
for a, b in pairs:
    for f in (a, b):
        im = Image.open(os.path.join(IMG, f)).convert("RGB")
        tiles.append(im.resize((tw, int(im.height * tw / im.width)), Image.LANCZOS))
sheet = Image.new("RGB", (tw + gap * 2, sum(t.height for t in tiles) + gap * (len(tiles) + 1)), (22, 26, 34))
y = gap
for t in tiles:
    sheet.paste(t, (gap, y)); y += t.height + gap
sheet.save(os.path.join(IMG, "_compare_v1_v2.jpg"), quality=88)
print("compare sheet:", sheet.size)
print("\n剩余文件:")
for f in sorted(os.listdir(IMG)):
    p = os.path.join(IMG, f)
    print("  %-42s %7.0f KB" % (f, os.path.getsize(p) / 1024 if os.path.isfile(p) else 0))
