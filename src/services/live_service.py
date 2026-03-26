"""
直播间互动服务
三层分工：AI 指挥 → PinchTab 执行 → JS DOM 整理

进入方式：
  1. 关注列表：找正在直播的主播头像，点击进入
  2. 搜索：搜索主播名，找直播卡片链接，点击进入
"""

import time
import json
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional
import requests as _req

from ..core import PinchTabClient


class LiveService:
    """直播间互动服务"""

    def __init__(self, pinchtab_url: str = "http://localhost:9867"):
        self.pinchtab = PinchTabClient(pinchtab_url)

    def connect(self, profile_name: str = None, headless: bool = False) -> bool:
        if profile_name:
            print(f"\n🔗 使用 Profile: {profile_name}")
        return self.pinchtab.connect(profile_name, headless)

    # ─────────────────────────────────────────────
    # 核心：进入直播间并发送消息
    # ─────────────────────────────────────────────
    def enter_and_chat(self, keyword: str, message: str = "hello 我是ai") -> bool:
        """
        进入直播间并发送消息。
        先尝试从关注列表找，找不到再搜索。
        keyword: 主播名称关键词
        """
        try:
            entered = False

            # 方式1：关注列表
            print(f"\n📋 方式1：从关注列表查找 '{keyword}'...")
            anchors = self._get_live_anchors_from_follow()
            if anchors:
                target = next((a for a in anchors if keyword in a.get('name', '')), anchors[0])
                print(f"   目标: {target.get('name')}")
                entered = self._click_follow_avatar(target)

            # 方式2：搜索
            if not entered:
                print(f"\n🔍 方式2：搜索 '{keyword}'...")
                entered = self._enter_via_search(keyword)

            if not entered:
                print(f"❌ 无法进入 '{keyword}' 的直播间")
                return False

            # 等待输入框
            if not self._wait_for_input(timeout=20):
                print("❌ 输入框未出现，可能未登录或直播已结束")
                return False

            # 输入并发送
            print(f"\n✉️  发送消息: {message}")
            typed = self._js(f"""
(function() {{
    var input = document.querySelector('.zone-container[contenteditable="true"]');
    if (!input) return false;
    input.focus();
    input.click();
    document.execCommand('insertText', false, {json.dumps(message)});
    return input.textContent.trim().length > 0;
}})()
""")
            if not typed:
                print("❌ 输入失败")
                return False

            time.sleep(0.5)

            # 点击发送
            if not self._click_send_button():
                print("⚠️  发送按钮未找到，尝试 Enter")
                self.pinchtab.press_key("Return")

            time.sleep(1.5)
            self._save_screenshot("live_sent")
            print("✅ 消息发送成功")
            return True

        finally:
            self.pinchtab.cleanup()

    # ─────────────────────────────────────────────
    # 方式1：从关注页获取正在直播的主播
    # ─────────────────────────────────────────────
    def _get_live_anchors_from_follow(self) -> list:
        """导航到关注页，提取正在直播的主播列表"""
        self.pinchtab.navigate('https://www.douyin.com/follow', wait_seconds=6)
        anchors = self._js("""
(function() {
    var items = Array.from(document.querySelectorAll('[data-e2e="follow-slide-avatar"]'));
    return items.map(function(item) {
        var a = item.querySelector('a');
        var rect = item.getBoundingClientRect();
        return {
            name: item.textContent.trim().slice(0, 20),
            href: a ? a.href : '',
            click_x: Math.round(rect.x + 20),
            click_y: Math.round(rect.y + rect.height / 2)
        };
    }).filter(function(a) { return a.href.includes('live.douyin.com'); });
})()
""")
        if anchors:
            print(f"   ✅ 找到 {len(anchors)} 个正在直播: {[a['name'] for a in anchors]}")
        return anchors or []

    def _click_follow_avatar(self, anchor: dict) -> bool:
        """点击关注页主播头像进入直播间"""
        cx = anchor.get('click_x', 84)
        cy = anchor.get('click_y', 200)
        result = self._js(f"""
(function() {{
    var el = document.elementFromPoint({cx}, {cy});
    if (!el) return false;
    var a = el.closest('a');
    if (a && a.href.includes('live.douyin.com')) {{
        a.click();
        return true;
    }}
    return false;
}})()
""")
        if result:
            time.sleep(5)
            url = self._js("window.location.href") or ''
            print(f"   URL: {url[:60]}")
            return 'live' in url
        return False

    # ─────────────────────────────────────────────
    # 方式2：搜索主播名进入直播间
    # ─────────────────────────────────────────────
    def _enter_via_search(self, keyword: str) -> bool:
        """搜索主播名，找直播卡片链接，点击进入"""
        self.pinchtab.navigate(
            f'https://www.douyin.com/search/{keyword}?type=live',
            wait_seconds=6
        )
        # 找直播卡片里的"进入直播间"链接（带 from_search=true）
        result = self._js("""
(function() {
    // 找所有指向 live.douyin.com 且带 from_search 的链接
    var links = Array.from(document.querySelectorAll('a[href*="live.douyin.com"]'));
    // 优先找"点击或按进入直播间"的那个
    var enterLink = links.find(function(a) {
        return a.textContent.includes('进入直播间') || a.href.includes('from_search');
    }) || links[0];
    
    if (!enterLink) return null;
    enterLink.click();
    return enterLink.href.slice(0, 80);
})()
""")
        if result:
            print(f"   点击: {result}")
            time.sleep(6)
            url = self._js("window.location.href") or ''
            print(f"   URL: {url[:60]}")
            return 'live' in url
        print("   ❌ 未找到直播链接")
        return False

    # ─────────────────────────────────────────────
    # 等待输入框
    # ─────────────────────────────────────────────
    def _wait_for_input(self, timeout: int = 20) -> bool:
        print("\n⏳ 等待输入框...")
        for i in range(timeout):
            time.sleep(1)
            if self._js('!!document.querySelector(\'.zone-container[contenteditable="true"]\')'):
                print(f"   ✅ 输入框出现 ({i+1}s)")
                return True
        return False

    # ─────────────────────────────────────────────
    # 点击发送按钮
    # ─────────────────────────────────────────────
    def _click_send_button(self) -> bool:
        """找并点击发送按钮"""
        result = self._js("""
(function() {
    // 找文字为"发送"的叶子节点
    var sendEl = Array.from(document.querySelectorAll('*')).find(function(el) {
        var rect = el.getBoundingClientRect();
        return el.textContent.trim() === '发送' && el.children.length === 0 && rect.width > 0;
    });
    if (sendEl) { sendEl.click(); return 'text:发送'; }
    
    // 找 send-btn class
    var selectors = ['.webcast-chatroom___send-btn', '[class*="send-btn"]', '[class*="sendBtn"]'];
    for (var i = 0; i < selectors.length; i++) {
        var btn = document.querySelector(selectors[i]);
        if (btn) { btn.click(); return selectors[i]; }
    }
    return false;
})()
""")
        if result:
            print(f"   ✅ 发送: {result}")
            return True
        return False

    # ─────────────────────────────────────────────
    # 工具方法
    # ─────────────────────────────────────────────
    def _js(self, code: str):
        resp = _req.post(
            f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
            json={"expression": code},
            timeout=15
        )
        return resp.json().get("result") if resp.status_code == 200 else None

    def _save_screenshot(self, prefix: str) -> Optional[Path]:
        data = self.pinchtab.screenshot()
        if not data:
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path(f"data/screenshots/{prefix}_{ts}.png")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(data))
        print(f"   📸 {path}")
        return path
