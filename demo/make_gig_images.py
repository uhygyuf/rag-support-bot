"""Build the three Fiverr gig gallery images (1280x769) from real screenshots.

Layout: a text band on top (headline + sub), the real product screenshot below, and a
one-line caption strip over the bottom of the screenshot. Sources are frames from the
demo recording, cropped like the video so no browser chrome or taskbar is visible.
"""
import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

FF = r"C:\Users\leo wang\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-full_build\bin\ffmpeg.exe"
SRC = r"C:\Users\leo wang\AppData\Local\hermes\attachments\Recording 2026-09-21 140129.mp4"
WORK = r"E:\Hermes\Projects\rag-support-bot\demo\video"
OUTDIR = r"F:\Fiverr\Image"
os.makedirs(OUTDIR, exist_ok=True)

W, H = 1280, 769
BAND = 169          # top text band
SHOT_H = H - BAND   # screenshot height
BG = (11, 18, 32)
FG = (255, 255, 255)
MUTED = (176, 190, 206)
ACCENT = (212, 172, 122)

FB = os.path.join(WORK, "arialbd.ttf")
FR = os.path.join(WORK, "arial.ttf")
f_head = ImageFont.truetype(FB, 44)
f_sub = ImageFont.truetype(FR, 22)
f_cap = ImageFont.truetype(FR, 17)


def frame_at(t, name):
    path = os.path.join(WORK, name)
    subprocess.run([FF, "-y", "-v", "error", "-ss", str(t), "-i", SRC,
                    "-frames:v", "1", "-q:v", "1", path], check=True)
    return Image.open(path).convert("RGB")


def build(out_name, headline, sub, shot, box, caption, mask_left=False):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    d.text((46, 36), headline, font=f_head, fill=FG)
    d.text((46, 96), sub, font=f_sub, fill=ACCENT)

    crop = shot.crop(box)
    if mask_left:                      # Telegram chat list: unrelated private chats
        ImageDraw.Draw(crop).rectangle([0, 0, box[2] - box[0] - 2080, crop.height], fill=BG)
    sw = int(crop.width * SHOT_H / crop.height)
    if sw > W:
        sw = W
        sh = int(crop.height * sw / crop.width)
    else:
        sh = SHOT_H
    crop = crop.resize((sw, sh), Image.LANCZOS)
    x = (W - sw) // 2
    img.paste(crop, (x, BAND))

    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 34, W, H], fill=(8, 13, 24))
    d.text((46, H - 27), caption, font=f_cap, fill=MUTED)
    img.save(os.path.join(OUTDIR, out_name), quality=92)
    print("%-42s %dx%d" % (out_name, img.width, img.height))


# 1 - the answer with its source, on the demo site
build("gig-1-answers-from-your-docs.jpg",
      "Answers from YOUR documents",
      "24/7 support - every answer shows the file it came from",
      frame_at(30, "_g1.png"), (330, 210, 3072, 1836),
      "Demo site with the chat widget: 'Do you ship to Canada?' answered with [faq.md]")

# 2 - the escalation ticket
build("gig-2-never-invents.jpg",
      "Never invents an answer",
      "If your documents have nothing, the question becomes a ticket",
      frame_at(38, "_g2.png"), (900, 760, 3072, 1836),
      "Supabase tickets table - the customer's own words, kept for follow-up")

# 3 - the channels
build("gig-3-channels.jpg",
      "Website, Telegram and email",
      "One knowledge base, three channels - your team is pinged in seconds",
      frame_at(33, "_g3.png"), (960, 470, 3072, 1836),
      "Escalation alert delivered to the team's Telegram chat (unrelated chats blanked)",
      mask_left=True)

for f in sorted(os.listdir(OUTDIR)):
    p = os.path.join(OUTDIR, f)
    im = Image.open(p)
    print("%-42s %sx%s  %.0f KB" % (f, im.width, im.height, os.path.getsize(p) / 1024))
