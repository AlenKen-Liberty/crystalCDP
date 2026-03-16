#!/usr/bin/env python3
import argparse
import os
import signal
import sys
from typing import List, Optional, Tuple

from browser import Browser
from proxy_loader import ProxyLoader
from stealth import PageStatus


STATUS_MESSAGES = {
    PageStatus.CLOUDFLARE_TURNSTILE: "Cloudflare Turnstile detected",
    PageStatus.CLOUDFLARE_BLOCK: "Cloudflare IP block detected",
    PageStatus.IP_BLOCKED: "Target site blocked your IP",
    PageStatus.RATE_LIMITED: "Rate limited",
    PageStatus.TIMEOUT: "Connection timeout",
    PageStatus.ERROR: "Unexpected error",
}


def normalize_url(url: str) -> str:
    """
    Ensure the URL has a scheme (defaults to https://).
    
    Args:
        url: The input URL string.
        
    Returns:
        The normalized URL.
    """
    if "://" not in url:
        return "https://" + url
    return url


def format_status(status: PageStatus, detail: Optional[str]) -> str:
    """
    Format the page status and detail into a human-readable string.
    
    Args:
        status: The PageStatus enum value.
        detail: Optional detailed error message.
        
    Returns:
        A formatted status message.
    """
    base = STATUS_MESSAGES.get(status, status.value)
    if detail and detail != "timeout":
        return f"{base} ({detail})"
    return base


def print_header(url: str) -> None:
    """Print the tool header and target URL."""
    print("[*] Crystal CDP - Stealth Browser Launcher")
    print(f"[*] Target: {url}")


def main() -> int:
    """
    Main entry point for Crystal CDP.
    Parses arguments, orchestrates direct and proxied browser launch attempts.
    """
    parser = argparse.ArgumentParser(description="Crystal CDP - Stealth Browser Launcher")
    parser.add_argument("url", help="Target URL")
    parser.add_argument("--proxy-only", action="store_true", help="Skip direct access and use proxies only")
    parser.add_argument("--proxy", default=None, help="Specify a single proxy to use")
    parser.add_argument("--max-proxies", type=int, default=10, help="Maximum proxies to try (default: 10)")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per attempt in seconds (default: 30)")
    parser.add_argument("--no-stealth", action="store_true", help="Disable stealth JS injection")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    url = normalize_url(args.url)
    timeout = max(5, int(args.timeout))
    max_proxies = max(0, int(args.max_proxies))

    os.environ.setdefault("DISPLAY", ":1")

    current_browser: Optional[Browser] = None

    def handle_sigint(sig, frame):
        print("\n[*] Interrupted. Closing browser...")
        if current_browser:
            current_browser.close()
        sys.exit(1)

    signal.signal(signal.SIGINT, handle_sigint)

    print_header(url)

    failures: List[Tuple[str, str]] = []

    def attempt(label: str, proxy: Optional[str]) -> Tuple[bool, PageStatus]:
        nonlocal current_browser
        print(f"[+] Launching Chromium (Default profile)...")
        browser = Browser(proxy=proxy, verbose=args.verbose, stealth=not args.no_stealth)
        current_browser = browser
        try:
            browser.launch()
            print(f"[+] Navigating to {url}...")
            status, detail = browser.navigate(url, timeout=timeout)
        except Exception as exc:
            status = PageStatus.ERROR
            detail = str(exc)
        if status == PageStatus.SUCCESS:
            print("[+] Page loaded successfully!")
            print("[*] Browser is open on DISPLAY=:1 - you can continue in VNC.")
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            finally:
                os._exit(0)
        else:
            reason = format_status(status, detail)
            print(f"[-] {label} failed: {reason}")
            failures.append((label, reason))
            browser.close()
            return False, status

    if not args.proxy_only:
        print("[*] Phase 1: Direct access (no proxy)")
        attempt("Direct", None)

    proxies: List[str] = []
    if args.proxy:
        proxies = [args.proxy]
    elif max_proxies == 0:
        proxies = []
    else:
        loader = ProxyLoader(max_proxies=max_proxies)
        proxies = loader.get_working_proxies()

    print(f"[*] Phase 2: Trying proxies ({len(proxies)} available)")
    if not proxies:
        print("[-] No working proxies available")
        failures.append(("Proxy", "No working proxies available"))
    else:
        for idx, proxy in enumerate(proxies, start=1):
            print(f"[*] Proxy {idx}/{len(proxies)}: {proxy}")
            attempt(f"Proxy {idx}", proxy)

    print(f"[!] Could not access {url}")
    if failures:
        print("\nFailure summary:")
        for label, reason in failures:
            print(f"  - {label}: {reason}")

    print("\nSuggestions:")
    print("  1. Refresh proxy pool: cd ~/scripts/openclaw-tool/proxy && npm run build:list")
    print("  2. Try a residential/SOCKS5 proxy: crystal_cdp --proxy socks5://host:port <url>")
    print("  3. Try accessing via Tor browser")
    print("  4. Wait 15-30 minutes and retry (rate limiting may expire)")
    print("  5. Use a VPN with a different exit IP")
    return 1


if __name__ == "__main__":
    sys.exit(main())
