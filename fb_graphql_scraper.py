# -*- coding: utf-8 -*-
"""
Facebook 帖子(标题) → 评论 完整工作流（已实测跑通）
====================================================
技术栈（2026-08 全网验证后的结论）：
  1. 传输层用 curl_cffi 冒充 Chrome TLS 指纹 —— 关键！requests/urllib3 会被 FB 反爬 400 拦截
  2. 数据源用 Facebook GraphQL API（/api/graphql/），无需浏览器
  3. 登录态用 cookies.txt（c_user + xs + datr/sb/fr），代理走 UniClash 7993
  4. fb_dtsg token 每次运行时从主页自动提取
  5. timeline 的 queryID + variables 从目标页面 HTML 自动提取（不硬编码，FB 改版也不怕）

依赖：pip install curl_cffi

用法：
    python fb_graphql_scraper.py <页面ID> [条数]      # 抓某个主页/专页的帖子+评论
    python fb_graphql_scraper.py <帖子URL>            # 抓单个帖子的全部评论

示例：
    python fb_graphql_scraper.py 100064368354094 5    # Nintendo 专页前 5 条
    python fb_graphql_scraper.py 61592447296792 3     # 你自己的主页

输出：桌面 fb_output/posts.json + posts.csv
"""

import sys, os, json, base64, re, csv
from urllib.parse import unquote
from curl_cffi import requests as cr

# ================= 配置区 =================
# cookies.txt 路径（"Get cookies.txt LOCALLY" 扩展导出，或 F12 手动拼的 Netscape 格式）。
# 只要桌面有这个文件就自动读取全部 cookie；没有才用下面硬编码兜底。
COOKIES_FILE = os.path.expanduser("~/Desktop/cookies.txt")


def load_cookies_from_file(path):
    cookies = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")  # Netscape：domain flag path secure expiry name value
            if len(parts) >= 7:
                cookies[parts[5]] = unquote(parts[6])
    return cookies


COOKIES = {}
if os.path.exists(COOKIES_FILE):
    COOKIES = load_cookies_from_file(COOKIES_FILE)
    print(f"✅ 已从 {COOKIES_FILE} 读取 {len(COOKIES)} 个 cookie")
else:
    COOKIES = {"c_user": "61592447296792", "xs": "36:LPPXpyHlAe_0hA:2:1785810326"}

PROXY = "http://127.0.0.1:7993"   # UniClash 混合端口
IMPERSONATE = "chrome"             # chrome / chrome124 / edge101 / firefox133
OUT_DIR = os.path.expanduser("~/Desktop/fb_output")

# 评论/回复的 doc_id（2026-08 实测仍有效；timeline 的 doc_id 改为运行时自动提取）
DOC_COMMENTS = "27806180149070312"   # CommentsListComponentsPaginationQuery
DOC_REPLIES  = "26570577339199586"   # Depth1CommentsListPaginationQuery

# 评论/回复 GraphQL 必需的 relay provider 字段（缺了会报 missing_required_variable_value）
COMMENT_RELAY = {
    "__relay_internal__pv__CometUFICommentAutoTranslationTyperelayprovider": "AUTO_TRANSLATE",
    "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
    "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": True,
    "__relay_internal__pv__IsWorkUserrelayprovider": False,
}
# =========================================

HEADERS = {
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://www.facebook.com",
    "referer": "https://www.facebook.com/",
}

FB_DTSG = ""


def get_dtsg(cookies=None):
    """从 Facebook 主页 HTML 提取 fb_dtsg token（GraphQL 请求必需）"""
    try:
        r = cr.get("https://www.facebook.com/", cookies=cookies, proxy=PROXY,
                   impersonate=IMPERSONATE, timeout=30)
        m = re.search(r'"DTSGInitialData"[^}]*?"token":"([^"]+)"', r.text) or \
            re.search(r'"dtsg":\{"token":"([^"]+)"', r.text)
        return m.group(1) if m else ""
    except Exception:
        return ""


def gql(doc_id, variables, friendly_name, cookies=None):
    """POST 到 GraphQL，返回解析后的 JSON dict。仅对致命错误(单数 error)抛异常；
    field_exception 等非致命 errors 列表忽略（data 里仍有数据）。"""
    global FB_DTSG
    if not FB_DTSG and cookies:
        FB_DTSG = get_dtsg(cookies)
    u = cookies.get("c_user", "0") if cookies else "0"
    payload = {
        "av": u, "__user": u, "__a": "1", "fb_dtsg": FB_DTSG,
        "fb_api_caller_class": "RelayModern", "server_timestamps": "true",
        "doc_id": doc_id, "variables": json.dumps(variables),
    }
    h = dict(HEADERS); h["x-fb-friendly-name"] = friendly_name
    r = cr.post("https://www.facebook.com/api/graphql/", headers=h, data=payload,
                cookies=cookies, proxy=PROXY, impersonate=IMPERSONATE, timeout=30)
    txt = r.text.strip()
    if txt.startswith("for (;;);"):
        txt = txt[len("for (;;);"):].strip()
    j = json.loads(txt.split("\n")[0])
    if j.get("error"):  # 致命错误（登录失效 / doc_id 过期等）
        raise RuntimeError(
            f"GraphQL error {j.get('error')}: {j.get('errorSummary','')} "
            f"[cookie 失效/checkpoint 或 doc_id 过期]")
    return j


def feedback_id_of(post_id):
    return base64.b64encode(f"feedback:{post_id}".encode()).decode()


# ---------- 帖子（标题） ----------
def _extract_timeline_params(target_id, cookies):
    """访问目标页面，从 HTML 的 preloader 里提取 timeline 的 queryID + 完整 variables 模板。
    这样不硬编码 doc_id 和 __relay_internal__pv__ 字段，FB 改版也能自适应。"""
    r = cr.get(f"https://www.facebook.com/profile.php?id={target_id}",
               cookies=cookies, proxy=PROXY, impersonate=IMPERSONATE, timeout=30)
    html = r.text
    i = html.find("ProfileCometTimelineFeedQueryRelayPreloader")
    if i < 0:
        raise RuntimeError("页面里找不到 timeline preloader（目标无效或未登录）")
    m = re.search(r'"queryID":"(\d+)"', html[i:i + 200])
    qid = m.group(1) if m else None
    start = html.find('"variables":{', i)
    depth, j = 0, start + len('"variables":')
    end = j
    for k in range(j, len(html)):
        if html[k] == '{':
            depth += 1
        elif html[k] == '}':
            depth -= 1
            if depth == 0:
                end = k + 1
                break
    template = json.loads(html[j:end])
    return qid, template


def fetch_page_posts(page_id, limit=10):
    qid, template = _extract_timeline_params(page_id, COOKIES or None)
    posts, cursor = [], None
    while len(posts) < limit:
        variables = dict(template)
        variables["count"] = 3
        variables["cursor"] = cursor
        j = gql(qid, variables, "ProfileCometTimelineFeedQuery", COOKIES or None)

        node = (j.get("data") or {}).get("user") or (j.get("data") or {}).get("node") or {}
        tlf = node.get("timeline_list_feed_units", {})
        edges = tlf.get("edges", [])
        if not edges:
            break
        for e in edges:
            n = e.get("node", {})
            if n.get("__typename") != "Story":
                continue
            msg = (n.get("comet_sections", {}).get("content", {}).get("story", {})
                     .get("message", {}) or {}).get("text")
            posts.append({
                "post_id": n.get("post_id"),
                "feedback_id": n.get("feedback", {}).get("id"),
                "title": (msg or "").split("\n")[0][:100],
                "text": msg or "",
                "time": n.get("creation_time"),
            })
            if len(posts) >= limit:
                break
        cursor = tlf.get("page_info", {}).get("end_cursor")
        if not cursor:
            break
    return posts


# ---------- 评论（含回复） ----------
def fetch_comments(feedback_id, cookies=None):
    out, cursor = [], None
    while True:
        j = gql(DOC_COMMENTS, {
            "commentsAfterCount": -1, "commentsAfterCursor": cursor,
            "commentsBeforeCount": None, "commentsBeforeCursor": None,
            "commentsIntentToken": None, "feedLocation": "POST_PERMALINK_DIALOG",
            "focusCommentID": None, "scale": 2, "useDefaultActor": False,
            "id": feedback_id, **COMMENT_RELAY,
        }, "CommentsListComponentsPaginationQuery", cookies)

        block = (j.get("data", {}).get("node", {})
                  .get("comment_rendering_instance_for_feed_location", {})
                  .get("comments", {}))
        edges = block.get("edges", [])
        if not edges:
            break
        for e in edges:
            n = e.get("node", {})
            fb = n.get("feedback", {})
            out.append({
                "commenter": (n.get("author") or {}).get("name"),
                "text": (n.get("body") or {}).get("text", ""),
                "likes": fb.get("reactors", {}).get("count_reduced", 0),
                "feedback_id": fb.get("id"),
                "expansion_token": (fb.get("expansion_info") or {}).get("expansion_token"),
                "replies": [],
            })
        cursor = block.get("page_info", {}).get("end_cursor")
        if not cursor:
            break

    # 抓每个评论的回复
    for c in out:
        if not c.get("expansion_token"):
            continue
        try:
            j = gql(DOC_REPLIES, {
                "clientKey": None, "expansionToken": c["expansion_token"],
                "feedLocation": "POST_PERMALINK_DIALOG", "focusCommentID": None,
                "scale": 2, "useDefaultActor": False, "id": c["feedback_id"],
                **COMMENT_RELAY,
            }, "Depth1CommentsListPaginationQuery", cookies)
            edges = (j.get("data", {}).get("node", {})
                      .get("replies_connection", {}).get("edges", []))
            for e in edges:
                n = e.get("node", {})
                c["replies"].append({
                    "commenter": (n.get("author") or {}).get("name"),
                    "text": (n.get("body") or {}).get("text", ""),
                    "likes": n.get("feedback", {}).get("reactors", {}).get("count_reduced", 0),
                })
        except Exception:
            pass
    return out


# ---------- 主流程 ----------
def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if not arg:
        print("用法: python fb_graphql_scraper.py <页面ID> [条数]  或  <帖子URL>")
        sys.exit(1)

    posts = []
    if arg.startswith("http"):
        m = re.search(r'/posts/(?:[^/]+/)?(\d+)', arg) or re.search(r'story_fbid=(\d+)', arg)
        if not m:
            print("无法从 URL 提取 post_id"); sys.exit(1)
        post_id = m.group(1)
        comments = fetch_comments(feedback_id_of(post_id), COOKIES or None)
        posts = [{"post_id": post_id, "title": "", "text": "", "comments": comments}]
    else:
        page_id = arg
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        posts = fetch_page_posts(page_id, limit)
        print(f"得到 {len(posts)} 条帖子，开始抓评论...")
        for p in posts:
            try:
                p["comments"] = fetch_comments(p["feedback_id"], COOKIES or None)
                print(f"  [{p['post_id']}] {p['title'][:40]} | 💬{len(p['comments'])}")
            except Exception as e:
                print(f"  [{p['post_id']}] 评论失败: {e}")
                p["comments"] = []

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "posts.json"), "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

    flat = []
    for p in posts:
        for c in p.get("comments", []):
            flat.append({"post_id": p["post_id"], "title": p.get("title", ""),
                         "text": p.get("text", "")[:200], "commenter": c.get("commenter", ""),
                         "comment": c.get("text", ""), "comment_likes": c.get("likes"),
                         "reply_to": "", "reply": ""})
            for r in c.get("replies", []):
                flat.append({"post_id": p["post_id"], "title": p.get("title", ""),
                             "text": "", "commenter": "", "comment": "",
                             "comment_likes": "", "reply_to": c.get("commenter", ""),
                             "reply": r.get("text", "")})
    if flat:
        with open(os.path.join(OUT_DIR, "posts.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(flat[0].keys()))
            w.writeheader(); w.writerows(flat)

    print(f"\n✅ 完成 → {OUT_DIR} (posts.json / posts.csv)")


if __name__ == "__main__":
    main()
