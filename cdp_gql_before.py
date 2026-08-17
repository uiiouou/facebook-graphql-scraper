# -*- coding: utf-8 -*-
"""在无头 Edge（CDP）里执行 GraphQL beforeTime 查询，验证 2025-06-16 之前是否有帖子"""
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

# 1. 从页面 HTML 提取 queryID + variables 模板（用 JS 提取返回 JSON 字符串）
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
  var template = JSON.parse(html.slice(start + 12, end));
  return JSON.stringify({qid: qid, variables: template});
})()
""")
info = json.loads(extract) if extract else {}
if info.get("error"):
    print("❌ 提取失败:", info, flush=True)
    raise SystemExit(1)
qid = info["qid"]
template = info["variables"]
print(f"queryID: {qid}", flush=True)

# 2. 构造 beforeTime 查询
BEFORE_TS = int(datetime(2025, 6, 16).timestamp())
base = dict(template)
base.update({
    "count": 10, "cursor": None, "beforeTime": BEFORE_TS, "afterTime": None,
    "privacy": {"exclusivity": "INCLUSIVE", "filter": "ALL"},
    "stream_count": 1, "useDefaultActor": False, "taggedInOnly": False,
})
print(f"beforeTime={BEFORE_TS} ({datetime.fromtimestamp(BEFORE_TS).date()})", flush=True)

# 3. 从页面提取 fb_dtsg
dtsg = ev(r"""
(function(){
  var html = document.documentElement.innerHTML;
  var m = html.match(/"dtsg":\{"token":"([^"]+)"/);
  return m ? m[1] : null;
})()
""")
if not dtsg:
    print("❌ 页面里没有 fb_dtsg", flush=True)
    raise SystemExit(1)
print(f"fb_dtsg: {dtsg[:20]}...", flush=True)

# 4. 在页面里执行 GraphQL fetch
fetch_js = r"""
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
resp = ev(fetch_js, await_promise=True)

# 5. 解析结果
try:
    j = json.loads(resp.split("\n")[0])
    data = j.get("data") or {}
    node = data.get("user") or data.get("node") or {}
    units = node.get("timeline_list_feed_units") or {}
    edges = units.get("edges", [])
    print(f"\n返回帖子数: {len(edges)}", flush=True)
    if edges:
        for e in edges[:10]:
            n = e.get("node", {})
            pid = n.get("post_id")
            ts = n.get("creation_time") or n.get("created_time")
            d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"
            print(f"  [{pid}] {d}", flush=True)
        print("⚠️ 有 2025-06-16 之前的帖子！", flush=True)
    else:
        print("✅ 无更早帖子 —— 账号最早就是 2025-06-16 左右", flush=True)
except Exception as e:
    print("❌ 解析失败:", str(e)[:100], flush=True)
    print("响应前 200 字符:", (resp or "")[:200], flush=True)

ws.close()
