"""
接码平台客户端
支持 sms-activate.org（默认）

用法：
  client = SmsClient()
  phone, activation_id = client.get_number("douyin")
  code = client.wait_for_code(activation_id)
  client.finish(activation_id)
"""

import os
import time
import requests
from typing import Optional, Tuple


class SmsClient:

    # 支持的平台
    PLATFORMS = {
        "sms-activate": "https://api.sms-activate.org/stubs/handler_api.php",
        "5sim":         "https://5sim.net/v1",
    }

    # 抖音在各平台的服务代码
    SERVICE_CODES = {
        "sms-activate": "dy",   # 抖音
        "5sim":         "douyin",
    }

    def __init__(self, platform: str = None, api_key: str = None):
        self.platform = platform or os.getenv("SMS_PLATFORM", "sms-activate")
        self.api_key  = api_key  or os.getenv("SMS_API_KEY", "")
        self.base_url = self.PLATFORMS.get(self.platform, self.PLATFORMS["sms-activate"])

    def get_balance(self) -> Optional[float]:
        """查询余额"""
        if not self.api_key:
            return None
        try:
            r = requests.get(self.base_url, params={
                "api_key": self.api_key,
                "action":  "getBalance"
            }, timeout=10)
            # 返回格式：ACCESS_BALANCE:12.50
            if "ACCESS_BALANCE" in r.text:
                return float(r.text.split(":")[1])
        except Exception as e:
            print(f"   ⚠️  查询余额失败: {e}")
        return None

    def get_number(self, country: str = "cn") -> Optional[Tuple[str, str]]:
        """
        获取一个虚拟手机号
        返回 (phone_number, activation_id)
        """
        if not self.api_key:
            print("❌ 未配置 SMS_API_KEY")
            return None

        service = self.SERVICE_CODES.get(self.platform, "dy")
        try:
            r = requests.get(self.base_url, params={
                "api_key":  self.api_key,
                "action":   "getNumber",
                "service":  service,
                "country":  0 if country == "cn" else country,
            }, timeout=10)

            # 返回格式：ACCESS_NUMBER:activation_id:phone
            if r.text.startswith("ACCESS_NUMBER"):
                parts = r.text.split(":")
                activation_id = parts[1]
                phone = parts[2]
                print(f"   📱 获取号码: +{phone} (id: {activation_id})")
                return phone, activation_id
            else:
                print(f"   ❌ 获取号码失败: {r.text}")
        except Exception as e:
            print(f"   ⚠️  获取号码异常: {e}")
        return None

    def wait_for_code(self, activation_id: str, timeout: int = 120) -> Optional[str]:
        """
        等待验证码，最多等 timeout 秒
        """
        print(f"   ⏳ 等待验证码 (最多 {timeout}s)...")
        start = time.time()

        while time.time() - start < timeout:
            try:
                r = requests.get(self.base_url, params={
                    "api_key":       self.api_key,
                    "action":        "getStatus",
                    "id":            activation_id,
                }, timeout=10)

                if r.text.startswith("STATUS_OK"):
                    code = r.text.split(":")[1]
                    print(f"   ✅ 验证码: {code}")
                    return code
                elif r.text == "STATUS_WAIT_CODE":
                    time.sleep(5)
                    continue
                elif r.text in ["STATUS_CANCEL", "STATUS_WAIT_RESEND"]:
                    print(f"   ❌ 号码状态异常: {r.text}")
                    return None
                else:
                    time.sleep(5)
            except Exception as e:
                print(f"   ⚠️  查询验证码异常: {e}")
                time.sleep(5)

        print(f"   ❌ 等待验证码超时")
        return None

    def finish(self, activation_id: str):
        """标记号码使用完成"""
        try:
            requests.get(self.base_url, params={
                "api_key": self.api_key,
                "action":  "setStatus",
                "id":      activation_id,
                "status":  6,  # 6 = 完成
            }, timeout=10)
        except:
            pass

    def cancel(self, activation_id: str):
        """取消号码（不扣费）"""
        try:
            requests.get(self.base_url, params={
                "api_key": self.api_key,
                "action":  "setStatus",
                "id":      activation_id,
                "status":  8,  # 8 = 取消
            }, timeout=10)
        except:
            pass
