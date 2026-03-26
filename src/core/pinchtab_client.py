"""
PinchTab 浏览器客户端
"""

import time
import requests
from typing import Optional, Dict, List, Any


class PinchTabClient:
    """PinchTab 浏览器控制客户端"""
    
    def __init__(self, base_url: str = "http://localhost:9867"):
        self.base_url = base_url
        self.session = requests.Session()
        self.instance_id: Optional[str] = None
        self.tab_id: Optional[str] = None
        self.profile_name: Optional[str] = None
    
    def connect(self, profile_name: str = "douyin_uploader", headless: bool = False) -> bool:
        """创建新实例，使用指定的 profile"""
        print(f"\n🔗 使用 Profile: {profile_name} (模式: {'有头' if not headless else '无头'})")
        
        try:
            # 先停止旧实例（确保每个任务使用全新实例）
            print(f"   🔍 检查旧实例...")
            instances_response = self.session.get(f"{self.base_url}/instances", timeout=10)
            if instances_response.status_code == 200:
                instances = instances_response.json()
                for inst in instances:
                    if inst.get("profileName") == profile_name and inst.get("status") == "running":
                        old_id = inst["id"]
                        print(f"   🗑️  停止旧实例: {old_id}")
                        self.session.post(f"{self.base_url}/instances/{old_id}/stop", timeout=10)
                        print(f"   ⏳ 等待清理完成...")
                        time.sleep(10)  # 等待清理完成
                        break
            
            # 创建新实例，最多重试3次
            mode = "headless" if headless else "headed"
            max_retries = 3
            for attempt in range(max_retries):
                print(f"   🆕 创建新实例（尝试 {attempt + 1}/{max_retries}）...")
                response = self.session.post(
                    f"{self.base_url}/instances/launch",
                    json={"name": profile_name, "mode": mode},
                    timeout=15
                )
                
                if response.status_code in [200, 201]:
                    self.instance_id = response.json()["id"]
                    self.profile_name = profile_name
                    print(f"   ✅ 新实例: {self.instance_id}")
                    print(f"   ⏳ 等待实例启动和加载 cookies...")
                    time.sleep(6)  # 等待实例启动和加载 profile cookies
                    break
                elif response.status_code == 409:
                    if attempt < max_retries - 1:
                        print(f"   ⚠️  仍有冲突，等待后重试...")
                        time.sleep(5)
                        continue
                    else:
                        print(f"   ❌ 创建失败: 409 冲突（已重试{max_retries}次）")
                        return False
                else:
                    print(f"   ❌ 创建失败: {response.status_code}")
                    if attempt < max_retries - 1:
                        time.sleep(3)
                        continue
                    return False
            
            # 轮询等待实例 ready（最多30秒）
            print(f"   ⏳ 等待实例就绪...")
            for _ in range(30):
                time.sleep(1)
                r = self.session.get(
                    f"{self.base_url}/instances/{self.instance_id}/tabs",
                    timeout=5
                )
                if r.status_code == 200:
                    tabs = r.json()
                    if tabs:
                        self.tab_id = tabs[0]["id"]
                        print(f"   ✅ 标签页: {self.tab_id}")
                        return True
            print(f"   ❌ 实例启动超时")
            return False
            
        except Exception as e:
            print(f"   ❌ 连接失败: {e}")
            return False
    
    def navigate(self, url: str, wait_seconds: int = 3) -> bool:
        """导航到指定 URL"""
        try:
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/navigate",
                json={"url": url},
                timeout=15
            )

            if response.status_code == 200:
                time.sleep(wait_seconds)
                return True
            return False

        except Exception as e:
            print(f"   ⚠️  导航失败: {e}")
            return False

    def navigate_and_wait(self, url: str, wait_for: str = "url_change", timeout: int = 10) -> Dict[str, Any]:
        """
        导航并智能等待

        wait_for: 'url_change' | 'element_load' | 'ready'
        """
        print(f"\n🚀 导航到: {url}")
        print(f"   等待条件: {wait_for}")

        # 先导航
        response = self.session.post(
            f"{self.base_url}/tabs/{self.tab_id}/navigate",
            json={"url": url},
            timeout=15
        )

        if response.status_code != 200:
            return {'success': False, 'error': 'navigate_failed'}

        # 智能等待
        if wait_for == 'url_change':
            return self._wait_for_url_contains(url, timeout)
        elif wait_for == 'ready':
            return self._wait_for_page_ready(timeout)
        else:
            # 默认等待
            time.sleep(3)
            return {'success': True}

    def _wait_for_url_contains(self, target_url: str, timeout: int) -> Dict[str, Any]:
        """等待URL包含目标字符串"""
        print(f"   监测URL变化... (目标: {target_url})")
        start_time = time.time()

        while time.time() - start_time < timeout:
            current_url = self._get_url_fast()
            if current_url:  # 只在URL不为空时打印
                print(f"   当前URL: {current_url}")

            if target_url in current_url:
                print(f"   ✅ URL已变化: {current_url}")
                return {'success': True, 'url': current_url}

            time.sleep(0.2)  # 每0.2秒检查一次

        print(f"   ❌ 超时: {timeout}秒内URL未变化")
        current_url = self._get_url_fast()
        print(f"   最终URL: {current_url}")
        return {'success': False, 'error': 'timeout', 'url': current_url}

    def _wait_for_page_ready(self, timeout: int) -> Dict[str, Any]:
        """等待页面就绪"""
        print(f"   等待页面就绪...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            # 检查页面是否有内容
            try:
                js_check = """
                (function() {
                    return {
                        hasBody: !!document.body,
                        bodyText: document.body ? document.body.textContent.length : 0,
                        readyState: document.readyState
                    };
                })();
                """

                response = self.session.post(
                    f"{self.base_url}/tabs/{self.tab_id}/evaluate",
                    json={"expression": js_check},
                    timeout=3
                )

                if response.status_code == 200:
                    result = response.json().get('result', {}).get('value', {})
                    if result.get('bodyText', 0) > 100:
                        print(f"   ✅ 页面已就绪")
                        return {'success': True}
            except:
                pass

            time.sleep(0.5)

        print(f"   ⚠️  等待超时,继续执行")
        return {'success': True}  # 超时也返回成功,不阻塞流程
    
    def get_page_text(self) -> Dict[str, Any]:
        """获取页面文本内容"""
        try:
            response = self.session.get(
                f"{self.base_url}/tabs/{self.tab_id}/text",
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            return {}
            
        except Exception as e:
            print(f"   ⚠️  获取页面文本失败: {e}")
            return {}
    
    def get_page_info(self, needs: dict) -> dict:
        """
        按需获取页面信息

        needs: {'url': True, 'buttons': True, 'text': True}
        返回: 只包含需要的信息
        """
        result = {}

        if needs.get('url'):
            result['url'] = self._get_url_fast()

        if needs.get('title'):
            result['title'] = self._get_title_fast()

        if needs.get('text'):
            result['text'] = self._get_text_summary()

        if needs.get('buttons'):
            result['buttons'] = self._get_buttons_only()

        if needs.get('all'):  # 完整状态(兼容旧代码)
            result.update(self._get_full_state())

        return result

    def _get_url_fast(self) -> str:
        """快速获取URL"""
        try:
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/evaluate",
                json={"expression": "window.location.href"},
                timeout=3
            )
            if response.status_code == 200:
                return response.json().get('result', {}).get('value', '')
        except:
            pass
        return ''

    def _get_title_fast(self) -> str:
        """快速获取标题"""
        try:
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/evaluate",
                json={"expression": "document.title"},
                timeout=3
            )
            if response.status_code == 200:
                return response.json().get('result', {}).get('value', '')
        except:
            pass
        return ''

    def _get_text_summary(self) -> str:
        """获取文本摘要"""
        try:
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/evaluate",
                json={"expression": "document.body.textContent.substring(0, 500)"},
                timeout=3
            )
            if response.status_code == 200:
                return response.json().get('result', {}).get('value', '')
        except:
            pass
        return ''

    def _get_buttons_only(self) -> list:
        """只获取按钮元素"""
        snapshot = self.get_snapshot()
        return [
            {
                'ref': node.get('ref'),
                'name': node.get('name'),
                'role': node.get('role')
            }
            for node in snapshot.get('nodes', [])
            if node.get('role') in ['button', 'link']
        ]

    def _get_full_state(self) -> dict:
        """获取完整状态(旧方法,兼容性保留)"""
        try:
            response = self.session.get(
                f"{self.base_url}/tabs/{self.tab_id}",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'url': data.get('url', ''),
                    'title': data.get('title', ''),
                    'text': data.get('text', '')
                }
        except:
            pass

        # 备用方法
        return {
            'url': self._get_url_fast(),
            'title': self._get_title_fast(),
            'text': self._get_text_summary()
        }

    def get_snapshot(self) -> Dict[str, Any]:
        """获取页面快照（元素树）"""
        try:
            response = self.session.get(
                f"{self.base_url}/tabs/{self.tab_id}/snapshot",
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
            return {}

        except Exception as e:
            print(f"   ⚠️  获取页面快照失败: {e}")
            return {}

    def click(self, ref: str) -> bool:
        """点击元素"""
        try:
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/action",
                json={"kind": "click", "ref": ref},
                timeout=5
            )
            return response.status_code == 200
            
        except Exception as e:
            print(f"   ⚠️  点击失败: {e}")
            return False
    
    def type_text(self, ref: str, text: str) -> bool:
        """输入文本"""
        try:
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/action",
                json={"kind": "type", "ref": ref, "text": text},
                timeout=5
            )
            return response.status_code == 200
            
        except Exception as e:
            print(f"   ⚠️  输入失败: {e}")
            return False
    
    def press_key(self, key: str) -> bool:
        """按键"""
        try:
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/action",
                json={"kind": "press", "key": key},
                timeout=5
            )
            return response.status_code == 200
            
        except Exception as e:
            print(f"   ⚠️  按键失败: {e}")
            return False
    
    def screenshot(self, quality: int = 80) -> Optional[str]:
        """截图（返回 base64）"""
        try:
            response = self.session.get(
                f"{self.base_url}/tabs/{self.tab_id}/screenshot",
                params={"quality": quality},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("base64")
            return None
            
        except Exception as e:
            print(f"   ⚠️  截图失败: {e}")
            return None
    
    def smart_click(self, ref: str, element_info: Optional[Dict] = None) -> Dict[str, Any]:
        """
        智能点击：尝试多种点击方式直到成功
        
        这是修复 PinchTab 点击操作失效问题的核心方法。
        按优先级尝试多种点击方式：
        1. JavaScript 直接点击（最可靠）
        2. 滚动到元素后 JavaScript 点击
        3. 获取 href 并直接导航（仅限链接）
        4. PinchTab 原生 click（最后尝试）
        
        Args:
            ref: 元素的 ref 属性（如 "e5"）
            element_info: 元素信息（可选，用于日志和决策）
                {
                    "name": "元素名称",
                    "role": "元素角色（link/button/image等）",
                    "href": "链接地址（如果是链接）"
                }
        
        Returns:
            dict: {
                "success": bool,  # 是否成功
                "method": str,    # 使用的方法
                "url_changed": bool,  # URL 是否变化
                "error": str      # 错误信息（如果失败）
            }
        """
        print(f"\n🎯 智能点击: {ref}")
        if element_info:
            print(f"   元素: {element_info.get('name', 'N/A')} ({element_info.get('role', 'N/A')})")
        
        # 记录点击前的 URL
        url_before = self._get_current_url()
        print(f"   点击前 URL: {url_before}")
        
        # 方法 1: JavaScript 直接点击
        print(f"\n   方法 1: JavaScript 直接点击...")
        result = self._js_click(ref)
        if result["success"]:
            time.sleep(2)  # 等待页面响应
            url_after = self._get_current_url()
            url_changed = url_after != url_before
            
            if url_changed:
                print(f"   ✅ 成功！URL 已变化: {url_after}")
                return {
                    "success": True,
                    "method": "js_click",
                    "url_changed": True,
                    "url_before": url_before,
                    "url_after": url_after
                }
            else:
                print(f"   ⚠️  点击执行了，但 URL 未变化")
        
        # 方法 2: 滚动到元素后 JavaScript 点击
        print(f"\n   方法 2: 滚动到元素后点击...")
        result = self._scroll_and_click(ref)
        if result["success"]:
            time.sleep(3)  # 等待页面响应
            url_after = self._get_current_url()
            url_changed = url_after != url_before
            
            if url_changed:
                print(f"   ✅ 成功！URL 已变化: {url_after}")
                return {
                    "success": True,
                    "method": "scroll_and_click",
                    "url_changed": True,
                    "url_before": url_before,
                    "url_after": url_after
                }
            else:
                print(f"   ⚠️  点击执行了，但 URL 未变化")
        
        # 方法 3: 获取 href 并直接导航（仅限链接）
        if element_info and element_info.get("role") == "link":
            print(f"\n   方法 3: 获取 href 并直接导航...")
            element_name = element_info.get("name", "")
            result = self._navigate_to_href(ref, element_name)
            if result["success"]:
                time.sleep(2)
                url_after = self._get_current_url()
                url_changed = url_after != url_before
                
                if url_changed:
                    print(f"   ✅ 成功！已导航到: {url_after}")
                    return {
                        "success": True,
                        "method": "navigate_to_href",
                        "url_changed": True,
                        "url_before": url_before,
                        "url_after": url_after
                    }
        
        # 方法 4: PinchTab 原生 click（最后尝试）
        print(f"\n   方法 4: PinchTab 原生 click...")
        result = self._pinchtab_click(ref)
        if result["success"]:
            time.sleep(3)
            url_after = self._get_current_url()
            url_changed = url_after != url_before
            
            if url_changed:
                print(f"   ✅ 成功！URL 已变化: {url_after}")
                return {
                    "success": True,
                    "method": "pinchtab_click",
                    "url_changed": True,
                    "url_before": url_before,
                    "url_after": url_after
                }
            else:
                print(f"   ⚠️  点击执行了，但 URL 未变化")
        
        # 所有方法都失败
        print(f"\n   ❌ 所有点击方法都失败")
        return {
            "success": False,
            "method": "none",
            "url_changed": False,
            "error": "All click methods failed"
        }
    
    def _get_current_url(self) -> str:
        """获取当前页面 URL"""
        try:
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/evaluate",
                json={"expression": "window.location.href"},
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                return result.get("result", "")
        except:
            pass
        return ""
    
    def _js_click(self, ref: str) -> Dict[str, Any]:
        """方法 1: JavaScript 直接点击"""
        try:
            js_script = f"""
            Array.from(document.querySelectorAll('*')).find(el => el.getAttribute && el.getAttribute('ref') === '{ref}')?.click();
            true
            """
            
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/evaluate",
                json={"expression": js_script},
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("result") == True:
                    return {"success": True}
            
            return {"success": False, "error": "JS click failed"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _scroll_and_click(self, ref: str) -> Dict[str, Any]:
        """方法 2: 滚动到元素后点击"""
        try:
            # 先滚动到元素
            scroll_script = f"""
            (function() {{
                const element = document.querySelector('[ref="{ref}"]');
                if (!element) return false;
                element.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                return true;
            }})();
            """
            
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/evaluate",
                json={"expression": scroll_script},
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json().get("result")
                if result:
                    # 等待滚动完成
                    time.sleep(0.5)
                    
                    # 然后点击
                    click_script = f"""
                    (function() {{
                        const element = document.querySelector('[ref="{ref}"]');
                        if (!element) return false;
                        element.click();
                        return true;
                    }})();
                    """
                    
                    click_response = self.session.post(
                        f"{self.base_url}/tabs/{self.tab_id}/evaluate",
                        json={"expression": click_script},
                        timeout=5
                    )
                    
                    if click_response.status_code == 200:
                        click_result = click_response.json().get("result")
                        if click_result:
                            return {"success": True}
            
            return {"success": False, "error": "Scroll and click failed"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _navigate_to_href(self, ref: str, element_name: str = "") -> Dict[str, Any]:
        """方法 3: 获取 href 并直接导航（仅限链接）"""
        try:
            # 使用元素名称来查找链接（更可靠）
            if element_name:
                js_script = f"""
                (function() {{
                    const links = Array.from(document.querySelectorAll('a'));
                    const target = links.find(el => {{
                        const text = el.textContent.trim();
                        return text.includes('{element_name}') || text === '{element_name}';
                    }});
                    return target ? target.href : null;
                }})();
                """
            else:
                # 备用方案：尝试通过 ref 属性查找（可能不工作）
                js_script = f"""
                Array.from(document.querySelectorAll('a')).find(el => el.getAttribute && el.getAttribute('ref') === '{ref}')?.href
                """
            
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/evaluate",
                json={"expression": js_script},
                timeout=5
            )
            
            if response.status_code == 200:
                href = response.json().get("result")
                
                print(f"      调试: 获取到的 href = {href}")
                
                if href and href.startswith("http"):
                    print(f"      获取到 href: {href}")
                    # 直接导航到目标 URL
                    nav_response = self.session.post(
                        f"{self.base_url}/tabs/{self.tab_id}/navigate",
                        json={"url": href},
                        timeout=15
                    )
                    
                    if nav_response.status_code == 200:
                        return {"success": True, "href": href}
                else:
                    print(f"      调试: href 无效或不是 http 开头")
            
            return {"success": False, "error": "No valid href found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _pinchtab_click(self, ref: str) -> Dict[str, Any]:
        """方法 4: PinchTab 原生 click API"""
        try:
            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/action",
                json={"kind": "click", "ref": ref},
                timeout=5
            )
            
            if response.status_code == 200:
                return {"success": True}
            
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


    def create_tab(self, url: str = "about:blank") -> Optional[str]:
        """
        创建新标签页（通过 JavaScript 打开新窗口）

        Returns:
            新标签页的 ID，如果失败返回 None
        """
        try:
            # 记录创建前的 Tab IDs
            tabs_before = self.get_all_tabs()
            tab_ids_before = {tab["id"] for tab in tabs_before}
            
            js_script = f'window.open("{url}", "_blank");'

            response = self.session.post(
                f"{self.base_url}/tabs/{self.tab_id}/evaluate",
                json={"expression": js_script},
                timeout=5
            )

            if response.status_code == 200:
                time.sleep(2)

                # 获取创建后的所有 Tab
                tabs_after = self.get_all_tabs()
                
                # 找出新创建的 Tab
                for tab in tabs_after:
                    if tab["id"] not in tab_ids_before:
                        return tab["id"]

            return None

        except Exception as e:
            print(f"   ⚠️  创建标签页失败: {e}")
            return None

    def get_all_tabs(self) -> List[Dict[str, Any]]:
        """获取实例的所有标签页"""
        try:
            response = self.session.get(
                f"{self.base_url}/instances/{self.instance_id}/tabs",
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
            return []

        except Exception as e:
            print(f"   ⚠️  获取标签页失败: {e}")
            return []


    def cleanup(self) -> bool:
        """清理并停止实例"""
        if not self.instance_id:
            return True

        try:
            print(f"\n🧹 清理实例: {self.instance_id}")
            response = self.session.post(
                f"{self.base_url}/instances/{self.instance_id}/stop",
                timeout=10
            )

            if response.status_code in [200, 204]:
                print(f"   ✅ 实例已停止")
                self.instance_id = None
                self.tab_id = None
                return True
            else:
                print(f"   ⚠️  停止失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            print(f"   ❌ 清理失败: {e}")
            return False

    def __del__(self):
        """析构函数：自动清理实例"""
        if hasattr(self, 'instance_id') and self.instance_id:
            try:
                self.cleanup()
            except:
                pass


