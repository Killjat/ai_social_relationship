"""
Neo4j 图谱存储服务

节点类型：
  User  — 抖音用户（uid, nickname, fans, following, works_count, bio）
  Work  — 作品（work_id, type, likes, title, url）

关系类型：
  FOLLOWS   — (User)-[:FOLLOWS]->(User)
  FANS      — (User)-[:FANS]->(User)
  PUBLISHED — (User)-[:PUBLISHED]->(Work)
"""

import os
from typing import Optional, Dict, Any, List
from neo4j import GraphDatabase


class GraphService:

    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self.uri      = uri      or os.getenv("NEO4J_URI",      "bolt://47.111.28.162:7687")
        self.user     = user     or os.getenv("NEO4J_USER",     "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "neo4j@2026")
        self.driver   = None

    def connect(self) -> bool:
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            print(f"✅ Neo4j 连接成功: {self.uri}")
            self._ensure_indexes()
            return True
        except Exception as e:
            print(f"❌ Neo4j 连接失败: {e}")
            return False

    def close(self):
        if self.driver:
            self.driver.close()

    # ─────────────────────────────────────────────
    # 索引初始化
    # ─────────────────────────────────────────────

    def _ensure_indexes(self):
        with self.driver.session() as s:
            s.run("CREATE CONSTRAINT user_uid IF NOT EXISTS FOR (u:User) REQUIRE u.uid IS UNIQUE")
            s.run("CREATE CONSTRAINT work_id IF NOT EXISTS FOR (w:Work) REQUIRE w.work_id IS UNIQUE")

    # ─────────────────────────────────────────────
    # 写入用户节点
    # ─────────────────────────────────────────────

    def upsert_user(self, uid: str, data: Dict[str, Any]) -> bool:
        """创建或更新用户节点"""
        try:
            with self.driver.session() as s:
                s.run("""
                    MERGE (u:User {uid: $uid})
                    SET u.nickname    = $nickname,
                        u.douyin_id   = $douyin_id,
                        u.bio         = $bio,
                        u.fans        = $fans,
                        u.following   = $following,
                        u.total_likes = $total_likes,
                        u.works_count = $works_count,
                        u.profile_url = $profile_url,
                        u.updated_at  = timestamp()
                """, uid=uid,
                     nickname=data.get("nickname", ""),
                     douyin_id=data.get("douyin_id", ""),
                     bio=data.get("bio", ""),
                     fans=data.get("fans", ""),
                     following=data.get("following", ""),
                     total_likes=data.get("total_likes", ""),
                     works_count=data.get("works_count", ""),
                     profile_url=data.get("url", f"https://www.douyin.com/user/{uid}"))
            return True
        except Exception as e:
            print(f"   ⚠️  upsert_user 失败: {e}")
            return False

    # ─────────────────────────────────────────────
    # 写入作品节点
    # ─────────────────────────────────────────────

    def upsert_work(self, uid: str, work: Dict[str, Any]) -> bool:
        """创建或更新作品节点，并建立 PUBLISHED 关系"""
        try:
            # 从 URL 提取 work_id
            url = work.get("video_url", "")
            import re
            m = re.search(r'/(video|note)/(\d+)', url)
            if not m:
                return False
            work_id = m.group(2)

            with self.driver.session() as s:
                s.run("""
                    MERGE (w:Work {work_id: $work_id})
                    SET w.type       = $type,
                        w.likes      = $likes,
                        w.title      = $title,
                        w.url        = $url,
                        w.updated_at = timestamp()
                    WITH w
                    MATCH (u:User {uid: $uid})
                    MERGE (u)-[:PUBLISHED]->(w)
                """, work_id=work_id, uid=uid,
                     type=work.get("type", "视频"),
                     likes=work.get("likes", "0"),
                     title=work.get("title", ""),
                     url=url)
            return True
        except Exception as e:
            print(f"   ⚠️  upsert_work 失败: {e}")
            return False

    # ─────────────────────────────────────────────
    # 写入关系
    # ─────────────────────────────────────────────

    def upsert_follows(self, from_uid: str, to_uid: str) -> bool:
        """建立 FOLLOWS 关系：from_uid 关注了 to_uid"""
        try:
            with self.driver.session() as s:
                s.run("""
                    MERGE (a:User {uid: $from_uid})
                    MERGE (b:User {uid: $to_uid})
                    MERGE (a)-[:FOLLOWS]->(b)
                """, from_uid=from_uid, to_uid=to_uid)
            return True
        except Exception as e:
            print(f"   ⚠️  upsert_follows 失败: {e}")
            return False

    def upsert_fans(self, from_uid: str, to_uid: str) -> bool:
        """建立 FANS 关系：from_uid 是 to_uid 的粉丝"""
        return self.upsert_follows(from_uid, to_uid)

    # ─────────────────────────────────────────────
    # 批量写入（spy_service 调用）
    # ─────────────────────────────────────────────

    def save_user_full(self, uid: str, info: Dict, following: Dict, followers: Dict):
        """
        保存一个用户的完整数据：
        - 用户节点
        - 作品节点 + PUBLISHED 关系
        - 关注列表 + FOLLOWS 关系
        - 粉丝列表 + FANS 关系
        """
        print(f"\n💾 存储用户: {info.get('nickname','?')} ({uid})")

        # 用户节点
        self.upsert_user(uid, info)

        # 作品
        works = info.get("works", [])
        for w in works:
            self.upsert_work(uid, w)
        print(f"   作品: {len(works)} 个")

        # 关注
        for u in following.get("users", []):
            to_uid = self._extract_uid(u.get("profile_url", ""))
            if to_uid:
                self.upsert_user(to_uid, u)
                self.upsert_follows(uid, to_uid)
                for w in u.get("works", []):
                    self.upsert_work(to_uid, w)
        print(f"   关注: {following.get('count', 0)} 人")

        # 粉丝
        for u in followers.get("users", []):
            fan_uid = self._extract_uid(u.get("profile_url", ""))
            if fan_uid:
                self.upsert_user(fan_uid, u)
                self.upsert_follows(fan_uid, uid)
                for w in u.get("works", []):
                    self.upsert_work(fan_uid, w)
        print(f"   粉丝: {followers.get('count', 0)} 人")

    def _extract_uid(self, profile_url: str) -> Optional[str]:
        import re
        m = re.search(r'/user/(MS4[^?#/]+)', profile_url)
        return m.group(1) if m else None

    # ─────────────────────────────────────────────
    # 查询
    # ─────────────────────────────────────────────

    def get_user(self, uid: str) -> Optional[Dict]:
        with self.driver.session() as s:
            r = s.run("MATCH (u:User {uid: $uid}) RETURN u", uid=uid)
            rec = r.single()
            return dict(rec["u"]) if rec else None

    def get_followers_uids(self, uid: str) -> List[str]:
        """获取某用户的所有粉丝 UID（已存入图谱的）"""
        with self.driver.session() as s:
            r = s.run("""
                MATCH (fan:User)-[:FOLLOWS]->(u:User {uid: $uid})
                RETURN fan.uid AS uid
            """, uid=uid)
            return [rec["uid"] for rec in r]

    def get_following_uids(self, uid: str) -> List[str]:
        """获取某用户关注的所有 UID"""
        with self.driver.session() as s:
            r = s.run("""
                MATCH (u:User {uid: $uid})-[:FOLLOWS]->(target:User)
                RETURN target.uid AS uid
            """, uid=uid)
            return [rec["uid"] for rec in r]

    def stats(self) -> Dict:
        """图谱统计"""
        with self.driver.session() as s:
            users = s.run("MATCH (u:User) RETURN count(u) AS n").single()["n"]
            works = s.run("MATCH (w:Work) RETURN count(w) AS n").single()["n"]
            rels  = s.run("MATCH ()-[r:FOLLOWS]->() RETURN count(r) AS n").single()["n"]
            return {"users": users, "works": works, "follows": rels}
