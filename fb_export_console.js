// Facebook 自动滚动收集脚本 v4（回到 v1 成功滚动方式，放宽到底判断）
// 用法：刷新目标账号主页 → F12 → Console → 粘贴整段 → 回车
// 边滚边收集 post_id，逐步滚动触发懒加载，到底判断更宽松，能滚到更早的帖子
(async () => {
  const seen = new Set();
  const posts = [];
  const step = 500;
  const wait = 2200;

  function harvest() {
    document.querySelectorAll(
      'a[href*="/posts/"], a[href*="/reel/"], a[href*="/videos/"], a[href*="story.php"]'
    ).forEach((a) => {
      const href = a.href;
      let m = href.match(/\/(?:posts|reel|videos)\/(?:[^/]+\/)?(\d{10,})/) || href.match(/story_fbid=(\d{10,})/);
      if (!m) return;
      const pid = m[1];
      if (!seen.has(pid)) { seen.add(pid); posts.push({ post_id: pid, url: href }); }
    });
  }

  harvest();

  let target = 0;
  let stuck = 0;
  for (let i = 0; i < 1500; i++) {
    target += step;
    window.scrollTo(0, target);
    await new Promise((r) => setTimeout(r, wait));
    harvest();

    const pos = window.pageYOffset;
    const docHeight = document.documentElement.scrollHeight;

    if (i % 20 === 0) {
      console.log(`#${i}  位置=${pos}  页面高=${docHeight}  已收集=${posts.length} 条`);
    }

    if (pos + window.innerHeight >= docHeight - 200) {
      stuck++;
      if (stuck >= 8) {
        // 到底后多等几秒，确认没有更多加载
        await new Promise((r) => setTimeout(r, 4000));
        harvest();
        break;
      }
    } else {
      stuck = 0;
    }
  }

  console.log('=== 收集完成，共 ' + posts.length + ' 条帖子 ===');
  console.log(JSON.stringify(posts));
  return posts;
})();
