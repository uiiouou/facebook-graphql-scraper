# -*- coding: utf-8 -*-
"""CDP 内 GraphQL 分页拉取 2025-06-16 之前的帖子（beforeTime 游标）"""
import json, re, time, urllib.request
from datetime import datetime
from websocket import create_connection

def get_ws_url():
    tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=10))
    for t in tabs:
        if t.get("type") == "page" and "facebook.com" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    return None

ws = create_connection(get_ws_url(), timeout=120)
mid = [0]

def ev(expr, await_promise=False):
    mid[0] += 1
    m = mid[0]
    ws.send(json.dumps({"id": m, "method": "Runtime.evaluate",
                        "params": {"expression": expr, "awaitPromise": await_promise, "returnByValue": True}}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == m:
            return r.get("result", {}).get("result", {}).get("value")

# 1. 提取 queryID + template
extract = ev(r"""
(function(){
  var html = document.documentElement.innerHTML;
  var i = html.indexOf('ProfileCometTimelineFeedQueryRelayPreloader');
  if (i < 0) return JSON.stringify({error: 'no preloader'});
  var m = html.slice(i, i + 300).match(/"queryID":"(\d+)"/);
  var qid = m ? m[1] : null;
  var start = html.indexOf('"variables":{', i);
  if (start < 0) return JSON.stringify({error: 'no variables', qid: qid});
  var depth = 0, end = -1;
  for (var k = start + 12; k < html.length; k++) {
    if (html[k] === '{') depth++;
    else if (html[k] === '}') { depth--; if (depth === 0) { end = k + 1; break; } }
  }
  return JSON.stringify({qid: qid, variables: JSON.parse(html.slice(start + 12, end))});
})()
""")
info = json.loads(extract)
qid, template = info["qid"], info["variables"]

dtsg = ev(r"""
(function(){
  var html = document.documentElement.innerHTML;
  var m = html.match(/"dtsg":\{"token":"([^"]+)"/);
  return m ? m[1] : null;
})()
""")
print(f"queryID: {qid} | fb_dtsg OK", flush=True)

def fetch_page(before_ts):
    base = dict(template)
    base.update({
        "count": 40, "cursor": None, "beforeTime": before_ts, "afterTime": None,
        "privacy": {"exclusivity": "INCLUSIVE", "filter": "ALL"},
        "stream_count": 1, "useDefaultActor": False, "taggedInOnly": False,
    })
    js = r"""
(async function() {
  var dtsg = %s;
  var qid = "%s";
  var variables = %s;
  var params = new URLSearchParams();
  params.append('av', '61592447296792');
  params.append('__user', '61592447296792');
  params.append('__a', '1');
  params.append('fb_dtsg', dtsg);
  params.append('fb_api_caller_class', 'RelayModern');
  params.append('server_timestamps', 'true');
  params.append('doc_id', qid);
  params.append('variables', JSON.stringify(variables));
  var resp = await fetch('/api/graphql/', {
    method: 'POST',
    headers: {'content-type': 'application/x-www-form-urlencoded'},
    body: params.toString()
  });
  var txt = await resp.text();
  if (txt.indexOf('for (;;);') === 0) txt = txt.slice(9).trim();
  return txt;
})()
""" % (json.dumps(dtsg), qid, json.dumps(base))
    for attempt in range(3):
        resp = ev(js, await_promise=True)
        if isinstance(resp, str) and resp.strip():
            break
        print(f"  响应异常（attempt {attempt+1}），重试...", flush=True)
        time.sleep(4)
    else:
        print("  连续响应异常，跳过本页", flush=True)
        return []
    try:
        j = json.loads(resp.split("\n")[0])
        node = (j.get("data") or {}).get("user") or {}
        edges = (node.get("timeline_list_feed_units") or {}).get("edges", [])
        out = []
        for e in edges:
            n = e.get("node", {})
            if n.get("__typename") != "Story":
                continue
            msg = (n.get("comet_sections", {}).get("content", {}).get("story", {})
                   .get("message", {}) or {}).get("text")
            ts = n.get("creation_time") or n.get("created_time")
            out.append({
                "post_id": n.get("post_id"),
                "created_time": ts,
                "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?",
                "text": (msg or "")[:60],
            })
        return out
    except Exception as e:
        print(f"  解析失败: {str(e)[:50]}", flush=True)
        return []

# 2. 分页拉取（断点续抓：从已有数据继续）
posts = []
import os
if os.path.exists("fb_output/posts_early.json"):
    try:
        with open("fb_output/posts_early.json", encoding="utf-8") as f:
            posts = json.load(f)
        print(f"断点续抓：已有 {len(posts)} 条，从 {datetime.fromtimestamp(min(p['created_time'] for p in posts)).strftime('%Y-%m-%d')} 继续", flush=True)
    except Exception:
        posts = []
if posts:
    before = min(p["created_time"] for p in posts) - 1
else:
    before = int(datetime(2025, 6, 16).timestamp())
page = 0
while page < 1500:
    page += 1
    batch = fetch_page(before)
    if not batch:
        print(f"第 {page} 页: 空，到底", flush=True)
        break
    posts.extend(batch)
    earliest = min(b["created_time"] for b in batch)
    before = earliest - 1
    print(f"第 {page} 页: +{len(batch)} 条 | 最早 {datetime.fromtimestamp(earliest).strftime('%Y-%m-%d')} | 累计 {len(posts)}", flush=True)
    time.sleep(3)

# 3. 保存
with open("fb_output/posts_early.json", "w", encoding="utf-8") as f:
    json.dump(posts, f, ensure_ascii=False, indent=2)
with open("post_ids_early.txt", "w", encoding="utf-8") as f:
    for p in posts:
        f.write(p["post_id"] + "\n")

print(f"\n✅ 共 {len(posts)} 条早期帖子（2025-06-16 之前），已保存", flush=True)
if posts:
    dates = sorted(p["created_time"] for p in posts)
    print(f"日期范围: {datetime.fromtimestamp(dates[0]).strftime('%Y-%m-%d')} ~ {datetime.fromtimestamp(dates[-1]).strftime('%Y-%m-%d')}", flush=True)
ws.close()
