"""
抖音推荐流分析服务

功能：
  - 刷推荐流，收集作品列表
  - 每个作品：作者 UID/昵称、点赞数、评论数、分享数
  - 进入作品详情页抓评论（用户名、内容、点赞数、时间）
  - 结果存入 Neo4j

三层架构：
  DeepSeek  → 决策层（可选，用于内容分析）
  PinchTab  → 执行层（滚动、导航）
  JS DOM    → 整理层（提取作品/评论数据）
"""

import time
import re
import os
import requests
from typing import Dict, Any, List, Optional

from ..core.pinchtab_client import PinchTabClient
from ..core.stealth import random_fingerprint, build_stealth_js, build_cookie_js, ProxyPool
from config import Config


class FeedService:

    PINCHTAB_URL   = Config.PINCHTAB_URL
    PINCHTAB_TOKEN = Config.PINCHTAB_TOKEN

    def __init__(self, deepseek_api_key: str = None):
        self.pinchtab = PinchTabClient(base_url=self.PINCHTAB_URL)
        if self.PINCHTAB_TOKEN:
            self.pinchtab.session.headers.update({
                "Authorization": f"Bearer {self.PINCHTAB_TOKEN}"
            })
        self.proxy_pool = ProxyPool()
        self.fp = random_fingerprint()

        self.deepseek_api_key = deepseek_api_key or os.getenv("DEEPSEEK_API_KEY")

        # Neo4j（可选）
        try:
            from .graph_service import GraphService
            self.graph = GraphService()
            if not self.graph.connect():
                self.graph = None
        except Exception:
            self.graph = None

    # ─────────────────────────────────────────────
    # 连接
    # ─────────────────────────────────────────────

    def connect(self, headless: bool = False) -> bool:
        self.fp = random_fingerprint()
        sess = self.pinchtab.session
        base = self.PINCHTAB_URL

        # 停旧实例
        try:
            insts = sess.get(f"{base}/instances", timeout=10).json()
            for inst in insts:
                if inst.get("profileName") == (Config.PINCHTAB_PROFILE or "default") \
                        and inst.get("status") == "running":
                    sess.post(f"{base}/instances/{inst['id']}/stop", timeout=10)
                    time.sleep(3)
                    break
        except Exception:
            pass

        proxy = self.proxy_pool.get()
        proxy_params = self.proxy_pool.format_for_pinchtab(proxy) if proxy else None

        mode = "headless" if headless else "headed"
        launch_body = {
            "name":      Config.PINCHTAB_PROFILE or "default",
            "mode":      mode,
            "userAgent": self.fp["ua"],
        }
        if proxy_params:
            launch_body["proxy"] = proxy_params

        try:
            r = sess.post(f"{base}/instances/launch", json=launch_body, timeout=15)
            if r.status_code not in [200, 201]:
                print(f"❌ 创建实例失败: {r.status_code}")
                return False
            self.pinchtab.instance_id = r.json()["id"]
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False

        for _ in range(30):
            time.sleep(1)
            try:
                r = sess.get(f"{base}/instances/{self.pinchtab.instance_id}/tabs", timeout=5)
                if r.status_code == 200 and r.json():
                    self.pinchtab.tab_id = r.json()[0]["id"]
                    self._evaluate(build_stealth_js(self.fp))
                    self._evaluate(build_cookie_js())
                    print(f"✅ 连接成功 | Tab: {self.pinchtab.tab_id}")
                    return True
            except Exception:
                pass

        print("❌ Tab 等待超时")
        return False

    # ─────────────────────────────────────────────
    # 主入口：刷推荐流
    # ─────────────────────────────────────────────

    def scrape_feed(self, max_works: int = 20, with_comments: bool = True,
                    max_comments: int = 30) -> List[Dict[str, Any]]:
        import random

        print(f"\n{'='*60}")
        print(f"📱 刷推荐流 | 目标: {max_works} 个作品 | 评论: {'是' if with_comments else '否'}")
        print(f"{'='*60}")

        self.pinchtab.navigate("https://www.douyin.com/?recommend=1&from_nav=1", wait_seconds=8)
        time.sleep(random.uniform(2, 4))

        works = []
        seen_urls = set()
        no_new = 0

        while len(works) < max_works:
            # 提取当前可见的 active 视频
            batch = self._extract_feed_items()
            new_found = 0

            for item in batch:
                url = item.get("work_url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                works.append(item)
                new_found += 1
                print(f"   [{len(works)}] {item.get('author_nickname','?')} | "
                      f"👍{item.get('likes','?')} 💬{item.get('comments_count','?')} | "
                      f"{item.get('title','')[:20]}")
                if len(works) >= max_works:
                    break

            if new_found == 0:
                no_new += 1
                if no_new >= 5:
                    break
            else:
                no_new = 0

            # 抓当前视频评论（在切换前）
            if with_comments and new_found > 0:
                last_work = works[-1]
                if "live.douyin.com" not in last_work.get("work_url", ""):
                    comments = self._scrape_comments(last_work["work_url"], max_comments)
                    last_work["comments"] = comments
                    last_work["comments_count_actual"] = len(comments)
                    if comments:
                        print(f"      💬 {len(comments)} 条评论")
                    self._close_comment_panel()
                    time.sleep(1)

            # 人类行为：看一会再切换到下一个视频
            self._human_next_video()

        print(f"\n✅ 共收集 {len(works)} 个作品")

        if self.graph:
            self._save_to_graph(works)

        # 补全作者主页信息（粉丝数、关注数、作品数）
        self._enrich_authors(works)

        return works

    def _enrich_authors(self, works: List[Dict]):
        """批量补全作者主页信息 + 作品列表"""
        uids = list({w["author_uid"] for w in works if w.get("author_uid")})
        if not uids:
            return

        print(f"\n📋 补全作者信息（{len(uids)} 人）...")
        for uid in uids:
            profile_url = f"https://www.douyin.com/user/{uid}"
            js_info = """
(function() {
    function getStatNum(key) {
        var el = document.querySelector('[data-e2e="' + key + '"]');
        if (!el) return null;
        var numDiv = el.children[1];
        if (numDiv) {
            var m = numDiv.textContent.trim().match(/^[0-9.]+[\u4e07\u4ebf]?/);
            if (m) return m[0];
        }
        var m2 = el.textContent.trim().match(/[0-9.]+[\u4e07\u4ebf]?/);
        return m2 ? m2[0] : null;
    }
    var nickEl = document.querySelector('[data-e2e="user-info"] h1');
    var worksEl = document.querySelector('[data-e2e="user-tab-count"]');

    // 作品列表
    var list = document.querySelector('[data-e2e="scroll-list"]');
    var works = [];
    if (list) {
        Array.from(list.querySelectorAll('li')).forEach(function(li, i) {
            var link = li.querySelector('a[href*="/video/"], a[href*="/note/"]');
            var likeEl = li.querySelector('.BgCg_ebQ');
            var imgEl = li.querySelector('img');
            var href = link ? link.getAttribute('href') : '';
            if (href.startsWith('/')) href = 'https://www.douyin.com' + href;
            if (href) works.push({
                position: i + 1,
                video_url: href,
                type: href.indexOf('/note/') >= 0 ? '图文' : '视频',
                likes: likeEl ? likeEl.textContent.trim() : '0',
                title: imgEl ? (imgEl.getAttribute('alt') || '') : ''
            });
        });
    }

    return {
        nickname:    nickEl ? nickEl.textContent.trim() : null,
        fans:        getStatNum('user-info-fans'),
        following:   getStatNum('user-info-follow'),
        total_likes: getStatNum('user-info-like'),
        works_count: worksEl ? worksEl.textContent.trim() : null,
        works:       works,
        url:         window.location.href
    };
})()
"""
            self.pinchtab.navigate(profile_url, wait_seconds=5)
            # 触发懒加载
            self._evaluate("window.scrollBy(0, 600)")
            import time as _t; _t.sleep(2)
            self._evaluate("window.scrollTo(0, 0)")
            _t.sleep(1)

            info = self._evaluate(js_info) or {}

            if info.get("nickname"):
                author_works = info.get("works", [])
                print(f"   {info['nickname']} | 粉丝:{info.get('fans','?')} | 关注:{info.get('following','?')} | 获赞:{info.get('total_likes','?')} | 作品:{len(author_works)}个")
                if self.graph:
                    self.graph.upsert_user(uid, info)
                    for w in author_works:
                        self.graph.upsert_work(uid, w)

    def _human_next_video(self):
        """模拟人类看完视频后切换到下一个"""
        import random

        # 看视频停留 5~20 秒
        watch_time = random.uniform(5, 20)
        print(f"   ⏱  停留 {watch_time:.1f}s...")
        time.sleep(watch_time)

        # 点击下一个视频按钮，或按键盘下箭头
        clicked = self._evaluate("""
(function() {
    var btn = document.querySelector('[data-e2e="video-switch-next-arrow"]');
    if (btn) { btn.click(); return 'clicked'; }
    return 'not_found';
})()
""")
        if clicked != 'clicked':
            # 兜底：按键盘下箭头
            self._evaluate("document.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowDown', keyCode:40, bubbles:true}))")

        time.sleep(random.uniform(1, 2))

    # ─────────────────────────────────────────────
    # JS DOM：提取推荐流作品卡片
    # ─────────────────────────────────────────────

    def _extract_feed_items(self) -> List[Dict]:
        """提取当前正在播放的推荐内容（视频/直播/图文）"""
        js = """
(function() {
    var card = document.querySelector('[data-e2e="feed-active-video"]') ||
               document.querySelector('[data-e2e="feed-item"]');
    if (!card) return [];

    // 昵称
    var nickEl = card.querySelector('[data-e2e="feed-video-nickname"]') ||
                 card.querySelector('[data-e2e="video-author-title"]');
    var nickname = nickEl ? nickEl.textContent.trim() : '';

    // 作者 UID
    var authorLink = card.querySelector('a[href*="/user/MS4"]');
    var authorHref = authorLink ? authorLink.getAttribute('href') : '';
    if (authorHref && authorHref.startsWith('/')) authorHref = 'https://www.douyin.com' + authorHref;
    var uidMatch = authorHref ? authorHref.match(/[/]user[/](MS4[^?#]+)/) : null;
    var uid = uidMatch ? uidMatch[1] : '';

    // 判断内容类型 + 获取链接
    var href = '';
    var contentType = 'unknown';

    // 1. 直播
    var liveLink = card.querySelector('a[href*="live.douyin.com"]');
    if (liveLink) {
        href = liveLink.href;
        contentType = '直播';
    }

    // 2. 普通视频
    if (!href) {
        var videoLink = card.querySelector('a[href*="/video/"]');
        if (videoLink) {
            href = videoLink.getAttribute('href') || '';
            if (href.startsWith('/')) href = 'https://www.douyin.com' + href;
            contentType = '视频';
        }
    }

    // 3. 图文
    if (!href) {
        var noteLink = card.querySelector('a[href*="/note/"]');
        if (noteLink) {
            href = noteLink.getAttribute('href') || '';
            if (href.startsWith('/')) href = 'https://www.douyin.com' + href;
            contentType = '图文';
        }
    }

    // 4. 从 aweme_id 参数构造（兜底）
    if (!href) {
        var anyLink = card.querySelector('a[href*="aweme_id="]');
        if (anyLink) {
            var m = anyLink.href.match(/aweme_id=([0-9]+)/);
            if (m) {
                href = 'https://www.douyin.com/video/' + m[1];
                contentType = '视频';
            }
        }
    }

    if (!href) return [];

    // 点赞数
    var likeEl = card.querySelector('[data-e2e="video-player-digg"] strong') ||
                 card.querySelector('[data-e2e="video-player-digg"]');
    var likes = likeEl ? likeEl.textContent.trim() : '0';

    // 评论数
    var commentEl = card.querySelector('[data-e2e="feed-comment-icon"] strong') ||
                    card.querySelector('[data-e2e="feed-comment-icon"]');
    var comments_count = commentEl ? commentEl.textContent.trim() : '0';

    // 分享数
    var shareEl = card.querySelector('[data-e2e="video-player-share"] strong') ||
                  card.querySelector('[data-e2e="video-player-share"]');
    var shares = shareEl ? shareEl.textContent.trim() : '0';

    // 标题/描述
    var titleEl = card.querySelector('[data-e2e="video-desc"]') ||
                  card.querySelector('[data-e2e="video-info"]');
    var title = titleEl ? titleEl.textContent.trim() : '';

    return [{
        work_url:        href,
        type:            contentType,
        author_uid:      uid,
        author_nickname: nickname,
        likes:           likes,
        comments_count:  comments_count,
        shares:          shares,
        title:           title.slice(0, 100)
    }];
})()
"""
        result = self._evaluate(js)
        return result if isinstance(result, list) else []

    # ─────────────────────────────────────────────
    # JS DOM：抓作品评论
    # ─────────────────────────────────────────────

    def _scrape_comments(self, work_url: str, max_comments: int = 30) -> List[Dict]:
        """
        在当前推荐流页面点击评论图标，从弹出的评论面板抓取评论
        不跳转到视频详情页
        """
        import random

        if "live.douyin.com" in work_url:
            return []

        # 点击评论图标打开面板（在推荐流页面操作）
        click_result = self._evaluate("""
(function(){
    var icon = document.querySelector('[data-e2e="feed-comment-icon"]');
    if (!icon) return 'not_found';
    icon.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));
    return 'clicked';
})()
""")
        if click_result != 'clicked':
            return []

        time.sleep(3)

        # 等评论面板出现
        panel = None
        for _ in range(8):
            count = self._evaluate('document.querySelectorAll(\'[data-e2e="comment-item"]\').length') or 0
            if count > 0:
                break
            time.sleep(1)

        js_extract = """
(function() {
    var container = document.querySelector('[data-e2e="comment-list"]');
    if (!container) return [];
    return Array.from(container.querySelectorAll('[data-e2e="comment-item"]')).map(function(el) {
        var userLink = el.querySelector('a[href*="/user/"]');
        var uid = '';
        if (userLink) {
            var m = userLink.getAttribute('href').match(/[/]user[/](MS4[^?#]+)/);
            uid = m ? m[1] : '';
        }
        var nickname = userLink ? userLink.textContent.trim() : '';
        var textEl = el.querySelector('.C7LroK_h') || el.querySelector('[data-e2e="comment-text"]');
        var text = textEl ? textEl.textContent.trim() : '';
        var likeEl = el.querySelector('p.xZhLomAs') || el.querySelector('[data-e2e="comment-like-count"]');
        var likes = likeEl ? likeEl.textContent.trim() : '0';
        var timeEl = el.querySelector('.fJhvAqos') || el.querySelector('[data-e2e="comment-time"]');
        var time_str = timeEl ? timeEl.textContent.trim() : '';
        return {uid: uid, nickname: nickname, text: text, likes: likes, time: time_str};
    }).filter(function(c) { return c.text; });
})()
"""
        # 点击"查看更多评论"按钮加载更多
        js_load_more = """
(function(){
    // 优先点击评论图标打开评论面板（推荐流模式）
    var commentIcon = document.querySelector('[data-e2e="feed-comment-icon"]');
    if (commentIcon) {
        commentIcon.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
        return 'icon_clicked';
    }
    // 兜底：点击"查看更多"按钮
    var btn = document.querySelector('[data-e2e="video-comment-more"]');
    if (btn) { btn.click(); return 'more_clicked'; }
    return 'none';
})()
"""
        seen = set()
        comments = []
        no_new = 0

        while len(comments) < max_comments:
            rows = self._evaluate(js_extract) or []
            new_found = 0
            for row in rows:
                key = row.get("nickname", "") + row.get("text", "")
                if key and key not in seen:
                    seen.add(key)
                    row["position"] = len(comments) + 1
                    comments.append(row)
                    new_found += 1
                    if len(comments) >= max_comments:
                        break

            if new_found == 0:
                no_new += 1
                if no_new >= 3:
                    break
            else:
                no_new = 0

            # 滚动评论面板加载更多
            scroll_result = self._evaluate("""
(function(){
    // 找可滚动的评论容器
    var selectors = [
        '[data-e2e="comment-list"]',
        '.comment-list',
        '[class*="commentList"]',
        '[class*="comment-panel"]'
    ];
    for (var i = 0; i < selectors.length; i++) {
        var el = document.querySelector(selectors[i]);
        if (el && el.scrollHeight > el.clientHeight) {
            el.scrollTop += 800;
            return 'scrolled:' + el.scrollTop;
        }
    }
    // 兜底：找所有 scrollHeight > clientHeight 的 div
    var divs = Array.from(document.querySelectorAll('div'));
    var scrollable = divs.find(d => d.scrollHeight > d.clientHeight + 100 && d.scrollHeight > 500);
    if (scrollable) { scrollable.scrollTop += 800; return 'fallback:' + scrollable.scrollTop; }
    return 'no_scroll';
})()
""")
            time.sleep(random.uniform(1.5, 2.5))

            if scroll_result == 'no_scroll':
                no_new += 1

        return comments

    def _close_comment_panel(self):
        """关闭评论面板"""
        self._evaluate("""
(function(){
    // 按 ESC 关闭
    document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', keyCode:27, bubbles:true}));
    // 或者点击关闭按钮
    var closeBtn = document.querySelector('[data-e2e="comment-close"]') ||
                   document.querySelector('[aria-label="关闭"]');
    if (closeBtn) closeBtn.click();
})()
""")

    # ─────────────────────────────────────────────
    # Neo4j 存储
    # ─────────────────────────────────────────────

    def _save_to_graph(self, works: List[Dict]):
        print(f"\n💾 存入 Neo4j...")
        for work in works:
            uid = work.get("author_uid")
            if uid:
                self.graph.upsert_user(uid, {
                    "nickname": work.get("author_nickname", ""),
                    "url": f"https://www.douyin.com/user/{uid}"
                })
                self.graph.upsert_work(uid, {
                    "video_url": work.get("work_url", ""),
                    "type":      work.get("type", "视频"),
                    "likes":     work.get("likes", "0"),
                    "title":     work.get("title", ""),
                })

                # 评论者也存为用户节点
                for c in work.get("comments", []):
                    c_uid = c.get("uid")
                    if c_uid:
                        self.graph.upsert_user(c_uid, {"nickname": c.get("nickname", "")})

        stats = self.graph.stats()
        print(f"   图谱: {stats['users']} 用户, {stats['works']} 作品, {stats['follows']} 关系")

    # ─────────────────────────────────────────────
    # 工具
    # ─────────────────────────────────────────────

    def _evaluate(self, js: str) -> Any:
        try:
            resp = self.pinchtab.session.post(
                f"{self.PINCHTAB_URL}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js}, timeout=10
            )
            if resp.status_code == 200:
                return resp.json().get("result")
        except Exception as e:
            print(f"   ⚠️  JS 执行失败: {e}")
        return None

    def cleanup(self):
        self.pinchtab.cleanup()
        if self.graph:
            self.graph.close()
