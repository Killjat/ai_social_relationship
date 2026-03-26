"""
关注列表监控服务

功能：
  - 从登录账号的关注列表获取所有关注用户
  - 逐个访问用户主页，抓取最新作品
  - 与 Neo4j 已有数据对比，找出新增作品
  - 将新作品全量写入 Neo4j
"""

import time
import os
from typing import Dict, Any, List, Optional, Set

from ..core.pinchtab_client import PinchTabClient
from config import Config


class WatchService:

    def __init__(self):
        self.pinchtab = PinchTabClient(base_url=Config.PINCHTAB_URL)
        if Config.PINCHTAB_TOKEN:
            self.pinchtab.session.headers.update({
                "Authorization": f"Bearer {Config.PINCHTAB_TOKEN}"
            })

        # Neo4j
        try:
            from .graph_service import GraphService
            self.graph = GraphService()
            if not self.graph.connect():
                self.graph = None
        except Exception:
            self.graph = None

    def connect(self, headless: bool = False) -> bool:
        return self.pinchtab.connect(
            profile_name=Config.PINCHTAB_PROFILE or "cyberstroll跨境电商",
            headless=headless
        )

    # ─────────────────────────────────────────────
    # 主入口
    # ─────────────────────────────────────────────

    def watch(self, max_following: int = 100, max_works_per_user: int = 20) -> Dict[str, Any]:
        """
        监控关注列表，找出新增作品写入 Neo4j

        返回：
          {
            "checked": int,      # 检查了多少人
            "new_works": int,    # 发现多少新作品
            "updated_users": []  # 有新作品的用户列表
          }
        """
        print(f"\n{'='*60}")
        print(f"👀 监控关注列表（最多 {max_following} 人）")
        print(f"{'='*60}")

        # Step 1: 获取关注列表
        following = self._get_following_list(max_following)
        print(f"\n✅ 关注列表: {len(following)} 人")

        if not following:
            return {"checked": 0, "new_works": 0, "updated_users": []}

        # Step 2: 逐个检查新作品
        total_new = 0
        updated_users = []

        for i, user in enumerate(following):
            uid = user.get("uid", "")
            nickname = user.get("nickname", "")
            if not uid:
                continue

            print(f"\n[{i+1}/{len(following)}] {nickname}...")

            # 人类行为：每个用户之间随机停顿
            self._human_pause(2, 5)
            self._human_scroll_page()

            # 获取该用户当前作品列表
            current_works = self._get_user_works(uid, max_works_per_user)

            # 与 Neo4j 对比，找新作品
            new_works = self._find_new_works(uid, current_works)

            if new_works:
                print(f"   🆕 {len(new_works)} 个新作品")
                updated_users.append({
                    "uid":       uid,
                    "nickname":  nickname,
                    "new_works": new_works
                })
                total_new += len(new_works)

                if self.graph:
                    self.graph.upsert_user(uid, user)
                    for w in new_works:
                        self.graph.upsert_work(uid, w)
            else:
                print(f"   ✓ 无新作品")

            # 每处理5个人，多停一会
            if (i + 1) % 5 == 0:
                self._human_pause(5, 15)

        print(f"\n{'='*60}")
        print(f"✅ 监控完成")
        print(f"   检查: {len(following)} 人")
        print(f"   新作品: {total_new} 个")
        print(f"   有更新: {len(updated_users)} 人")
        if updated_users:
            for u in updated_users:
                print(f"   - {u['nickname']}: {len(u['new_works'])} 个新作品")
        print(f"{'='*60}")

        return {
            "checked":       len(following),
            "new_works":     total_new,
            "updated_users": updated_users
        }

    # ─────────────────────────────────────────────
    # 获取关注列表
    # ─────────────────────────────────────────────

    def watch_deep(self, max_following: int = 50, max_following_of_following: int = 30) -> Dict[str, Any]:
        """
        二层关注扩展：
          我的关注 → 他们的关注列表 → 每人最新1个作品 → Neo4j
        """
        print(f"\n{'='*60}")
        print(f"🕸️  二层关注扩展")
        print(f"   我的关注: 最多 {max_following} 人")
        print(f"   每人的关注: 最多 {max_following_of_following} 人")
        print(f"{'='*60}")

        # Step 1: 获取我的关注列表
        my_following = self._get_following_list(max_following)
        print(f"\n✅ 我的关注: {len(my_following)} 人")

        total_new = 0
        all_level2_users = []

        for i, user in enumerate(my_following):
            uid = user.get("uid", "")
            nickname = user.get("nickname", "")
            if not uid:
                continue

            print(f"\n[{i+1}/{len(my_following)}] {nickname} 的关注列表...")

            # 人类行为：进入每个人主页前随机停顿
            self._human_pause(2, 6)

            # Step 2: 获取该用户的关注列表
            level2_users = self._get_user_following(uid, max_following_of_following)
            print(f"   找到 {len(level2_users)} 个关注")

            # Step 3: 每个二层用户取最新1个作品
            for j, u2 in enumerate(level2_users):
                uid2 = u2.get("uid", "")
                if not uid2:
                    continue

                # 人类行为：每隔几个用户多停一下
                if j > 0 and j % 5 == 0:
                    self._human_pause(3, 8)
                else:
                    self._human_pause(1, 3)

                works = self._get_user_works(uid2, max_count=1)
                if works:
                    if self.graph:
                        self.graph.upsert_user(uid2, u2)
                        self.graph.upsert_work(uid2, works[0])
                        self.graph.upsert_follows(uid, uid2)
                    total_new += 1
                    all_level2_users.append({**u2, "latest_work": works[0]})

            print(f"   写入 {len(level2_users)} 个二层用户的最新作品")

            # 人类行为：处理完一个人后随机长停顿
            self._human_pause(3, 10)

        print(f"\n{'='*60}")
        print(f"✅ 二层扩展完成")
        print(f"   二层用户: {len(all_level2_users)} 人")
        print(f"   新作品: {total_new} 个")
        if self.graph:
            stats = self.graph.stats()
            print(f"   图谱: {stats['users']} 用户, {stats['works']} 作品, {stats['follows']} 关系")
        print(f"{'='*60}")

        return {"level2_users": len(all_level2_users), "new_works": total_new}

    def _get_following_list(self, max_count: int) -> List[Dict]:
        """从个人主页关注弹窗抓取完整关注列表（我自己的）"""
        print(f"\n➕ 获取关注列表...")
        self.pinchtab.navigate("https://www.douyin.com/user/self", wait_seconds=6)

        self._evaluate("var el=document.querySelector('[data-e2e=\"user-info-follow\"]'); if(el) el.click();")
        time.sleep(3)

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
        if (href && href.startsWith('/')) href = 'https://www.douyin.com' + href;
        var uidMatch = href.match(/[/]user[/]([^?#]+)/);
        var uid = uidMatch ? uidMatch[1] : '';
        var nickEl = row.querySelector('.kUKK9Qal a span');
        var nickname = nickEl ? nickEl.textContent.trim() : '';
        var bioEl = row.querySelector('.B_5R_Mpq span');
        var bio = bioEl ? bioEl.textContent.trim() : '';
        return {uid: uid, nickname: nickname, bio: bio, profile_url: 'https://www.douyin.com/user/' + uid};
    }).filter(function(u) { return u.uid; });
})()
"""
        js_scroll = """
(function() {
    var c = document.querySelector('[data-e2e="user-fans-container"]');
    if (!c) return -1;
    c.scrollTop += 600;
    return c.scrollTop;
})()
"""
        seen_uids: Set[str] = set()
        users = []
        no_new = 0
        last_pos = -1

        while len(users) < max_count:
            rows = self._evaluate(js_extract) or []
            new_found = 0
            for row in rows:
                uid = row.get("uid", "")
                if uid and uid not in seen_uids:
                    seen_uids.add(uid)
                    users.append(row)
                    new_found += 1
                    if len(users) >= max_count:
                        break
            if new_found == 0:
                no_new += 1
                if no_new >= 3:
                    break
            else:
                no_new = 0
            cur_pos = self._evaluate(js_scroll) or -1
            time.sleep(1.5)
            if cur_pos != -1 and cur_pos == last_pos:
                break
            last_pos = cur_pos

        print(f"   找到 {len(users)} 个关注用户")
        return users

    def _get_user_following(self, uid: str, max_count: int) -> List[Dict]:
        """获取指定用户的关注列表（需要登录，私密账号或隐藏关注列表会返回空）"""
        profile_url = f"https://www.douyin.com/user/{uid}"
        self.pinchtab.navigate(profile_url, wait_seconds=5)
        self._human_pause(1, 3)

        # 点击关注数
        self._evaluate("var el=document.querySelector('[data-e2e=\"user-info-follow\"]'); if(el) el.click();")
        time.sleep(3)

        # 检测是否被限制（私密账号或关注列表不可见）
        blocked = self._evaluate("""
(function(){
    var container = document.querySelector('[data-e2e="user-fans-container"]');
    if (!container) return 'no_container';
    var rows = container.querySelectorAll('.i5U4dMnB');
    if (rows.length === 0) {
        // 检查是否有"暂无关注"或隐私提示
        var text = container.textContent.trim();
        if (text.includes('暂无') || text.includes('私密') || text.includes('隐私') || text.length < 10) {
            return 'hidden';
        }
    }
    return 'ok';
})()
""")
        if blocked in ('no_container', 'hidden'):
            print(f"   ⚠️  关注列表不可见（私密或隐藏）")
            return []

        # 点击关注数打开弹窗
        self._evaluate("var el=document.querySelector('[data-e2e=\"user-info-follow\"]'); if(el) el.click();")
        time.sleep(3)

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
        if (href && href.startsWith('/')) href = 'https://www.douyin.com' + href;
        var uidMatch = href.match(/[/]user[/]([^?#]+)/);
        var uid = uidMatch ? uidMatch[1] : '';
        var nickEl = row.querySelector('.kUKK9Qal a span');
        var nickname = nickEl ? nickEl.textContent.trim() : '';
        return {uid: uid, nickname: nickname, profile_url: 'https://www.douyin.com/user/' + uid};
    }).filter(function(u) { return u.uid; });
})()
"""
        js_scroll = """
(function() {
    var c = document.querySelector('[data-e2e="user-fans-container"]');
    if (!c) return -1;
    c.scrollTop += 600;
    return c.scrollTop;
})()
"""
        seen: Set[str] = set()
        users = []
        no_new = 0
        last_pos = -1

        while len(users) < max_count:
            rows = self._evaluate(js_extract) or []
            new_found = 0
            for row in rows:
                u = row.get("uid", "")
                if u and u not in seen:
                    seen.add(u)
                    users.append(row)
                    new_found += 1
                    if len(users) >= max_count:
                        break
            if new_found == 0:
                no_new += 1
                if no_new >= 3:
                    break
            else:
                no_new = 0
            cur_pos = self._evaluate(js_scroll) or -1
            time.sleep(1.5)
            if cur_pos != -1 and cur_pos == last_pos:
                break
            last_pos = cur_pos

        return users
        """从个人主页关注弹窗抓取完整关注列表"""
        print(f"\n➕ 获取关注列表...")
        self.pinchtab.navigate("https://www.douyin.com/user/self", wait_seconds=6)

        # 点击关注数打开弹窗
        self._evaluate("var el=document.querySelector('[data-e2e=\"user-info-follow\"]'); if(el) el.click();")
        time.sleep(3)

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
        if (href && href.startsWith('/')) href = 'https://www.douyin.com' + href;
        var uidMatch = href.match(/[/]user[/]([^?#]+)/);
        var uid = uidMatch ? uidMatch[1] : '';
        var nickEl = row.querySelector('.kUKK9Qal a span');
        var nickname = nickEl ? nickEl.textContent.trim() : '';
        var bioEl = row.querySelector('.B_5R_Mpq span');
        var bio = bioEl ? bioEl.textContent.trim() : '';
        return {uid: uid, nickname: nickname, bio: bio, profile_url: 'https://www.douyin.com/user/' + uid};
    }).filter(function(u) { return u.uid; });
})()
"""
        js_scroll = """
(function() {
    var c = document.querySelector('[data-e2e="user-fans-container"]');
    if (!c) return -1;
    c.scrollTop += 600;
    return c.scrollTop;
})()
"""
        seen_uids: Set[str] = set()
        users = []
        no_new = 0
        last_pos = -1

        while len(users) < max_count:
            rows = self._evaluate(js_extract) or []
            new_found = 0
            for row in rows:
                uid = row.get("uid", "")
                if uid and uid not in seen_uids:
                    seen_uids.add(uid)
                    users.append(row)
                    new_found += 1
                    if len(users) >= max_count:
                        break

            if new_found == 0:
                no_new += 1
                if no_new >= 3:
                    break
            else:
                no_new = 0

            cur_pos = self._evaluate(js_scroll) or -1
            time.sleep(1.5)
            if cur_pos != -1 and cur_pos == last_pos:
                break
            last_pos = cur_pos

        print(f"   找到 {len(users)} 个关注用户")
        return users

    # ─────────────────────────────────────────────
    # 获取用户作品列表
    # ─────────────────────────────────────────────

    def _get_user_works(self, uid: str, max_count: int) -> List[Dict]:
        """访问用户主页，抓取作品列表"""
        self.pinchtab.navigate(f"https://www.douyin.com/user/{uid}", wait_seconds=5)
        # 模拟人类：进入主页后先停留看一下
        self._human_pause(1.5, 4)
        self._evaluate("window.scrollBy(0, 600)")
        time.sleep(2)
        self._evaluate("window.scrollTo(0, 0)")
        time.sleep(1)

        js = """
(function() {
    var list = document.querySelector('[data-e2e="scroll-list"]');
    if (!list) return [];
    return Array.from(list.querySelectorAll('li')).map(function(li, i) {
        var link = li.querySelector('a[href*="/video/"], a[href*="/note/"]');
        var likeEl = li.querySelector('.BgCg_ebQ');
        var imgEl = li.querySelector('img');
        var href = link ? link.getAttribute('href') : '';
        if (href.startsWith('/')) href = 'https://www.douyin.com' + href;
        if (href.startsWith('//')) href = 'https:' + href;
        return {
            position:  i + 1,
            video_url: href,
            type:      href.indexOf('/note/') >= 0 ? '图文' : '视频',
            likes:     likeEl ? likeEl.textContent.trim() : '0',
            title:     imgEl ? (imgEl.getAttribute('alt') || '') : ''
        };
    }).filter(function(w) { return w.video_url; });
})()
"""
        works = self._evaluate(js) or []

        # 如果没有作品，可能是私密账号
        if not works:
            return []

        # 滚动加载更多
        seen_urls: Set[str] = set(w["video_url"] for w in works)
        no_new = 0
        last_pos = -1

        while len(works) < max_count:
            self._evaluate("window.scrollBy(0, 800)")
            time.sleep(1.5)
            cur_pos = self._evaluate("document.documentElement.scrollTop || document.body.scrollTop") or -1
            if cur_pos != -1 and cur_pos == last_pos:
                break
            last_pos = cur_pos

            rows = self._evaluate(js) or []
            new_found = 0
            for row in rows:
                if row["video_url"] not in seen_urls:
                    seen_urls.add(row["video_url"])
                    works.append(row)
                    new_found += 1
            if new_found == 0:
                no_new += 1
                if no_new >= 3:
                    break

        return works[:max_count]

    # ─────────────────────────────────────────────
    # 对比新作品
    # ─────────────────────────────────────────────

    def _find_new_works(self, uid: str, current_works: List[Dict]) -> List[Dict]:
        """与 Neo4j 对比，返回新增的作品"""
        if not self.graph:
            return current_works  # 没有 Neo4j，全部视为新作品

        # 查 Neo4j 里该用户已有的作品 URL
        try:
            with self.graph.driver.session() as s:
                result = s.run(
                    "MATCH (u:User {uid:$uid})-[:PUBLISHED]->(w:Work) RETURN w.url AS url",
                    uid=uid
                )
                existing_urls = {rec["url"] for rec in result}
        except Exception:
            existing_urls = set()

        import re
        new_works = []
        for w in current_works:
            url = w.get("video_url", "")
            # 标准化 URL（去掉参数）
            clean_url = url.split("?")[0]
            if clean_url not in existing_urls and url not in existing_urls:
                new_works.append(w)

        return new_works

    # ─────────────────────────────────────────────
    # 工具
    # ─────────────────────────────────────────────

    def _human_pause(self, min_sec: float = 1.5, max_sec: float = 4.0):
        """随机停顿，模拟人类阅读/思考"""
        import random
        time.sleep(random.uniform(min_sec, max_sec))

    def _human_scroll_page(self):
        """随机滚动页面，模拟人类浏览"""
        import random
        steps = random.randint(1, 3)
        for _ in range(steps):
            amount = random.randint(200, 600)
            self._evaluate(f"window.scrollBy(0, {amount})")
            time.sleep(random.uniform(0.3, 0.8))
        # 偶尔往回滚
        if random.random() < 0.2:
            self._evaluate(f"window.scrollBy(0, -{random.randint(100, 300)})")
            time.sleep(random.uniform(0.5, 1.0))

    def _evaluate(self, js: str):
        try:
            resp = self.pinchtab.session.post(
                f"{Config.PINCHTAB_URL}/tabs/{self.pinchtab.tab_id}/evaluate",
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
