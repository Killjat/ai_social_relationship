"""
PinchTab 执行层 - 系统的"手脚"

负责执行操作、捕获结果、获取页面状态、反馈执行信息
"""

import time
import json
import base64
from typing import Dict, Any, Optional

from .pinchtab_client import PinchTabClient


class ActionExecutor:
    """PinchTab 执行层"""

    def __init__(self, pinchtab_client: PinchTabClient):
        self.pinchtab = pinchtab_client
        self.last_screenshot = None

    def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 AI 决策的操作

        返回：
        {
            "success": bool,
            "error": str,
            "execution_time": float,
            "evidence": {
                "before_url": str,
                "after_url": str,
                "method_used": str,
                "details": dict
            }
        }
        """
        action_type = action.get("action")
        params = action.get("params", {})

        start_time = time.time()
        before_url = self._get_current_url()

        print(f"  ⚙️  执行操作: {action_type}")

        try:
            if action_type == "navigate":
                result = self._execute_navigate(params)
            elif action_type == "search_element":
                result = self._execute_search_element(params)
            elif action_type == "click":
                result = self._execute_click(params)
            elif action_type == "scroll":
                result = self._execute_scroll(params)
            elif action_type == "wait":
                result = self._execute_wait(params)
            elif action_type == "extract_data":
                result = self._execute_extract_data(params)
            elif action_type == "verify_result":
                result = self._execute_verify(params)
            elif action_type == "refresh":
                result = self._execute_refresh(params)
            elif action_type == "fallback":
                result = self._execute_fallback(params)
            elif action_type == "complete":
                result = {"success": True, "message": "任务完成"}
            else:
                result = {
                    "success": False,
                    "error": f"未知操作类型: {action_type}"
                }

            execution_time = time.time() - start_time
            after_url = self._get_current_url()

            result["execution_time"] = execution_time
            result["evidence"] = {
                "before_url": before_url,
                "after_url": after_url,
                "url_changed": before_url != after_url
            }

            print(f"  ✅ 执行完成: {action_type} ({execution_time:.2f}s)")
            print(f"  📍 URL: {before_url} → {after_url}")

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            return {
                "success": False,
                "error": str(e),
                "execution_time": execution_time,
                "evidence": {
                    "before_url": before_url,
                    "after_url": self._get_current_url(),
                    "error_occurred": True
                }
            }

    def _execute_navigate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """导航到指定 URL - 使用智能等待"""
        url = params.get("url")
        if not url:
            return {"success": False, "error": "缺少 URL 参数"}

        # 使用智能等待导航
        result = self.pinchtab.navigate_and_wait(url, wait_for='url_change', timeout=10)

        return {
            "success": result.get("success", False),
            "url": url,
            "current_url": result.get("url", ""),
            "url_matched": result.get("success", False),
            "error": result.get("error", "")
        }

    def _execute_search_element(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """搜索页面元素"""
        target = params.get("target")  # 目标元素描述，如"关注按钮"
        element_type = params.get("element_type", "")  # 可选：button, link 等
        role = params.get("role", "")  # 可选：角色

        snapshot = self.pinchtab.get_snapshot()
        nodes = snapshot.get("nodes", [])

        # 搜索匹配的元素
        matched = []
        for node in nodes:
            name = node.get("name", "")
            node_role = node.get("role", "")

            # 匹配逻辑
            score = 0
            if target and target.lower() in name.lower():
                score += 3
            if element_type and element_type.lower() in node_role.lower():
                score += 2
            if role and role.lower() in node_role.lower():
                score += 2

            if score > 0:
                matched.append({
                    "ref": node.get("ref"),
                    "name": name,
                    "role": node_role,
                    "score": score
                })

        # 按分数排序
        matched.sort(key=lambda x: x["score"], reverse=True)

        if matched:
            best = matched[0]
            print(f"  🔍 找到元素: {best['name']} (分数: {best['score']})")
            return {
                "success": True,
                "element_ref": best["ref"],
                "element_name": best["name"],
                "matched_count": len(matched)
            }
        else:
            return {
                "success": False,
                "error": f"未找到元素: {target}",
                "matched_count": 0
            }

    def _execute_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """点击元素"""
        element_ref = params.get("ref")
        method = params.get("method", "smart_click")  # smart_click, evaluate_js, direct

        if not element_ref:
            return {"success": False, "error": "缺少元素 ref"}

        # 获取点击前的 URL
        before_url = self._get_current_url()

        if method == "smart_click":
            result = self.pinchtab.smart_click(
                element_ref,
                {"name": params.get("name", ""), "role": params.get("role", "")}
            )
            # smart_click内部已经处理了等待和URL变化检测
            return {
                "success": result.get("success", False),
                "method_used": result.get("method", "smart_click"),
                "url_changed": result.get("url_changed", False),
                "before_url": result.get("url_before", before_url),
                "after_url": result.get("url_after", ""),
                "error": result.get("error", "")
            }
        elif method == "evaluate_js":
            js_code = f"document.querySelector('[ref=\"{element_ref}\"]').click()"
            response = self.pinchtab.session.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_code},
                timeout=10
            )
            result = {"success": response.status_code == 200}
        elif method == "direct":
            result = self.pinchtab.click(element_ref)
        else:
            return {"success": False, "error": f"未知点击方法: {method}"}

        # 等待页面响应（抖音页面加载较慢，增加等待时间）
        time.sleep(3)

        # 检查 URL 是否变化
        after_url = self._get_current_url()
        url_changed = before_url != after_url

        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "点击失败"),
                "url_changed": url_changed
            }

        return {
            "success": True,
            "method_used": method,
            "url_changed": url_changed,
            "before_url": before_url,
            "after_url": after_url
        }

    def _execute_scroll(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """滚动页面"""
        direction = params.get("direction", "down")
        amount = params.get("amount", 500)

        if direction == "down":
            js_code = f"window.scrollBy(0, {amount});"
        elif direction == "up":
            js_code = f"window.scrollBy(0, -{amount});"
        else:
            return {"success": False, "error": f"未知滚动方向: {direction}"}

        response = self.pinchtab.session.post(
            f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
            json={"expression": js_code},
            timeout=10
        )

        time.sleep(1)  # 等待滚动完成

        return {
            "success": response.status_code == 200,
            "direction": direction,
            "amount": amount
        }

    def _execute_wait(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """等待"""
        seconds = params.get("seconds", 2)
        time.sleep(seconds)
        return {"success": True, "waited_seconds": seconds}

    def _execute_refresh(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """刷新页面"""
        before_url = self._get_current_url()

        # 使用 JavaScript 刷新页面
        js_code = "location.reload();"

        response = self.pinchtab.session.post(
            f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
            json={"expression": js_code},
            timeout=10
        )

        time.sleep(2)  # 等待页面重新加载

        after_url = self._get_current_url()

        return {
            "success": response.status_code == 200,
            "before_url": before_url,
            "after_url": after_url
        }

    def _execute_fallback(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行降级方案"""
        strategy = params.get("strategy", "navigate")

        if strategy == "navigate_home":
            # 导航回主页
            url = params.get("url", "https://www.douyin.com/user/self")
            return self._execute_navigate({"url": url})

        elif strategy == "extract_from_text":
            # 从文本中提取数据
            target_text = params.get("target_text", "")
            context_length = params.get("context_length", 20)

            page_state = self.get_page_state()
            text = page_state.get("text", "")

            # 简单的文本提取
            result = {
                "success": True,
                "strategy": "extract_from_text",
                "target_text": target_text,
                "context": text[:context_length] if text else "",
                "found": target_text in text if text else False
            }

            return result

        else:
            # 默认：等待
            return self._execute_wait({"seconds": 2})

    def _execute_extract_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """提取页面数据"""
        data_type = params.get("type", "generic")

        # 获取页面状态
        page_state = self.get_page_state()
        text = page_state.get("text", "")

        if data_type == "user_list":
            result = self._extract_user_list(text, params)
        elif data_type == "work_list":
            result = self._extract_work_list(text, params)
        else:
            result = self._extract_generic(text, params)

        return result

    def _execute_verify(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """验证结果"""
        check = params.get("check", "")
        url = self._get_current_url()

        if check == "url_contains_follow":
            success = "/follow" in url.lower()
        elif check == "url_contains_fan":
            success = "/fan" in url.lower() or "/followers" in url.lower()
        elif check == "not_login_page":
            page_text = self.pinchtab.get_page_text().get("text", "")
            is_login = "扫码登录" in page_text[:300] and "密码登录" in page_text[:300]
            success = not is_login
        else:
            success = True

        return {
            "success": success,
            "checked": check,
            "url": url
        }

    def get_page_state(self, needs: dict = None) -> Dict[str, Any]:
        """
        获取页面状态

        needs: {'url': True, 'buttons': True, 'text': True} (按需获取)
        如果needs为None,返回完整状态(兼容旧代码)
        """
        if needs is None:
            # 旧代码兼容: 返回完整状态
            return self._get_full_state_legacy()
        else:
            # 新方式: 按需获取
            return self.pinchtab.get_page_info(needs)

    def _get_full_state_legacy(self) -> Dict[str, Any]:
        """完整状态获取(旧方法,保留兼容性)"""
        # 方法1: 使用PinchTab API
        try:
            response = self.pinchtab.session.get(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'url': data.get('url', ''),
                    'title': data.get('title', ''),
                    'text': data.get('text', ''),
                    'nodes': self.pinchtab.get_snapshot().get('nodes', [])
                }
        except:
            pass

        # 方法2: 使用JavaScript备用
        return {
            'url': self._get_current_url(),
            'title': self._get_title_fast(),
            'text': self._get_text_fast()
        }

    def _get_current_url(self) -> str:
        """快速获取URL"""
        try:
            js_code = "window.location.href"
            response = self.pinchtab.session.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_code},
                timeout=5
            )
            if response.status_code == 200:
                return response.json().get('result', {}).get('value', '')
        except:
            pass
        return ''

    def _get_title_fast(self) -> str:
        """快速获取标题"""
        try:
            js_code = "document.title"
            response = self.pinchtab.session.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_code},
                timeout=5
            )
            if response.status_code == 200:
                return response.json().get('result', {}).get('value', '')
        except:
            pass
        return ''

    def _get_text_fast(self) -> str:
        """快速获取文本"""
        try:
            js_code = "document.body.textContent.substring(0, 500)"
            response = self.pinchtab.session.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_code},
                timeout=5
            )
            if response.status_code == 200:
                return response.json().get('result', {}).get('value', '')
        except:
            pass
        return ''
        """
        获取当前页面完整状态

        返回：
        {
            "url": str,
            "title": str,
            "text": str,
            "elements": list,
            "snapshot": dict
        }
        """
        state = {
            "url": "",
            "title": "",
            "text": "",
            "elements": []
        }

        try:
            # 获取页面文本（增加备用方法）
            text_response = self.pinchtab.get_page_text()
            url = text_response.get("url", "")
            title = text_response.get("title", "")
            text = text_response.get("text", "")
            
            # 如果pinchtab API返回空，用JavaScript备用方法
            if not url or not title or not text:
                try:
                    js_get_state = """
                    (function() {
                        return {
                            url: window.location.href,
                            title: document.title || '',
                            text: document.body.textContent || document.documentElement.textContent || ''
                        };
                    })();
                    """
                    response = self.pinchtab.session.post(
                        f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                        json={"expression": js_get_state},
                        timeout=5
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        result_data = result.get("result", "")
                        if result_data and isinstance(result_data, str):
                            import json
                            js_state = json.loads(result_data)
                            if not url: url = js_state.get("url", "")
                            if not title: title = js_state.get("title", "")
                            if not text: text = js_state.get("text", "")
                except Exception as e:
                    print(f"    ⚠️  JavaScript备用获取状态失败: {e}")
            
            state["url"] = url
            state["title"] = title
            state["text"] = text
        except Exception as e:
            print(f"    ⚠️  获取文本失败: {e}")

        try:
            # 获取页面元素
            snapshot = self.pinchtab.get_snapshot()
            nodes = snapshot.get("nodes", [])

            # 过滤可交互元素
            interactive_roles = [
                "button", "link", "textbox", "searchbox",
                "combobox", "checkbox", "radio", "tab"
            ]

            elements = []
            for node in nodes:
                role = node.get("role", "")
                name = node.get("name", "")
                ref = node.get("ref", "")

                if role.lower() in interactive_roles or node.get("focusable"):
                    elements.append({
                        "ref": ref,
                        "role": role,
                        "name": name,
                        "value": node.get("value", "")
                    })

            state["elements"] = elements
            state["snapshot"] = snapshot
        except Exception as e:
            print(f"    ⚠️  获取元素失败: {e}")

        return state

    def _get_current_url(self) -> str:
        """获取当前 URL"""
        try:
            response = self.pinchtab.session.get(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("url", "")
        except:
            pass
        return ""

    def _extract_user_list(self, text: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """提取用户列表数据 - 直接从页面 DOM 提取"""
        max_count = params.get("max_count", 20)
        print(f"    🔧 DEBUG: _extract_user_list 被调用，max_count={max_count}")

        # 先用 JavaScript 获取完整页面文本（因为 text 参数可能为空）
        js_get_text = """
        (function() {
            return document.body.textContent || document.documentElement.textContent || '';
        })();
        """

        try:
            response = self.pinchtab.session.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_get_text},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                full_text = result.get("result", "")
                if full_text:
                    text = full_text
                    print(f"    📄 从 DOM 获取到文本长度: {len(text)} 字符")
                    print(f"    📄 文本前500字符: {text[:500]}")
        except Exception as e:
            print(f"    ⚠️  获取 DOM 文本失败: {e}")

        # 使用 JavaScript 直接从 DOM 提取用户数据
        js_script = """
        (function() {
            const users = [];
            const userCards = document.querySelectorAll('[data-e2e="user-list-item"]');
            
            userCards.forEach((card, index) => {
                if (index >= %d) return;
                
                // 提取昵称
                const nicknameEl = card.querySelector('[data-e2e="user-nickname"]');
                const nickname = nicknameEl ? nicknameEl.textContent.trim() : '';
                
                // 提取抖音号
                const douyinIdEl = card.querySelector('[data-e2e="user-unique-id"]');
                let douyinId = douyinIdEl ? douyinIdEl.textContent.trim() : '';
                if (douyinId && douyinId.startsWith('抖音号：')) {
                    douyinId = douyinId.replace('抖音号：', '');
                }
                
                // 提取地区
                const locationEl = card.querySelector('[data-e2e="user-location"]');
                const location = locationEl ? locationEl.textContent.trim() : '';
                
                // 提取简介
                const descEl = card.querySelector('[data-e2e="user-desc"]');
                const description = descEl ? descEl.textContent.trim() : '';
                
                // 检查是否直播中
                const liveEl = card.querySelector('[data-e2e="user-live-status"]');
                const isLive = liveEl !== null;
                
                if (nickname) {
                    users.push({
                        nickname: nickname,
                        douyin_id: douyinId,
                        location: location,
                        description: description,
                        is_live: isLive
                    });
                }
            });
            
            // 如果没找到用户，尝试从 DOM 中提取
            if (users.length === 0) {
                const allDivs = document.querySelectorAll('div');
                for (let i = 0; i < allDivs.length && users.length < %d; i++) {
                    const div = allDivs[i];
                    const text = div.textContent || '';
                    const trimmed = text.trim();

                    // 跳过过短或过长的文本
                    if (trimmed.length < 3 || trimmed.length > 100) continue;

                    // 跳过导航和无关文本
                    const skipWords = ['我的关注', '抖音', '粉丝', '关注', '主页', '消息', '我', '直播', '红包', '作品', '喜欢'];
                    if (skipWords.some(w => trimmed.includes(w))) continue;

                    // 查找可能包含用户信息的 div
                    const nickname = trimmed.split('\\n')[0].trim();
                    const fullText = trimmed;

                    // 检查是否包含 LiveIcon（直播）
                    const isLive = fullText.includes('LiveIcon') || fullText.includes('正在直播');

                    // 尝试从文本中提取抖音号
                    const douyinIdMatch = fullText.match(/@?[a-zA-Z0-9_]{4,20}/);
                    const douyinId = douyinIdMatch ? douyinIdMatch[0].replace('@', '') : '';

                    if (nickname && nickname.length >= 2) {
                        users.push({
                            nickname: nickname,
                            douyin_id: douyinId,
                            location: '',
                            description: '',
                            is_live: isLive
                        });
                    }
                }
            }

            return JSON.stringify(users);
        })();
        """

        try:
            formatted_js = js_script % (max_count, max_count)
            print(f"    🔧 DEBUG: JavaScript 格式化成功")
        except Exception as e:
            print(f"    ❌ DEBUG: JavaScript 格式化失败: {e}")
            raise

        try:
            response = self.pinchtab.session.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": formatted_js},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                users_json = result.get("result", "[]")
                print(f"    📝 JavaScript 返回结果: {users_json[:200] if len(users_json) > 200 else users_json}")
                users = eval(users_json) if users_json else []

                if users:
                    return {
                        "success": True,
                        "data_type": "user_list",
                        "users": users,
                        "count": len(users)
                    }

        except Exception as e:
            print(f"    ⚠️  JavaScript 提取失败: {e}")

        # JavaScript 失败，尝试文本解析（使用从 DOM 获取的文本）
        users = self._parse_users_from_text(text, max_count)
        print(f"    📊 从文本解析到 {len(users)} 个用户")

        return {
            "success": True,
            "data_type": "user_list",
            "users": users,
            "count": len(users)
        }

    def _extract_work_list(self, text: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """提取作品列表数据"""
        max_count = params.get("max_count", 20)

        # 使用 JavaScript 直接从 DOM 提取作品数据
        js_script = """
        (function() {
            const works = [];
            const workCards = document.querySelectorAll('[data-e2e="aweme-item"]');
            
            workCards.forEach((card, index) => {
                if (index >= %d) return;
                
                // 提取标题
                const titleEl = card.querySelector('[data-e2e="aweme-title"]');
                const title = titleEl ? titleEl.textContent.trim() : '';
                
                // 提取点赞数
                const likesEl = card.querySelector('[data-e2e="aweme-like"]');
                const likesText = likesEl ? likesEl.textContent.trim() : '0';
                const likes = parseInt(likesText.replace(/[^\\d]/g, '')) || 0;
                
                // 提取评论数
                const commentsEl = card.querySelector('[data-e2e="aweme-comment"]');
                const commentsText = commentsEl ? commentsEl.textContent.trim() : '0';
                const comments = parseInt(commentsText.replace(/[^\\d]/g, '')) || 0;
                
                // 提取分享数
                const sharesEl = card.querySelector('[data-e2e="aweme-share"]');
                const sharesText = sharesEl ? sharesEl.textContent.trim() : '0';
                const shares = parseInt(sharesText.replace(/[^\\d]/g, '')) || 0;
                
                // 提取发布时间
                const timeEl = card.querySelector('[data-e2e="aweme-time"]');
                const publishTime = timeEl ? timeEl.textContent.trim() : '';
                
                works.push({
                    title: title,
                    likes: likes,
                    comments: comments,
                    shares: shares,
                    publish_time: publishTime
                });
            });
            
            // 如果没找到作品，尝试从文本解析
            if (works.length === 0) {
                const pattern = /(\\d+)赞\\s*(\\d+)评论\\s*(\\d+)分享/;
                const allText = document.body.textContent;
                const matches = [...allText.matchAll(pattern)];
                
                matches.forEach((match, index) => {
                    if (index >= %d) return;
                    
                    works.push({
                        title: '作品' + (index + 1),
                        likes: parseInt(match[1]) || 0,
                        comments: parseInt(match[2]) || 0,
                        shares: parseInt(match[3]) || 0,
                        publish_time: ''
                    });
                });
            }
            
            return JSON.stringify(works);
        })();
        """

        try:
            formatted_js = js_script % (max_count, max_count)
            response = self.pinchtab.session.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": formatted_js},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                works_json = result.get("result", "[]")
                works = eval(works_json) if works_json else []

                return {
                    "success": True,
                    "data_type": "work_list",
                    "works": works,
                    "count": len(works)
                }

        except Exception as e:
            print(f"    ⚠️  JavaScript 提取失败: {e}")

        # 如果 JavaScript 失败，尝试文本解析
        works = self._parse_works_from_text(text, max_count)

        return {
            "success": True,
            "data_type": "work_list",
            "works": works,
            "count": len(works)
        }

    def _extract_generic(self, text: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """通用数据提取"""
        return {
            "success": True,
            "data_type": "generic",
            "text_length": len(text),
            "raw_text": text[:2000]
        }

    def _parse_users_from_text(self, text: str, max_count: int) -> list:
        """从文本中解析用户信息（降级方案）"""
        import re

        users = []

        # 匹配用户昵称和抖音号的模式
        # 格式: "昵称(机构) 抖音号：xxx"
        pattern = r'([^\n]+?)\s*抖音号：([^\s\n]+)'
        matches = re.findall(pattern, text)

        for i, (nickname, douyin_id) in enumerate(matches[:max_count]):
            # 清理昵称
            nickname = nickname.strip()
            # 移除括号内的机构名
            nickname = re.sub(r'\([^)]*\)', '', nickname).strip()

            users.append({
                "nickname": nickname,
                "douyin_id": douyin_id,
                "location": "",
                "description": "",
                "is_live": False
            })

        # 如果没有匹配到抖音号，尝试提取昵称列表
        if not users:
            # 从 session 记录看到页面文本中包含用户名
            # 格式类似: "钢铁猫Atopos733"、"cyberstrollz241115" 等
            # 提取看起来像用户名的行
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                # 跳过过短或过长的行，以及导航相关文本
                if 3 <= len(line) <= 40:
                    # 跳过明确的导航文本
                    skip_patterns = ['我的关注', '抖音', '粉丝', '关注', '主页', '消息', '我', '直播', '红包', '海杉文化', '³¹²']
                    if any(p in line for p in skip_patterns):
                        continue
                    # 跳过纯数字或特殊字符
                    if not re.match(r'^[\w\u4e00-\u9fa5]+$', line):
                        continue
                    # 提取 LiveIcon 等特殊标记后的用户名
                    clean_line = re.sub(r'LiveIcon|红包', '', line).strip()
                    if clean_line and len(clean_line) >= 3:
                        users.append({
                            "nickname": clean_line,
                            "douyin_id": "",
                            "location": "",
                            "description": "",
                            "is_live": False
                        })
                        if len(users) >= max_count:
                            break

        return users

    def _parse_works_from_text(self, text: str, max_count: int) -> list:
        """从文本中解析作品信息（降级方案）"""
        import re

        works = []

        # 匹配作品的互动数据
        # 格式: "点赞数 评论数 分享数"
        pattern = r'(\d+)\s*赞\s*(\d+)\s*评论\s*(\d+)\s*分享'
        matches = re.findall(pattern, text)

        for i, (likes, comments, shares) in enumerate(matches[:max_count]):
            works.append({
                "title": f"作品{i + 1}",
                "likes": int(likes),
                "comments": int(comments),
                "shares": int(shares),
                "publish_time": ""
            })

        return works
