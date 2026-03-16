import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

try:
    from patchright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except Exception:  # pragma: no cover
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from stealth import PageStatus, detect_page_status, inject_stealth_scripts, make_google_referer, solve_turnstile


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


class Browser:
    """Manages the lifecycle of a Patchright/Playwright chromium browser instance."""
    
    def __init__(
        self,
        proxy: Optional[str] = None,
        verbose: bool = False,
        stealth: bool = True,
        profile_dir: Optional[Path] = None,
        profile_name: str = "Default",
        display: str = ":1",
    ) -> None:
        """
        Initialize the Browser configuration.
        
        Args:
            proxy: Proxy URL to use (e.g., http://ip:port).
            verbose: Enable verbose logging.
            stealth: Enable stealth configurations and injections.
            profile_dir: Path to the browser profile directory.
            profile_name: Name of the profile to load.
            display: X11 display to launch the browser on.
        """
        self.proxy = proxy
        self.verbose = verbose
        self.stealth = stealth
        self.profile_dir = profile_dir or (Path.home() / ".config" / "chromium")
        self.profile_name = profile_name
        self.display = display

        self._pw = None
        self._context = None

    def _log(self, message: str) -> None:
        """Log messages if verbose mode is enabled."""
        if self.verbose:
            print(f"[browser] {message}", file=sys.stderr)

    def kill_existing(self) -> None:
        """Kill any existing chromium processes and remove profile locks to prevent startup issues."""
        try:
            subprocess.run(["pkill", "-f", "chromium"], capture_output=True, check=False)
            time.sleep(1)
        except Exception:
            pass

        for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
            try:
                (self.profile_dir / lock_file).unlink(missing_ok=True)
            except Exception:
                pass

    def launch(self) -> None:
        """
        Launch the persistent chromium context with stealth arguments and profile.
        Requires DISPLAY to be set correctly.
        """
        os.environ["DISPLAY"] = self.display
        self.kill_existing()

        self._pw = sync_playwright().start()
        args = list(STEALTH_ARGS)
        if self.profile_name:
            args.append(f"--profile-directory={self.profile_name}")

        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            channel="chromium",
            headless=False,
            args=args,
            proxy={"server": self.proxy} if self.proxy else None,
            ignore_https_errors=True,
            viewport=None,
            no_viewport=True,
        )
        self._context.set_default_timeout(30000)

    def get_page(self):
        """
        Get the currently active page in the context, or create a new one.
        
        Returns:
            The playwright Page object.
        """
        if not self._context:
            raise RuntimeError("Browser context not initialized")
        for page in self._context.pages:
            try:
                if not page.is_closed():
                    return page
            except Exception:
                continue
        return self._context.new_page()

    def navigate(self, url: str, timeout: int = 30) -> Tuple[PageStatus, Optional[str]]:
        """
        Navigate to a URL and wait for load state, handling stealth injections and Cloudflare bypass.
        
        Args:
            url: Target URL to navigate to.
            timeout: Navigation timeout in seconds.
            
        Returns:
            Tuple containing the final PageStatus and an optional detail string (e.g. error message).
        """
        if not self._context:
            raise RuntimeError("Browser not launched")

        page = self.get_page()
        if self.stealth:
            inject_stealth_scripts(page)

        timeout_ms = max(1, int(timeout * 1000))
        response_status = None
        try:
            response = page.goto(
                url,
                wait_until="load",
                timeout=timeout_ms,
                referer=make_google_referer(url),
            )
            if response is not None:
                try:
                    response_status = response.status
                except Exception:
                    response_status = None
        except PlaywrightTimeoutError:
            return PageStatus.TIMEOUT, "timeout"
        except Exception as exc:
            return PageStatus.ERROR, str(exc)

        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        status = detect_page_status(page, response_status)
        if status == PageStatus.CLOUDFLARE_TURNSTILE:
            print("[!] Cloudflare Turnstile detected, solving...")
            solved = solve_turnstile(page, timeout=min(20, timeout))
            if solved:
                print("[+] Turnstile solved!")
                status = detect_page_status(page, response_status)
            else:
                return status, "turnstile_unsolved"

        return status, None

    def close(self) -> None:
        """
        Close the browser context and cleanly exit the playwright instance.
        If navigation succeeds, this is typically bypassed to leave the browser running.
        """
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._context = None
        self._pw = None
