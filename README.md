# Facebook GraphQL Scraper（帖子标题 → 评论）

无浏览器抓取 Facebook 主页/专页/个人主页的帖子（标题/正文）→ 评论 → 嵌套回复，输出 JSON/CSV。

## 特性
- ✅ 纯 HTTP（curl_cffi 冒充 Chrome TLS 指纹），**无需浏览器/Selenium**
- ✅ `doc_id` 运行时自动提取 —— 不怕 Facebook 改版
- ✅ `fb_dtsg` token 自动提取
- ✅ 支持主页/专页/个人主页帖子列表 + 单帖全部评论 + 嵌套回复
- ✅ 输出 JSON + CSV 双格式

## 为什么能跑通（关键技术）

| 问题 | 解法 |
|---|---|
| `requests` 被 FB 400 拦截（TLS 指纹识别） | 用 `curl_cffi` 的 `impersonate="chrome"` |
| `doc_id` 会过期、query 名会变 | 运行时从页面 HTML 的 preloader 自动提取 |
| GraphQL 需要 `fb_dtsg` | 从主页 HTML 的 `DTSGInitialData` 自动提取 |
| 评论缺 `__relay_internal__pv__` 字段报错 | 脚本内置 relay provider 字段 |

## 安装

```bash
pip install curl_cffi
```

Python 3.8+，Windows/macOS/Linux 均可。

## 使用

```bash
# 抓主页/专页的帖子 + 评论（Nintendo 专页前 5 条）
python fb_graphql_scraper.py 100064368354094 5

# 抓单个帖子的全部评论
python fb_graphql_scraper.py https://www.facebook.com/xxx/posts/xxx
```

输出到 `~/Desktop/fb_output/posts.json` + `posts.csv`。

## Cookies

把 `cookies.txt`（Netscape 格式）放桌面，脚本自动读取，需要含 `c_user` + `xs`（建议再加 `datr`/`sb`/`fr`）。

> ⚠️ Edge/Chrome 新版 cookie 是 v20 App-Bound 加密，**本地无法解密**。用浏览器扩展「Get cookies.txt LOCALLY」（Chrome 商店）导出，或 F12 → 应用 → Cookie → 手动复制 `c_user` 和 `xs`。

## 网络要求

- 需要能访问 `www.facebook.com`
- 中国大陆环境需代理，脚本默认走 `127.0.0.1:7993`（可改脚本顶部 `PROXY`）

## 免责声明

仅用于个人学习与公开数据研究。请遵守 Facebook 服务条款与当地法律，勿用于未授权数据采集。
