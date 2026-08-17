# -*- coding: utf-8 -*-
"""抓取剩余帖子的详情+互动数据（一次访问），断点续抓，合并到 posts_355.json"""
import os, json, csv, re, time
from html import unescape
from urllib.parse import unquote
from curl_cffi import requests as cr

BASE = os.path.expanduser("~/Desktop/facebook-scraper")
COOKIES_FILE = os.path.join(BASE, "cookies.txt")
IDS_FILE = os.path.join(BASE, "post_ids.txt")
OUT_JSON = os.path.join(BASE, "fb_output", "posts_355.json")
OUT_CSV = os.path.join(BASE, "fb_output", "posts_355.csv")
PROXY = "http://127.0.0.1:7993"
IMPERSONATE = "chrome"
SLEEP_EACH = 4
SLEEP_BATCH = 30
BATCH_SIZE = 20
SAVE_EVERY = 5
MAX_RETRY = 3


def load_cookies(path):
    cookies = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = unquote(parts[6])
    return cookies


def extract(html):
    text = ""
    m = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]*)"', html)
    if m:
        text = unescape(m.group(1))

    def g(pats):
        for p in pats:
            mm = re.search(p, html)
            if mm:
                return mm.group(1)
        return ""

    likes = g([r'"unified_reactors":\{"count":(\d+)\}',
               r'"reaction_count":\{"count":(\d+)\}',
               r'"reactors":\{"count":(\d+)\}'])
    shares = g([r'"share_count_reduced":"?(\d+)"?',
                r'"share_count":\{"count":(\d+)\}'])
    comments = g([r'"total_comment_count":(\d+)',
                  r'"comment_count":\{"total_count":(\d+)\}'])
    return text, likes, shares, comments


def main():
    cookies = load_cookies(COOKIES_FILE)
    with open(IDS_FILE, encoding="utf-8") as f:
        post_ids = [l.strip() for l in f if l.strip()]

    with open(OUT_JSON, encoding="utf-8") as f:
        posts = json.load(f)
    done_ids = {p["post_id"] for p in posts}

    print(f"总 {len(post_ids)} 条，已抓 {len(done_ids)} 条，待抓 {len(post_ids) - len(done_ids)} 条", flush=True)

    def save():
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
        try:
            fields = ["post_id", "title", "text", "url", "likes", "shares", "comments_count"]
            with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                w.writeheader()
                for p in posts:
                    w.writerow({k: p.get(k, "") for k in fields})
        except PermissionError:
            print("  ⚠️ CSV 被占用", flush=True)

    new_count = 0
    for pid in post_ids:
        if pid in done_ids:
            continue
        text = likes = shares = comments = ""
        for attempt in range(MAX_RETRY):
            try:
                r = cr.get(f"https://www.facebook.com/reel/{pid}/",
                           impersonate=IMPERSONATE, proxy=PROXY, cookies=cookies, timeout=45)
                text, likes, shares, comments = extract(r.text)
                if text:
                    break
            except Exception:
                time.sleep(5)
        posts.append({
            "post_id": pid,
            "title": (text or "").split("\n")[0][:100],
            "text": text,
            "url": f"https://www.facebook.com/reel/{pid}/",
            "likes": likes, "shares": shares, "comments_count": comments,
        })
        new_count += 1
        print(f"[{len(posts)}/{len(post_ids)}] {pid} 👍{likes} 🔗{shares} 💬{comments} {text[:30]}", flush=True)

        if new_count % SAVE_EVERY == 0:
            save()
        time.sleep(SLEEP_EACH)
        if new_count % BATCH_SIZE == 0:
            print(f"--- 暂停 {SLEEP_BATCH} 秒 ---", flush=True)
            time.sleep(SLEEP_BATCH)

    save()
    print(f"✅ 完成！共 {len(posts)} 条", flush=True)


if __name__ == "__main__":
    main()
