"""
爬虫账号池管理

职责：
  - 管理多个爬虫小号（PinchTab profile）
  - 自动轮换：每次取一个可用账号
  - 封号检测：发现异常自动标记，切换下一个
  - 接码平台注册新号（sms_client）
"""

import os
import json
import time
import requests
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime


POOL_FILE = Path("data/account_pool.json")


class AccountPool:

    def __init__(self, pinchtab_url: str = None):
        self.base_url = pinchtab_url or os.getenv("PINCHTAB_URL", "http://localhost:9867")
        token = os.getenv("PINCHTAB_TOKEN", "")
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        self._pool: List[Dict] = []
        self._load()

    # ─────────────────────────────────────────────
    # 持久化
    # ─────────────────────────────────────────────

    def _load(self):
        POOL_FILE.parent.mkdir(parents=True, exist_ok=True)
        if POOL_FILE.exists():
            self._pool = json.loads(POOL_FILE.read_text())
        else:
            self._pool = []

    def _save(self):
        POOL_FILE.write_text(json.dumps(self._pool, ensure_ascii=False, indent=2))

    # ─────────────────────────────────────────────
    # 账号管理
    # ─────────────────────────────────────────────

    def add(self, profile_name: str, phone: str = "", note: str = "") -> Dict:
        """添加一个爬虫账号到池子"""
        account = {
            "profile_name": profile_name,
            "phone":        phone,
            "note":         note,
            "status":       "active",   # active / banned / cooldown
            "request_count": 0,
            "last_used":    None,
            "banned_at":    None,
            "created_at":   datetime.now().isoformat(),
        }
        # 去重
        if not any(a["profile_name"] == profile_name for a in self._pool):
            self._pool.append(account)
            self._save()
            print(f"✅ 账号已加入池: {profile_name}")
        return account

    def get_available(self) -> Optional[Dict]:
        """
        取一个可用账号（轮换策略：最久未使用的优先）
        冷却中的账号（cooldown）等冷却时间过了再用
        """
        now = time.time()
        candidates = []

        for a in self._pool:
            if a["status"] == "banned":
                continue
            if a["status"] == "cooldown":
                # 冷却 30 分钟
                banned_at = a.get("banned_at")
                if banned_at and (now - banned_at) < 1800:
                    continue
                else:
                    a["status"] = "active"  # 冷却结束

            candidates.append(a)

        if not candidates:
            return None

        # 最久未使用的优先
        candidates.sort(key=lambda a: a.get("last_used") or "")
        return candidates[0]

    def mark_used(self, profile_name: str):
        """记录使用次数和时间"""
        for a in self._pool:
            if a["profile_name"] == profile_name:
                a["request_count"] += 1
                a["last_used"] = datetime.now().isoformat()
                self._save()
                break

    def mark_banned(self, profile_name: str):
        """标记账号被封，进入冷却"""
        for a in self._pool:
            if a["profile_name"] == profile_name:
                a["status"]    = "cooldown"
                a["banned_at"] = time.time()
                self._save()
                print(f"⚠️  账号进入冷却: {profile_name}")
                break

    def mark_dead(self, profile_name: str):
        """标记账号永久封禁"""
        for a in self._pool:
            if a["profile_name"] == profile_name:
                a["status"] = "banned"
                self._save()
                print(f"💀 账号永久封禁: {profile_name}")
                break

    def list_all(self) -> List[Dict]:
        return self._pool

    def stats(self) -> Dict:
        total    = len(self._pool)
        active   = sum(1 for a in self._pool if a["status"] == "active")
        cooldown = sum(1 for a in self._pool if a["status"] == "cooldown")
        banned   = sum(1 for a in self._pool if a["status"] == "banned")
        return {"total": total, "active": active, "cooldown": cooldown, "banned": banned}

    # ─────────────────────────────────────────────
    # 封号检测
    # ─────────────────────────────────────────────

    def is_banned_page(self, page_text: str) -> bool:
        """检测页面是否出现封号/风控特征"""
        signals = [
            "账号异常", "账号已被封禁", "违规", "风险操作",
            "请完成验证", "滑动验证", "请输入验证码",
            "账号存在风险", "暂时无法使用"
        ]
        return any(s in page_text for s in signals)
