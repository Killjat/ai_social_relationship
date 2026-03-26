"""
任务循环控制器 - 协调 AI 和 PinchTab

负责初始化任务、循环执行、处理异常、记录历史、判断完成
"""

import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .ai_planner import AIPlanner
from .action_executor import ActionExecutor


class TaskOrchestrator:
    """任务循环控制器"""

    def __init__(self, ai_planner: AIPlanner, executor: ActionExecutor):
        self.ai = ai_planner
        self.executor = executor

        self.max_iterations = 20
        self.retry_count = 0
        self.max_retries = 3

        self.history = []
        self.session_dir = Path("data/sessions")
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.current_session_id = None
        self._init_session()

    def _init_session(self):
        """初始化会话"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_session_id = f"session_{timestamp}"
        self.session_file = self.session_dir / f"{self.current_session_id}.json"

    def execute_task(self, task: str, initial_url: str = "https://www.douyin.com/user/self") -> Dict[str, Any]:
        """
        执行完整的任务

        流程：
        1. 设置任务目标
        2. 初始化页面
        3. 进入循环：感知 -> 决策 -> 执行 -> 验证
        4. 返回结果
        """
        print("\n" + "="*70)
        print(f"🚀 开始执行任务: {task}")
        print("="*70)

        # 1. 设置目标
        self.ai.set_task_goal(task)

        # 2. 初始化页面
        print(f"\n📍 初始化页面，导航到: {initial_url}")
        init_result = self.executor.execute({
            "action": "navigate",
            "params": {"url": initial_url}
        })

        if not init_result.get("success"):
            return self._build_failure_result("初始化失败", init_result)

        time.sleep(2)  # 等待页面加载

        # 3. 任务循环
        print(f"\n🔄 进入任务循环（最多 {self.max_iterations} 轮）")
        print("-"*70)

        for iteration in range(self.max_iterations):
            print(f"\n{'='*70}")
            print(f"第 {iteration + 1}/{self.max_iterations} 轮")
            print(f"{'='*70}")

            # 3a. 感知：获取页面状态
            page_state = self.executor.get_page_state()
            print(f"👁️  当前 URL: {page_state.get('url', 'N/A')}")

            # 3b. 决策：AI 规划下一步
            action = self.ai.plan_next_action(page_state)

            # 检查是否任务完成
            if action.get("action") == "complete":
                print("\n" + "="*70)
                print("✅ AI 判断任务完成")
                print("="*70)
                return self._build_success_result(
                    action.get("params", {}).get("result", {}),
                    self.history
                )

            # 3c. 执行：PinchTab 执行操作
            print(f"\n执行 AI 决策的操作...")
            result = self.executor.execute(action)

            # 特殊处理：如果是 refresh 操作，需要等待更长时间
            if action.get("action") == "refresh":
                time.sleep(3)  # 等待刷新完成
                # 验证刷新后页面是否恢复
                new_state = self.executor.get_page_state()
                if self.ai._is_page_state_broken(new_state):
                    print("  ⚠️  刷新后页面仍然异常，尝试重新导航")
                    # 强制导航到初始URL
                    nav_result = self.executor.execute({
                        "action": "navigate",
                        "params": {"url": initial_url}
                    })
                    if nav_result.get("success"):
                        time.sleep(2)

            # 3d. 获取新页面状态
            new_page_state = self.executor.get_page_state()

            # 3d-1. 快速检测页面异常（在 AI 验证之前）
            if self.ai._is_page_state_broken(new_page_state):
                print("  ⚠️  检测到页面状态异常，自动执行 refresh")
                # 自动执行 refresh
                refresh_result = self.executor.execute({
                    "action": "refresh",
                    "params": {}
                })

                # 等待刷新完成
                time.sleep(3)

                # 验证刷新是否成功
                new_page_state = self.executor.get_page_state()
                if self.ai._is_page_state_broken(new_page_state):
                    print("  ⚠️  刷新后仍然异常，尝试重新导航")
                    nav_result = self.executor.execute({
                        "action": "navigate",
                        "params": {"url": initial_url}
                    })
                    if nav_result.get("success"):
                        time.sleep(2)
                        new_page_state = self.executor.get_page_state()

            # 3e. 验证：AI 验证结果
            print(f"\nAI 验证操作结果...")
            verification = self.ai.verify_action_result(action, result, new_page_state)

            # 3f. 记录历史
            step_record = {
                "iteration": iteration,
                "page_state": {
                    "url": page_state.get("url"),
                    "title": page_state.get("title")
                },
                "action": action,
                "result": {
                    "success": result.get("success"),
                    "error": result.get("error"),
                    "execution_time": result.get("execution_time"),
                    "url_changed": result.get("evidence", {}).get("url_changed", False)
                },
                "new_page_state": {
                    "url": new_page_state.get("url"),
                    "title": new_page_state.get("title")
                },
                "verification": verification
            }
            self.history.append(step_record)

            # 3g. 处理验证结果
            next_action = verification.get("next_action", "continue")

            # 检测连续失败
            if not verification.get("success", False):
                self.retry_count += 1
                print(f"  🔄 失败计数: {self.retry_count}/{self.max_retries}")

                if self.retry_count >= self.max_retries:
                    print("\n" + "="*70)
                    print("❌ 重试次数超限，任务失败")
                    print("="*70)
                    return self._build_failure_result(
                        f"重试次数超限: {verification.get('reason', '未知原因')}",
                        self.history
                    )
            else:
                # 成功后重置计数
                self.retry_count = 0

            if next_action == "complete":
                print("\n" + "="*70)
                print("✅ 验证通过，任务完成")
                print("="*70)
                return self._build_success_result(
                    verification.get("result", {}),
                    self.history
                )

            elif next_action == "retry":
                self.retry_count += 1
                if self.retry_count >= self.max_retries:
                    print(f"\n❌ 重试次数已达上限 ({self.max_retries})")
                    return self._build_failure_result(
                        f"重试次数超限: {verification.get('reason', '')}",
                        self.history
                    )
                print(f"⚠️  需要重试 ({self.retry_count}/{self.max_retries}): {verification.get('reason')}")
                time.sleep(2)
                continue

            elif next_action == "fallback":
                print(f"⚠️  使用降级方案: {verification.get('reason')}")
                # 降级方案处理
                fallback_result = self._handle_fallback(action, result, verification)
                if fallback_result.get("success"):
                    self.retry_count = 0  # 重置重试计数
                else:
                    self.retry_count += 1
                time.sleep(1)
                continue

            elif next_action == "continue":
                self.retry_count = 0  # 重置重试计数
                time.sleep(1)
                continue

            else:
                print(f"⚠️  未知的下一步指令: {next_action}")
                continue

        # 超过最大迭代次数
        print(f"\n⏱️  达到最大迭代次数 ({self.max_iterations})")
        return self._build_timeout_result(self.history)

    def _handle_fallback(self, action: Dict[str, Any], result: Dict[str, Any], verification: Dict[str, Any]) -> Dict[str, Any]:
        """处理降级方案"""
        action_type = action.get("action")

        print(f"  🔧 降级处理: {action_type}")

        if action_type == "click":
            # 点击失败的降级：尝试其他点击方法
            current_method = action.get("params", {}).get("method", "smart_click")

            if current_method == "smart_click":
                # 尝试 evaluate_js
                print(f"    尝试 evaluate_js 方法...")
                new_action = action.copy()
                new_action["params"]["method"] = "evaluate_js"
                result = self.executor.execute(new_action)
                if result.get("success"):
                    print(f"    ✅ evaluate_js 成功")
                    return {"success": True}

            if current_method == "evaluate_js":
                # 尝试直接 JavaScript 搜索点击
                print(f"    尝试直接 JavaScript 搜索...")
                target_name = action.get("params", {}).get("name", "")
                js_code = f"""
                (function() {{
                    const elements = Array.from(document.querySelectorAll('*'));
                    for (const el of elements) {{
                        if (el.textContent.includes('{target_name}') &&
                            (el.tagName === 'A' || el.tagName === 'BUTTON' || el.role === 'link' || el.onclick)) {{
                            el.click();
                            return 'clicked';
                        }}
                    }}
                    return 'not_found';
                }})();
                """
                try:
                    response = self.executor.pinchtab.session.post(
                        f"{self.executor.pinchtab.base_url}/tabs/{self.executor.pinchtab.tab_id}/evaluate",
                        json={"expression": js_code},
                        timeout=10
                    )
                    if response.status_code == 200 and response.json().get("result") == "clicked":
                        print(f"    ✅ JavaScript 点击成功")
                        return {"success": True}
                except:
                    pass

            return {"success": False, "error": "所有降级方案均失败"}

        else:
            return {"success": False, "error": f"无降级方案: {action_type}"}

    def _build_success_result(self, final_result: Dict[str, Any], history: list) -> Dict[str, Any]:
        """构建成功结果"""
        result = {
            "success": True,
            "message": "任务执行成功",
            "result": final_result,
            "total_iterations": len(history),
            "total_time": sum(
                step.get("result", {}).get("execution_time", 0)
                for step in history
            ),
            "history": history
        }

        # 保存会话
        self._save_session(result)

        return result

    def _build_failure_result(self, reason: str, history_or_result) -> Dict[str, Any]:
        """构建失败结果"""
        history = history_or_result if isinstance(history_or_result, list) else []

        result = {
            "success": False,
            "message": "任务执行失败",
            "error": reason,
            "total_iterations": len(history),
            "history": history
        }

        # 保存会话
        self._save_session(result)

        return result

    def _build_timeout_result(self, history: list) -> Dict[str, Any]:
        """构建超时结果"""
        result = {
            "success": False,
            "message": "任务执行超时",
            "error": "达到最大迭代次数",
            "total_iterations": len(history),
            "history": history
        }

        # 保存会话
        self._save_session(result)

        return result

    def _save_session(self, result: Dict[str, Any]):
        """保存会话历史"""
        try:
            session_data = {
                "session_id": self.current_session_id,
                "task": self.ai.task_goal,
                "result": result,
                "timestamp": datetime.now().isoformat()
            }

            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)

            print(f"💾 会话已保存: {self.session_file}")
        except Exception as e:
            print(f"⚠️  保存会话失败: {e}")
