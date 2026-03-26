"""
配置文件
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(override=True)


class Config:
    """配置类"""
    
    # PinchTab 远程配置（数据抓取）
    PINCHTAB_URL = os.getenv("PINCHTAB_URL", "http://localhost:9867")
    PINCHTAB_TOKEN = os.getenv("PINCHTAB_TOKEN", "")
    PINCHTAB_PROFILE_ID = os.getenv("PINCHTAB_PROFILE_ID", "")
    PINCHTAB_PROFILE = os.getenv("PINCHTAB_PROFILE", "")

    # PinchTab 本地配置（搜索 UID，需要已登录 profile）
    PINCHTAB_LOCAL_URL = os.getenv("PINCHTAB_LOCAL_URL", "http://localhost:9867")
    PINCHTAB_LOCAL_TOKEN = os.getenv("PINCHTAB_LOCAL_TOKEN", "")
    PINCHTAB_LOCAL_PROFILE = os.getenv("PINCHTAB_LOCAL_PROFILE", "cyberstroll跨境电商")

    PINCHTAB_HEADLESS = os.getenv("PINCHTAB_HEADLESS", "false").lower() == "true"
    
    # DeepSeek 配置
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    
    # 抖音配置
    DOUYIN_HOME_URL = "https://www.douyin.com/"
    DOUYIN_SEARCH_URL = "https://www.douyin.com/search/{keyword}?type=live"
    
    # 数据目录
    DATA_DIR = Path("data")
    SCREENSHOTS_DIR = DATA_DIR / "screenshots"
    SESSIONS_DIR = DATA_DIR / "sessions"
    CONVERSATIONS_DIR = DATA_DIR / "conversations"
    TRAINING_DIR = DATA_DIR / "training"
    
    # 确保目录存在
    @classmethod
    def ensure_dirs(cls):
        """确保所有数据目录存在"""
        for dir_path in [
            cls.SCREENSHOTS_DIR,
            cls.SESSIONS_DIR,
            cls.CONVERSATIONS_DIR,
            cls.TRAINING_DIR
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)


# 初始化时创建目录
Config.ensure_dirs()
