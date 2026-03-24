#!/usr/bin/env python3
import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from browser import Browser
from content_cleaner import clean_for_llm, extract_links
from cookie_manager import CHROMIUM_PROFILE_ROOT, CookieManager
from http_engine import HttpEngine
from playwright_backend import BACKEND_NAME
from proxy_manager import DEFAULT_MAC_PROXY, DEFAULT_WARP_PROXY, ProxyManager
from stealth import PageStatus


STATUS_MESSAGES = {
    PageStatus.SUCCESS: "success",
    PageStatus.JAVASCRIPT_REQUIRED: "JavaScript rendering required",
    PageStatus.CLOUDFLARE_TURNSTILE: "Cloudflare Turnstile detected",
    PageStatus.CLOUDFLARE_BLOCK: "Cloudflare IP block detected",
    PageStatus.IP_BLOCKED: "Target site blocked the current egress IP",
    PageStatus.RATE_LIMITED: "Rate limited",
    PageStatus.TIMEOUT: "Connection timeout",
    PageStatus.ERROR: "Unexpected error",
}
HTTP_UPGRADE_STATUSES = {
    PageStatus.JAVASCRIPT_REQUIRED,
    PageStatus.CLOUDFLARE_TURNSTILE,
}
MODE_ORDER = ("http", "headless", "headed")
__all__ = [
    "AttemptRecord",
    "Crystal",
    "FetchResult",
    "OpenResult",
    "build_mode_order",
    "format_status",
    "normalize_url",
]


def normalize_url(url: str) -> str:
    if "://" not in url:
        return "https://" + url
    return url


def format_status(status: PageStatus, detail: Optional[str]) -> str:
    base = STATUS_MESSAGES.get(status, status.value)
    if detail and detail not in {"timeout", status.value}:
        return f"{base} ({detail})"
    return base


def build_mode_order(start_mode: str, auto_upgrade: bool = True) -> List[str]:
    lowered = (start_mode or "http").strip().lower()
    if lowered not in MODE_ORDER:
        lowered = "http"
    start_index = MODE_ORDER.index(lowered)
    if not auto_upgrade:
        return [MODE_ORDER[start_index]]
    return list(MODE_ORDER[start_index:])


@dataclass
class AttemptRecord:
    mode: str
    proxy: str
    ok: bool
    status: str
    error: Optional[str] = None
    final_url: Optional[str] = None


@dataclass
class FetchResult:
    ok: bool
    url: str
    text: str = ""
    html: str = ""
    links: List[dict] = field(default_factory=list)
    mode_used: Optional[str] = None
    proxy_used: Optional[str] = None
    elapsed_ms: int = 0
    error: Optional[str] = None
    attempts: List[AttemptRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "url": self.url,
            "text": self.text,
            "html": self.html,
            "links": self.links,
            "mode_used": self.mode_used,
            "proxy_used": self.proxy_used,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "attempts": [attempt.__dict__ for attempt in self.attempts],
        }


@dataclass
class OpenResult:
    ok: bool
    url: str
    page: Any = None
    browser: Optional[Browser] = None
    mode_used: Optional[str] = None
    proxy_used: Optional[str] = None
    elapsed_ms: int = 0
    error: Optional[str] = None
    attempts: List[AttemptRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "url": self.url,
            "mode_used": self.mode_used,
            "proxy_used": self.proxy_used,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "attempts": [attempt.__dict__ for attempt in self.attempts],
        }


class Crystal:
    def __init__(
        self,
        *,
        proxy: str = "auto",
        mode: str = "http",
        auto_upgrade: bool = True,
        timeout_ms: int = 15000,
        max_text_chars: int = 50000,
        warp_proxy: str = DEFAULT_WARP_PROXY,
        mac_proxy: str = DEFAULT_MAC_PROXY,
        display: str = ":1",
        verbose: bool = False,
        disable_resources: bool = True,
        locale: str = "en-US",
        timezone_id: str = "America/New_York",
        use_persistent_profile: bool = False,
        profile_root: str | None = None,
        profile_name: str = "Default",
        cdp_url: str | None = None,
    ) -> None:
        self.default_proxy = proxy
        self.default_mode = mode
        self.default_auto_upgrade = auto_upgrade
        self.default_timeout_ms = timeout_ms
        self.default_max_text_chars = max_text_chars
        self.display = display
        self.verbose = verbose
        self.disable_resources = disable_resources
        self.locale = locale
        self.timezone_id = timezone_id
        self.use_persistent_profile = use_persistent_profile
        self.profile_root = Path(profile_root).expanduser() if profile_root else CHROMIUM_PROFILE_ROOT
        self.profile_name = profile_name
        self.cdp_url = cdp_url

        self.cookie_manager = CookieManager(profile_root=self.profile_root, profile_name=self.profile_name)
        self.proxy_manager = ProxyManager(warp_proxy=warp_proxy, mac_proxy=mac_proxy)
        self.http_engine = HttpEngine(verbose=verbose)

    def health(self) -> dict:
        return {
            "default_proxy": self.default_proxy,
            "default_mode": self.default_mode,
            "use_persistent_profile": self.use_persistent_profile,
            "profile_name": self.profile_name,
            "cdp_url": self.cdp_url,
            "proxy_health": self.proxy_manager.health_snapshot(),
            "playwright_backend": BACKEND_NAME,
        }

    def fetch(
        self,
        url: str,
        *,
        mode: Optional[str] = None,
        proxy: Optional[str] = None,
        auto_upgrade: Optional[bool] = None,
        timeout_ms: Optional[int] = None,
        max_text_chars: Optional[int] = None,
    ) -> FetchResult:
        normalized_url = normalize_url(url)
        started = time.time()
        attempts: List[AttemptRecord] = []
        mode_order = build_mode_order(mode or self.default_mode, self._resolve_auto_upgrade(auto_upgrade))
        proxy_targets = self.proxy_manager.resolve_targets(proxy or self.default_proxy)
        timeout_value = self._resolve_timeout(timeout_ms)
        text_limit = max(1000, int(max_text_chars or self.default_max_text_chars))

        last_error = "no_attempts"
        for current_mode in mode_order:
            for target in proxy_targets:
                if current_mode == "http":
                    http_result = self.http_engine.fetch(
                        normalized_url,
                        proxy=target.server,
                        timeout_ms=timeout_value,
                        cookie_header=self.cookie_manager.build_cookie_header(normalized_url) or None,
                    )
                    attempt = AttemptRecord(
                        mode="http",
                        proxy=target.name,
                        ok=http_result.ok,
                        status=http_result.status.value,
                        error=http_result.error,
                        final_url=http_result.final_url,
                    )
                    attempts.append(attempt)
                    if http_result.ok:
                        return self._build_fetch_result(
                            url=http_result.final_url or normalized_url,
                            html=http_result.html,
                            mode_used="http",
                            proxy_used=target.name,
                            attempts=attempts,
                            started=started,
                            max_text_chars=text_limit,
                        )
                    last_error = attempt.error or attempt.status
                    if http_result.status in HTTP_UPGRADE_STATUSES:
                        break
                    continue

                browser = None
                try:
                    browser = self._build_browser(current_mode, target.server, normalized_url)
                    browser.launch()
                    browser_attempt = browser.fetch(normalized_url, timeout=max(3, int(timeout_value / 1000)))
                except Exception as exc:
                    browser_attempt = None
                    last_error = str(exc)
                    attempts.append(
                        AttemptRecord(
                            mode=current_mode,
                            proxy=target.name,
                            ok=False,
                            status=PageStatus.ERROR.value,
                            error=str(exc),
                        )
                    )
                else:
                    if browser_attempt.ok:
                        self._remember_cookies(normalized_url, browser.export_cookies())
                        result = self._build_fetch_result(
                            url=browser_attempt.final_url or normalized_url,
                            html=browser_attempt.html,
                            mode_used=current_mode,
                            proxy_used=target.name,
                            attempts=attempts
                            + [
                                AttemptRecord(
                                    mode=current_mode,
                                    proxy=target.name,
                                    ok=True,
                                    status=browser_attempt.status.value,
                                    final_url=browser_attempt.final_url,
                                )
                            ],
                            started=started,
                            max_text_chars=text_limit,
                        )
                        browser.close()
                        return result
                    last_error = browser_attempt.error or browser_attempt.status.value
                    attempts.append(
                        AttemptRecord(
                            mode=current_mode,
                            proxy=target.name,
                            ok=False,
                            status=browser_attempt.status.value,
                            error=browser_attempt.error,
                            final_url=browser_attempt.final_url,
                        )
                    )
                finally:
                    if browser is not None:
                        browser.close()

        return FetchResult(
            ok=False,
            url=normalized_url,
            elapsed_ms=int((time.time() - started) * 1000),
            error=last_error,
            attempts=attempts,
        )

    def open(
        self,
        url: str,
        *,
        mode: Optional[str] = None,
        proxy: Optional[str] = None,
        auto_upgrade: Optional[bool] = None,
        timeout_ms: Optional[int] = None,
    ) -> OpenResult:
        normalized_url = normalize_url(url)
        started = time.time()
        attempts: List[AttemptRecord] = []
        mode_order = [item for item in build_mode_order(mode or self.default_mode, self._resolve_auto_upgrade(auto_upgrade)) if item != "http"]
        if not mode_order:
            mode_order = ["headless", "headed"]
        proxy_targets = self.proxy_manager.resolve_targets(proxy or self.default_proxy)
        timeout_value = self._resolve_timeout(timeout_ms)
        last_error = "no_attempts"

        for current_mode in mode_order:
            for target in proxy_targets:
                browser = None
                try:
                    browser = self._build_browser(current_mode, target.server, normalized_url)
                    browser.launch()
                    status, detail = browser.navigate(normalized_url, timeout=max(3, int(timeout_value / 1000)))
                    if status == PageStatus.SUCCESS:
                        self._remember_cookies(normalized_url, browser.export_cookies())
                        attempts.append(
                            AttemptRecord(
                                mode=current_mode,
                                proxy=target.name,
                                ok=True,
                                status=status.value,
                                final_url=browser.get_page().url,
                            )
                        )
                        return OpenResult(
                            ok=True,
                            url=browser.get_page().url,
                            page=browser.get_page(),
                            browser=browser,
                            mode_used=current_mode,
                            proxy_used=target.name,
                            elapsed_ms=int((time.time() - started) * 1000),
                            attempts=attempts,
                        )
                    last_error = detail or status.value
                    attempts.append(
                        AttemptRecord(
                            mode=current_mode,
                            proxy=target.name,
                            ok=False,
                            status=status.value,
                            error=detail,
                        )
                    )
                except Exception as exc:
                    last_error = str(exc)
                    attempts.append(
                        AttemptRecord(
                            mode=current_mode,
                            proxy=target.name,
                            ok=False,
                            status=PageStatus.ERROR.value,
                            error=str(exc),
                        )
                    )
                if browser is not None:
                    browser.close()

        return OpenResult(
            ok=False,
            url=normalized_url,
            elapsed_ms=int((time.time() - started) * 1000),
            error=last_error,
            attempts=attempts,
        )

    def _resolve_timeout(self, timeout_ms: Optional[int]) -> int:
        return max(3000, int(timeout_ms or self.default_timeout_ms))

    def _resolve_auto_upgrade(self, auto_upgrade: Optional[bool]) -> bool:
        return self.default_auto_upgrade if auto_upgrade is None else bool(auto_upgrade)

    def _build_browser(self, mode: str, proxy_server: Optional[str], url: str) -> Browser:
        use_cdp = bool(self.cdp_url) and mode == "headed"
        use_profile = self.use_persistent_profile and mode == "headed" and not use_cdp
        cookies = [] if (use_profile or use_cdp) else self.cookie_manager.get_cookies_for_url(url)
        return Browser(
            proxy=proxy_server,
            verbose=self.verbose,
            stealth=not (use_profile or use_cdp),
            display=self.display,
            headless=mode == "headless",
            disable_resources=self.disable_resources if not (use_profile or use_cdp) else False,
            locale=self.locale,
            timezone_id=self.timezone_id,
            cookies=cookies,
            user_data_dir=str(self.profile_root) if use_profile else None,
            profile_name=self.profile_name,
            cdp_url=self.cdp_url if use_cdp else None,
        )

    def _remember_cookies(self, url: str, cookies: List[dict]) -> None:
        self.cookie_manager.remember_cookies(url, cookies)

    def _build_fetch_result(
        self,
        *,
        url: str,
        html: str,
        mode_used: str,
        proxy_used: str,
        attempts: List[AttemptRecord],
        started: float,
        max_text_chars: int,
    ) -> FetchResult:
        text = clean_for_llm(html, url, max_chars=max_text_chars)
        links = extract_links(html, url)
        return FetchResult(
            ok=True,
            url=url,
            text=text,
            html=html,
            links=links,
            mode_used=mode_used,
            proxy_used=proxy_used,
            elapsed_ms=int((time.time() - started) * 1000),
            attempts=attempts,
        )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crystal CDP library helper")
    parser.add_argument("url", nargs="?", help="Target URL for one-shot fetch")
    parser.add_argument("--mode", default="http", choices=list(MODE_ORDER), help="Start mode")
    parser.add_argument(
        "--proxy",
        default="auto",
        help="auto|warp|mac|direct|<custom proxy url>",
    )
    parser.add_argument("--timeout-ms", type=int, default=15000, help="Timeout per attempt")
    parser.add_argument("--max-text-chars", type=int, default=50000, help="Trim cleaned text")
    parser.add_argument("--no-auto-upgrade", action="store_true", help="Disable engine upgrades")
    parser.add_argument("--json", action="store_true", help="Print one-shot result as JSON")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    crystal = Crystal(
        proxy=args.proxy,
        mode=args.mode,
        auto_upgrade=not args.no_auto_upgrade,
        timeout_ms=args.timeout_ms,
        max_text_chars=args.max_text_chars,
        verbose=args.verbose,
    )

    if not args.url:
        parser.error("url is required")

    result = crystal.fetch(
        args.url,
        mode=args.mode,
        proxy=args.proxy,
        auto_upgrade=not args.no_auto_upgrade,
        timeout_ms=args.timeout_ms,
        max_text_chars=args.max_text_chars,
    )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        if result.ok:
            print(result.text)
        else:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
