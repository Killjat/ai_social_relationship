"""
视频爆款分析

用 Gemini 2.0 Flash（通过 OpenRouter）分析视频帧 + 字幕
输出结构化的爆款原因分析
"""

import os
import base64
import json
import re
import requests
from pathlib import Path
from typing import Dict, Any, List


OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"

# 分析用模型：Gemini 2.0 Flash，支持多图，价格低，速度快
ANALYSIS_MODEL = "google/gemini-2.0-flash-001"


class VideoAnalyzer:

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")

    def analyze(self, frames: List[str], subtitle: str = "",
                title: str = "", platform: str = "douyin",
                lang: str = "zh") -> Dict[str, Any]:
        """
        分析视频爆款原因

        返回结构化分析结果：
        {
          "hook":        str,   # 钩子设计（前3秒）
          "structure":   str,   # 内容结构
          "emotion":     str,   # 情绪触发点
          "visual":      str,   # 视觉风格
          "music":       str,   # 音乐/音效
          "interaction": str,   # 评论区互动模式
          "why_viral":   str,   # 综合爆款原因
          "target":      str,   # 目标受众
          "scenes":      [      # 分镜场景列表（用于后续生成图片和脚本）
            {
              "index":       int,
              "time_range":  str,   # "00:00-00:03"
              "description": str,   # 画面描述
              "text":        str,   # 文案/字幕
              "emotion":     str,   # 情绪
              "purpose":     str,   # 这个镜头的作用
            }
          ]
        }
        """
        print(f"\n🤖 AI 分析视频（{len(frames)} 帧）...")

        if not self.api_key:
            return {"error": "未配置 OPENROUTER_API_KEY"}

        # 构建消息：图片 + 文字
        content = self._build_content(frames, subtitle, title, platform, lang)

        try:
            resp = requests.post(
                OPENROUTER_API,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type":  "application/json",
                    "HTTP-Referer":  "https://github.com/douyinai",
                },
                json={
                    "model":    ANALYSIS_MODEL,
                    "messages": [{"role": "user", "content": content}],
                    "temperature": 0.3,
                    "max_tokens":  4000,
                },
                timeout=120
            )

            if resp.status_code != 200:
                return {"error": f"API 错误: {resp.status_code} {resp.text[:200]}"}

            raw = resp.json()["choices"][0]["message"]["content"]
            print(f"   ✅ 分析完成")
            return self._parse_response(raw)

        except Exception as e:
            return {"error": str(e)}

    def _build_content(self, frames: List[str], subtitle: str,
                       title: str, platform: str, lang: str) -> List[Dict]:
        """构建多模态消息内容"""
        content = []

        # 系统提示
        prompt_lang = "中文" if lang == "zh" else "English"
        system_prompt = f"""你是一位顶级短视频运营专家，擅长分析{platform}爆款视频。

我会给你一个视频的关键帧截图{'和字幕文本' if subtitle else ''}，请深度分析这个视频为什么会爆火，并给出可复制的制作建议。

请用{prompt_lang}回答，输出严格的 JSON 格式：
{{
  "hook": "前3秒钩子设计分析",
  "structure": "内容结构分析（起承转合）",
  "emotion": "情绪触发点分析（什么情绪让人点赞/转发/评论）",
  "visual": "视觉风格分析（色调、剪辑节奏、字幕风格、特效）",
  "music": "音乐/音效分析",
  "interaction": "评论区互动模式预测",
  "why_viral": "综合爆款原因总结（3-5条核心原因）",
  "target": "目标受众画像",
  "scenes": [
    {{
      "index": 1,
      "time_range": "00:00-00:03",
      "description": "画面内容描述",
      "text": "字幕/文案内容",
      "emotion": "情绪",
      "purpose": "这个镜头的作用"
    }}
  ]
}}

只返回 JSON，不要其他文字。"""

        content.append({"type": "text", "text": system_prompt})

        if title:
            content.append({"type": "text", "text": f"视频标题：{title}"})

        if subtitle:
            content.append({"type": "text", "text": f"视频字幕/旁白：\n{subtitle}"})

        content.append({"type": "text", "text": f"以下是视频的 {len(frames)} 张关键帧截图："})

        # 添加图片（最多15张，避免超出 token 限制）
        for frame_path in frames[:15]:
            try:
                with open(frame_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                })
            except Exception as e:
                print(f"   ⚠️  读取帧失败: {frame_path}: {e}")

        return content

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """解析 AI 返回的 JSON"""
        try:
            clean = re.sub(r"```json|```", "", raw).strip()
            return json.loads(clean)
        except Exception:
            # 解析失败，返回原始文本
            return {"raw": raw, "parse_error": True}
