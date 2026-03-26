"""
分镜脚本生成

基于视频分析结果，用 Claude 生成可复制的分镜脚本
"""

import os
import json
import re
import requests
from typing import Dict, Any, List


OPENROUTER_API  = "https://openrouter.ai/api/v1/chat/completions"
SCRIPT_MODEL    = "anthropic/claude-sonnet-4-5"


class ScriptGenerator:

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")

    def generate(self, analysis: Dict[str, Any],
                 platform: str = "douyin",
                 lang: str = "zh",
                 duration_target: int = 30) -> Dict[str, Any]:
        """
        基于分析结果生成分镜脚本

        返回：
        {
          "title_options": [str, ...],   # 3个标题备选
          "hook_text":     str,          # 开头钩子文案
          "scenes": [
            {
              "index":       int,
              "time_range":  str,        # "00:00-00:03"
              "duration":    int,        # 秒数
              "shot_type":   str,        # 镜头类型（特写/中景/全景）
              "action":      str,        # 画面动作描述
              "text":        str,        # 字幕文案
              "voiceover":   str,        # 旁白（如有）
              "emotion":     str,        # 情绪基调
              "image_prompt": str,       # 用于生成参考图的英文提示词
            }
          ],
          "cta":           str,          # 结尾 CTA（引导评论/关注）
          "hashtags":      [str, ...],   # 推荐话题标签
          "music_style":   str,          # 推荐音乐风格
          "shooting_tips": str,          # 拍摄建议
        }
        """
        print(f"\n✍️  生成分镜脚本（目标时长: {duration_target}s）...")

        if not self.api_key:
            return {"error": "未配置 OPENROUTER_API_KEY"}

        prompt = self._build_prompt(analysis, platform, lang, duration_target)

        try:
            resp = requests.post(
                OPENROUTER_API,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type":  "application/json",
                    "HTTP-Referer":  "https://github.com/douyinai",
                },
                json={
                    "model":       SCRIPT_MODEL,
                    "messages":    [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens":  5000,
                },
                timeout=120
            )

            if resp.status_code != 200:
                return {"error": f"API 错误: {resp.status_code} {resp.text[:200]}"}

            raw = resp.json()["choices"][0]["message"]["content"]
            print(f"   ✅ 脚本生成完成")
            return self._parse_response(raw)

        except Exception as e:
            return {"error": str(e)}

    def _build_prompt(self, analysis: Dict, platform: str,
                      lang: str, duration: int) -> str:
        prompt_lang = "中文" if lang == "zh" else "English"
        why_viral   = analysis.get("why_viral", "")
        structure   = analysis.get("structure", "")
        emotion     = analysis.get("emotion", "")
        visual      = analysis.get("visual", "")
        target      = analysis.get("target", "")
        scenes_ref  = analysis.get("scenes", [])

        return f"""你是顶级短视频编导，请基于以下爆款视频分析，创作一个可以复制爆款效果的全新分镜脚本。

## 爆款分析参考
- 爆款原因：{why_viral}
- 内容结构：{structure}
- 情绪触发：{emotion}
- 视觉风格：{visual}
- 目标受众：{target}

## 创作要求
- 平台：{platform}
- 目标时长：{duration} 秒
- 语言：{prompt_lang}
- 保留爆款核心要素，但内容必须原创，不能抄袭
- 每个场景都要有对应的图片生成提示词（英文，用于 Flux 图片生成）

## 输出格式（严格 JSON）
{{
  "title_options": ["标题1", "标题2", "标题3"],
  "hook_text": "开头3秒钩子文案",
  "scenes": [
    {{
      "index": 1,
      "time_range": "00:00-00:03",
      "duration": 3,
      "shot_type": "特写/中景/全景/航拍",
      "action": "画面动作描述（拍摄者需要做什么）",
      "text": "字幕文案",
      "voiceover": "旁白文案（没有则为空）",
      "emotion": "情绪基调",
      "image_prompt": "photorealistic, [detailed scene description in English for Flux image generation]"
    }}
  ],
  "cta": "结尾引导语",
  "hashtags": ["话题1", "话题2", "话题3"],
  "music_style": "推荐音乐风格描述",
  "shooting_tips": "拍摄注意事项和技巧"
}}

只返回 JSON，不要其他文字。"""

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        try:
            clean = re.sub(r"```json|```", "", raw).strip()
            return json.loads(clean)
        except Exception:
            return {"raw": raw, "parse_error": True}
