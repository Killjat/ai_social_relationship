"""
抖音用户侦察服务 - 无需登录，通过抖音号获取目标用户的公开信息

三层架构：
  DeepSeek  → 决策层：分析页面、解析搜索结果、判断下一步
  PinchTab  → 执行层：控制浏览器导航、点击（远程服务器）
  JS DOM    → 整理层：精确读取页面结构，输出干净数据
"""

import time
import json
import re
import requests
from typing import Optional, Dict, Any, List
from urllib.parse import quote

from ..core.pinchtab_client import PinchTabClient
from ..core.stealth import random_fingerprint, build_stealth_js, build_cookie_js, ProxyPool
from config import Config


class SpyService:
    """
    无账号侦察服务
    给一个抖音号，返回：基本信息、作品列表、关注列表（含详情）、粉丝列表（含详情）
    """

    PINCHTAB_URL   = Config.PINCHTAB_URL
    PINCHTAB_TOKEN = Config.PINCHTAB_TOKEN
    PROFILE_ID     = Config.PINCHTAB_PROFILE_ID

    def __init__(self, deepseek_api_key: str = None):
        self.pinchtab = PinchTabClient(base_url=self.PINCHTAB_URL)
        if self.PINCHTAB_TOKEN:
            self.pinchtab.session.headers.update({
                "Authorization": f"Bearer {self.PINCHTAB_TOKEN}"
            })
        self.proxy_pool = ProxyPool()
        self.fp = random_fingerprint()

        if not deepseek_api_key:
            import os
            deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_api_key = deepseek_api_key

        # Neo4j（可选，连不上不影响抓取）
        from .graph_service import GraphService
        self.graph = GraphService()
        if not self.graph.connect():
            self.graph = None

    # ─────────────────────────────────────────────
    # 公开入口
    # ─────────────────────────────────────────────

    def connect(self, headless: bool = True) -> bool:
        """创建浏览器实例，注入随机 fingerprint + cookie，预留代理接口"""
        print(f"\n🕵️  连接 PinchTab...")
        sess = self.pinchtab.session
        base = self.PINCHTAB_URL

        # 每次连接刷新一套新 fingerprint
        self.fp = random_fingerprint()
        print(f"   🎭 Fingerprint: {self.fp['ua'][:60]}...")

        # 停掉旧实例
        try:
            insts = sess.get(f"{base}/instances", timeout=10).json()
            for inst in insts:
                name_match = inst.get("profileName") == (Config.PINCHTAB_PROFILE or "default")
                if name_match and inst.get("status") == "running":
                    sess.post(f"{base}/instances/{inst['id']}/stop", timeout=10)
                    time.sleep(3)
                    break
        except Exception as e:
            print(f"   ⚠️  检查旧实例失败: {e}")

        # 获取代理（没配置则直连）
        proxy = self.proxy_pool.get()
        proxy_params = self.proxy_pool.format_for_pinchtab(proxy) if proxy else None
        if proxy:
            print(f"   🌐 代理: {proxy}")
        else:
            print(f"   🌐 直连（未配置代理）")

        # 创建新实例，带 UA + 代理
        mode = "headless" if headless else "headed"
        launch_body = {
            "name": Config.PINCHTAB_PROFILE or "default",
            "mode": mode,
            "userAgent": self.fp["ua"],
        }
        if proxy_params:
            launch_body["proxy"] = proxy_params

        print(f"   🆕 创建新实例（{mode}）...")
        try:
            r = sess.post(f"{base}/instances/launch", json=launch_body, timeout=15)
            if r.status_code not in [200, 201]:
                print(f"   ❌ 创建失败: {r.status_code} {r.text}")
                return False
            self.pinchtab.instance_id = r.json()["id"]
            print(f"   ✅ 实例: {self.pinchtab.instance_id}")
        except Exception as e:
            print(f"   ❌ 创建失败: {e}")
            return False

        # 等待 tab 就绪
        for _ in range(30):
            time.sleep(1)
            try:
                r = sess.get(f"{base}/instances/{self.pinchtab.instance_id}/tabs", timeout=5)
                if r.status_code == 200 and r.json():
                    self.pinchtab.tab_id = r.json()[0]["id"]
                    print(f"   ✅ Tab: {self.pinchtab.tab_id}")

                    # 注入 fingerprint 覆盖 JS
                    self._evaluate(build_stealth_js(self.fp))
                    # 注入抖音访客 cookie
                    self._evaluate(build_cookie_js())
                    print(f"   ✅ Fingerprint + Cookie 注入完成")
                    return True
            except:
                pass

        print(f"   ❌ Tab 等待超时")
        return False

    def research(self, douyin_id: str, max_works: int = 20, max_following: int = 20, max_followers: int = 20) -> Dict[str, Any]:
        """
        主入口：给抖音号或 UID，返回完整侦察报告

        - 如果传入的是 UID（MS4wLjABAAAA 开头），直接访问主页
        - 如果是抖音号，尝试搜索（未登录可能受限，建议直接用 UID）
        """
        print(f"\n{'='*60}")
        print(f"🕵️  侦察目标: {douyin_id}")
        print(f"{'='*60}")

        # 判断是 UID 还是抖音号
        if douyin_id.startswith("MS4wLjABAAAA") or douyin_id.startswith("MS4"):
            profile_url = f"https://www.douyin.com/user/{douyin_id}"
            print(f"✅ 直接访问主页: {profile_url}")
        else:
            profile_url = self._find_profile_url(douyin_id)
            if not profile_url:
                return {
                    "success": False,
                    "message": f"未找到 @{douyin_id}，抖音搜索需要登录。\n"
                               f"请提供 UID（主页 URL 中 /user/ 后面的部分）直接访问。\n"
                               f"示例: python cli.py spy MS4wLjABAAAAxxxxxxxx"
                }

        print(f"\n✅ 找到主页: {profile_url}")

        # Step 2: 基本信息 + 作品
        info = self._get_user_info(profile_url, max_works=max_works)

        # Step 3: 关注列表
        following = self._get_following_list(profile_url, max_count=max_following)

        # Step 4: 粉丝列表
        followers = self._get_followers_list(profile_url, max_count=max_followers)

        # Step 5: 逐个获取关注/粉丝详情
        if following.get("users"):
            print(f"\n🔍 获取关注用户详情（{len(following['users'])} 人）...")
            for u in following["users"]:
                detail = self._get_user_info(u["profile_url"], max_works=10)
                u.update(detail)

        if followers.get("users"):
            print(f"\n🔍 获取粉丝详情（{len(followers['users'])} 人）...")
            for u in followers["users"]:
                detail = self._get_user_info(u["profile_url"], max_works=10)
                u.update(detail)

        report = {
            "success": True,
            "target_douyin_id": douyin_id,
            "profile_url": profile_url,
            "info": info,
            "following": following,
            "followers": followers,
        }

        self._print_report(report)

        # Step 6: 存入 Neo4j
        uid = self._extract_uid(profile_url)
        if uid and self.graph:
            self.graph.save_user_full(uid, info, following, followers)

        return report

    def research_graph(self, seed_uid: str, depth: int = 2, max_per_node: int = 20) -> Dict[str, Any]:
        """
        从种子 UID 出发，做 N 层关系扩展，结果存入 Neo4j

        depth=2 表示：
          第0层: seed_uid 本人
          第1层: seed 的关注 + 粉丝
          第2层: 每个1层用户的关注 + 粉丝

        max_per_node: 每个节点最多抓多少关注/粉丝
        """
        print(f"\n{'='*60}")
        print(f"🕸️  关系图谱扩展: {seed_uid}")
        print(f"   深度: {depth} 层 | 每节点最多: {max_per_node} 人")
        print(f"{'='*60}")

        if not self.graph:
            print("❌ Neo4j 未连接，无法存储图谱")
            return {"success": False}

        visited  = set()   # 已处理的 UID
        queue    = [(seed_uid, 0)]  # (uid, 当前层数)
        total    = 0

        while queue:
            uid, current_depth = queue.pop(0)

            if uid in visited:
                continue
            visited.add(uid)

            profile_url = f"https://www.douyin.com/user/{uid}"
            print(f"\n[层{current_depth}] 处理: {uid[:30]}...")

            # 抓基本信息 + 作品
            info = self._get_user_info(profile_url, max_works=10)
            self.graph.upsert_user(uid, info)
            for w in info.get("works", []):
                self.graph.upsert_work(uid, w)

            # 抓关注 + 粉丝
            following = {"users": [], "count": 0, "limited": True}
            followers = {"users": [], "count": 0, "limited": True}

            if current_depth < depth:
                following = self._get_following_list(profile_url, max_count=max_per_node)
                followers = self._get_followers_list(profile_url, max_count=max_per_node)

            # 存关系，并把下一层加入队列
            for u in following.get("users", []):
                next_uid = self._extract_uid(u.get("profile_url", ""))
                if next_uid:
                    self.graph.upsert_user(next_uid, u)
                    self.graph.upsert_follows(uid, next_uid)
                    if current_depth < depth and next_uid not in visited:
                        queue.append((next_uid, current_depth + 1))

            for u in followers.get("users", []):
                fan_uid = self._extract_uid(u.get("profile_url", ""))
                if fan_uid:
                    self.graph.upsert_user(fan_uid, u)
                    self.graph.upsert_follows(fan_uid, uid)
                    if current_depth < depth and fan_uid not in visited:
                        queue.append((fan_uid, current_depth + 1))

            total += 1
            stats = self.graph.stats()
            print(f"   ✅ 已处理 {total} 个节点 | 图谱: {stats['users']} 用户, {stats['follows']} 关系")

        return {"success": True, "processed": total, "stats": self.graph.stats()}

    def _find_profile_url(self, douyin_id: str) -> Optional[str]:
        """
        直接用当前远程实例搜索抖音号，等待页面异步渲染完成
        """
        print(f"\n🔍 搜索抖音号: @{douyin_id}")

        search_url = f"https://www.douyin.com/search/{quote(douyin_id)}?type=user"
        self.pinchtab.navigate(search_url, wait_seconds=3)

        # 等待用户卡片异步渲染，最多等 15 秒
        js_check = """document.querySelectorAll('a[href*="/user/MS4"]').length"""
        for i in range(15):
            time.sleep(1)
            count = self._evaluate(js_check) or 0
            print(f"   等待渲染... {i+1}s，找到 {count} 个用户链接")
            if count > 0:
                break

        js_extract = """
(function() {
    var results = [];
    var cards = document.querySelectorAll('[data-e2e="search-user-card"]');
    cards.forEach(function(card) {
        var link = card.querySelector('a[href*="/user/"]');
        var nickEl = card.querySelector('[data-e2e="search-user-name"]') ||
                     card.querySelector('h3') || card.querySelector('strong');
        var idEl = card.querySelector('[data-e2e="search-user-id"]') ||
                   card.querySelector('p');
        var href = link ? link.getAttribute('href') : '';
        if (href.startsWith('//')) href = 'https:' + href;
        else if (href.startsWith('/')) href = 'https://www.douyin.com' + href;
        results.push({
            href: href,
            nickname: nickEl ? nickEl.textContent.trim() : '',
            id_text: idEl ? idEl.textContent.trim() : ''
        });
    });
    // 兜底：找所有带 MS4 的 /user/ 链接
    if (results.length === 0) {
        document.querySelectorAll('a[href*="/user/MS4"]').forEach(function(a) {
            var href = a.getAttribute('href') || '';
            if (href.startsWith('/')) href = 'https://www.douyin.com' + href;
            results.push({href: href, nickname: a.textContent.trim(), id_text: ''});
        });
    }
    return results;
})()
"""
        candidates = self._evaluate(js_extract) or []
        print(f"   找到 {len(candidates)} 个候选用户")

        if not candidates:
            return None

        return self._ai_pick_best_match(douyin_id, candidates)

        # DeepSeek 决策：从候选中选出最匹配的
        return self._ai_pick_best_match(douyin_id, candidates)

    def _ai_pick_best_match(self, douyin_id: str, candidates: List[Dict]) -> Optional[str]:
        """DeepSeek 从候选用户列表中选出最匹配目标抖音号的用户"""
        if not candidates:
            return None

        # 先尝试精确匹配（不依赖 AI）
        for c in candidates:
            id_text = c.get("id_text", "")
            if douyin_id in id_text or douyin_id == c.get("nickname", ""):
                print(f"   ✅ 精确匹配: {c['href']}")
                return c["href"]

        # 如果只有一个候选，直接用
        if len(candidates) == 1:
            print(f"   ✅ 唯一候选: {candidates[0]['href']}")
            return candidates[0]["href"]

        # DeepSeek 决策
        if not self.deepseek_api_key:
            print(f"   ⚠️  无 DeepSeek Key，使用第一个候选")
            return candidates[0]["href"] if candidates else None

        print(f"   🤖 DeepSeek 分析最佳匹配...")
        prompt = f"""从以下搜索结果中，找出抖音号为 "{douyin_id}" 的用户。

搜索结果：
{json.dumps(candidates, ensure_ascii=False, indent=2)}

规则：
1. id_text 字段通常包含"抖音号：xxx"，优先匹配
2. nickname 也可能就是抖音号本身
3. 如果没有精确匹配，选最相似的

只返回 JSON：{{"index": 0, "reason": "匹配原因"}}
index 是 candidates 数组的下标（从0开始）。"""

        try:
            r = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {self.deepseek_api_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 100
                },
                timeout=15
            )
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"].strip()
                content = re.sub(r"```json|```", "", content).strip()
                result = json.loads(content)
                idx = result.get("index", 0)
                reason = result.get("reason", "")
                print(f"   🤖 DeepSeek 选择 index={idx}: {reason}")
                if 0 <= idx < len(candidates):
                    return candidates[idx]["href"]
        except Exception as e:
            print(f"   ⚠️  DeepSeek 决策失败: {e}")

        return candidates[0]["href"]

    # ─────────────────────────────────────────────
    # Step 2: JS DOM — 用户基本信息 + 作品列表
    # ─────────────────────────────────────────────

    def _get_user_info(self, profile_url: str, max_works: int = 20) -> Dict[str, Any]:
        """JS DOM 提取用户主页：基本信息 + 作品列表（含滚动加载）"""
        print(f"\n📋 读取主页: {profile_url}")
        self.pinchtab.navigate(profile_url, wait_seconds=5)

        # 触发懒加载
        self._evaluate("window.scrollBy(0, 600)")
        time.sleep(2)
        self._evaluate("window.scrollTo(0, 0)")
        time.sleep(1)

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
    var nickname = nickEl ? nickEl.textContent.trim() : null;

    // 抖音号
    var douyinId = null;
    var spans = document.querySelectorAll('[data-e2e="user-info"] span');
    spans.forEach(function(s) {
        var m = s.textContent.match(/\u6296\u97f3\u53f7[\uff1a:][ ]*([0-9a-zA-Z_.\\-]+)/);
        if (m) douyinId = m[1];
    });

    // 简介
    var bioEl = document.querySelector('[data-e2e="user-info-desc"]') ||
                document.querySelector('[data-e2e="user-info"] .desc');
    var bio = bioEl ? bioEl.textContent.trim() : '';

    // 作品数
    var worksCountEl = document.querySelector('[data-e2e="user-tab-count"]');
    var worksCount = worksCountEl ? worksCountEl.textContent.trim() : null;

    return {
        nickname: nickname,
        douyin_id: douyinId,
        bio: bio,
        fans: getStatNum('user-info-fans'),
        following: getStatNum('user-info-follow'),
        total_likes: getStatNum('user-info-like'),
        works_count: worksCount,
        url: window.location.href
    };
})()
"""
        info = self._evaluate(js_info) or {}
        print(f"   昵称: {info.get('nickname','?')} | 抖音号: {info.get('douyin_id','?')}")
        print(f"   粉丝: {info.get('fans','?')} | 关注: {info.get('following','?')} | 获赞: {info.get('total_likes','?')}")
        print(f"   作品数: {info.get('works_count','?')}")

        # 滚动加载作品
        works = self._scroll_collect_works(max_works)
        info["works"] = works
        return info

    def _scroll_collect_works(self, max_count: int) -> List[Dict]:
        """JS DOM + PinchTab 滚动：收集作品列表"""
        js_extract = """
(function() {
    var list = document.querySelector('[data-e2e="scroll-list"]');
    if (!list) return [];
    return Array.from(list.querySelectorAll('li')).map(function(li, i) {
        var link = li.querySelector('a[href*="/video/"], a[href*="/note/"]');
        var likeEl = li.querySelector('.BgCg_ebQ');
        var imgEl = li.querySelector('img');
        var href = link ? link.getAttribute('href') : '';
        if (href.startsWith('//')) href = 'https:' + href;
        else if (href.startsWith('/')) href = 'https://www.douyin.com' + href;
        return {
            position: i + 1,
            video_url: href,
            type: href.indexOf('/note/') >= 0 ? '图文' : '视频',
            likes: likeEl ? likeEl.textContent.trim() : '0',
            title: imgEl ? (imgEl.getAttribute('alt') || '') : ''
        };
    }).filter(function(w) { return w.video_url; });
})()
"""
        seen = set()
        works = []
        no_new = 0
        last_pos = -1

        while len(works) < max_count:
            rows = self._evaluate(js_extract) or []
            new_found = 0
            for row in rows:
                url = row.get("video_url", "")
                if url and url not in seen:
                    seen.add(url)
                    row["position"] = len(works) + 1
                    works.append(row)
                    new_found += 1
                    if len(works) >= max_count:
                        break

            if new_found == 0:
                no_new += 1
                if no_new >= 3:
                    break
            else:
                no_new = 0

            self._evaluate("window.scrollBy(0, 800)")
            time.sleep(1.5)

            cur_pos = self._evaluate("document.documentElement.scrollTop || document.body.scrollTop") or -1
            if cur_pos != -1 and cur_pos == last_pos:
                break
            last_pos = cur_pos

        print(f"   作品: {len(works)} 个")
        return works

    # ─────────────────────────────────────────────
    # Step 3 & 4: JS DOM — 关注 / 粉丝列表
    # ─────────────────────────────────────────────

    def _get_following_list(self, profile_url: str, max_count: int = 20) -> Dict[str, Any]:
        """尝试获取关注列表（未登录时部分账号可见）"""
        print(f"\n➕ 获取关注列表...")
        self.pinchtab.navigate(profile_url, wait_seconds=5)

        # 点击关注数打开弹窗
        self._evaluate("var el = document.querySelector('[data-e2e=\"user-info-follow\"]'); if(el) el.click();")
        time.sleep(3)

        users = self._scroll_collect_user_list(max_count, list_type="following")
        print(f"   关注: {len(users)} 人" + ("（未登录受限）" if not users else ""))
        return {"count": len(users), "users": users, "limited": len(users) == 0}

    def _get_followers_list(self, profile_url: str, max_count: int = 20) -> Dict[str, Any]:
        """尝试获取粉丝列表（未登录时部分账号可见）"""
        print(f"\n👥 获取粉丝列表...")
        self.pinchtab.navigate(profile_url, wait_seconds=5)

        # 点击粉丝数打开弹窗，再切换到粉丝 tab
        self._evaluate("var el = document.querySelector('[data-e2e=\"user-info-fans\"]'); if(el) el.click();")
        time.sleep(3)
        self._evaluate("var t = document.getElementById('semiTab1'); if(t) t.click();")
        time.sleep(2)

        users = self._scroll_collect_user_list(max_count, list_type="followers")
        print(f"   粉丝: {len(users)} 人" + ("（未登录受限）" if not users else ""))
        return {"count": len(users), "users": users, "limited": len(users) == 0}

    def _scroll_collect_user_list(self, max_count: int, list_type: str) -> List[Dict]:
        """JS DOM + 滚动：从弹窗中收集用户列表"""
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
        seen = set()
        users = []
        no_new = 0
        last_pos = -1

        while len(users) < max_count:
            rows = self._evaluate(js_extract) or []
            new_found = 0
            for row in rows:
                uid = row.get("uid", "")
                if uid and uid not in seen:
                    seen.add(uid)
                    row["position"] = len(users) + 1
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

    # ─────────────────────────────────────────────
    # 工具方法
    # ─────────────────────────────────────────────

    def _evaluate(self, js: str) -> Any:
        """PinchTab 执行层：在浏览器中执行 JS，返回结果"""
        try:
            resp = self.pinchtab.session.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json().get("result")
        except Exception as e:
            print(f"   ⚠️  JS 执行失败: {e}")
        return None

    def _print_report(self, report: Dict):
        """打印侦察报告摘要"""
        info = report.get("info", {})
        following = report.get("following", {})
        followers = report.get("followers", {})

        print(f"\n{'='*60}")
        print(f"📊 侦察报告: @{report['target_douyin_id']}")
        print(f"{'='*60}")
        print(f"昵称: {info.get('nickname','?')}")
        print(f"抖音号: {info.get('douyin_id','?')}")
        print(f"简介: {info.get('bio','无')}")
        print(f"粉丝: {info.get('fans','?')} | 关注: {info.get('following','?')} | 获赞: {info.get('total_likes','?')}")
        print(f"作品数: {info.get('works_count','?')} | 已抓取: {len(info.get('works',[]))}")

        print(f"\n关注列表: {following.get('count',0)} 人{'（未登录受限，无法获取）' if following.get('limited') else ''}")
        for u in following.get("users", [])[:5]:
            print(f"  {u['position']}. {u.get('nickname','?')} | 粉丝:{u.get('fans','?')} | 作品:{len(u.get('works',[]))}")

        print(f"\n粉丝列表: {followers.get('count',0)} 人{'（未登录受限，无法获取）' if followers.get('limited') else ''}")
        for u in followers.get("users", [])[:5]:
            print(f"  {u['position']}. {u.get('nickname','?')} | 粉丝:{u.get('fans','?')} | 作品:{len(u.get('works',[]))}")

        print(f"{'='*60}")

    def _extract_uid(self, profile_url: str) -> Optional[str]:
        m = re.search(r'/user/(MS4[^?#/]+)', profile_url)
        return m.group(1) if m else None

    def cleanup(self):
        self.pinchtab.cleanup()
