"""
视频分析主流程

串联：下载 → 分析 → 生成脚本 → 生成图片 → 输出报告
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from .video_downloader import VideoDownloader
from .video_analyzer import VideoAnalyzer
from .script_generator import ScriptGenerator
from .image_generator import ImageGenerator


class AnalysisPipeline:

    def __init__(self, openrouter_api_key: str = None,
                 douyin_cookie_file: str = None):
        self.api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.douyin_cookie_file = douyin_cookie_file or os.getenv("DOUYIN_COOKIE_FILE", "")

    def run(self, url: str, lang: str = "zh",
            duration_target: int = 30) -> Dict[str, Any]:
        """
        完整分析流程

        url:             视频链接（抖音或 TikTok）
        lang:            输出语言 zh | en
        duration_target: 目标脚本时长（秒）

        返回完整结果，并在 output/ 目录生成报告
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(f"output/analysis_{ts}")
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"🎬 视频爆款分析")
        print(f"   URL: {url[:60]}")
        print(f"   输出: {output_dir}")
        print(f"{'='*60}")

        # ── Step 1: 下载视频 ──────────────────────────
        downloader = VideoDownloader(
            output_dir=output_dir,
            douyin_cookie_file=self.douyin_cookie_file
        )
        download_result = downloader.download(url)

        if not download_result.get("success"):
            return {"success": False, "message": download_result.get("message", "下载失败")}

        # ── Step 2: AI 分析视频 ───────────────────────
        analyzer = VideoAnalyzer(api_key=self.api_key)
        analysis = analyzer.analyze(
            frames=download_result["frames"],
            subtitle=download_result.get("subtitle", ""),
            title=download_result.get("title", ""),
            platform=download_result.get("platform", "douyin"),
            lang=lang
        )

        if "error" in analysis:
            return {"success": False, "message": f"分析失败: {analysis['error']}"}

        # ── Step 3: 生成分镜脚本 ─────────────────────
        script_gen = ScriptGenerator(api_key=self.api_key)
        script = script_gen.generate(
            analysis=analysis,
            platform=download_result.get("platform", "douyin"),
            lang=lang,
            duration_target=duration_target
        )

        if "error" in script:
            return {"success": False, "message": f"脚本生成失败: {script['error']}"}

        # ── Step 4: 生成分镜参考图 ───────────────────
        images_dir = output_dir / "images"
        img_gen = ImageGenerator(api_key=self.api_key, output_dir=images_dir)
        scenes_with_images = img_gen.generate_scenes(script.get("scenes", []))
        script["scenes"] = scenes_with_images

        # ── Step 5: 生成报告 ─────────────────────────
        result = {
            "success":   True,
            "url":       url,
            "platform":  download_result.get("platform"),
            "title":     download_result.get("title"),
            "duration":  download_result.get("duration"),
            "analysis":  analysis,
            "script":    script,
            "output_dir": str(output_dir),
        }

        self._save_report(result, output_dir)

        print(f"\n{'='*60}")
        print(f"✅ 分析完成！报告保存在: {output_dir}")
        print(f"{'='*60}")
        self._print_summary(result)

        return result

    def _save_report(self, result: Dict, output_dir: Path):
        """保存 JSON + Markdown 报告"""
        # JSON
        (output_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Markdown 报告
        md = self._build_markdown(result)
        (output_dir / "report.md").write_text(md, encoding="utf-8")

        # 脚本单独保存
        script_md = self._build_script_markdown(result.get("script", {}))
        (output_dir / "script.md").write_text(script_md, encoding="utf-8")

        print(f"\n💾 报告已保存:")
        print(f"   {output_dir}/report.md")
        print(f"   {output_dir}/script.md")
        print(f"   {output_dir}/result.json")

    def _build_markdown(self, result: Dict) -> str:
        a = result.get("analysis", {})
        s = result.get("script", {})

        lines = [
            f"# 爆款视频分析报告",
            f"",
            f"**平台**: {result.get('platform', '?')}  ",
            f"**标题**: {result.get('title', '?')}  ",
            f"**时长**: {result.get('duration', '?')}s  ",
            f"**URL**: {result.get('url', '')}",
            f"",
            f"---",
            f"",
            f"## 🔥 爆款原因分析",
            f"",
            f"### 为什么会火",
            f"{a.get('why_viral', '')}",
            f"",
            f"### 钩子设计（前3秒）",
            f"{a.get('hook', '')}",
            f"",
            f"### 内容结构",
            f"{a.get('structure', '')}",
            f"",
            f"### 情绪触发点",
            f"{a.get('emotion', '')}",
            f"",
            f"### 视觉风格",
            f"{a.get('visual', '')}",
            f"",
            f"### 音乐/音效",
            f"{a.get('music', '')}",
            f"",
            f"### 目标受众",
            f"{a.get('target', '')}",
            f"",
            f"---",
            f"",
            f"## 📋 原视频分镜解析",
            f"",
        ]

        for scene in a.get("scenes", []):
            lines += [
                f"### 场景 {scene.get('index', '?')} [{scene.get('time_range', '')}]",
                f"- **画面**: {scene.get('description', '')}",
                f"- **文案**: {scene.get('text', '')}",
                f"- **情绪**: {scene.get('emotion', '')}",
                f"- **作用**: {scene.get('purpose', '')}",
                f"",
            ]

        lines += [
            f"---",
            f"",
            f"## 🎬 复制脚本",
            f"",
            f"详见 `script.md`",
        ]

        return "\n".join(lines)

    def _build_script_markdown(self, script: Dict) -> str:
        if not script or "parse_error" in script:
            return f"# 脚本生成失败\n\n{script.get('raw', '')}"

        lines = [
            f"# 分镜脚本",
            f"",
            f"## 标题备选",
        ]
        for i, t in enumerate(script.get("title_options", []), 1):
            lines.append(f"{i}. {t}")

        lines += [
            f"",
            f"## 开头钩子",
            f"{script.get('hook_text', '')}",
            f"",
            f"## 分镜详情",
            f"",
        ]

        for scene in script.get("scenes", []):
            img_path = scene.get("image_path", "")
            img_line = f"![场景{scene.get('index','')}]({img_path})" if img_path else ""

            lines += [
                f"### 场景 {scene.get('index', '?')} [{scene.get('time_range', '')}] {scene.get('duration', '')}s",
                f"",
                img_line,
                f"",
                f"| 项目 | 内容 |",
                f"|------|------|",
                f"| 镜头类型 | {scene.get('shot_type', '')} |",
                f"| 画面动作 | {scene.get('action', '')} |",
                f"| 字幕文案 | {scene.get('text', '')} |",
                f"| 旁白 | {scene.get('voiceover', '无')} |",
                f"| 情绪基调 | {scene.get('emotion', '')} |",
                f"",
            ]

        lines += [
            f"## 结尾 CTA",
            f"{script.get('cta', '')}",
            f"",
            f"## 话题标签",
            f"{' '.join(['#' + t for t in script.get('hashtags', [])])}",
            f"",
            f"## 推荐音乐风格",
            f"{script.get('music_style', '')}",
            f"",
            f"## 拍摄建议",
            f"{script.get('shooting_tips', '')}",
        ]

        return "\n".join(lines)

    def _print_summary(self, result: Dict):
        a = result.get("analysis", {})
        s = result.get("script", {})
        print(f"\n📊 分析摘要:")
        print(f"   爆款原因: {str(a.get('why_viral', ''))[:80]}...")
        print(f"   场景数量: {len(s.get('scenes', []))} 个")
        titles = s.get("title_options", [])
        if titles:
            print(f"   推荐标题: {titles[0]}")
        images = [sc for sc in s.get("scenes", []) if sc.get("image_path")]
        print(f"   参考图片: {len(images)} 张")
