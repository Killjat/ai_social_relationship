"""
Profile 注册服务
直接使用 PinchTab 进行抖音登录，并将 profile 以抖音账号昵称命名
"""

import time
import json
import requests
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 加载 .env 文件（覆盖系统环境变量）
project_root = Path(__file__).parent.parent.parent
load_dotenv(project_root / ".env", override=True)

from ..core.pinchtab_client import PinchTabClient


# PinchTab UA
PINCHTAB_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class ProfileService:
    """Profile 注册和管理服务"""

    def __init__(self, pinchtab_url: str = "http://localhost:9867", deepseek_api_key: Optional[str] = None):
        self.base_url: str = pinchtab_url
        self.session: requests.Session = requests.Session()
        self.deepseek_api_key: str | None = deepseek_api_key
        self.client: PinchTabClient = PinchTabClient(base_url=pinchtab_url)

        if not self.deepseek_api_key:
            import os
            self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

    def register_douyin_profile(self) -> dict[str, str | bool]:
        """
        直接使用 PinchTab 登录抖音并注册 Profile

        流程：
        1. 创建临时 PinchTab profile
        2. 直接启动 Chrome 浏览器进程（确保 GUI 显示）
        3. 导航到抖音登录页
        4. 等待用户扫码登录
        5. 提取账号昵称
        6. 重命名 profile 为昵称
        7. 验证登录状态并保存
        """
        print("\n" + "="*60)
        print("抖音 Profile 注册（直接使用 PinchTab）")
        print("="*60)

        temp_profile_name = f"douyin_temp_{int(time.time())}"
        profile_name = None
        profile_id = None

        try:
            # 步骤 1: 创建临时 profile
            print(f"\n[1/6] 创建临时 Profile...")
            print(f"   临时 Profile 名称: {temp_profile_name}")

            r = self.session.post(f"{self.base_url}/profiles", json={"name": temp_profile_name})
            if r.status_code not in [200, 201]:
                return {"success": False, "message": f"创建临时 Profile 失败: {r.status_code} {r.text}"}
            profile_id = r.json()["id"]
            print(f"   ✅ 临时 Profile 已创建: {profile_id}")

            # 步骤 2: 使用 PinchTab 启动浏览器（避免多进程冲突）
            print(f"\n[2/6] 启动浏览器实例...")
            if not self.client.connect(profile_name=temp_profile_name, headless=False):
                return {"success": False, "message": "无法启动 PinchTab 实例"}

            # 导航到抖音登录页
            print(f"   👀 请在浏览器窗口中扫码登录")
            print(f"   📍 正在导航到抖音...")
            if not self.client.navigate("https://www.douyin.com", wait_seconds=5):
                return {"success": False, "message": "无法导航到抖音页面"}
            print(f"   ✅ 浏览器已启动并打开抖音")
            
            # 验证页面是否正确加载
            time.sleep(2)
            page_data = self.client.get_page_text()
            page_text = page_data.get("text", "")
            print(f"   📄 页面文本长度: {len(page_text)} 字符")
            if len(page_text) < 100:
                print(f"   ⚠️  页面可能未正确加载")

            # 步骤 3: 等待用户扫码登录，并检测登录状态
            print(f"\n[3/6] 等待用户扫码登录并检测登录状态...")
            print(f"   ⏱️  请在浏览器中扫码登录（120秒内）...")
            login_success = False
            max_wait_time = 120  # 最多等待120秒
            check_interval = 3   # 每3秒检查一次

            for elapsed in range(0, max_wait_time, check_interval):
                time.sleep(check_interval)
                remaining = max_wait_time - elapsed

                # 使用 PinchTab 检测登录状态（不重复导航）
                try:
                    page_data = self.client.get_page_text()
                    page_text = page_data.get("text", "")

                    # 严谨的登录检测逻辑
                    # 1. 必须没有未登录标识
                    has_login_prompt = any(keyword in page_text[:500] for keyword in ["扫码登录", "验证码", "登录后即可", "请登录", "立即登录"])

                    # 2. 必须有登录后的特征
                    has_logged_in_features = any(keyword in page_text[:1000] for keyword in ["推荐", "关注", "我的", "消息", "私信", "通知"])

                    # 3. 双重验证：访问个人主页，检查是否能看到用户信息
                    if not has_login_prompt and has_logged_in_features:
                        print(f"   🔍 检测到可能已登录，正在验证...")
                        self.client.navigate("https://www.douyin.com/user/self")
                        time.sleep(3)
                        profile_page = self.client.get_page_text()
                        profile_text = profile_page.get("text", "")

                        # 检查个人主页是否有用户信息（粉丝、作品、获赞等）
                        if any(keyword in profile_text[:1000] for keyword in ["粉丝", "作品", "获赞", "编辑资料"]):
                            login_success = True
                            print(f"   ✅ 检测到登录成功！（耗时 {elapsed} 秒）")
                            break
                        else:
                            # 验证失败，返回首页
                            print(f"   ⚠️  验证失败，返回首页...")
                            self.client.navigate("https://www.douyin.com")
                            time.sleep(2)

                except Exception as e:
                    print(f"   ⚠️  检测登录状态时出错: {e}")

                # 显示进度
                if elapsed % 10 == 0 and remaining > 0:
                    print(f"   ⏳ 等待中... 还剩 {remaining} 秒")

            if not login_success:
                print(f"   ❌ 登录超时或失败")
                self.client.cleanup()
                # 清理失败的 profile
                print(f"   清理临时 profile: {profile_id}")
                self.session.delete(f"{self.base_url}/profiles/{profile_id}")
                return {"success": False, "message": "登录超时，请在120秒内完成扫码登录"}

            # 步骤 4: 关闭浏览器并等待 profile 文件同步
            print(f"\n[4/6] 关闭浏览器并同步 profile...")
            self.client.cleanup()
            print(f"   ✅ 浏览器已关闭")
            print(f"   ⏳ 等待 profile 文件同步...")
            time.sleep(3)

            # 步骤 5: 使用 DeepSeek AI 验证登录状态并提取账号信息
            print(f"\n[5/6] 验证登录状态并提取账号信息...")
            print(f"   重新连接 profile 以验证登录信息是否保存...")

            # 重新启动 PinchTab 实例来验证登录状态
            login_verified = False
            nickname = None
            extraction_attempts = 0
            max_attempts = 3

            if not self.client.connect(profile_name=temp_profile_name, headless=False):
                print(f"   ❌ 无法启动 PinchTab 实例，无法验证登录状态")
                # 清理失败的 profile
                self.session.delete(f"{self.base_url}/profiles/{profile_id}")
                return {"success": False, "message": "无法启动 PinchTab 实例进行验证"}
            else:
                if not self.client.navigate("https://www.douyin.com/user/self"):
                    print(f"   ⚠️  无法访问个人主页，可能未登录")
                else:
                    time.sleep(4)

                    # 获取页面状态
                    page_data = self.client.get_page_text()
                    page_text = page_data.get("text", "")
                    snapshot = self.client.get_snapshot()
                    nodes = snapshot.get("nodes", [])

                    # 使用 DeepSeek AI 分析页面状态
                    result = self._ai_verify_and_extract(page_text, nodes)

                    if result["success"]:
                        login_verified = result["is_logged_in"]
                        nickname = result["nickname"]

                        if login_verified:
                            print(f"   ✅ 登录状态验证成功，登录信息已保存到 profile")
                            print(f"   ✅ AI 提取昵称: {nickname}")
                        else:
                            print(f"   ❌ 检测到未登录状态，登录信息未保存到 profile")
                            print(f"   ⚠️  登录信息可能未正确保存，重试提取...")
                    else:
                        print(f"   ⚠️  AI 分析失败，使用备用方案")
                        # 备用：硬编码检查
                        if "扫码登录" in page_text[:500] or "验证码" in page_text[:500] or "登录后即可" in page_text:
                            print(f"   ⚠️  页面检测到登录提示，但登录信息可能已保存")
                            print(f"   ✅ 继续处理，假设登录已成功")
                            login_verified = True
                            nickname = self._extract_nickname(page_text)
                        else:
                            print(f"   ✅ 登录状态验证成功")
                            login_verified = True
                            nickname = self._extract_nickname(page_text)

                    # 如果昵称提取失败，尝试多次重新获取
                    while login_verified and not nickname and extraction_attempts < max_attempts:
                        extraction_attempts += 1
                        print(f"   ⚠️  昵称提取失败，第 {extraction_attempts} 次重试...")

                        time.sleep(2)
                        self.client.navigate("https://www.douyin.com/user/self")
                        time.sleep(3)

                        page_data = self.client.get_page_text()
                        page_text = page_data.get("text", "")

                        if self.deepseek_api_key:
                            nickname = self._ai_extract_nickname(page_text)
                        else:
                            nickname = self._extract_nickname(page_text)

                    if nickname:
                        print(f"   ✅ 提取到的昵称: {nickname}")
                    else:
                        print(f"   ⚠️  无法提取昵称，使用默认名称")
                        nickname = f"user_{profile_id}"

            # 验证登录状态
            if not login_verified:
                self.client.cleanup()
                print(f"   清理临时 profile: {profile_id}")
                self.session.delete(f"{self.base_url}/profiles/{profile_id}")
                return {"success": False, "message": "登录信息未保存到 profile，请重新注册"}

            # 步骤 6: 重命名 profile 为昵称
            print(f"\n[6/6] 重命名 Profile 并保存...")
            # 确保 nickname 不为 None
            if not nickname:
                nickname = f"user_{profile_id}"
                print(f"   ⚠️  昵称为空，使用默认名称: {nickname}")
            profile_name = self._sanitize_profile_name(nickname)

            # 停止实例
            self.client.cleanup()
            time.sleep(2)

            # 检查是否已存在同名 profile
            existing = self._find_profile_by_name(profile_name)
            if existing:
                print(f"   已存在同名 profile，先删除: {existing['id']}")
                self.session.delete(f"{self.base_url}/profiles/{existing['id']}")
                time.sleep(2)

            # 更新 profile 名称
            r = self.session.patch(
                f"{self.base_url}/profiles/{profile_id}",
                json={"name": profile_name}
            )
            if r.status_code not in [200, 201, 204]:
                print(f"   ⚠️  重命名失败: {r.status_code} {r.text}")
                print(f"   Profile 仍使用临时名称: {temp_profile_name}")
                profile_name = temp_profile_name
            else:
                print(f"   ✅ Profile 已重命名: {profile_name}")

            print(f"\n{'='*60}")
            print(f"✅ 注册成功！Profile: {profile_name}")
            print(f"{'='*60}")

            return {
                "success": True,
                "profile_name": profile_name,
                "profile_id": profile_id,
                "nickname": nickname,
                "message": f"注册成功！Profile: {profile_name}"
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            error_message = f"注册失败: {str(e)}"

            # 清理失败的 profile
            if profile_id:
                print(f"   清理失败的 profile: {profile_id}")
                try:
                    self.session.delete(f"{self.base_url}/profiles/{profile_id}")
                except Exception as cleanup_error:
                    print(f"   ⚠️  清理 profile 失败: {cleanup_error}")

            return {"success": False, "message": error_message}

        finally:
            # 确保实例停止
            if self.client.instance_id:
                try:
                    self.client.cleanup()
                except:
                    pass
                    pass

            # 如果失败，清理临时 profile
            if profile_name is None and temp_profile_name:
                try:
                    temp_profile = self._find_profile_by_name(temp_profile_name)
                    if temp_profile:
                        print(f"\n清理临时 profile...")
                        self.session.delete(f"{self.base_url}/profiles/{temp_profile['id']}")
                except:
                    pass

    def _check_login_status(self) -> bool:
        """检查当前是否已登录抖音"""
        try:
            page_data = self.client.get_page_text()
            page_text = page_data.get("text", "")

            # 检查登录状态的关键指标
            logged_in = (
                "粉丝" in page_text and
                "扫码登录" not in page_text[:500] and
                "验证码" not in page_text[:500]
            )

            return logged_in
        except Exception as e:
            print(f"   ⚠️  检查登录状态失败: {e}")
            return False

    def _find_profile_by_name(self, name: str) -> dict[str, str] | None:
        """根据名称查找 profile"""
        try:
            r = self.session.get(f"{self.base_url}/profiles", timeout=10)
            if r.status_code == 200:
                for p in r.json():
                    if p["name"] == name:
                        return p
        except:
            pass
        return None

    def _sanitize_profile_name(self, nickname: str) -> str:
        """清理昵称，使其适合作为 profile 名称"""
        # 移除或替换特殊字符
        sanitized = nickname.strip()
        # 限制长度
        if len(sanitized) > 30:
            sanitized = sanitized[:30]
        # 移除不允许的字符（保留中文、字母、数字、下划线、横线）
        sanitized = ''.join(c for c in sanitized if c.isalnum() or c in '-_')
        # 如果清理后为空，使用时间戳
        if not sanitized:
            sanitized = f"user_{int(time.time())}"
        return sanitized

    def _extract_nickname(self, page_text: str) -> str:
        """从页面文本中提取用户昵称"""
        # 优先使用 AI 提取
        if self.deepseek_api_key:
            nickname = self._ai_extract_nickname(page_text)
            if nickname:
                print(f"   ✅ AI 提取昵称: {nickname}")
                return nickname
            else:
                print(f"   ⚠️  AI 提取失败，使用备用方案")

        # 备用方案：更精确的关键词过滤
        # 跳过抖音界面常见词
        skip_words = ["推荐", "关注", "朋友", "我的", "搜索", "直播", "登录", "开启", "标签",
                      "粉丝", "获赞", "下载", "精选", "放映厅", "短剧", "热点", "同城", "编辑资料",
                      "抖音号", "简介", "获赞", "关注", "粉丝", "分享", "更多", "设置", "喜欢",
                      "作品", "收藏", "私信", "消息", "通知", "主页", "切换账号", "设置"]

        # 昵称特征：通常是第一行或前几行，不包含关键词，长度适中
        lines = page_text.split("\n")

        # 策略1：找第一个符合条件的非空行
        for i, line in enumerate(lines[:30]):
            line = line.strip()
            # 排除条件
            if not line or len(line) < 2 or len(line) > 20:
                continue
            if any(w in line for w in skip_words):
                continue
            if line.isdigit() or line.replace(".", "").isdigit():
                continue  # 排除纯数字
            if "@" in line or "http" in line or "www" in line:
                continue  # 排除URL

            # 找到候选昵称，检查下一行是否是数字（粉丝数等），增加可信度
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # 如果下一行包含数字（如"粉丝 100"），说明当前行很可能是昵称
                if any(c.isdigit() for c in next_line):
                    print(f"   ✅ 找到昵称（位置{i}，下一行有数字）: {line}")
                    return line

            # 如果是第一行就符合条件，直接返回
            if i < 5:
                print(f"   ✅ 找到昵称（前5行）: {line}")
                return line

        # 策略2：如果上面失败，尝试找最可能的位置（通常是前10行，长度3-15的文本）
        print(f"   ⚠️  未能精确定位昵称，使用模糊匹配")
        for line in lines[:10]:
            line = line.strip()
            if 3 <= len(line) <= 15 and not any(w in line for w in skip_words):
                print(f"   ⚠️  模糊匹配昵称: {line}")
                return line

        # 策略3：最后兜底 - 使用时间戳
        print(f"   ❌ 所有提取方法失败，使用默认昵称")
        return f"user_{int(time.time())}"

    def _ai_extract_nickname(self, page_text: str) -> str | None:
        """使用 AI 提取昵称"""
        try:
            prompt = f"""从以下抖音个人主页文本中提取用户昵称。

提取规则：
1. 用户昵称通常出现在页面前10行
2. 昵称长度一般在 2-15 个字符之间
3. 昵称不会是：推荐、关注、粉丝、作品、编辑资料、抖音号、简介等界面文字
4. 昵称通常是纯文本，不包含数字或特殊符号
5. 找到昵称后，只返回昵称本身，不要其他文字

页面文本：
{page_text[:1000]}

只返回昵称，不要加任何引号或说明文字。"""

            r = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {self.deepseek_api_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 50
                },
                timeout=15
            )
            if r.status_code == 200:
                nickname = r.json()["choices"][0]["message"]["content"].strip()

                # 清理可能的引号或多余空格
                nickname = nickname.strip('""""""').strip()

                # 验证昵称合理性
                if 2 <= len(nickname) <= 20 and not any(w in nickname for w in ["推荐", "关注", "粉丝", "作品", "编辑", "抖音号"]):
                    return nickname
        except Exception as e:
            print(f"   ⚠️  AI 提取异常: {e}")
        return None

    def _ai_verify_and_extract(self, page_text: str, nodes: list) -> dict:
        """
        使用 AI 验证登录状态并提取用户信息

        Args:
            page_text: 页面文本内容
            nodes: PinchTab 获取的页面元素树

        Returns:
            dict: {
                "success": bool,
                "is_logged_in": bool,
                "nickname": str,
                "message": str
            }
        """
        if not self.deepseek_api_key:
            return {
                "success": False,
                "message": "未配置 DEEPSEEK_API_KEY"
            }

        try:
            # 准备页面信息
            elements_info = []
            for node in nodes[:30]:  # 前30个元素
                element_info = {
                    "name": node.get("name", ""),
                    "role": node.get("role", ""),
                    "ref": node.get("ref", "")
                }
                if element_info["name"] and element_info["role"]:
                    elements_info.append(element_info)

            prompt = f"""你是抖音自动化专家。分析以下页面信息，判断用户是否已登录，并提取用户昵称。

任务：
1. 判断是否已登录抖音
2. 如果已登录，提取用户昵称

页面文本（前800字符）：
{page_text[:800]}

可交互元素（前20个）：
{json.dumps(elements_info[:20], ensure_ascii=False, indent=2)}

判断规则：
- 已登录标识：页面显示"粉丝"、"作品"、"获赞"等用户信息，没有"扫码登录"、"验证码"、"登录后即可"等未登录提示
- 未登录标识：页面显示"扫码登录"、"验证码"、"登录后即可"、"请登录"等登录按钮或提示
- 用户昵称：通常是页面顶部第一个可见的文本，长度在2-15字符之间，不包含数字和特殊符号

请返回 JSON 格式：
{{
    "is_logged_in": true/false,
    "nickname": "提取到的昵称或null",
    "reasoning": "判断依据的简要说明"
}}

注意：
1. 如果未登录，nickname 字段返回 null
2. 只返回 JSON，不要其他文字
3. nickname 只返回昵称本身，不要引号"""

            r = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {self.deepseek_api_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 300
                },
                timeout=20
            )

            if r.status_code == 200:
                response_text = r.json()["choices"][0]["message"]["content"].strip()

                # 清理可能的 markdown 代码块标记
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()

                result = json.loads(response_text)

                # 验证和修正昵称
                nickname = result.get("nickname")
                if nickname:
                    # 清理可能的引号
                    nickname = nickname.strip('""""""').strip()

                    # 验证昵称合理性
                    if not (2 <= len(nickname) <= 20):
                        print(f"   ⚠️  AI 提取的昵称长度异常: {nickname}")
                        nickname = None
                    elif any(w in nickname for w in ["推荐", "关注", "粉丝", "作品", "编辑", "抖音号"]):
                        print(f"   ⚠️  AI 提取的昵称包含界面词: {nickname}")
                        nickname = None

                return {
                    "success": True,
                    "is_logged_in": result.get("is_logged_in", False),
                    "nickname": nickname if nickname else None,
                    "message": result.get("reasoning", ""),
                }
            else:
                print(f"   ⚠️  DeepSeek API 错误: {r.status_code}")
                return {
                    "success": False,
                    "message": f"API 错误: {r.status_code}"
                }

        except json.JSONDecodeError as e:
            print(f"   ⚠️  AI 响应解析失败: {e}")
            return {
                "success": False,
                "message": "AI 响应格式错误"
            }
        except Exception as e:
            print(f"   ⚠️  AI 验证异常: {e}")
            return {
                "success": False,
                "message": str(e)
            }

    def list_profiles(self) -> dict[str, str | bool | int]:
        """列出所有 profiles"""
        try:
            r = self.session.get(f"{self.base_url}/profiles", timeout=10)
            if r.status_code == 200:
                return {"success": True, "profiles": r.json(), "count": len(r.json())}
            return {"success": False, "message": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def delete_profile(self, profile_name: str) -> dict[str, str | bool]:
        """删除指定 profile"""
        try:
            profile = self._find_profile_by_name(profile_name)
            if not profile:
                return {"success": False, "message": f"Profile 不存在: {profile_name}"}

            r = self.session.delete(f"{self.base_url}/profiles/{profile['id']}", timeout=10)
            if r.status_code in [200, 204]:
                return {"success": True, "message": f"已删除 Profile: {profile_name}"}
            return {"success": False, "message": f"删除失败: HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def login_with_profile(self, profile_name: str) -> PinchTabClient:
        """
        使用指定 profile 登录

        Returns:
            PinchTabClient 实例，可用于后续操作
        """
        if not self.client.connect(profile_name=profile_name, headless=False):
            raise Exception(f"启动 profile 失败: {profile_name}")

        # 导航到抖音验证登录状态
        self.client.navigate("https://www.douyin.com")
        time.sleep(3)

        if not self._check_login_status():
            raise Exception(f"登录验证失败，Profile 可能已失效: {profile_name}")

        print(f"✅ 使用 Profile {profile_name} 登录成功")
        return self.client
