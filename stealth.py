import re
import time
from enum import Enum
from random import randint
from typing import Optional
from urllib.parse import urlparse


CANVAS_NOISE_JS = """
(function() {
  const _origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
  CanvasRenderingContext2D.prototype.getImageData = function() {
    const imageData = _origGetImageData.apply(this, arguments);
    const data = imageData.data;
    for (let i = 0; i < data.length; i += 4) {
      data[i] = Math.max(0, Math.min(255, data[i] + (Math.random() < 0.1 ? (Math.random() > 0.5 ? 1 : -1) : 0)));
      data[i + 1] = Math.max(0, Math.min(255, data[i + 1] + (Math.random() < 0.1 ? (Math.random() > 0.5 ? 1 : -1) : 0)));
      data[i + 2] = Math.max(0, Math.min(255, data[i + 2] + (Math.random() < 0.1 ? (Math.random() > 0.5 ? 1 : -1) : 0)));
    }
    return imageData;
  };

  const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function() {
    const ctx = this.getContext('2d');
    if (ctx) {
      const imageData = ctx.getImageData(0, 0, this.width, this.height);
      ctx.putImageData(imageData, 0, 0);
    }
    return _origToDataURL.apply(this, arguments);
  };
})();
"""


class PageStatus(Enum):
    SUCCESS = "success"
    CLOUDFLARE_TURNSTILE = "cf_turnstile"
    CLOUDFLARE_BLOCK = "cf_block"
    IP_BLOCKED = "ip_blocked"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    ERROR = "error"


_CF_IFRAME_RE = re.compile(r"^https?://challenges\.cloudflare\.com/cdn-cgi/challenge-platform/.*")


def make_google_referer(url: str) -> str:
    """
    Generate a referer URL that makes the request look like it came from Google Search.
    
    Args:
        url: The target URL.
        
    Returns:
        A Google search URL for the target domain.
    """
    try:
        domain = urlparse(url).netloc or urlparse(url).path.split("/")[0]
    except Exception:
        domain = "example.com"
    return f"https://www.google.com/search?q=site:{domain}"


def inject_stealth_scripts(page) -> None:
    """
    Inject stealth JavaScript into the given playwright page to avoid detection.
    Current injections: Canvas fingerprint noise.
    """
    try:
        page.add_init_script(CANVAS_NOISE_JS)
    except Exception:
        pass


def _safe_lower(value: Optional[str]) -> str:
    """Safely convert a string to lowercase, handling None and exceptions."""
    try:
        return (value or "").lower()
    except Exception:
        return ""


def detect_page_status(page, response_status: Optional[int] = None) -> PageStatus:
    """
    Detect the status of the current page based on content, title, and URL.
    
    Args:
        page: Playwright Page object.
        response_status: HTTP response status code.
        
    Returns:
        PageStatus enum indicating the current state.
    """
    try:
        title = _safe_lower(page.title())
    except Exception:
        title = ""

    try:
        url = _safe_lower(page.url)
    except Exception:
        url = ""

    try:
        content = _safe_lower(page.content())
    except Exception:
        content = ""

    if response_status == 429 or "too many requests" in content:
        return PageStatus.RATE_LIMITED

    if (
        "cf-turnstile" in content
        or "cf_turnstile" in content
        or "turnstile" in content
        or "checking your browser" in content
        or "verify you are human" in content
        or "verifying you are human" in content
        or "challenge-form" in content
        or "/cdn-cgi/challenge-platform/" in url
        or "just a moment" in title
        or "attention required" in title
    ):
        return PageStatus.CLOUDFLARE_TURNSTILE

    if (
        "access denied" in title
        or "access denied" in content
        or "error 1020" in content
        or "cf-error-code" in content
    ):
        return PageStatus.CLOUDFLARE_BLOCK

    if response_status in (401, 403):
        return PageStatus.IP_BLOCKED

    if response_status and response_status >= 400:
        return PageStatus.ERROR

    return PageStatus.SUCCESS


def detect_turnstile_type(html: str) -> Optional[str]:
    """
    Detect the type of Cloudflare Turnstile challenge present in the HTML.
    
    Args:
        html: HTML content of the page.
        
    Returns:
        'embedded', 'interactive', 'non-interactive', or None.
    """
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
    """
    Attempt to automatically solve Cloudflare Turnstile on the page.
    
    Args:
        page: Playwright Page object.
        timeout: Maximum time in seconds to wait for resolution.
        
    Returns:
        True if solved or no challenge detected, False if timed out or failed.
    """
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
