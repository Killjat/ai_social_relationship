"""
抖音客户端 - 封装抖音相关操作
"""

import time
from typing import Optional, Dict, List
from urllib.parse import quote
from .pinchtab_client import PinchTabClient


class DouyinClient:
    """抖音操作客户端"""
    
    def __init__(self, pinchtab: PinchTabClient):
        self.pinchtab = pinchtab
    
    def search_live_room(self, keyword: str) -> bool:
        """搜索直播间"""
        print(f"\n🔍 搜索主播 '{keyword}'...")
        
        # 使用搜索 URL
        search_url = f"https://www.douyin.com/search/{quote(keyword)}?type=live"
        print(f"   URL: {search_url}")
        
        if not self.pinchtab.navigate(search_url, wait_seconds=8):
            print("   ❌ 搜索失败")
            return False
        
        print("   ✅ 搜索结果已加载")
        return True
    
    def find_live_room_link(self, keyword: str) -> Optional[Dict]:
        """查找直播间链接（返回元素信息）"""
        print(f"   查找 '{keyword}' 的直播间...")
        
        snapshot = self.pinchtab.get_snapshot()
        nodes = snapshot.get("nodes", [])
        
        print(f"   页面节点数: {len(nodes)}")
        
        # 查找包含关键词的直播间链接
        for node in nodes:
            role = node.get("role", "")
            name = node.get("name", "")
            ref = node.get("ref", "")
            
            if role == "link" and ref and name:
                if keyword in name or "直播" in name:
                    print(f"   ✅ 找到直播间: {name}")
                    print(f"   调试: ref={ref}, role={role}")  # 添加调试信息
                    print(f"   调试: 完整节点信息: {node}")  # 打印完整节点
                    return {
                        "ref": ref,
                        "name": name,
                        "role": role
                    }
        
        print(f"   ⚠️  未找到 '{keyword}' 的直播间")
        return None
    
    def enter_live_room(self, ref: str, element_info: Optional[Dict] = None) -> bool:
        """进入直播间（使用智能点击）"""
        print(f"\n🎯 进入直播间...")
        
        # 使用智能点击
        result = self.pinchtab.smart_click(ref, element_info)
        
        if not result["success"]:
            print("   ❌ 智能点击失败")
            return False
        
        print(f"   ✅ 点击成功（方法: {result['method']}）")
        
        # 验证是否真的进入了直播间
        if result.get("url_changed"):
            url_after = result.get("url_after", "")
            if url_after.startswith("https://live.douyin.com/") and "search" not in url_after:
                print(f"   ✅ 成功进入直播间！")
                return True
        
        # 如果 URL 没变化，再等待一下检查
        print("   ⏳ 等待直播间加载...")
        time.sleep(3)
        
        page_data = self.pinchtab.get_page_text()
        current_url = page_data.get("url", "")
        print(f"   当前 URL: {current_url}")
        
        if current_url.startswith("https://live.douyin.com/") and "search" not in current_url:
            print(f"   ✅ 成功进入直播间！")
            return True
        else:
            print(f"   ❌ 未进入直播间")
            return False
    
    def send_message(self, message: str) -> bool:
        """发送消息到直播间"""
        print(f"\n💬 发送消息: '{message}'...")
        
        # 获取页面元素
        snapshot = self.pinchtab.get_snapshot()
        nodes = snapshot.get("nodes", [])
        
        # 查找输入框
        input_ref = None
        for node in nodes:
            role = node.get("role", "").lower()
            name = node.get("name", "")
            
            if role in ["textbox", "searchbox"] or "输入" in name or "评论" in name or "说点什么" in name:
                if "搜索" not in name:  # 排除搜索框
                    input_ref = node.get("ref")
                    print(f"   🎯 找到输入框: {input_ref}")
                    break
        
        if not input_ref:
            print(f"   ⚠️  未找到输入框")
            return False
        
        # 点击输入框
        self.pinchtab.click(input_ref)
        time.sleep(0.5)
        
        # 输入消息
        self.pinchtab.type_text(input_ref, message)
        time.sleep(0.5)
        
        # 发送
        self.pinchtab.press_key("Enter")
        
        print(f"   ✅ 消息已发送！")
        return True
