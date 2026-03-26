"""
抖音账号管理服务
DeepSeek 作为大脑分析页面，PinchTab 作为手脚执行操作
"""

import time
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..core import PinchTabClient


class AccountService:
    """抖音账号管理服务"""

    def __init__(self, pinchtab_url: str = "http://localhost:9867", deepseek_api_key: str = None):
        self.pinchtab = PinchTabClient(pinchtab_url)

        if not deepseek_api_key:
            import os
            deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

        self.deepseek = OpenAI(
            api_key=deepseek_api_key,
            base_url="https://api.deepseek.com"
        ) if deepseek_api_key else None

    def connect(self, profile_name: str = None, headless: bool = False) -> bool:
        if profile_name:
            print(f"\n🔗 使用 Profile: {profile_name}")
        return self.pinchtab.connect(profile_name, headless)

    # ─────────────────────────────────────────────
    # 1. 个人主页信息（昵称、简介、抖音号、粉丝、关注、获赞）
    # ─────────────────────────────────────────────
    def get_profile_info(self) -> Dict[str, Any]:
        """用 JS 直接从 DOM 提取个人主页信息，精准不依赖 AI"""
        print("\n📋 获取个人主页信息...")
        self.pinchtab.navigate("https://www.douyin.com/user/self", wait_seconds=5)

        js = """
(function() {
    function getE2E(key) {
        var el = document.querySelector('[data-e2e="' + key + '"]');
        return el ? el.textContent.trim() : null;
    }
    function parseNum(text) {
        if (!text) return null;
        var m = text.match(/[0-9.]+[万亿]?/);
        return m ? m[0] : null;
    }

    // 昵称：user-info 下的 H1
    var nickEl = document.querySelector('[data-e2e="user-info"] h1');
    var nickname = nickEl ? nickEl.textContent.trim() : null;

    // 简介：抖音号那行的 P 标签之后可能有简介，先尝试 user-info-desc
    var bioEl = document.querySelector('[data-e2e="user-info-desc"]');
    var bio = bioEl ? bioEl.textContent.trim() : '';

    // 抖音号
    var infoText = getE2E('user-info') || '';
    var idMatch = infoText.match(/\u6296\u97f3\u53f7[\uff1a:]\\s*(\\S+)/);
    var douyinId = idMatch ? idMatch[1] : null;

    // 粉丝、关注、获赞：取第二个子 DIV（纯数字那个），忽略后面的"X人正在直播"
    function getStatNum(key) {
        var el = document.querySelector('[data-e2e="' + key + '"]');
        if (!el) return null;
        // 结构：DIV[0]=标签文字, DIV[1]=数字, DIV[2]=直播人数（可选）
        var numDiv = el.children[1];
        if (numDiv) {
            var m = numDiv.textContent.trim().match(/^[0-9.]+[万亿]?/);
            if (m) return m[0];
        }
        // 兜底：从完整文本提取
        return parseNum(el.textContent.trim());
    }

    // 作品数：user-tab-count 或 scroll-list 实际条数
    var worksCountEl = document.querySelector('[data-e2e="user-tab-count"]');
    var worksCount = worksCountEl ? worksCountEl.textContent.trim() : null;
    // 兜底：数 scroll-list 里的 li
    if (!worksCount) {
        var list = document.querySelector('[data-e2e="scroll-list"]');
        if (list) worksCount = String(list.querySelectorAll('li').length);
    }

    return {
        nickname: nickname,
        bio: bio,
        douyin_id: douyinId,
        fans: getStatNum('user-info-fans'),
        following: getStatNum('user-info-follow'),
        likes: getStatNum('user-info-like'),
        works_count: worksCount
    };
})()
"""
        import requests as _req
        resp = _req.post(
            f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
            json={"expression": js},
            timeout=10
        )
        result = resp.json().get("result", {}) if resp.status_code == 200 else {}

        print(f"   昵称: {result.get('nickname', '未知')}")
        print(f"   简介: {result.get('bio', '无')}")
        print(f"   抖音号: {result.get('douyin_id', '未知')}")
        print(f"   粉丝: {result.get('fans', '?')}")
        print(f"   关注: {result.get('following', '?')}")
        print(f"   获赞: {result.get('likes', '?')}")
        print(f"   作品数: {result.get('works_count', '?')}")
        return result

    # ─────────────────────────────────────────────
    # 2. 粉丝列表（昵称、简介、UID、位置）
    # ─────────────────────────────────────────────
    def get_followers(self, max_count: int = 20) -> Dict[str, Any]:
        """用 JS 直接从 DOM 提取粉丝列表"""
        print(f"\n👥 获取粉丝列表（最多 {max_count} 人）...")
        self.pinchtab.navigate("https://www.douyin.com/user/self", wait_seconds=5)

        import requests as _req

        # 点击"粉丝"数字打开弹窗
        _req.post(
            f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
            json={"expression": "document.querySelector('[data-e2e=\"user-info-fans\"]').click()"},
            timeout=5
        )
        time.sleep(3)

        # 弹窗默认打开的是关注 tab，需要切换到粉丝 tab（semiTab1）
        _req.post(
            f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
            json={"expression": "var t = document.getElementById('semiTab1'); if(t) t.click();"},
            timeout=5
        )
        time.sleep(2)

        js_extract = """
(function() {
    var container = document.querySelector('[data-e2e="user-fans-container"]');
    if (!container) return [];
    var rows = Array.from(container.querySelectorAll('.i5U4dMnB'));
    return rows.map(function(row) {
        var nickLink = row.querySelector('.kUKK9Qal a');
        var href = nickLink ? nickLink.getAttribute('href') : '';
        if (!href || href.indexOf('/user/') < 0) {
            var avatarLink = row.querySelector('.umh5JQVJ a[href*="/user/"]');
            href = avatarLink ? avatarLink.getAttribute('href') : '';
        }
        var uidMatch = href.match(/\\/user\\/([^?#]+)/);
        var uid = uidMatch ? uidMatch[1] : '';
        var nickEl = row.querySelector('.kUKK9Qal a span');
        var nickname = nickEl ? nickEl.textContent.trim() : '';
        var bioEl = row.querySelector('.B_5R_Mpq span');
        var bio = bioEl ? bioEl.textContent.trim() : '';
        return {uid: uid, nickname: nickname, bio: bio};
    }).filter(function(u) { return u.uid; });
})()
"""
        js_scroll = """
(function() {
    var container = document.querySelector('[data-e2e="user-fans-container"]');
    if (!container) return false;
    container.scrollTop += 600;
    return container.scrollTop;
})()
"""
        js_scroll_pos = """
(function() {
    var container = document.querySelector('[data-e2e="user-fans-container"]');
    if (!container) return -1;
    return container.scrollTop;
})()
"""
        seen_uids = set()
        users = []
        no_new_count = 0
        last_scroll_pos = -1

        while len(users) < max_count:
            resp = _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_extract}, timeout=10
            )
            rows = resp.json().get("result", []) if resp.status_code == 200 else []

            new_found = 0
            for row in rows:
                uid = row.get("uid", "")
                if uid and uid not in seen_uids:
                    seen_uids.add(uid)
                    users.append({
                        "position": len(users) + 1,
                        "nickname": row.get("nickname", ""),
                        "uid": uid,
                        "bio": row.get("bio", ""),
                        "profile_url": f"https://www.douyin.com/user/{uid}"
                    })
                    new_found += 1
                    if len(users) >= max_count:
                        break

            if new_found == 0:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0

            _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_scroll}, timeout=5
            )
            time.sleep(1.5)

            pos_resp = _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_scroll_pos}, timeout=5
            )
            cur_pos = pos_resp.json().get("result", -1) if pos_resp.status_code == 200 else -1
            if cur_pos != -1 and cur_pos == last_scroll_pos:
                break
            last_scroll_pos = cur_pos

        print(f"   共收集 {len(users)} 个粉丝")
        for u in users:
            print(f"   {u['position']}. {u.get('nickname', '?')} | 简介: {u.get('bio', '无')[:30]}")
        return {"success": True, "count": len(users), "followers": users}

    # ─────────────────────────────────────────────
    # 3. 关注列表（昵称、简介、UID、位置）
    # ─────────────────────────────────────────────
    def get_following(self, max_count: int = 20) -> Dict[str, Any]:
        """用 JS 直接从 DOM 提取关注列表"""
        print(f"\n➕ 获取关注列表（最多 {max_count} 人）...")
        self.pinchtab.navigate("https://www.douyin.com/user/self", wait_seconds=5)

        # 点击"关注"数字打开弹窗
        import requests as _req
        _req.post(
            f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
            json={"expression": "document.querySelector('[data-e2e=\"user-info-follow\"]').click()"},
            timeout=5
        )
        time.sleep(3)

        # JS：提取当前可见的所有用户行
        js_extract = """
(function() {
    var container = document.querySelector('[data-e2e="user-fans-container"]');
    if (!container) return [];
    var rows = Array.from(container.querySelectorAll('.i5U4dMnB'));
    return rows.map(function(row) {
        // UID：优先从 PETaiSYi 里的昵称链接取（正在直播时头像链接是 live.douyin.com）
        var nickLink = row.querySelector('.kUKK9Qal a');
        var href = nickLink ? nickLink.getAttribute('href') : '';
        // 备用：头像链接
        if (!href || href.indexOf('/user/') < 0) {
            var avatarLink = row.querySelector('.umh5JQVJ a[href*="/user/"]');
            href = avatarLink ? avatarLink.getAttribute('href') : '';
        }
        var uidMatch = href.match(/\\/user\\/([^?#]+)/);
        var uid = uidMatch ? uidMatch[1] : '';

        // 昵称
        var nickEl = row.querySelector('.kUKK9Qal a span');
        var nickname = nickEl ? nickEl.textContent.trim() : '';

        // 简介
        var bioEl = row.querySelector('.B_5R_Mpq span');
        var bio = bioEl ? bioEl.textContent.trim() : '';

        return {uid: uid, nickname: nickname, bio: bio};
    }).filter(function(u) { return u.uid; });
})()
"""
        # JS：滚动弹窗列表容器
        js_scroll = """
(function() {
    var container = document.querySelector('[data-e2e="user-fans-container"]');
    if (!container) return false;
    container.scrollTop += 600;
    return container.scrollTop;
})()
"""
        # JS：检查滚动是否到底（scrollTop 不再增加）
        js_scroll_pos = """
(function() {
    var container = document.querySelector('[data-e2e="user-fans-container"]');
    if (!container) return -1;
    return container.scrollTop;
})()
"""

        seen_uids = set()
        users = []
        no_new_count = 0
        last_scroll_pos = -1

        while len(users) < max_count:
            resp = _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_extract}, timeout=10
            )
            rows = resp.json().get("result", []) if resp.status_code == 200 else []

            new_found = 0
            for row in rows:
                uid = row.get("uid", "")
                if uid and uid not in seen_uids:
                    seen_uids.add(uid)
                    users.append({
                        "position": len(users) + 1,
                        "nickname": row.get("nickname", ""),
                        "uid": uid,
                        "bio": row.get("bio", ""),
                        "profile_url": f"https://www.douyin.com/user/{uid}"
                    })
                    new_found += 1
                    if len(users) >= max_count:
                        break

            if new_found == 0:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0

            # 滚动，检查位置是否变化
            _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_scroll}, timeout=5
            )
            time.sleep(1.5)

            pos_resp = _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_scroll_pos}, timeout=5
            )
            cur_pos = pos_resp.json().get("result", -1) if pos_resp.status_code == 200 else -1
            if cur_pos != -1 and cur_pos == last_scroll_pos:
                # 滚动位置没变，真的到底了
                break
            last_scroll_pos = cur_pos

        print(f"   共收集 {len(users)} 个关注")
        for u in users:
            print(f"   {u['position']}. {u.get('nickname', '?')} | 简介: {u.get('bio', '无')[:30]}")
        return {"success": True, "count": len(users), "following": users}

    # ─────────────────────────────────────────────
    # 4. 作品列表（点赞、链接、标题）
    # ─────────────────────────────────────────────
    def get_works(self, max_count: int = 20) -> Dict[str, Any]:
        """用 JS 直接从 DOM 提取作品列表，支持滚动加载"""
        print(f"\n🎬 获取作品数据（最多 {max_count} 个）...")
        import requests as _req
        self.pinchtab.navigate("https://www.douyin.com/user/self", wait_seconds=6)
        # 触发懒加载：先滚动一次再回顶
        _req.post(f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                  json={"expression": "window.scrollBy(0, 600)"}, timeout=5)
        time.sleep(2)
        _req.post(f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                  json={"expression": "window.scrollTo(0, 0)"}, timeout=5)
        time.sleep(1)

        js_extract = """
(function() {
    var list = document.querySelector('[data-e2e="scroll-list"]');
    if (!list) return [];
    return Array.from(list.querySelectorAll('li')).map(function(li, i) {
        var link = li.querySelector('a[href*="/video/"], a[href*="/note/"]');
        var likeEl = li.querySelector('.BgCg_ebQ');
        var imgEl = li.querySelector('img');
        var href = link ? link.getAttribute('href') : '';
        // 补全协议头
        if (href.startsWith('//')) href = 'https:' + href;
        else if (href.startsWith('/')) href = 'https://www.douyin.com' + href;
        var type = href.indexOf('/note/') >= 0 ? '图文' : '视频';
        return {
            position: i + 1,
            video_url: href,
            type: type,
            likes: likeEl ? likeEl.textContent.trim() : '0',
            title: imgEl ? (imgEl.getAttribute('alt') || '') : ''
        };
    }).filter(function(w) { return w.video_url; });
})()
"""
        js_scroll = "window.scrollBy(0, 800)"
        js_scroll_pos = "document.documentElement.scrollTop || document.body.scrollTop"

        seen_urls = set()
        works = []
        no_new_count = 0
        last_scroll_pos = -1

        while len(works) < max_count:
            resp = _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_extract}, timeout=10
            )
            rows = resp.json().get("result", []) if resp.status_code == 200 else []

            new_found = 0
            for row in rows:
                url = row.get("video_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    row["position"] = len(works) + 1
                    works.append(row)
                    new_found += 1
                    if len(works) >= max_count:
                        break

            if new_found == 0:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0

            _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_scroll}, timeout=5
            )
            time.sleep(1.5)

            pos_resp = _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_scroll_pos}, timeout=5
            )
            cur_pos = pos_resp.json().get("result", -1) if pos_resp.status_code == 200 else -1
            if cur_pos != -1 and cur_pos == last_scroll_pos:
                break
            last_scroll_pos = cur_pos

        print(f"   共找到 {len(works)} 个作品")
        for w in works:
            print(f"   {w['position']}. [{w.get('type','?')}] 点赞:{w['likes']} | {w['title'][:20] or w['video_url'][-40:]}")
        return {"success": True, "count": len(works), "works": works}

    def get_work_comments(self, work_url: str, max_comments: int = 50) -> List[Dict]:
        """进入作品详情页，用 JS 提取评论列表（含滚动加载）"""
        import requests as _req
        self.pinchtab.navigate(work_url, wait_seconds=5)

        # 等评论区加载完（最多 6 秒），同时检测"暂无评论"快速退出
        has_comments = False
        for _ in range(6):
            resp = _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": """
(function() {
    var item = document.querySelector('[data-e2e="comment-list"] [data-e2e="comment-item"]');
    if (item) return 'has';
    var empty = document.querySelector('[data-e2e="comment-list"] [data-e2e="error-page"]');
    if (empty) return 'empty';
    return 'loading';
})()
"""},
                timeout=5
            )
            state = resp.json().get("result", "loading") if resp.status_code == 200 else "loading"
            if state == "has":
                has_comments = True
                break
            if state == "empty":
                return []  # 暂无评论，直接返回
            time.sleep(1)

        if not has_comments:
            return []

        js_extract = """
(function() {
    var container = document.querySelector('[data-e2e="comment-list"]');
    if (!container) return [];
    return Array.from(container.querySelectorAll('[data-e2e="comment-item"]')).map(function(el) {
        var userLink = el.querySelector('a[href*="/user/"]');
        var user = userLink ? userLink.textContent.trim() : '';
        var uid = '';
        if (userLink) {
            var m = userLink.getAttribute('href').match(/\\/user\\/([^?#]+)/);
            uid = m ? m[1] : '';
        }
        var textEl = el.querySelector('.C7LroK_h');
        var text = textEl ? textEl.textContent.trim() : '';
        var timeEl = el.querySelector('.fJhvAqos');
        var time_str = timeEl ? timeEl.textContent.trim() : '';
        var likeEl = el.querySelector('p.xZhLomAs');
        var likes = likeEl ? likeEl.textContent.trim() : '0';
        return {user: user, uid: uid, text: text, likes: likes, time: time_str};
    });
})()
"""
        js_scroll = "window.scrollBy(0, 600); document.documentElement.scrollTop || document.body.scrollTop"
        js_scroll_pos = "document.documentElement.scrollTop || document.body.scrollTop"

        seen_texts = set()
        comments = []
        no_new_count = 0
        last_scroll_pos = None

        while len(comments) < max_comments:
            resp = _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_extract}, timeout=10
            )
            rows = resp.json().get("result", []) if resp.status_code == 200 else []

            new_found = 0
            for row in rows:
                key = row.get("user", "") + row.get("text", "")
                if key and key not in seen_texts:
                    seen_texts.add(key)
                    row["position"] = len(comments) + 1
                    comments.append(row)
                    new_found += 1
                    if len(comments) >= max_comments:
                        break

            if new_found == 0:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0

            pos_resp = _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_scroll}, timeout=5
            )
            time.sleep(1.5)

            cur_pos = _req.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_scroll_pos}, timeout=5
            ).json().get("result", None)
            if cur_pos is not None and cur_pos == last_scroll_pos:
                break
            last_scroll_pos = cur_pos

        return comments

    def get_works_with_comments(self, max_works: int = 20, max_comments: int = 50) -> Dict[str, Any]:
        """获取自己所有作品，并逐个提取评论"""
        works_result = self.get_works(max_works)
        works = works_result.get("works", [])

        print(f"\n💬 逐个读取作品评论（共 {len(works)} 个作品）...")
        for w in works:
            print(f"\n   [{w['position']}] {w.get('type','?')} | 点赞:{w['likes']} | {w['video_url'][-40:]}")
            comments = self.get_work_comments(w["video_url"], max_comments)
            w["comments"] = comments
            w["comment_count"] = len(comments)
            if comments:
                for c in comments:
                    print(f"      💬 {c['user']}: {c['text'][:40]} | 赞:{c['likes']} {c.get('time','')}")
            else:
                print(f"      (暂无评论)")

        return {"success": True, "count": len(works), "works": works}

    # ─────────────────────────────────────────────
    # 4. 获取指定用户主页详情（抖音号、关注、粉丝、作品及点赞）
    # ─────────────────────────────────────────────
    def get_user_detail(self, profile_url: str, with_comments: bool = False, max_comments: int = 50) -> Dict[str, Any]:
        """导航到用户主页，用 JS 提取抖音号、关注数、粉丝数、作品列表（含点赞数）。
        with_comments=True 时逐个进入作品详情页提取评论。
        """
        import requests as _req
        self.pinchtab.navigate(profile_url, wait_seconds=5)

        js = """
(function() {
    function getE2E(key) {
        var el = document.querySelector('[data-e2e="' + key + '"]');
        return el ? el.textContent.trim() : null;
    }
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

    // 昵称
    var nickEl = document.querySelector('[data-e2e="user-info"] h1');
    var nickname = nickEl ? nickEl.textContent.trim() : null;

    // 抖音号：从专用 span 精确提取（避免混入 IP 归属地）
    var douyinId = null;
    var idSpan = document.querySelector('[data-e2e="user-info"] span.OcCvtZ2a');
    if (idSpan) {
        var m = idSpan.textContent.match(/\u6296\u97f3\u53f7[\uff1a:]\\s*([0-9a-zA-Z_.-]+)/);
        if (m) douyinId = m[1];
    }
    // 兜底：从 p 标签第一个 span 取
    if (!douyinId) {
        var pTags = Array.from(document.querySelectorAll('[data-e2e="user-info"] p'));
        pTags.forEach(function(p) {
            var firstSpan = p.querySelector('span');
            if (firstSpan) {
                var m2 = firstSpan.textContent.match(/\u6296\u97f3\u53f7[\uff1a:]\\s*([0-9a-zA-Z_.-]+)/);
                if (m2) douyinId = m2[1];
            }
        });
    }

    // 作品数
    var worksCount = getE2E('user-tab-count');

    // 作品列表（点赞数）
    var works = [];
    var list = document.querySelector('[data-e2e="scroll-list"]');
    if (list) {
        Array.from(list.querySelectorAll('li')).forEach(function(li, i) {
            var link = li.querySelector('a[href*="/video/"], a[href*="/note/"]');
            var likeEl = li.querySelector('.BgCg_ebQ');
            var imgEl = li.querySelector('img');
            var href = link ? link.getAttribute('href') : '';
            if (href.indexOf('//') === 0) href = 'https:' + href;
            else if (href.indexOf('/') === 0) href = 'https://www.douyin.com' + href;
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
        nickname: nickname,
        douyin_id: douyinId,
        fans: getStatNum('user-info-fans'),
        following: getStatNum('user-info-follow'),
        total_likes: getStatNum('user-info-like'),
        works_count: worksCount,
        works: works,
        url: window.location.href
    };
})()
"""
        resp = _req.post(
            f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
            json={"expression": js}, timeout=10
        )
        result = resp.json().get("result", {}) if resp.status_code == 200 else {}

        # 如果需要评论，逐个进入作品详情页提取
        if with_comments and result.get("works"):
            for w in result["works"]:
                comments = self.get_work_comments(w["video_url"], max_comments)
                w["comments"] = comments
                w["comment_count"] = len(comments)

        return result

    def get_following_with_detail(self, max_count: int = 20, with_comments: bool = False, max_comments: int = 50) -> Dict[str, Any]:
        """获取关注列表，并逐个进入主页提取详细数据（可选含评论）"""
        following_result = self.get_following(max_count)
        users = following_result.get("following", [])

        print(f"\n🔍 逐个获取关注用户详情（共 {len(users)} 人）{'含评论' if with_comments else ''}...")
        detailed = []
        for u in users:
            print(f"\n   [{u['position']}] {u['nickname']} ...")
            detail = self.get_user_detail(u["profile_url"], with_comments=with_comments, max_comments=max_comments)
            detail["position"] = u["position"]
            detail["bio"] = u.get("bio", "")
            detailed.append(detail)
            print(f"       抖音号: {detail.get('douyin_id', '?')}")
            print(f"       粉丝: {detail.get('fans', '?')} | 关注: {detail.get('following', '?')} | 获赞: {detail.get('total_likes', '?')}")
            print(f"       作品数: {detail.get('works_count', '?')}")
            for w in detail.get("works", []):
                print(f"         [{w.get('type','?')}] 作品{w['position']}: 点赞={w['likes']} | {w['video_url'][-40:]}")
                if with_comments:
                    for c in w.get("comments", []):
                        print(f"           💬 {c['user']}: {c['text'][:40]} | 赞:{c['likes']} {c.get('time','')}")
                    if not w.get("comments"):
                        print(f"           (暂无评论)")

        return {"success": True, "count": len(detailed), "users": detailed}

    def get_followers_with_detail(self, max_count: int = 20, with_comments: bool = False, max_comments: int = 50) -> Dict[str, Any]:
        """获取粉丝列表，并逐个进入主页提取详细数据（可选含评论）"""
        followers_result = self.get_followers(max_count)
        users = followers_result.get("followers", [])

        print(f"\n🔍 逐个获取粉丝详情（共 {len(users)} 人）{'含评论' if with_comments else ''}...")
        detailed = []
        for u in users:
            print(f"\n   [{u['position']}] {u['nickname']} ...")
            detail = self.get_user_detail(u["profile_url"], with_comments=with_comments, max_comments=max_comments)
            detail["position"] = u["position"]
            detail["bio"] = u.get("bio", "")
            detailed.append(detail)
            print(f"       抖音号: {detail.get('douyin_id', '?')}")
            print(f"       粉丝: {detail.get('fans', '?')} | 关注: {detail.get('following', '?')} | 获赞: {detail.get('total_likes', '?')}")
            print(f"       作品数: {detail.get('works_count', '?')}")
            for w in detail.get("works", []):
                print(f"         [{w.get('type','?')}] 作品{w['position']}: 点赞={w['likes']} | {w['video_url'][-40:]}")
                if with_comments:
                    for c in w.get("comments", []):
                        print(f"           💬 {c['user']}: {c['text'][:40]} | 赞:{c['likes']} {c.get('time','')}")
                    if not w.get("comments"):
                        print(f"           (暂无评论)")

        return {"success": True, "count": len(detailed), "users": detailed}

    def manage_account(self, task: str) -> bool:
        """AI 驱动的通用账号管理任务"""
        try:
            if not self.deepseek:
                print("❌ 需要配置 DEEPSEEK_API_KEY")
                return False
            return self._ai_driven_task(task)
        finally:
            self.pinchtab.cleanup()

    def _ai_driven_task(self, task: str) -> bool:
        """DeepSeek + PinchTab 协同循环"""
        print(f"\n{'='*60}")
        print(f"抖音账号管理 - AI 驱动")
        print(f"任务: {task}")
        print(f"{'='*60}")

        self.pinchtab.navigate("https://www.douyin.com", wait_seconds=3)

        history = [{
            "role": "system",
            "content": (
                "你是抖音账号管理专家，通过 PinchTab 控制浏览器完成任务。\n"
                "每次收到页面状态后，返回纯 JSON 操作指令：\n"
                "{\"thought\": \"思考\", \"action\": \"navigate|click|type|scroll|get_profile_info|done\", "
                "\"params\": {}, \"result\": \"如果action是done，填写任务结果\"}\n"
                f"当前任务：{task}"
            )
        }]

        for i in range(15):
            print(f"\n第 {i+1} 轮...")
            state = self._get_page_state()
            history.append({"role": "user", "content": f"URL: {state['url']}\n\n页面文本:\n{state['text'][:1500]}"})

            resp = self.deepseek.chat.completions.create(
                model="deepseek-chat",
                messages=history,
                temperature=0.3,
                max_tokens=1000
            )
            content = resp.choices[0].message.content.strip()
            history.append({"role": "assistant", "content": content})

            try:
                # 去掉可能的 markdown 代码块
                clean = re.sub(r"```json|```", "", content).strip()
                cmd = json.loads(clean)
            except:
                print(f"   解析失败: {content[:100]}")
                continue

            print(f"   💭 {cmd.get('thought', '')[:80]}")
            action = cmd.get("action", "")
            params = cmd.get("params", {})
            print(f"   🎯 {action} {params}")

            if action == "done":
                print(f"\n✅ 完成: {cmd.get('result', '')}")
                return True
            elif action == "navigate":
                self.pinchtab.navigate(params.get("url", ""), wait_seconds=3)
            elif action == "click":
                self.pinchtab.click(params.get("ref", ""))
                time.sleep(2)
            elif action == "type":
                self.pinchtab.type_text(params.get("ref", ""), params.get("text", ""))
                time.sleep(1)
            elif action == "scroll":
                self._scroll(params.get("direction", "down"), params.get("amount", 500))
                time.sleep(1)
            elif action == "get_profile_info":
                info = self._extract_profile_from_text(state["text"])
                print(f"   📋 {info}")
                history.append({"role": "user", "content": f"提取到的信息: {json.dumps(info, ensure_ascii=False)}"})

        return False

    # ─────────────────────────────────────────────
    # 内部工具方法
    # ─────────────────────────────────────────────
    def _get_page_state(self) -> Dict:
        data = self.pinchtab.get_page_text()
        return {"url": data.get("url", ""), "text": data.get("text", "")}

    def _scroll(self, direction: str, amount: int = 500):
        import requests
        dy = amount if direction == "down" else -amount
        requests.post(
            f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
            json={"expression": f"window.scrollBy(0, {dy})"},
            timeout=10
        )

    def _find_ref_by_keyword(self, snapshot: Dict, keywords: List[str]) -> Optional[str]:
        for node in snapshot.get("nodes", []):
            name = node.get("name", "").lower()
            if any(k.lower() in name for k in keywords):
                return node.get("ref")
        return None

    def _scroll_and_collect_users(self, max_count: int) -> List[Dict]:
        """滚动页面收集用户列表，用 AI 提取"""
        all_text = ""
        for _ in range(5):
            text = self.pinchtab.get_page_text().get("text", "")
            all_text = text  # 取最新的完整文本
            self._scroll("down", 800)
            time.sleep(2)

        result = self._ai_extract(
            all_text,
            f"从抖音用户列表页面文本中提取用户信息，最多 {max_count} 个。"
            "返回 JSON：{\"users\": [{\"nickname\": \"\", \"douyin_id\": \"\"}]}"
        )
        users = result.get("users", [])
        # 加上位置序号
        for i, u in enumerate(users, 1):
            u["position"] = i
        return users[:max_count]

    def _ai_extract(self, text: str, prompt: str) -> Dict:
        """用 DeepSeek 从文本中提取结构化数据"""
        if not self.deepseek:
            return {}
        try:
            resp = self.deepseek.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": f"{prompt}\n\n页面文本：\n{text[:3000]}"}],
                temperature=0.1,
                max_tokens=2000
            )
            content = resp.choices[0].message.content.strip()
            clean = re.sub(r"```json|```", "", content).strip()
            return json.loads(clean)
        except Exception as e:
            print(f"   ⚠️  AI 提取失败: {e}")
            return {}

    def _extract_profile_from_text(self, text: str) -> Dict:
        return self._ai_extract(
            text,
            "从抖音个人主页文本提取：昵称、简介、抖音号、粉丝数、关注数、获赞数。"
            "返回 JSON：{\"nickname\":\"\",\"bio\":\"\",\"douyin_id\":\"\",\"fans\":\"\",\"following\":\"\",\"likes\":\"\"}"
        )
