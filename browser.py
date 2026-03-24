import os
import shutil
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

from playwright_backend import (
    BACKEND_NAME,
    PERSISTENT_PROFILE_BACKEND_NAME,
    PersistentProfileTimeoutError,
    PlaywrightTimeoutError,
    persistent_profile_sync_playwright,
    sync_playwright,
)
from stealth import (
    PageStatus,
    detect_page_status,
    enable_resource_filter,
    inject_stealth_scripts,
    make_google_referer,
    solve_turnstile,
)


STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--disable-notifications",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--enforce-webrtc-ip-permission-check",
    "--ignore-certificate-errors",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-timer-throttling",
]
PERSISTENT_PROFILE_ARGS = [
    "--disable-dev-shm-usage",
    "--ignore-certificate-errors",
    "--no-first-run",
    "--no-default-browser-check",
]
SYSTEM_CHROMIUM_PATH = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")


@dataclass
class BrowserFetchResult:
    ok: bool
    status: PageStatus
    final_url: str
    html: str
    title: str
    error: Optional[str] = None


class Browser:
    def __init__(
        self,
        proxy: Optional[str] = None,
        *,
        verbose: bool = False,
        stealth: bool = True,
        display: str = ":1",
        headless: bool = False,
        disable_resources: bool = True,
        locale: str = "en-US",
        timezone_id: str = "America/New_York",
        cookies: Optional[List[dict]] = None,
        user_data_dir: Optional[str] = None,
        profile_name: str = "Default",
        cdp_url: Optional[str] = None,
    ) -> None:
        self.proxy = proxy
        self.verbose = verbose
        self.stealth = stealth
        self.display = display
        self.headless = headless
        self.disable_resources = disable_resources
        self.locale = locale
        self.timezone_id = timezone_id
        self.cookies = list(cookies or [])
        self.user_data_dir = user_data_dir
        self.profile_name = profile_name
        self.cdp_url = cdp_url

        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._timeout_error = PlaywrightTimeoutError
        self._owns_context = True
        self._owns_browser = True

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[browser] {message}", file=sys.stderr)

    def launch(self) -> None:
        if not self.headless:
            os.environ["DISPLAY"] = self.display
        cdp_mode = bool(self.cdp_url)
        persistent_profile = bool(self.user_data_dir) and not cdp_mode
        backend_name = PERSISTENT_PROFILE_BACKEND_NAME if persistent_profile else BACKEND_NAME
        sync_api = persistent_profile_sync_playwright if persistent_profile else sync_playwright
        self._timeout_error = PersistentProfileTimeoutError if persistent_profile else PlaywrightTimeoutError
        self._log(f"playwright backend: {backend_name}")
        self._pw = sync_api().start()
        launch_args = list(PERSISTENT_PROFILE_ARGS if self.user_data_dir else STEALTH_ARGS)
        if cdp_mode:
            self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
            self._owns_browser = False
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
                self._owns_context = False
            else:
                self._context = self._browser.new_context(
                    ignore_https_errors=True,
                    locale=self.locale,
                    timezone_id=self.timezone_id,
                    viewport={"width": 1366, "height": 900},
                    color_scheme="light",
                )
            self._page = self._context.new_page()
        elif self.user_data_dir:
            launch_args.append(f"--profile-directory={self.profile_name}")
            launch_kwargs = {
                "user_data_dir": self.user_data_dir,
                "headless": self.headless,
                "args": launch_args,
                "ignore_https_errors": True,
                "locale": self.locale,
                "timezone_id": self.timezone_id,
                "viewport": {"width": 1366, "height": 900},
                "color_scheme": "light",
                "proxy": {"server": self.proxy} if self.proxy else None,
            }
            if SYSTEM_CHROMIUM_PATH:
                launch_kwargs["executable_path"] = SYSTEM_CHROMIUM_PATH
            else:
                launch_kwargs["channel"] = "chromium"
            self._context = self._pw.chromium.launch_persistent_context(**launch_kwargs)
            self._page = self._context.new_page()
        else:
            launch_kwargs = {
                "headless": self.headless,
                "args": launch_args,
                "proxy": {"server": self.proxy} if self.proxy else None,
            }
            if SYSTEM_CHROMIUM_PATH:
                launch_kwargs["executable_path"] = SYSTEM_CHROMIUM_PATH
            else:
                launch_kwargs["channel"] = "chromium"
            self._browser = self._pw.chromium.launch(**launch_kwargs)
            self._context = self._browser.new_context(
                ignore_https_errors=True,
                locale=self.locale,
                timezone_id=self.timezone_id,
                viewport={"width": 1366, "height": 900},
                color_scheme="light",
            )
            self._page = self._context.new_page()
        self._context.set_default_timeout(30000)
        if self.cookies:
            try:
                self._context.add_cookies(self.cookies)
            except Exception as exc:
                self._log(f"add_cookies failed: {exc}")
        if self.disable_resources:
            enable_resource_filter(self._page)
        if self.stealth:
            inject_stealth_scripts(self._page)

    def get_page(self):
        if not self._page:
            raise RuntimeError("Browser page not initialized")
        return self._page

    def export_cookies(self) -> List[dict]:
        if not self._context:
            return []
        try:
            return self._context.cookies()
        except Exception:
            return []

    def navigate(self, url: str, timeout: int = 30) -> Tuple[PageStatus, Optional[str]]:
        if not self._page:
            raise RuntimeError("Browser not launched")

        timeout_ms = max(1, int(timeout * 1000))
        response_status = None
        try:
            response = self._page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=timeout_ms,
                referer=None if (self.user_data_dir or self.cdp_url) else make_google_referer(url),
            )
            if response is not None:
                try:
                    response_status = response.status
                except Exception:
                    response_status = None
        except self._timeout_error:
            return PageStatus.TIMEOUT, "timeout"
        except Exception as exc:
            return PageStatus.ERROR, str(exc)

        try:
            self._page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
        except Exception:
            pass

        status = detect_page_status(self._page, response_status)
        if status == PageStatus.CLOUDFLARE_TURNSTILE:
            solved = solve_turnstile(self._page, timeout=min(20, timeout))
            if solved:
                status = detect_page_status(self._page, response_status)
            else:
                return status, "turnstile_unsolved"
        return status, None if status == PageStatus.SUCCESS else status.value

    def fetch(self, url: str, timeout: int = 30) -> BrowserFetchResult:
        status, detail = self.navigate(url, timeout=timeout)
        page = self.get_page()
        html = ""
        title = ""
        final_url = url
        try:
            html = page.content()
        except Exception:
            html = ""
        try:
            title = page.title()
        except Exception:
            title = ""
        try:
            final_url = page.url
        except Exception:
            final_url = url
        return BrowserFetchResult(
            ok=status == PageStatus.SUCCESS,
            status=status,
            final_url=final_url,
            html=html,
            title=title,
            error=None if status == PageStatus.SUCCESS else detail,
        )

    def close(self) -> None:
        try:
            if self._page is not None and self.cdp_url:
                self._page.close()
        except Exception:
            pass
        try:
            if self._context is not None and self._owns_context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser is not None and self._owns_browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None
