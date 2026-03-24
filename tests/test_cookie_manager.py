import sqlite3
from pathlib import Path

from cookie_manager import CookieManager, chromium_timestamp_to_unix


def test_chromium_timestamp_to_unix():
    assert chromium_timestamp_to_unix(0) is None
    assert chromium_timestamp_to_unix(11644473600 * 1_000_000) == 0


def test_cookie_manager_reads_plain_sqlite_cookie(tmp_path):
    profile_root = tmp_path / "chromium"
    default_dir = profile_root / "Default"
    default_dir.mkdir(parents=True)
    db_path = default_dir / "Cookies"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE cookies (
            host_key TEXT,
            name TEXT,
            value TEXT,
            encrypted_value BLOB,
            path TEXT,
            expires_utc INTEGER,
            is_secure INTEGER,
            is_httponly INTEGER,
            samesite INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO cookies
        (host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (".example.com", "session", "abc123", b"", "/", 0, 1, 1, 1),
    )
    conn.commit()
    conn.close()

    manager = CookieManager(profile_root=profile_root, profile_name="Default")
    cookies = manager.get_cookies_for_url("https://www.example.com/path")

    assert cookies == [
        {
            "name": "session",
            "value": "abc123",
            "domain": ".example.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
        }
    ]


def test_cookie_manager_remember_cookie():
    manager = CookieManager(profile_root=Path("/tmp/does-not-matter"))
    manager.remember_cookies("https://example.com", [{"name": "sid", "value": "1"}])
    assert manager.build_cookie_header("https://example.com") == "sid=1"
