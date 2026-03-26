"""
反指纹追踪模块
每次请求随机化：Fingerprint + Cookie 初始化
代理接口预留，买到住宅代理后填入即可
"""

import random
import time
import json
import requests
from typing import Optional, Dict, Any


# ─────────────────────────────────────────────
# Fingerprint 随机化配置池
# ─────────────────────────────────────────────

_RESOLUTIONS = [
    (1920, 1080), (1440, 900), (1536, 864),
    (1366, 768),  (2560, 1440), (1280, 800),
]

_TIMEZONES = [
    "Asia/Shanghai", "Asia/Chongqing", "Asia/Harbin",
]

_LANGUAGES = [
    "zh-CN,zh;q=0.9",
    "zh-CN,zh;q=0.9,en;q=0.8",
    "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
]

_CHROME_VERSIONS = ["131.0.0.0", "130.0.0.0", "129.0.0.0", "128.0.0.0"]

_PLATFORMS = [
    ("Windows NT 10.0; Win64; x64", "Win32"),
    ("Windows NT 11.0; Win64; x64", "Win32"),
    ("Macintosh; Intel Mac OS X 10_15_7", "MacIntel"),
]


def random_fingerprint() -> Dict[str, Any]:
    """生成一套随机 fingerprint 配置"""
    w, h        = random.choice(_RESOLUTIONS)
    os_str, pf  = random.choice(_PLATFORMS)
    chrome_ver  = random.choice(_CHROME_VERSIONS)
    lang        = random.choice(_LANGUAGES)
    tz          = random.choice(_TIMEZONES)

    ua = (
        f"Mozilla/5.0 ({os_str}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_ver} Safari/537.36"
    )

    return {
        "ua":         ua,
        "platform":   pf,
        "language":   lang,
        "timezone":   tz,
        "width":      w,
        "height":     h,
        "color_depth": random.choice([24, 30]),
        "pixel_ratio": random.choice([1, 1.25, 1.5, 2]),
        # Canvas/WebGL 噪声种子（注入 JS 时用）
        "canvas_noise": random.randint(1, 999),
        "webgl_noise":  random.randint(1, 999),
    }


# ─────────────────────────────────────────────
# JS 注入：覆盖浏览器指纹
# ─────────────────────────────────────────────

def build_stealth_js(fp: Dict[str, Any]) -> str:
    """生成覆盖 fingerprint 的 JS，在页面加载后执行"""
    return f"""
(function() {{
    // Navigator
    Object.defineProperty(navigator, 'platform',  {{get: () => '{fp["platform"]}'}});
    Object.defineProperty(navigator, 'language',  {{get: () => '{fp["language"].split(",")[0]}'}});
    Object.defineProperty(navigator, 'languages', {{get: () => {json.dumps(fp["language"].split(","))}}});
    Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {random.choice([4,6,8,12,16])}}});
    Object.defineProperty(navigator, 'deviceMemory', {{get: () => {random.choice([4,8,16])}}});

    // Screen
    Object.defineProperty(screen, 'width',      {{get: () => {fp["width"]}}});
    Object.defineProperty(screen, 'height',     {{get: () => {fp["height"]}}});
    Object.defineProperty(screen, 'colorDepth', {{get: () => {fp["color_depth"]}}});
    Object.defineProperty(window, 'devicePixelRatio', {{get: () => {fp["pixel_ratio"]}}});

    // Canvas 噪声
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {{
        const ctx = this.getContext('2d');
        if (ctx) {{
            const noise = {fp["canvas_noise"]};
            ctx.fillStyle = 'rgba(0,0,0,' + (noise/100000) + ')';
            ctx.fillRect(0, 0, 1, 1);
        }}
        return origToDataURL.apply(this, arguments);
    }};

    // WebGL 噪声
    const origGetParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {{
        if (param === 37445) return 'Intel Inc. {fp["webgl_noise"]}';
        if (param === 37446) return 'Intel Iris OpenGL Engine {fp["webgl_noise"]}';
        return origGetParam.apply(this, arguments);
    }};

    // 隐藏自动化特征
    Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
}})();
"""


# ─────────────────────────────────────────────
# Cookie 池：抖音访客 cookie 初始化
# ─────────────────────────────────────────────

# 抖音访客必要 cookie（不登录也需要这些才能渲染内容）
_DOUYIN_COOKIE_TEMPLATES = [
    {
        "s_v_web_id":    lambda: f"verify_{_rand_hex(8)}_{_rand_hex(8)}_{_rand_hex(4)}_{_rand_hex(4)}_{_rand_hex(12)}",
        "ttwid":         lambda: f"1%7C{_rand_hex(43)}%7C{int(time.time())}%7C{_rand_hex(40)}",
        "msToken":       lambda: _rand_b64(107),
        "tt_chain_token": lambda: _rand_b64(24),
    }
]


def _rand_hex(n: int) -> str:
    return ''.join(random.choices('0123456789abcdef', k=n))


def _rand_b64(n: int) -> str:
    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    return ''.join(random.choices(chars, k=n))


def build_cookie_js(domain: str = ".douyin.com") -> str:
    """生成注入抖音访客 cookie 的 JS"""
    template = random.choice(_DOUYIN_COOKIE_TEMPLATES)
    cookies  = {k: v() for k, v in template.items()}
    expire   = int(time.time()) + 86400 * 30  # 30天后过期

    js_lines = []
    for name, value in cookies.items():
        js_lines.append(
            f'document.cookie = "{name}={value}; domain={domain}; path=/; expires=" + new Date({expire}000).toUTCString();'
        )

    return "\n".join(js_lines)


# ─────────────────────────────────────────────
# 代理接口（预留，买到住宅代理后填入）
# ─────────────────────────────────────────────

class ProxyPool:
    """
    住宅代理池接口
    买到代理后，在 .env 里配置 PROXY_API_URL 和 PROXY_API_KEY
    支持格式：http://user:pass@host:port
    """

    def __init__(self, api_url: str = None, api_key: str = None):
        import os
        self.api_url = api_url or os.getenv("PROXY_API_URL", "")
        self.api_key = api_key or os.getenv("PROXY_API_KEY", "")
        self._pool   = []

    def get(self) -> Optional[str]:
        """获取一个住宅代理，没配置时返回 None（直连）"""
        import os
        # 优先用固定代理 URL
        fixed = os.getenv("PROXY_URL", "")
        if fixed:
            return fixed

        if not self.api_url:
            return None

        try:
            r = requests.get(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5
            )
            if r.status_code == 200:
                data = r.json()
                # 兼容常见代理 API 返回格式
                proxy = data.get("proxy") or data.get("data", {}).get("proxy") or ""
                if proxy:
                    return proxy
        except Exception as e:
            print(f"   ⚠️  代理获取失败: {e}")

        return None

    def format_for_pinchtab(self, proxy: str) -> Optional[Dict]:
        """转换为 PinchTab launch 参数格式"""
        if not proxy:
            return None
        # PinchTab 代理格式：{"server": "http://host:port", "username": "...", "password": "..."}
        # 解析 http://user:pass@host:port
        try:
            from urllib.parse import urlparse
            p = urlparse(proxy)
            return {
                "server":   f"{p.scheme}://{p.hostname}:{p.port}",
                "username": p.username or "",
                "password": p.password or "",
            }
        except:
            return {"server": proxy}
