# Facebook GraphQL Scraper（帖子 → 评论 → 全量历史）

无浏览器抓取 Facebook 主页/专页的帖子（标题/正文/点赞/分享/评论/日期），支持**全量历史**（可回溯到账号创建的第一条，实测 3 年 3467 条）。

## 特性
- ✅ 纯 HTTP（curl_cffi 冒充 Chrome TLS 指纹）+ CDP 无头浏览器双通道
- ✅ `doc_id` / `fb_dtsg` 运行时自动提取 —— 不怕 Facebook 改版
- ✅ **GraphQL beforeTime 时间分页**：从任意日期往前拉，直到账号创建的第一条
- ✅ **CDP 内执行 GraphQL**：curl 被风控（fb_dtsg 停发）时，浏览器 session 不受影响，完美绕过
- ✅ 输出 JSON + CSV 双格式，全程断点续抓

## 为什么能跑通（关键技术）

| 问题 | 解法 |
|---|---|
| `requests` 被 FB 400 拦截（TLS 指纹识别） | 用 `curl_cffi` 的 `impersonate="chrome"` |
| `doc_id` 会过期、query 名会变 | 运行时从页面 HTML 的 preloader 自动提取 |
| GraphQL 需要 `fb_dtsg` | 从主页 HTML 的 `DTSGInitialData` 自动提取 |
| 浏览器滚动有深度限制（只显示最近 1-2 千条） | **GraphQL beforeTime 时间游标**逐页往前拉 |
| curl_cffi 被风控（fb_dtsg 停发 → 1357001） | **在 CDP 无头浏览器页面里执行 GraphQL fetch**（浏览器 session 正常） |
| 懒加载只在页面可见时触发 | **无头模式 `--headless=new`**（页面始终 visible） |
| 早期帖子（2023-2025）reel URL 抓不到 | 改用 `/页面名/posts/{pid}` 格式 |

## 安装

```bash
pip install curl_cffi websocket-client
```

Python 3.8+，Windows/macOS/Linux 均可。

## 使用

### 基础：帖子 + 评论

```bash
# 抓主页/专页的帖子 + 评论
python fb_graphql_scraper.py 100064368354094 5

# 抓单个帖子的全部评论
python fb_graphql_scraper.py https://www.facebook.com/xxx/posts/xxx
```

### 全量历史（三步，完整 3 年数据）

**① CDP 无头滚动收集 post_id**

```bash
# 启动无头 Edge（临时 profile 需先手动登录一次）
"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  --headless=new --remote-debugging-port=9222 --remote-allow-origins=* \
  --user-data-dir="C:\Users\13107\AppData\Local\Temp\edge_cdp" \
  "https://www.facebook.com/目标账号"

# 自动滚动收集 post_id
python cdp_scroll.py
```

**② curl_cffi 抓主数据详情（断点续抓）**

```bash
python fetch_remaining.py   # 读取 post_ids.txt，逐条抓 og:description + 互动数据
```

**③ GraphQL beforeTime 分页拉早期帖子 + posts URL 补抓**

```bash
python cdp_gql_paginate.py  # CDP 内 GraphQL 分页，从主数据最早日期往前拉（每页 1 条，慢但可靠）
python fetch_early.py       # 用 posts URL 补抓早期帖子完整详情
```

> 实战：HunanTodayHICC 从"3 条"误判 → 最终 **3467 条**（2023-06-13 ~ 2026-08-17）。
> 教训：浏览器滚动有深度限制，**必须 GraphQL beforeTime 才能拉到账号创建的第一条**。

## 脚本清单

| 脚本 | 用途 |
|---|---|
| `fb_graphql_scraper.py` | 基础：帖子标题/正文 + 评论 + 嵌套回复 |
| `cdp_scroll.py` | CDP 无头滚动收集全部 post_id |
| `fetch_remaining.py` | 主数据详情抓取（reel URL，断点续抓） |
| `cdp_gql_paginate.py` | **CDP 内 GraphQL beforeTime 分页**（拉早期帖子，核心） |
| `cdp_gql_before.py` | GraphQL beforeTime 单次查询（诊断/验证用） |
| `fetch_early.py` | 早期帖子补抓（posts URL） |
| `fb_export_console.js` | 浏览器 console 手动滚动脚本（备选方案） |

## Cookies

把 `cookies.txt`（Netscape 格式）放桌面，脚本自动读取，需要含 `c_user` + `xs`。

> ⚠️ Edge/Chrome 新版 cookie 是 v20 App-Bound 加密，**本地无法解密**。用浏览器扩展「Get cookies.txt LOCALLY」导出。
> ⚠️ 重新登录后必须重新导出（旧 session 失效）。

## 网络要求

- 需要能访问 `www.facebook.com`，中国大陆环境需代理（脚本默认 `127.0.0.1:7993`，可改 `PROXY`）
- **风控应对**：低频（4s/条 + 每 20 条停 30s）、断点续抓；curl 被风控时换 CDP 通道或重新登录

## 免责声明

仅用于个人学习与公开数据研究。请遵守 Facebook 服务条款与当地法律，勿用于未授权数据采集。
