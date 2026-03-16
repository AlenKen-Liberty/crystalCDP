# Crystal CDP - 详细设计文档

## 项目目标

提供一个命令行工具 `crystal_cdp <url>`，在 VNC 桌面（DISPLAY=:1）打开一个 headed Chromium 浏览器，使用 Default profile（保留用户已有的登录信息），通过多层反检测和 proxy 轮换策略绕过 Cloudflare 验证和 IP 封锁，成功打开目标网页后程序退出，浏览器保持打开供用户继续操作。

---

## 使用方式

```bash
# 基本用法
python3 crystal_cdp.py https://perplexity.ai

# 或通过 shell wrapper
./crystal_cdp https://perplexity.ai
```

---

## 架构概览

```
crystal_cdp.py          # CLI 入口 + 主控逻辑
├── browser.py          # Patchright 浏览器启动/管理
├── stealth.py          # 反检测 JS 注入 + Cloudflare 检测/解决
├── proxy_loader.py     # Proxy 加载 + 验证
└── crystal_cdp         # Shell wrapper (可选)

外部依赖：
├── patchright           # Stealth Playwright fork
└── ~/scripts/openclaw-tool/proxy/proxy_pool.txt  # Proxy 列表
```

---

## 模块设计

### 1. `crystal_cdp.py` — 主控入口

**职责：** CLI 参数解析 + 策略调度

**流程：**

```
接收 URL 参数
    │
    ▼
Phase 1: 直接访问（无 proxy）
    ├─ 启动 Chromium（stealth flags + Default profile）
    ├─ 导航到 URL
    ├─ 注入 stealth JS（canvas noise 等）
    ├─ 检测页面状态
    │   ├─ 成功 → 打印成功信息，程序退出，浏览器保持
    │   ├─ Cloudflare Turnstile → 尝试自动解决 → 成功则退出
    │   └─ 被 block/超时 → 进入 Phase 2
    │
    ▼
Phase 2: Proxy 轮换
    ├─ 加载 proxy 列表
    ├─ 关闭当前浏览器
    ├─ 对每个 proxy:
    │   ├─ 快速验证 proxy 可用性
    │   ├─ 用该 proxy 重启 Chromium
    │   ├─ 导航 + stealth + 检测
    │   ├─ 成功 → 退出
    │   └─ 失败 → 关闭，尝试下一个 proxy
    │
    ▼
Phase 3: 全部失败
    └─ 打印失败原因 + 建议
```

**CLI 接口：**

```python
crystal_cdp.py <url> [options]

位置参数:
  url                   目标 URL

可选参数:
  --proxy-only          跳过直接访问，直接用 proxy
  --proxy <proxy_url>   指定单个 proxy（不从 pool 加载）
  --max-proxies N       最多尝试 N 个 proxy（默认 5）
  --timeout N           每次尝试的超时秒数（默认 30）
  --no-stealth          禁用 stealth JS 注入
  --verbose             显示详细日志
```

---

### 2. `browser.py` — 浏览器管理

**职责：** Patchright 浏览器启动、页面导航、关闭

**关键设计决策：**
- 使用 `patchright`（非 CDP websocket），它是 Playwright 的反检测 fork
- 使用 `launch_persistent_context()` 加载 Default profile（保留登录信息）
- 每次只保持一个浏览器实例，切换 proxy 时关闭重启

**类设计：**

```python
class Browser:
    def __init__(self, proxy: str | None = None, verbose: bool = False):
        """初始化浏览器配置"""

    def launch(self) -> None:
        """
        启动 Chromium（headed, DISPLAY=:1）
        - 先清理残留进程和 profile locks
        - 使用 launch_persistent_context() 加载 Default profile
        - 应用所有 stealth launch flags
        """

    def navigate(self, url: str, timeout: int = 30) -> PageStatus:
        """
        导航到 URL 并等待加载
        返回页面状态（成功/被block/Cloudflare/超时/错误）
        """

    def get_page(self) -> Page:
        """获取当前活跃页面"""

    def close(self) -> None:
        """
        关闭浏览器但不影响用户体验
        当页面成功打开时：detach（断开 patchright 控制，浏览器保持运行）
        当需要切换 proxy 时：完全关闭
        """

    def kill_existing(self) -> None:
        """杀死所有已有 Chromium 进程，清除 profile locks"""
```

**启动参数（从 web_browser/headed_engine.py 提取）：**

```python
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",   # 隐藏 navigator.webdriver
    "--disable-dev-shm-usage",
    "--disable-notifications",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",  # 防止 WebRTC IP 泄露
    "--enforce-webrtc-ip-permission-check",
    "--ignore-certificate-errors",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-timer-throttling",
]
```

**Profile 处理：**

```python
PROFILE_DIR = Path.home() / ".config" / "chromium"
PROFILE_NAME = "Default"

# 启动前清理 locks（避免 "profile in use" 错误）
for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
    (PROFILE_DIR / lock_file).unlink(missing_ok=True)
```

**Detach 策略（关键）：**
- 页面成功打开后，需要让浏览器继续运行但程序退出
- Patchright/Playwright 的 `browser.close()` 会关闭浏览器窗口
- 解决方案：使用 `playwright.stop()` 断开控制，不调用 `browser.close()`
- 浏览器进程变为"孤儿进程"继续运行，用户可在 VNC 操作

---

### 3. `stealth.py` — 反检测 + Cloudflare 解决

**职责：** JS 注入、页面状态检测、Cloudflare Turnstile 自动解决

**提取自 web_browser/stealth.py 的功能：**

#### 3.1 Canvas Fingerprint 噪声

```python
CANVAS_NOISE_JS = """
(function() {
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function() {
        const imageData = origGetImageData.apply(this, arguments);
        const data = imageData.data;
        for (let i = 0; i < data.length; i += 4) {
            // 10% 概率对 RGB 通道加 ±1 噪声（不可感知但改变 fingerprint）
            if (Math.random() < 0.1) data[i] += (Math.random() < 0.5 ? 1 : -1);
            if (Math.random() < 0.1) data[i+1] += (Math.random() < 0.5 ? 1 : -1);
            if (Math.random() < 0.1) data[i+2] += (Math.random() < 0.5 ? 1 : -1);
        }
        return imageData;
    };
    // 同样处理 toDataURL
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function() {
        // ... 类似噪声注入
    };
})();
"""
```

#### 3.2 页面状态检测

```python
class PageStatus(Enum):
    SUCCESS = "success"             # 页面正常加载
    CLOUDFLARE_TURNSTILE = "cf_turnstile"  # Cloudflare 验证页
    CLOUDFLARE_BLOCK = "cf_block"   # Cloudflare 完全封锁
    IP_BLOCKED = "ip_blocked"       # IP 被目标网站封锁
    RATE_LIMITED = "rate_limited"   # 请求频率限制
    TIMEOUT = "timeout"            # 加载超时
    ERROR = "error"                # 其他错误

def detect_page_status(page) -> PageStatus:
    """
    检测页面状态，基于：
    - 页面标题（"Just a Moment", "Access Denied", "Too Many Requests"）
    - 页面内容标记（cdn-cgi/challenge-platform, captcha, checking your browser）
    - HTTP 状态码（403, 429, 503）
    - Turnstile iframe 存在
    """
```

#### 3.3 Cloudflare Turnstile 自动解决

```python
async def solve_turnstile(page, timeout: int = 20) -> bool:
    """
    检测并解决 Cloudflare Turnstile 验证：

    1. 检测 Turnstile 类型：
       - non-interactive: 等待自动通过
       - interactive: 需要点击 checkbox

    2. 对 interactive 类型：
       - 定位 Turnstile iframe
       - 找到 checkbox 元素
       - 在随机偏移位置点击（模拟人类）
       - 等待验证完成

    3. 返回是否解决成功
    """
```

#### 3.4 Google Referer 伪装

```python
def make_google_referer(url: str) -> str:
    """生成看似来自 Google 搜索的 referer"""
    domain = urlparse(url).netloc
    return f"https://www.google.com/search?q=site:{domain}"
```

---

### 4. `proxy_loader.py` — Proxy 加载和验证

**职责：** 从 proxy pool 加载、快速验证、排序

**数据源：** `~/scripts/openclaw-tool/proxy/proxy_pool.txt`

```python
PROXY_POOL_FILE = Path.home() / "scripts/openclaw-tool/proxy/proxy_pool.txt"

class ProxyLoader:
    def __init__(self, pool_file: Path = PROXY_POOL_FILE, max_proxies: int = 5):
        """加载 proxy 列表"""

    def load(self) -> list[str]:
        """
        从 proxy_pool.txt 读取 proxy 列表
        格式: 每行一个 http://ip:port
        """

    def quick_validate(self, proxy: str, timeout: int = 5) -> bool:
        """
        快速验证 proxy 是否可用
        - 通过 proxy 访问 https://httpbin.org/ip
        - 超时 5 秒
        - 检查返回的 IP 不是本机 IP
        """

    def get_working_proxies(self) -> list[str]:
        """
        并发验证所有 proxy，返回可用的前 N 个
        使用 ThreadPoolExecutor 并发检查
        """
```

---

## 文件清单

| 文件 | 行数估计 | 说明 |
|------|---------|------|
| `crystal_cdp.py` | ~150 | CLI 入口 + 策略调度主循环 |
| `browser.py` | ~200 | Patchright 浏览器启动/导航/detach |
| `stealth.py` | ~250 | 反检测 JS + 页面检测 + Turnstile 解决 |
| `proxy_loader.py` | ~80 | Proxy 加载和验证 |
| `crystal_cdp` | ~5 | Shell wrapper |
| `requirements.txt` | ~3 | 依赖列表 |
| `.gitignore` | 已有 | 保持不变 |

---

## 依赖

```
patchright>=0.5
requests>=2.28
```

- `patchright`: Stealth Playwright fork（已通过 openclaw-tool 安装）
- `requests`: Proxy 验证用（标准库 urllib 也可替代，但 requests 更方便）

**注意：** 不安装独立 venv，使用 openclaw-tool 的 venv：
```bash
~/scripts/openclaw-tool/.venv/bin/python crystal_cdp.py <url>
```

或在 shell wrapper 中硬编码 python 路径。

---

## 输出设计

### 成功

```
[*] Crystal CDP - Stealth Browser Launcher
[*] Target: https://perplexity.ai
[*] Phase 1: Direct access (no proxy)
[+] Launching Chromium (Default profile)...
[+] Navigating to https://perplexity.ai...
[!] Cloudflare Turnstile detected, solving...
[+] Turnstile solved!
[+] Page loaded successfully!
[*] Browser is open on DISPLAY=:1 - you can continue in VNC.
```

### 需要 Proxy

```
[*] Crystal CDP - Stealth Browser Launcher
[*] Target: https://perplexity.ai
[*] Phase 1: Direct access (no proxy)
[-] Blocked: Cloudflare IP block detected
[*] Phase 2: Trying proxies (5 available)
[*] Proxy 1/5: http://209.97.150.167:3128
[-] Proxy 1 failed: timeout
[*] Proxy 2/5: http://205.209.118.30:3138
[+] Page loaded successfully!
[*] Browser is open on DISPLAY=:1 - you can continue in VNC.
```

### 全部失败

```
[*] Crystal CDP - Stealth Browser Launcher
[*] Target: https://perplexity.ai
[*] Phase 1: Direct access (no proxy)
[-] Blocked: Cloudflare IP block detected
[*] Phase 2: Trying proxies (3 available)
[-] All 3 proxies failed
[!] Could not access https://perplexity.ai

Failure summary:
  - Direct: Cloudflare IP block (your IP is flagged)
  - Proxy 1: Connection timeout
  - Proxy 2: Also blocked by Cloudflare
  - Proxy 3: Proxy returned 502

Suggestions:
  1. Refresh proxy pool: cd ~/scripts/openclaw-tool/proxy && npm run build:list
  2. Try a residential/SOCKS5 proxy: crystal_cdp --proxy socks5://host:port <url>
  3. Try accessing via Tor browser
  4. Wait 15-30 minutes and retry (rate limiting may expire)
  5. Use a VPN with a different exit IP
```

---

## 关键实现细节

### Patchright Persistent Context

```python
# 使用 persistent context 加载 Default profile
# 这样可以保留用户的 cookies、登录状态、扩展等
context = playwright.chromium.launch_persistent_context(
    user_data_dir=str(PROFILE_DIR),
    channel="chromium",
    headless=False,
    args=STEALTH_ARGS,
    proxy={"server": proxy} if proxy else None,
    ignore_https_errors=True,
    viewport=None,           # 使用默认窗口大小，不强制 viewport
    no_viewport=True,        # 让浏览器自己决定 viewport
)
```

### 进程清理

```python
def kill_existing():
    """确保桌面干净"""
    # 找到所有 chromium 进程
    subprocess.run(["pkill", "-f", "chromium"], capture_output=True)
    time.sleep(1)
    # 清理 profile locks
    for lock in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        (PROFILE_DIR / lock).unlink(missing_ok=True)
```

### Detach（程序退出但浏览器保持）

```python
# 成功后：断开 patchright 控制，不关闭浏览器
# playwright.stop() 会释放连接但不杀浏览器进程
# 因为我们用的是 launch（非 connect），需要特殊处理

# 方案：在成功后直接 os._exit(0)
# patchright 的 cleanup handler 不会执行，浏览器继续运行
import os
os._exit(0)
```

### 信号处理

```python
# 用户按 Ctrl+C 时：完全关闭浏览器并清理
import signal

def handle_sigint(sig, frame):
    print("\n[*] Interrupted. Closing browser...")
    browser.close()  # 这里才真正关闭
    sys.exit(1)

signal.signal(signal.SIGINT, handle_sigint)
```

---

## 测试目标

| 网站 | 预期挑战 | 验证标准 |
|------|---------|---------|
| https://perplexity.ai | Cloudflare Turnstile | 页面加载，可以看到搜索框 |
| https://chat.openai.com | Cloudflare + IP 检测 | 页面加载，可以看到登录/聊天界面 |
| https://nowsecure.nl | Bot 检测测试页 | 显示 "passed" |

---

## 后续扩展（不在当前范围）

- 支持 Firefox（不同 fingerprint surface）
- 支持 SOCKS5 proxy
- Proxy 质量评分和持久化
- Cookie 持久化（per-proxy）
- 集成到 openclaw-tool 作为模块
