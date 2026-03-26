"""
AI 决策引擎 - 系统的"大脑"

负责感知、分析、决策、验证
"""

import json
import base64
from typing import Dict, Any, Optional
from openai import OpenAI


class AIPlanner:
    """AI 决策引擎"""

    def __init__(self, deepseek_api_key: str = None):
        if not deepseek_api_key:
            import os
            deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

        if deepseek_api_key:
            self.deepseek = OpenAI(
                api_key=deepseek_api_key,
                base_url="https://api.deepseek.com"
            )
        else:
            raise ValueError("DEEPSEEK_API_KEY 未配置")

        self.task_goal = ""
        self.context = []
        self.max_context_turns = 10

    def set_task_goal(self, goal: str):
        """设置任务目标"""
        self.task_goal = goal
        self._reset_context()

    def _reset_context(self):
        """重置对话上下文"""
        self.context = []

    def _add_to_context(self, role: str, content: str):
        """添加消息到上下文"""
        self.context.append({
            "role": role,
            "content": content
        })

        # 限制上下文长度
        if len(self.context) > self.max_context_turns * 2:
            # 保留系统消息和最近的消息
            self.context = [self.context[0]] + self.context[-(self.max_context_turns * 2 - 1):]

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return f"""你是抖音自动化操作的 AI 智能体，任务是：{self.task_goal}

你的职责：
1. 感知页面状态（URL、标题、文本、元素）
2. 分析当前情况
3. 决策下一步操作
4. 验证操作结果
5. 处理异常和错误

操作类型：
- navigate: 导航到指定 URL
- search_element: 搜索页面上的元素（返回元素的 ref）
- click: 点击元素（method 可选：smart_click, evaluate_js, direct）
- scroll: 滚动页面（direction: up/down, amount: 像素数）
- wait: 等待页面加载（seconds: 秒数）
- refresh: 刷新当前页面（使用 JavaScript location.reload()）
- extract_data: 提取页面数据（type: user_list/work_list/etc, schema: 数据结构）
- verify_result: 验证操作结果（check: 验证内容）
- complete: 任务完成（result: 最终结果）
- fallback: 使用降级方案
    - strategy="navigate_home": 导航回主页，params 包含 "url"
    - strategy="extract_from_text": 从文本中提取数据，params 包含 "target_text", "context_length"

决策原则：
1. 优先使用最可靠的方法
2. 失败后分析原因，智能选择重试策略
3. 始终验证操作结果（特别是 URL 变化）
4. 记录清晰的思考过程
5. 确保数据质量，不在错误的页面提取数据
6. 点击操作后必须验证 URL 是否正确跳转
7. 提取数据前必须确认页面类型正确
8. 如果页面状态异常（URL为空、标题为空、文本为空），优先尝试 refresh 而不是重新导航
9. refresh 后仍然异常，才考虑重新导航到目标 URL
10. 不要使用 execute_script 或其他未列出的操作类型，只使用上述支持的操作
11. **搜索元素失败时的策略**：
    - 第一次搜索失败：尝试滚动页面到目标区域，然后重新搜索
    - 第二次搜索失败：尝试直接 navigate 到目标 URL（如 /fan、/followers、/follow）
    - 第三次搜索失败：使用 fallback 方案或报告失败
12. **抖音用户主页导航规律**：
    - 粉丝列表：https://www.douyin.com/fan 或通过点击"粉丝"按钮获取
    - 关注列表：https://www.douyin.com/follow 或通过点击"关注"按钮获取
    - 作品列表：https://www.douyin.com/user/self/video 或直接在主页点击作品标签
    - **重要**: 不要导航到 /user/self/follow 或 /user/self/fan，这些 URL 不存在！直接从主页点击对应按钮即可。
    - 搜索按钮/元素失败时，优先使用直接导航而不是继续搜索

返回格式（必须是有效的 JSON）：
{{
  "thought": "思考过程（当前情况、为什么选择这个操作）",
  "action": "操作类型",
  "params": {{"参数": "值"}},
  "expected_result": "期望看到什么结果",
  "next_condition": "成功后应该满足的条件"
}}

重要规则：
- 如果点击关注按钮后，URL 必须包含 /follow，否则需要重试
- 如果点击粉丝按钮后，URL 必须包含 /fan 或 /followers，否则需要重试
- 如果点击作品标签后，页面应该显示作品列表
- 不在正确的页面时不要提取数据，应该先导航或重试
- 连续失败 3 次后应该考虑使用 fallback 或 complete"""

    def plan_next_action(self, page_state: Dict[str, Any]) -> Dict[str, Any]:
        """根据页面状态规划下一步操作"""

        # 检测页面状态异常
        if self._is_page_state_broken(page_state):
            print("  ⚠️  检测到页面状态异常，尝试快速恢复")
            return {
                "thought": "页面状态异常（URL为空或页面未加载），先尝试刷新页面恢复",
                "action": "refresh",
                "params": {},
                "expected_result": "页面刷新后恢复正常",
                "next_condition": "URL 和标题恢复正常"
            }

        # 分析历史，检测连续搜索失败
        if self.context:
            last_actions = self._extract_recent_actions(3)
            search_failures = [a for a in last_actions if a.get("action") == "search_element"]

            # 如果连续2次搜索失败，自动建议 navigate
            if len(search_failures) >= 2:
                print("  💡 检测到连续搜索失败，尝试直接导航")
                suggested_url = self._suggest_url_from_task()
                if suggested_url:
                    return {
                        "thought": f"连续{len(search_failures)}次搜索元素失败，使用直接导航到目标页面：{suggested_url}",
                        "action": "navigate",
                        "params": {"url": suggested_url},
                        "expected_result": "直接导航到目标页面",
                        "next_condition": "URL 包含目标路径"
                    }

        # 构建用户消息
        user_message = self._build_state_message(page_state)
        self._add_to_context("user", user_message)

        # 第一次调用添加系统提示
        if len(self.context) == 1:
            system_prompt = self._build_system_prompt()
            self._add_to_context("system", system_prompt)

        # 调用 DeepSeek
        try:
            response = self.deepseek.chat.completions.create(
                model="deepseek-chat",
                messages=self.context,
                temperature=0.3,  # 降低温度以获得更稳定的决策
                max_tokens=1500
            )

            ai_response = response.choices[0].message.content.strip()

            # 提取 JSON
            json_str = self._extract_json_from_response(ai_response)
            action = json.loads(json_str)

            self._add_to_context("assistant", ai_response)

            print(f"  💭 AI 思考: {action.get('thought', 'N/A')}")
            print(f"  🎯 AI 决策: {action.get('action', 'N/A')}")
            print(f"  📋 参数: {action.get('params', {})}")

            return action

        except Exception as e:
            print(f"  ❌ AI 决策失败: {e}")
            # 返回降级操作
            return {
                "thought": "AI 决策失败，使用安全降级",
                "action": "wait",
                "params": {"seconds": 2},
                "expected_result": "等待后重试",
                "next_condition": "页面稳定"
            }

    def verify_action_result(
        self,
        action: Dict[str, Any],
        result: Dict[str, Any],
        new_page_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """验证操作结果，决定下一步"""

        # 构建验证消息
        verify_message = f"""验证操作结果：

执行的操作：
{json.dumps(action, indent=2, ensure_ascii=False)}

执行结果：
{json.dumps(result, indent=2, ensure_ascii=False)}

执行后页面状态：
URL: {new_page_state.get('url', 'N/A')}
标题: {new_page_state.get('title', 'N/A')}
文本长度: {len(new_page_state.get('text', ''))} 字符

请验证：
1. 操作是否成功？
2. 是否达到了期望结果？
3. 下一步应该做什么？（next_action: continue/retry/fallback/complete）
4. 如果失败，失败原因是什么？（reason）

重要：如果是 extract_data 操作，检查结果中是否包含 users 或 works 数组：
- 如果用户数据已提取（result.users 存在且不为空），设置 next_action = "complete"，并在 result 字段中返回完整的用户列表
- 如果作品数据已提取（result.works 存在且不为空），设置 next_action = "complete"，并在 result 字段中返回完整的作品列表
- 如果数据为空或不完整，设置 next_action = "retry"

返回格式：
{{
  "success": true/false,
  "reason": "原因说明",
  "next_action": "continue/retry/fallback/complete",
  "confidence": 0.0-1.0,
  "result": {{"users": [...]}} 或 {{"works": [...]}} （仅在 complete 时包含）
}}"""

        self._add_to_context("user", verify_message)

        # 调用 DeepSeek 验证
        try:
            response = self.deepseek.chat.completions.create(
                model="deepseek-chat",
                messages=self.context,
                temperature=0.2,
                max_tokens=500
            )

            ai_response = response.choices[0].message.content.strip()

            # 提取 JSON
            json_str = self._extract_json_from_response(ai_response)
            verification = json.loads(json_str)

            self._add_to_context("assistant", ai_response)

            print(f"  ✓ 验证: {verification.get('success', False)}")
            print(f"  📊 置信度: {verification.get('confidence', 0)}")
            print(f"  ➡️  下一步: {verification.get('next_action', 'N/A')}")

            return verification

        except Exception as e:
            print(f"  ❌ 验证失败: {e}")
            # 简单降级验证
            return {
                "success": result.get("success", False),
                "reason": "验证异常，依赖执行结果",
                "next_action": "continue" if result.get("success") else "retry",
                "confidence": 0.5
            }

    def _is_page_state_broken(self, page_state: Dict[str, Any]) -> bool:
        """检测页面状态是否异常"""
        url = page_state.get("url", "")
        title = page_state.get("title", "")
        text = page_state.get("text", "")
        elements = page_state.get("elements", [])

        # 如果 URL、标题、文本都为空，且没有元素，说明页面异常
        if not url and not title and not text and not elements:
            return True

        return False

    def _extract_recent_actions(self, count: int = 3) -> list:
        """从上下文中提取最近的操作"""
        recent_actions = []
        # 只看 assistant 的消息
        for msg in reversed(self.context):
            if msg.get("role") == "assistant":
                try:
                    action = json.loads(self._extract_json_from_response(msg.get("content", "{}")))
                    recent_actions.append(action)
                    if len(recent_actions) >= count:
                        break
                except:
                    pass
        return recent_actions

    def _suggest_url_from_task(self) -> Optional[str]:
        """根据任务目标建议目标 URL"""
        task_lower = self.task_goal.lower()

        if "粉丝" in task_lower or "fan" in task_lower or "followers" in task_lower:
            return "https://www.douyin.com/user/self/fan"
        elif "关注" in task_lower or "follow" in task_lower:
            return "https://www.douyin.com/user/self/follow"
        elif "作品" in task_lower or "video" in task_lower or "work" in task_lower:
            return "https://www.douyin.com/user/self/video"
        else:
            return None

    def _build_state_message(self, page_state: Dict[str, Any]) -> str:
        """构建页面状态消息"""
        elements_preview = page_state.get("elements", [])[:15]

        elements_json = json.dumps(elements_preview, indent=2, ensure_ascii=False)
        # 限制长度
        if len(elements_json) > 1500:
            elements_json = elements_json[:1500] + "...（已截断）"

        text_preview = page_state.get("text", "")[:800]

        return f"""当前页面状态：

URL: {page_state.get('url', 'N/A')}
标题: {page_state.get('title', 'N/A')}

可交互元素（前 15 个）：
{elements_json}

页面文本（前 800 字符）：
{text_preview}

请分析当前页面状态，决定下一步操作。"""

    def _extract_json_from_response(self, response: str) -> str:
        """从 AI 响应中提取 JSON"""
        # 尝试提取 ```json ``` 代码块
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0].strip()
        else:
            # 尝试找到第一个 { 和最后一个 }
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end > start:
                json_str = response[start:end]
            else:
                json_str = response

        return json_str
