"""
视频分析模块

功能：
  - 下载抖音/TikTok 视频
  - 截取关键帧 + 提取字幕
  - AI 分析爆款原因
  - 生成分镜脚本
  - 生成分镜参考图
"""

from .analysis_pipeline import AnalysisPipeline

__all__ = ["AnalysisPipeline"]
