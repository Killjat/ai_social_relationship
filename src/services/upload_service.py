"""
视频上传服务 - AI 驱动版本
DeepSeek 作为大脑分析页面并决策，PinchTab 作为手脚执行操作
"""

import time
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from openai import OpenAI

from ..core import PinchTabClient


class UploadService:
    """视频上传服务 - AI 驱动"""
    
    def __init__(self, pinchtab_url: str = "http://localhost:9867", deepseek_api_key: str = None):
        self.pinchtab = PinchTabClient(pinchtab_url)
        self.cookies_file = Path("data/sessions/douyin_cookies.json")
        
        # DeepSeek 客户端（AI 大脑）
        if not deepseek_api_key:
            import os
            deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        
        if not deepseek_api_key:
            raise ValueError("需要 DEEPSEEK_API_KEY")
        
        self.deepseek = OpenAI(
            api_key=deepseek_api_key,
            base_url="https://api.deepseek.com"
        )
        
        # 对话历史
        self.conversation_history = []
        self.conversation_file = None
    
    def connect(self, profile_name: str = "douyin_uploader", headless: bool = False) -> bool:
        """连接到浏览器实例并加载登录状态"""
        if not self.pinchtab.connect(profile_name, headless):
            return False
        
        # 加载登录状态
        return self._load_login_state()
    
    def _load_login_state(self) -> bool:
        """加载登录状态"""
        print("\n🍪 加载登录状态...")
        
        if not self.cookies_file.exists():
            print("   ❌ 未找到登录状态")
            print("   💡 请先运行: python login_douyin_user.py")
            return False
        
        try:
            # 加载 cookies
            with open(self.cookies_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            cookies = session_data.get("cookies", [])
            print(f"   📦 找到 {len(cookies)} 个 Cookie")
            
            # 先导航到抖音
            print("   🌐 导航到抖音...")
            if not self.pinchtab.navigate("https://creator.douyin.com/", wait_seconds=3):
                print("   ⚠️  导航失败")
                return False
            
            # 转换并注入 Cookie
            pinchtab_cookies = []
            for cookie in cookies:
                pc = {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": cookie.get("domain", ".douyin.com"),
                    "path": cookie.get("path", "/"),
                    "secure": cookie.get("secure", False),
                    "httpOnly": cookie.get("httpOnly", False)
                }
                
                if "sameSite" in cookie:
                    pc["sameSite"] = cookie["sameSite"]
                
                if "expiry" in cookie:
                    pc["expires"] = cookie["expiry"]
                
                pinchtab_cookies.append(pc)
            
            # 批量注入 Cookie
            response = self.pinchtab.session.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/cookies",
                json={
                    "url": "https://creator.douyin.com",
                    "cookies": pinchtab_cookies
                }
            )
            
            if response.status_code == 200:
                print(f"   ✅ 成功加载 {len(pinchtab_cookies)} 个 Cookie")
                
                # 刷新页面验证
                print("   🔄 刷新页面验证登录...")
                self.pinchtab.navigate("https://creator.douyin.com/", wait_seconds=3)
                
                # 检查登录状态
                page_data = self.pinchtab.get_page_text()
                page_text = page_data.get("text", "")
                
                if "登录" in page_text and "扫码" in page_text:
                    print("   ❌ 登录状态已失效！")
                    print("   💡 请重新登录: python login_douyin_user.py")
                    return False
                elif "创作" in page_text or "发布" in page_text:
                    print("   ✅ 登录状态有效")
                    return True
                else:
                    print("   ⚠️  无法确定登录状态")
                    print(f"   页面文本片段: {page_text[:200]}")
                    return False
            else:
                print(f"   ⚠️  Cookie 加载失败: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ❌ 加载登录状态失败: {e}")
            return False
    
    def upload_video(self, video_path: Path, title: str = None, description: str = None) -> bool:
        """
        上传视频到抖音 - AI 驱动版本
        
        Args:
            video_path: 视频文件路径
            title: 视频标题（可选）
            description: 视频描述（可选）
        
        Returns:
            bool: 是否成功
        """
        print("\n" + "="*70)
        print("抖音视频上传 - AI 驱动")
        print("="*70)
        
        if not video_path.exists():
            print(f"❌ 视频文件不存在: {video_path}")
            return False
        
        print(f"\n📹 视频文件: {video_path.name}")
        print(f"   大小: {video_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        # 创建对话记录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.conversation_file = Path(f"data/conversations/upload_{timestamp}.json")
        self.conversation_file.parent.mkdir(parents=True, exist_ok=True)
        self.conversation_history = []
        
        # 系统提示词
        system_prompt = f"""你是浏览器自动化专家，负责指挥 PinchTab 完成抖音视频上传任务。

当前任务：上传视频到抖音创作者平台
视频路径：{video_path}
视频标题：{title or '（使用默认）'}

你的工作流程：
1. 分析当前页面的元素（Accessibility Tree）
2. 决定下一步操作
3. 返回 JSON 格式的操作指令

可用操作：
- navigate: 导航到 URL
- click: 点击元素（使用 ref）
- type: 输入文本（使用 ref + text）
- upload_file: 上传文件（params: {{"file_path": "路径", "selector": "input[type='file']"}})
- wait: 等待（seconds）
- screenshot: 截图
- done: 任务完成

返回格式（必须是纯 JSON）：
{{
    "thought": "你的思考过程",
    "action": "操作类型",
    "params": {{操作参数}},
    "next": "下一步计划"
}}

重要提示：
- 如果看到"继续编辑/放弃"对话框，点击"放弃"按钮
- 上传文件后需要等待视频处理完成（wait 10秒）
- 填写标题时要清空原有内容
- 最后点击"发布"或"高清发布"按钮
- 发布后必须等待至少5秒，确保发布操作完成
- 如果看到"发布成功"或跳转到作品列表，才能返回 done"""
        
        self._add_message("system", system_prompt)
        
        # 导航到上传页面
        print(f"\n🌐 导航到上传页面...")
        upload_url = "https://creator.douyin.com/creator-micro/content/upload"
        self.pinchtab.navigate(upload_url, wait_seconds=5)
        
        # AI 驱动的上传流程
        print(f"\n🧠 启动 AI 驱动模式...")
        max_iterations = 20
        
        for iteration in range(max_iterations):
            print(f"\n{'='*70}")
            print(f"第 {iteration + 1} 轮 - DeepSeek 分析中...")
            print(f"{'='*70}")

            # 规则兜底：优先处理“继续编辑/放弃”草稿弹层，避免 AI 无 ref 可点导致循环
            self._dismiss_draft_dialog_if_present()
            
            # 1. 获取当前页面状态
            page_state = self._get_page_state()
            
            # 2. 发送给 DeepSeek 分析
            user_message = f"""当前页面状态：

URL: {page_state['url']}
标题: {page_state['title']}

可交互元素：
{json.dumps(page_state['elements'][:20], indent=2, ensure_ascii=False)}

页面文本片段：
{page_state['text'][:500]}

请分析页面，决定下一步操作。"""
            
            self._add_message("user", user_message)
            
            # 调用 DeepSeek
            response = self._call_deepseek()
            self._add_message("assistant", response)
            
            # 3. 解析并执行指令
            try:
                instruction = json.loads(response)
                print(f"💭 思考: {instruction.get('thought', 'N/A')}")
                print(f"🎯 操作: {instruction.get('action', 'N/A')}")
                
                action = instruction.get("action")
                params = instruction.get("params", {})
                
                if action == "done":
                    print("✅ AI 判断任务完成！")
                    self._save_screenshot("upload_final")
                    self._save_conversation()
                    
                    # 验证发布是否真的成功
                    print("\n🔍 验证发布结果...")
                    if self._verify_upload_success(video_path.name):
                        print("✅ 验证成功：视频已发布到作品列表！")
                        return True
                    else:
                        print("⚠️  警告：无法确认视频是否发布成功")
                        print("   请手动检查抖音账号的作品列表")
                        return False
                
                # 执行操作
                self._execute_action(action, params, video_path)

                # 规则兜底：AI 点击发布后，固定等待并尝试验证/二次点击
                if action == "click":
                    target_ref = params.get("ref")
                    if target_ref and self._looks_like_publish_button_ref(target_ref):
                        self._post_publish_stabilize()
                
                # 保存对话历史
                self._save_conversation()
                
                # 等待页面响应
                time.sleep(2)
                
            except json.JSONDecodeError as e:
                print(f"⚠️  AI 返回格式错误: {e}")
                print(f"原始响应: {response[:200]}")
                continue
            except Exception as e:
                print(f"❌ 执行失败: {e}")
                continue
        
        print(f"\n⚠️  达到最大迭代次数，任务可能未完成")
        self._save_conversation()
        return False
    
    def _get_page_state(self) -> dict:
        """获取当前页面状态"""
        state = {
            "url": "",
            "title": "",
            "elements": [],
            "text": ""
        }
        
        try:
            # 获取页面文本
            response = self.pinchtab.get_page_text()
            state["url"] = response.get("url", "")
            state["title"] = response.get("title", "")
            state["text"] = response.get("text", "")
        except Exception as e:
            print(f"   ⚠️  获取页面文本失败: {e}")
        
        try:
            # 获取可交互元素
            snapshot = self.pinchtab.get_snapshot()
            nodes = snapshot.get("nodes", [])
            
            # 过滤可交互元素
            interactive_elements = []
            for node in nodes:
                role = node.get("role", "")
                name = node.get("name", "")
                ref = node.get("ref", "")
                
                interactive_roles = [
                    "button", "link", "textbox", "searchbox",
                    "combobox", "checkbox", "radio", "tab"
                ]
                
                if role.lower() in interactive_roles or node.get("focusable"):
                    interactive_elements.append({
                        "ref": ref,
                        "role": role,
                        "name": name,
                        "value": node.get("value", "")
                    })
            
            state["elements"] = interactive_elements
            
        except Exception as e:
            print(f"   ⚠️  获取元素失败: {e}")
        
        return state
    
    def _call_deepseek(self) -> str:
        """调用 DeepSeek API"""
        try:
            response = self.deepseek.chat.completions.create(
                model="deepseek-chat",
                messages=self.conversation_history,
                temperature=0.7,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"   ❌ DeepSeek 调用失败: {e}")
            return '{"action": "wait", "params": {"seconds": 2}, "thought": "API 调用失败"}'
    
    def _execute_action(self, action: str, params: dict, video_path: Path = None):
        """执行操作"""
        print(f"   🤖 执行: {action}")
        
        try:
            if action == "navigate":
                url = params.get("url")
                self.pinchtab.navigate(url, wait_seconds=3)
                print(f"   ✅ 已导航到: {url}")
            
            elif action == "click":
                ref = params.get("ref")
                self.pinchtab.click(ref)
                print(f"   ✅ 已点击: {ref}")
            
            elif action == "type":
                ref = params.get("ref")
                text = params.get("text")
                self.pinchtab.click(ref)
                time.sleep(0.5)
                self.pinchtab.type_text(ref, text)
                print(f"   ✅ 已输入: {text}")
            
            elif action == "upload_file":
                # 使用实际的视频路径
                if video_path:
                    file_path = str(video_path)
                else:
                    file_path = params.get("file_path")
                
                selector = params.get("selector", "input[type='file']")

                source_path = Path(file_path).resolve()
                if not source_path.exists():
                    print(f"   ❌ 视频文件不存在: {source_path}")
                    return

                staged_rel_path = self._stage_file_for_pinchtab_upload(source_path)
                if not staged_rel_path:
                    return

                print(f"   📂 上传文件(相对 profile): {staged_rel_path}")
                self._upload_file_with_fallbacks(staged_rel_path, selector)
            
            elif action == "wait":
                seconds = params.get("seconds", 2)
                print(f"   ⏳ 等待 {seconds} 秒...")
                time.sleep(seconds)
            
            elif action == "screenshot":
                self._save_screenshot("ai_step")
            
            else:
                print(f"   ⚠️  未知操作: {action}")
        
        except Exception as e:
            print(f"   ❌ 操作失败: {e}")

    def _upload_file_with_fallbacks(self, rel_path: str, preferred_selector: str) -> bool:
        """尝试多种 selector 上传文件，并输出详细诊断信息"""
        selectors = []
        if preferred_selector:
            selectors.append(preferred_selector)
        selectors.extend([
            "input[type='file']",
            "input[type=file]",
            "[type='file']",
            "[type=file]"
        ])
        # 去重并保持顺序
        selectors = list(dict.fromkeys(selectors))

        for idx, sel in enumerate(selectors, 1):
            print(f"   🔎 尝试上传 selector[{idx}]: {sel}")
            try:
                response = self.pinchtab.session.post(
                    f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/upload",
                    json={
                        "paths": [rel_path],
                        "selector": sel
                    }
                )
            except Exception as e:
                print(f"   ❌ 上传请求异常: {e}")
                continue

            if response.status_code == 200:
                print(f"   ✅ 文件上传成功（selector: {sel}）")
                return True

            body_preview = response.text[:300].replace("\n", " ")
            print(f"   ❌ 上传失败: HTTP {response.status_code}（selector: {sel}）")
            if body_preview:
                print(f"   🧾 响应片段: {body_preview}")

        print("   ❌ 所有 selector 上传尝试均失败")
        return False

    def _dismiss_draft_dialog_if_present(self) -> bool:
        """检测并点击“放弃”以关闭未发布草稿弹层"""
        try:
            page_data = self.pinchtab.get_page_text()
            page_text = page_data.get("text", "")
            if "继续编辑" not in page_text and "放弃" not in page_text:
                return False

            print("   🧹 检测到草稿弹层，尝试点击“放弃”...")
            js_script = r"""
            (function () {
              const nodes = Array.from(document.querySelectorAll('button, a, span, div'));
              const target = nodes.find(el => {
                const text = (el.innerText || el.textContent || '').trim();
                return text === '放弃' || text.includes('放弃');
              });
              if (!target) return {ok:false, reason:'not_found'};
              target.click();
              return {ok:true};
            })();
            """
            response = self.pinchtab.session.post(
                f"{self.pinchtab.base_url}/tabs/{self.pinchtab.tab_id}/evaluate",
                json={"expression": js_script},
                timeout=10
            )
            if response.status_code != 200:
                print(f"   ⚠️  点击放弃失败: HTTP {response.status_code}")
                return False
            result = response.json().get("result", {})
            if isinstance(result, dict) and result.get("ok"):
                print("   ✅ 已尝试点击“放弃”")
                time.sleep(1.5)
                return True
            print(f"   ⚠️  未找到“放弃”按钮: {result}")
            return False
        except Exception as e:
            print(f"   ⚠️  草稿弹层处理异常: {e}")
            return False

    def _looks_like_publish_button_ref(self, ref: str) -> bool:
        """
        依据当前 snapshot 判断 ref 是否对应“发布/高清发布”按钮。
        """
        try:
            snapshot = self.pinchtab.get_snapshot()
            for node in snapshot.get("nodes", []):
                if node.get("ref") == ref:
                    name = (node.get("name") or "").strip()
                    return ("发布" in name) or ("高清发布" in name)
        except Exception:
            pass
        return False

    def _post_publish_stabilize(self):
        """
        发布后的固定兜底：等待 + 处理草稿弹层 + 必要时补点一次发布按钮。
        """
        print("   🛟 发布兜底：等待并检查页面状态...")
        time.sleep(5)
        self._dismiss_draft_dialog_if_present()

        try:
            snapshot = self.pinchtab.get_snapshot()
            publish_ref = None
            hd_publish_ref = None
            for node in snapshot.get("nodes", []):
                name = (node.get("name") or "").strip()
                role = (node.get("role") or "").lower()
                if role not in ("button", "link"):
                    continue
                if "高清发布" in name and not hd_publish_ref:
                    hd_publish_ref = node.get("ref")
                if name == "发布" and not publish_ref:
                    publish_ref = node.get("ref")

            # 优先普通发布，再兜底高清发布
            for candidate in [publish_ref, hd_publish_ref]:
                if not candidate:
                    continue
                self.pinchtab.click(candidate)
                print(f"   🛟 兜底点击发布按钮: {candidate}")
                time.sleep(4)
                self._dismiss_draft_dialog_if_present()
                break
        except Exception as e:
            print(f"   ⚠️  发布兜底阶段异常: {e}")

    def _stage_file_for_pinchtab_upload(self, source_path: Path) -> Optional[str]:
        """
        将文件复制到 PinchTab profile 的 .pinchtab-state/uploads 下，
        返回供 /upload 使用的相对路径（例如 uploads/xxx.mp4）。
        """
        profile_name = self.pinchtab.profile_name
        if not profile_name:
            print("   ❌ 缺少 PinchTab profile 信息，无法准备上传路径")
            return None

        pinchtab_state_dir = Path.home() / ".pinchtab" / "profiles" / profile_name / ".pinchtab-state"
        uploads_dir = pinchtab_state_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"{timestamp}_{source_path.name}"
        target_path = uploads_dir / safe_name

        try:
            shutil.copy2(source_path, target_path)
        except Exception as e:
            print(f"   ❌ 复制视频到 PinchTab 工作目录失败: {e}")
            return None

        print(f"   📦 已同步到 PinchTab 工作目录: {target_path}")
        return f"uploads/{safe_name}"
    
    def _add_message(self, role: str, content: str):
        """添加消息到对话历史"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def _save_conversation(self):
        """保存对话历史"""
        if self.conversation_file:
            with open(self.conversation_file, 'w', encoding='utf-8') as f:
                json.dump(self.conversation_history, f, indent=2, ensure_ascii=False)
    
    def _save_screenshot(self, prefix: str) -> Optional[Path]:
        """保存截图"""
        try:
            import base64
            
            screenshot_base64 = self.pinchtab.screenshot()
            if not screenshot_base64:
                return None
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_file = Path(f"data/screenshots/{prefix}_{timestamp}.png")
            screenshot_file.parent.mkdir(parents=True, exist_ok=True)
            
            image_data = base64.b64decode(screenshot_base64)
            with open(screenshot_file, 'wb') as f:
                f.write(image_data)
            
            print(f"   ✅ 截图: {screenshot_file}")
            return screenshot_file
            
        except Exception as e:
            print(f"   ⚠️  截图失败: {e}")
            return None
    
    def _verify_upload_success(self, video_filename: str) -> bool:
        """
        验证视频是否真的发布成功
        
        方法：导航到作品列表，检查是否有新作品
        
        Args:
            video_filename: 视频文件名（用于日志）
        
        Returns:
            bool: 是否确认发布成功
        """
        try:
            print("   📋 导航到作品列表...")
            
            # 导航到内容管理页面
            content_url = "https://creator.douyin.com/creator-micro/content/manage"
            if not self.pinchtab.navigate(content_url, wait_seconds=5):
                print("   ⚠️  无法导航到作品列表")
                return False
            
            # 等待页面加载
            time.sleep(3)
            
            # 获取页面文本
            page_data = self.pinchtab.get_page_text()
            page_text = page_data.get("text", "")
            
            # 截图保存
            self._save_screenshot("verify_works")
            
            # 检查是否有作品
            # 如果页面包含"暂无内容"或"还没有作品"，说明没有发布成功
            if "暂无内容" in page_text or "还没有作品" in page_text or "暂无作品" in page_text:
                print("   ❌ 作品列表为空，发布可能失败")
                return False
            
            # 检查是否有视频相关的元素
            snapshot = self.pinchtab.get_snapshot()
            nodes = snapshot.get("nodes", [])
            
            # 统计视频相关元素
            video_count = 0
            for node in nodes:
                name = node.get("name", "").lower()
                role = node.get("role", "").lower()
                
                # 查找视频、作品、播放等关键词
                if any(keyword in name for keyword in ["视频", "作品", "播放", "点赞", "评论"]):
                    video_count += 1
            
            print(f"   📊 检测到 {video_count} 个视频相关元素")
            
            if video_count > 5:  # 如果有足够多的视频相关元素，说明有作品
                print("   ✅ 作品列表中有内容")
                return True
            else:
                print("   ⚠️  作品列表中内容较少，无法确认")
                return False
                
        except Exception as e:
            print(f"   ❌ 验证失败: {e}")
            return False
    
    def batch_upload(self, video_dir: Path, title_prefix: str = "") -> dict:
        """批量上传视频"""
        print("\n" + "="*70)
        print("批量视频上传 - AI 驱动")
        print("="*70)
        
        video_files = list(video_dir.glob("*.mp4"))
        
        if not video_files:
            print(f"❌ 目录中没有视频文件: {video_dir}")
            return {"total": 0, "success": 0, "failed": 0}
        
        print(f"\n📹 找到 {len(video_files)} 个视频文件")
        
        stats = {
            "total": len(video_files),
            "success": 0,
            "failed": 0,
            "files": []
        }
        
        for i, video_path in enumerate(video_files, 1):
            print(f"\n{'='*70}")
            print(f"上传进度: {i}/{len(video_files)}")
            print(f"{'='*70}")
            
            title = f"{title_prefix}{video_path.stem}" if title_prefix else video_path.stem
            
            success = self.upload_video(video_path, title=title)
            
            if success:
                stats["success"] += 1
                stats["files"].append({"file": video_path.name, "status": "success"})
            else:
                stats["failed"] += 1
                stats["files"].append({"file": video_path.name, "status": "failed"})
            
            if i < len(video_files):
                print(f"\n⏳ 等待 30 秒后上传下一个...")
                time.sleep(30)
        
        print(f"\n{'='*70}")
        print("上传完成")
        print(f"{'='*70}")
        print(f"总数: {stats['total']}")
        print(f"成功: {stats['success']}")
        print(f"失败: {stats['failed']}")
        
        return stats
