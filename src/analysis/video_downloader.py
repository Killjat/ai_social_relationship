"""
视频下载 + 预处理

- yt-dlp 下载抖音/TikTok 视频
- ffmpeg 截取关键帧
- Whisper 提取字幕
"""

import os
import subprocess
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List


class VideoDownloader:

    def __init__(self, output_dir: Path, douyin_cookie_file: str = None):
        """
        output_dir: 输出目录
        douyin_cookie_file: 抖音 cookie 文件路径（Netscape 格式，从浏览器导出）
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir = self.output_dir / "frames"
        self.frames_dir.mkdir(exist_ok=True)
        self.douyin_cookie_file = douyin_cookie_file or os.getenv("DOUYIN_COOKIE_FILE", "")

    def download(self, url: str) -> Dict[str, Any]:
        """
        下载视频，返回本地文件路径和元数据

        返回：
          {
            "video_path": str,
            "title": str,
            "duration": float,
            "platform": "douyin" | "tiktok",
            "frames": [str, ...],   # 截帧路径列表
            "subtitle": str,        # 字幕文本
          }
        """
        platform = self._detect_platform(url)
        print(f"\n📥 下载视频 [{platform}]: {url[:60]}...")

        video_path = self._download_video(url, platform)
        if not video_path:
            return {"success": False, "message": "下载失败"}

        print(f"   ✅ 视频: {video_path}")

        # 获取视频元数据
        meta = self._get_metadata(video_path)
        print(f"   时长: {meta.get('duration', '?')}s | 分辨率: {meta.get('resolution', '?')}")

        # 截取关键帧
        frames = self._extract_frames(video_path, meta.get("duration", 30))
        print(f"   截帧: {len(frames)} 张")

        # 提取字幕
        subtitle = self._extract_subtitle(video_path)
        if subtitle:
            print(f"   字幕: {len(subtitle)} 字")

        return {
            "success":    True,
            "video_path": str(video_path),
            "platform":   platform,
            "title":      meta.get("title", ""),
            "duration":   meta.get("duration", 0),
            "resolution": meta.get("resolution", ""),
            "frames":     frames,
            "subtitle":   subtitle,
        }

    def _detect_platform(self, url: str) -> str:
        if "douyin.com" in url or "iesdouyin.com" in url:
            return "douyin"
        elif "tiktok.com" in url:
            return "tiktok"
        return "unknown"

    def _download_video(self, url: str, platform: str) -> Optional[Path]:
        """用 yt-dlp 下载视频"""
        output_template = str(self.output_dir / "video.%(ext)s")

        cmd = [
            "yt-dlp",
            "--no-playlist",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "-o", output_template,
            "--merge-output-format", "mp4",
        ]

        # 抖音需要 cookie
        if platform == "douyin" and self.douyin_cookie_file:
            cmd += ["--cookies", self.douyin_cookie_file]

        cmd.append(url)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                print(f"   ❌ yt-dlp 错误: {result.stderr[-200:]}")
                return None

            # 找到下载的文件
            for f in self.output_dir.glob("video.*"):
                if f.suffix in [".mp4", ".webm", ".mkv"]:
                    return f
        except FileNotFoundError:
            print("   ❌ yt-dlp 未安装，请运行: pip install yt-dlp")
        except subprocess.TimeoutExpired:
            print("   ❌ 下载超时")
        except Exception as e:
            print(f"   ❌ 下载异常: {e}")

        return None

    def _get_metadata(self, video_path: Path) -> Dict:
        """用 ffprobe 获取视频元数据"""
        try:
            cmd = [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                fmt = data.get("format", {})
                streams = data.get("streams", [])
                video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
                return {
                    "duration":   float(fmt.get("duration", 0)),
                    "title":      fmt.get("tags", {}).get("title", ""),
                    "resolution": f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}",
                }
        except Exception as e:
            print(f"   ⚠️  获取元数据失败: {e}")
        return {}

    def _extract_frames(self, video_path: Path, duration: float) -> List[str]:
        """
        用 ffmpeg 截取关键帧
        策略：每2秒1帧，最多20帧，确保覆盖完整视频
        """
        if duration <= 0:
            duration = 30

        # 计算截帧间隔
        max_frames = 20
        interval = max(1, duration / max_frames)
        interval = min(interval, 3)  # 最多每3秒1帧

        frames = []
        t = 0.5  # 从0.5秒开始，避免黑帧
        idx = 1

        while t < duration and len(frames) < max_frames:
            frame_path = self.frames_dir / f"frame_{idx:02d}.jpg"
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(t),
                "-i", str(video_path),
                "-vframes", "1",
                "-q:v", "2",
                str(frame_path)
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=10)
                if result.returncode == 0 and frame_path.exists():
                    frames.append(str(frame_path))
                    idx += 1
            except Exception:
                pass
            t += interval

        return frames

    def _extract_subtitle(self, video_path: Path) -> str:
        """
        用 Whisper 提取字幕/旁白
        需要安装: pip install openai-whisper
        """
        try:
            import whisper
            print("   🎙  Whisper 提取字幕...")
            model = whisper.load_model("base")
            result = model.transcribe(str(video_path), language="zh")
            return result.get("text", "")
        except ImportError:
            print("   ⚠️  Whisper 未安装（pip install openai-whisper），跳过字幕提取")
            return ""
        except Exception as e:
            print(f"   ⚠️  字幕提取失败: {e}")
            return ""
