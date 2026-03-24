import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from playwright_backend import persistent_profile_sync_playwright

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except Exception:  # pragma: no cover
    Cipher = None
    algorithms = None
    modes = None
    default_backend = None

COOKIE_EPOCH_OFFSET = 11644473600
CHROMIUM_PROFILE_ROOT = Path.home() / ".config" / "chromium"
SYSTEM_CHROMIUM_PATH = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")


def chromium_timestamp_to_unix(value: int) -> Optional[int]:
    if not value:
        return None
    if value < 0:
        return None
    return max(0, int(value / 1_000_000) - COOKIE_EPOCH_OFFSET)


def _candidate_domains(hostname: str) -> List[str]:
    host = (hostname or "").strip(".").lower()
    if not host:
        return []
    parts = host.split(".")
    candidates = {host, "." + host}
    for index in range(1, len(parts) - 1):
        suffix = ".".join(parts[index:])
        candidates.add(suffix)
        candidates.add("." + suffix)
    return sorted(candidates)


class CookieManager:
    def __init__(
        self,
        profile_root: Path = CHROMIUM_PROFILE_ROOT,
        profile_name: str = "Default",
        browser_timeout_ms: int = 10000,
    ) -> None:
        self.profile_root = Path(profile_root).expanduser()
        self.profile_name = profile_name
        self.browser_timeout_ms = browser_timeout_ms
        self.cookie_db = self.profile_root / profile_name / "Cookies"
        self.local_state_path = self.profile_root / "Local State"
        self._cache: dict[str, List[dict]] = {}

    def get_cookies_for_url(self, url: str) -> List[dict]:
        hostname = (urlparse(url).hostname or "").lower()
        if not hostname:
            return []
        if hostname in self._cache:
            return list(self._cache[hostname])
        cookies = self._read_sqlite_cookies(hostname)
        if not cookies:
            cookies = self._export_cookies_from_browser(url)
        self._cache[hostname] = list(cookies)
        return cookies

    def build_cookie_header(self, url: str) -> str:
        pairs = []
        for cookie in self.get_cookies_for_url(url):
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value is not None:
                pairs.append(f"{name}={value}")
        return "; ".join(pairs)

    def remember_cookies(self, url: str, cookies: List[dict]) -> None:
        hostname = (urlparse(url).hostname or "").lower()
        if hostname:
            self._cache[hostname] = list(cookies)

    def _read_sqlite_cookies(self, hostname: str) -> List[dict]:
        if not self.cookie_db.exists():
            return []
        tmp_path = Path(tempfile.gettempdir()) / f"crystal-cookies-{self.profile_name}.db"
        try:
            shutil.copy2(self.cookie_db, tmp_path)
        except OSError:
            return []

        rows: List[sqlite3.Row]
        query_domains = _candidate_domains(hostname)
        placeholders = ",".join("?" for _ in query_domains) or "?"
        try:
            conn = sqlite3.connect(tmp_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT host_key, name, value, encrypted_value, path, expires_utc,
                       is_secure, is_httponly, samesite
                FROM cookies
                WHERE host_key IN ({placeholders})
                ORDER BY length(host_key) DESC
                """,
                query_domains or [hostname],
            ).fetchall()
            conn.close()
        except sqlite3.Error:
            return []

        cookies: List[dict] = []
        for row in rows:
            value = row["value"] or self._decrypt_cookie_value(row["encrypted_value"])
            if not value:
                continue
            cookie = {
                "name": row["name"],
                "value": value,
                "domain": row["host_key"],
                "path": row["path"] or "/",
                "secure": bool(row["is_secure"]),
                "httpOnly": bool(row["is_httponly"]),
            }
            expires = chromium_timestamp_to_unix(int(row["expires_utc"] or 0))
            if expires:
                cookie["expires"] = expires
            same_site = self._map_same_site(row["samesite"])
            if same_site:
                cookie["sameSite"] = same_site
            cookies.append(cookie)
        return cookies

    def _decrypt_cookie_value(self, encrypted_value: bytes) -> str:
        if not encrypted_value:
            return ""
        payload = bytes(encrypted_value)
        if not payload.startswith((b"v10", b"v11")):
            try:
                return payload.decode("utf-8")
            except UnicodeDecodeError:
                return ""
        return self._decrypt_linux_cookie(payload[3:])

    def _decrypt_linux_cookie(self, payload: bytes) -> str:
        if Cipher is None:
            return ""
        key = hashlib.pbkdf2_hmac("sha1", b"peanuts", b"saltysalt", 1, 16)
        try:
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(b" " * 16),
                backend=default_backend(),
            )
            decryptor = cipher.decryptor()
            decrypted = decryptor.update(payload) + decryptor.finalize()
            padding = decrypted[-1]
            if padding < 1 or padding > 16:
                return ""
            value = decrypted[:-padding]
            return value.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _map_same_site(self, value: int) -> Optional[str]:
        return {
            0: "None",
            1: "Lax",
            2: "Strict",
        }.get(int(value or 0))

    def _export_cookies_from_browser(self, url: str) -> List[dict]:
        if not self.profile_root.exists():
            return []
        args = [
            "--disable-dev-shm-usage",
            "--ignore-certificate-errors",
            "--no-first-run",
            "--no-default-browser-check",
            f"--profile-directory={self.profile_name}",
        ]
        playwright = None
        context = None
        try:
            playwright = persistent_profile_sync_playwright().start()
            launch_kwargs = {
                "user_data_dir": str(self.profile_root),
                "headless": True,
                "args": args,
                "ignore_https_errors": True,
            }
            if SYSTEM_CHROMIUM_PATH:
                launch_kwargs["executable_path"] = SYSTEM_CHROMIUM_PATH
            else:
                launch_kwargs["channel"] = "chromium"
            context = playwright.chromium.launch_persistent_context(**launch_kwargs)
            return context.cookies([url])
        except Exception:
            return []
        finally:
            try:
                if context is not None:
                    context.close()
            except Exception:
                pass
            try:
                if playwright is not None:
                    playwright.stop()
            except Exception:
                pass

    def local_state(self) -> dict:
        if not self.local_state_path.exists():
            return {}
        try:
            return json.loads(self.local_state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
