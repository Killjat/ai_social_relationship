"""
分镜参考图生成

用 Flux 1.1 Pro（通过 OpenRouter）生成每个场景的参考图
"""

import os
import base64
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional


OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
IMAGE_MODEL    = "black-forest-labs/flux-1.1-pro"


class ImageGenerator:

    def __init__(self, api_key: str = None, output_dir: Path = None):
        self.api_key    = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.output_dir = Path(output_dir) if output_dir else Path("output/images")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_scenes(self, scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        为每个场景生成参考图

        scenes: script_generator 输出的 scenes 列表
        返回：每个 scene 加上 image_path 字段
        """
        print(f"\n🎨 生成分镜参考图（{len(scenes)} 个场景）...")
        results = []

        for scene in scenes:
            idx   = scene.get("index", 0)
            prompt = scene.get("image_prompt", "")
            if not prompt:
                # 用 action 描述兜底
                prompt = f"photorealistic short video scene, {scene.get('action', '')}"

            print(f"   [{idx}] {prompt[:60]}...")
            image_path = self._generate_one(prompt, idx)

            scene_result = dict(scene)
            scene_result["image_path"] = str(image_path) if image_path else None
            results.append(scene_result)

        success = sum(1 for s in results if s.get("image_path"))
        print(f"   ✅ 生成完成: {success}/{len(scenes)} 张")
        return results

    def _generate_one(self, prompt: str, index: int) -> Optional[Path]:
        """生成单张图片"""
        if not self.api_key:
            print("   ❌ 未配置 OPENROUTER_API_KEY")
            return None

        # 增强提示词：确保竖屏比例（适合短视频）
        full_prompt = (
            f"{prompt}, "
            "vertical 9:16 aspect ratio, "
            "short video style, "
            "high quality, cinematic"
        )

        try:
            resp = requests.post(
                OPENROUTER_API,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type":  "application/json",
                    "HTTP-Referer":  "https://github.com/douyinai",
                },
                json={
                    "model":  IMAGE_MODEL,
                    "messages": [{"role": "user", "content": full_prompt}],
                },
                timeout=120
            )

            if resp.status_code != 200:
                print(f"   ❌ 图片生成失败: {resp.status_code}")
                return None

            data = resp.json()

            # OpenRouter 图片模型返回 base64 或 URL
            content = data["choices"][0]["message"]["content"]

            # 尝试提取 base64 图片
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        url = item["image_url"]["url"]
                        if url.startswith("data:image"):
                            # base64
                            b64 = url.split(",", 1)[1]
                            return self._save_image(base64.b64decode(b64), index)
                        else:
                            # URL，下载
                            return self._download_image(url, index)
            elif isinstance(content, str) and content.startswith("http"):
                return self._download_image(content, index)

        except Exception as e:
            print(f"   ⚠️  生成异常: {e}")

        return None

    def _save_image(self, data: bytes, index: int) -> Path:
        path = self.output_dir / f"scene_{index:02d}.png"
        path.write_bytes(data)
        return path

    def _download_image(self, url: str, index: int) -> Optional[Path]:
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                return self._save_image(r.content, index)
        except Exception as e:
            print(f"   ⚠️  下载图片失败: {e}")
        return None
