# -*- coding: utf-8 -*-
"""通过 CDP 驱动 Edge，自动滚动 HunanTodayHICC 收集全部 post_id"""
import json, time, sys, urllib.request
from websocket import create_connection

def get_ws_url():
    tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=10))
    for t in tabs:
        if t.get("type") == "page" and "facebook.com" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    for t in tabs:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    return None

def main():
    ws_url = get_ws_url()
    if not ws_url:
        print("❌ 找不到 Facebook 标签页")
        sys.exit(1)
    ws = create_connection(ws_url, timeout=120)
    msg_id = [0]

    def eval_js(expr, await_promise=False, timeout=180):
        msg_id[0] += 1
        mid = msg_id[0]
        ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                            "params": {"expression": expr, "awaitPromise": await_promise,
                                       "returnByValue": True}}))
        while True:
            resp = json.loads(ws.recv())
            if resp.get("id") == mid:
                r = resp.get("result", {}).get("result", {})
                return r.get("value")

    # 注入全局状态 + harvest 函数
    eval_js("window.__seen = new Set(); window.__posts = []; window.__stuck = 0;")
    eval_js(r"""
window.__harvest = function() {
  document.querySelectorAll('a[href*="/posts/"], a[href*="/reel/"], a[href*="/videos/"], a[href*="story.php"]').forEach(function(a) {
    var href = a.href;
    var m = href.match(/\/(?:posts|reel|videos)\/(?:[^/]+\/)?(\d{10,})/) || href.match(/story_fbid=(\d{10,})/);
    if (!m) return;
    var pid = m[1];
    if (!window.__seen.has(pid)) { window.__seen.add(pid); window.__posts.push({post_id: pid, url: href}); }
  });
};
window.__harvest();
""")
    print("✅ CDP 已连接，开始自动滚动收集...", flush=True)

    # 分段滚动：每段 15 步
    def scroll_once(round_no):
        for batch in range(200):
            result = eval_js(r"""
(async function() {
  for (var i = 0; i < 15; i++) {
    window.scrollBy(0, 500);
    await new Promise(r => setTimeout(r, 2200));
    window.__harvest();
  }
  var pos = window.pageYOffset;
  var height = document.documentElement.scrollHeight;
  var atBottom = (pos + window.innerHeight >= height - 200);
  if (atBottom) window.__stuck++; else window.__stuck = 0;
  return {count: window.__posts.length, pos: pos, height: height, stuck: window.__stuck};
})()
""", await_promise=True, timeout=60)
            if result:
                print(f"[轮{round_no}] 批次 {batch+1}: 已收集 {result['count']} 条 | 位置 {result['pos']} | 高 {result['height']} | stuck={result['stuck']}", flush=True)
                if result['stuck'] >= 6:
                    print(f"→ 轮{round_no} 到底，返回 {result['count']} 条", flush=True)
                    return result['count']
            else:
                time.sleep(3)
        return None

    # 先回顶部
    eval_js("window.scrollTo(0, 0)")
    time.sleep(3)
    count1 = scroll_once(1)
    # 二次确认：回顶部再滚一次，收集 DOM 回收遗漏的帖子
    eval_js("window.scrollTo(0, 0)")
    time.sleep(3)
    eval_js("window.__stuck = 0")
    count2 = scroll_once(2)
    print(f"第一轮 {count1} 条，第二轮 {count2} 条", flush=True)

    # 读取最终结果
    final = eval_js("JSON.stringify(window.__posts)")
    if final:
        posts = json.loads(final)
        with open("post_ids_new.txt", "w", encoding="utf-8") as f:
            for p in posts:
                f.write(p["post_id"] + "\n")
        print(f"\n✅ 收集完成！共 {len(posts)} 条，已保存 post_ids_new.txt", flush=True)
        # 对比旧的
        try:
            with open("post_ids.txt", encoding="utf-8") as f:
                old = set(l.strip() for l in f if l.strip())
            new = set(p["post_id"] for p in posts)
            print(f"旧 {len(old)} 条，新 {len(new)} 条，新增 {len(new - old)} 条", flush=True)
            added = sorted(new - old, key=lambda x: int(x))
            print(f"新增 post_id（前20）: {added[:20]}", flush=True)
        except Exception:
            pass
    ws.close()

if __name__ == "__main__":
    main()
