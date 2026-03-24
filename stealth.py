import re
import time
from enum import Enum
from random import randint
from typing import Optional
from urllib.parse import urlparse


STEALTH_INIT_JS = """
(() => {
  const patch = (obj, key, getter) => {
    try {
      Object.defineProperty(obj, key, { get: getter, configurable: true });
    } catch (err) {}
  };

  patch(Navigator.prototype, 'webdriver', () => undefined);
  patch(Navigator.prototype, 'languages', () => ['en-US', 'en']);
  patch(Navigator.prototype, 'language', () => 'en-US');
  patch(Navigator.prototype, 'plugins', () => [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
  ]);
  patch(Navigator.prototype, 'mimeTypes', () => [
    { type: 'application/pdf' },
    { type: 'text/pdf' },
  ]);
  patch(Navigator.prototype, 'maxTouchPoints', () => 0);
  patch(Navigator.prototype, 'hardwareConcurrency', () => 8);
  patch(Navigator.prototype, 'deviceMemory', () => 8);

  if (!window.chrome) {
    window.chrome = {};
  }
  if (!window.chrome.runtime) {
    window.chrome.runtime = {};
  }
  if (!window.chrome.app) {
    window.chrome.app = {
      InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
      RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
      isInstalled: false,
    };
  }

  const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
  if (originalQuery) {
    window.navigator.permissions.query = (parameters) => (
      parameters && parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters)
    );
  }

  const getParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Open Source Technology Center';
    if (parameter === 37446) return 'Mesa DRI Intel(R) UHD Graphics';
    return getParameter.call(this, parameter);
  };

  if (window.outerWidth === 0 || window.outerHeight === 0) {
    patch(window, 'outerWidth', () => window.innerWidth);
    patch(window, 'outerHeight', () => window.innerHeight + 72);
  }
})();
"""

TRACKING_PATTERNS = (
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "adsystem",
    "adservice",
    "segment.io",
    "hotjar",
)
_CF_IFRAME_RE = re.compile(r"^https?://challenges\.cloudflare\.com/cdn-cgi/challenge-platform/.*")


class PageStatus(Enum):
    SUCCESS = "success"
    JAVASCRIPT_REQUIRED = "javascript_required"
    CLOUDFLARE_TURNSTILE = "cf_turnstile"
    CLOUDFLARE_BLOCK = "cf_block"
    IP_BLOCKED = "ip_blocked"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    ERROR = "error"


def make_google_referer(url: str) -> str:
    try:
        domain = urlparse(url).netloc or urlparse(url).path.split("/")[0]
    except Exception:
        domain = "example.com"
    return f"https://www.google.com/search?q=site:{domain}"


def inject_stealth_scripts(page) -> None:
    try:
        page.add_init_script(STEALTH_INIT_JS)
    except Exception:
        pass


def enable_resource_filter(page) -> None:
    def handle_route(route):
        request = route.request
        try:
            resource_type = request.resource_type
            request_url = request.url.lower()
        except Exception:
            return route.continue_()
        if resource_type in {"image", "media", "font"}:
            return route.abort()
        if any(token in request_url for token in TRACKING_PATTERNS):
            return route.abort()
        return route.continue_()

    try:
        page.route("**/*", handle_route)
    except Exception:
        pass


def _safe_lower(value: Optional[str]) -> str:
    try:
        return (value or "").lower()
    except Exception:
        return ""


def detect_html_status(
    html: str,
    url: str = "",
    status_code: Optional[int] = None,
    content_type: Optional[str] = None,
) -> PageStatus:
    content = _safe_lower(html)
    lowered_url = _safe_lower(url)
    lowered_type = _safe_lower(content_type)

    if status_code == 429 or "too many requests" in content:
        return PageStatus.RATE_LIMITED
    if status_code in (401, 403):
        if "cloudflare" in content or "error 1020" in content:
            return PageStatus.CLOUDFLARE_BLOCK
        return PageStatus.IP_BLOCKED
    if status_code and status_code >= 500 and "just a moment" in content:
        return PageStatus.CLOUDFLARE_TURNSTILE
    if (
        "/cdn-cgi/challenge-platform/" in lowered_url
        or "cf-turnstile" in content
        or "cf_turnstile" in content
        or "turnstile" in content
        or "checking your browser" in content
        or "verify you are human" in content
        or "verifying you are human" in content
        or "just a moment" in content
        or "attention required" in content
    ):
        return PageStatus.CLOUDFLARE_TURNSTILE
    if "access denied" in content or "error 1020" in content or "cf-error-code" in content:
        return PageStatus.CLOUDFLARE_BLOCK
    if (
        "enable javascript" in content
        or "javascript is required" in content
        or "please turn javascript on" in content
        or ("text/html" in lowered_type and "<script" in content and "<body" in content and len(content) < 5000)
    ):
        return PageStatus.JAVASCRIPT_REQUIRED
    if status_code and status_code >= 400:
        return PageStatus.ERROR
    return PageStatus.SUCCESS


def detect_page_status(page, response_status: Optional[int] = None) -> PageStatus:
    try:
        page_html = page.content()
    except Exception:
        page_html = ""
    try:
        page_url = page.url
    except Exception:
        page_url = ""
    try:
        title = page.title()
    except Exception:
        title = ""

    status = detect_html_status(page_html + "\n" + title, page_url, response_status, "text/html")
    return status


def detect_turnstile_type(html: str) -> Optional[str]:
    low = _safe_lower(html)
    if "<title>just a moment" not in low:
        if "cf_turnstile" in low or "cf-turnstile" in low:
            return "embedded"
        if "verify you are human" in low:
            return "interactive"
        return None
    if "verifying you are human" in low or "verify you are human" in low:
        return "interactive"
    if "/cdn-cgi/challenge-platform/" in low or "challenge-form" in low:
        return "non-interactive"
    return "non-interactive"


def solve_turnstile(page, timeout: int = 20) -> bool:
    try:
        html = page.content() or ""
    except Exception:
        return True

    challenge_type = detect_turnstile_type(html)
    if not challenge_type:
        return True

    if challenge_type == "non-interactive":
        start = time.time()
        while time.time() - start < timeout:
            try:
                page.wait_for_timeout(1000)
                page.wait_for_load_state("load", timeout=3000)
            except Exception:
                pass
            try:
                cur_html = page.content() or ""
            except Exception:
                cur_html = ""
            if detect_turnstile_type(cur_html) is None:
                return True
        return False

    try:
        box_selector = "#cf_turnstile div, #cf-turnstile div, .turnstile>div>div"
        if challenge_type == "interactive":
            box_selector = ".main-content p+div>div>div"

        iframe = page.frame(url=_CF_IFRAME_RE)
        outer_box = None
        if iframe is not None:
            try:
                page.wait_for_timeout(1500)
                frame_el = iframe.frame_element()
                outer_box = frame_el.bounding_box()
            except Exception:
                outer_box = None

        if not outer_box:
            try:
                outer_box = page.locator(box_selector).last.bounding_box()
            except Exception:
                outer_box = None

        if not outer_box:
            return False

        click_x = outer_box["x"] + randint(26, 28)
        click_y = outer_box["y"] + randint(25, 27)
        page.mouse.click(click_x, click_y, delay=randint(100, 200), button="left")

        start = time.time()
        while time.time() - start < timeout:
            try:
                page.wait_for_timeout(500)
            except Exception:
                pass
            try:
                cur_html = page.content() or ""
            except Exception:
                cur_html = ""
            if detect_turnstile_type(cur_html) is None:
                return True
        return False
    except Exception:
        return False
