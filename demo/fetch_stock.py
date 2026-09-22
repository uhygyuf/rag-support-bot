"""Openverse stock-photo fetch: broad queries, pauses between calls (the API rate-limits
fast anonymous callers and then answers with a non-JSON body), retry, client-side
aspect-ratio filter."""
import json
import os
import time
import urllib.parse
import urllib.request

OUT = r"F:\Fiverr\Image\stock"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Hermes/1.0"}

QUERIES = {
    "q1": ["customer service", "call center", "help desk"],
    "q2": ["artificial intelligence", "chatbot", "robot hand"],
    "q3": ["smartphone laptop", "office desk computer", "messaging app"],
}


def api(params, tries=4):
    url = "https://api.openverse.org/v1/images/?" + params
    for t in range(tries):
        try:
            body = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode()
            return json.loads(body)
        except Exception as e:
            wait = 4 * (t + 1)
            print("      (retry %d after %ss: %s)" % (t + 1, wait, str(e)[:50]))
            time.sleep(wait)
    return {"results": []}


def download(url, path):
    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
    open(path, "wb").write(data)
    return len(data)


report = []
for tag, queries in QUERIES.items():
    got = 0
    for q in queries:
        if got >= 3:
            break
        params = ("q=" + urllib.parse.quote(q) + "&license=cc0,pdm,by&size=large&page_size=20")
        r = api(params)
        items = r.get("results") or []
        print("%s '%s' -> %s 结果" % (tag, q, r.get("result_count", 0)))
        for it in items:
            if got >= 3:
                break
            w, h = it.get("width") or 0, it.get("height") or 0
            if not w or not h or (w / h) < 1.25 or w < 1200:
                continue
            url = it.get("url")
            if not url:
                continue
            ext = ".png" if str(url).lower().endswith(".png") else ".jpg"
            path = os.path.join(OUT, "%s_%d%s" % (tag, got, ext))
            try:
                n = download(url, path)
            except Exception as e:
                print("      下载失败 %s" % str(e)[:60])
                continue
            print("      %s  %sx%s  %-4s  %-18s %6.0fKB  %s" % (
                os.path.basename(path), w, h, it.get("license"),
                (it.get("creator") or "?")[:18], n / 1024, (it.get("title") or "")[:34]))
            report.append({"tag": tag, "file": os.path.basename(path), "query": q,
                           "title": it.get("title"), "creator": it.get("creator"),
                           "license": it.get("license"), "license_url": it.get("license_url"),
                           "source": it.get("foreign_landing_url"), "w": w, "h": h})
            got += 1
        time.sleep(4)

json.dump(report, open(os.path.join(OUT, "credits.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n共 %d 张 -> %s" % (len(report), OUT))
