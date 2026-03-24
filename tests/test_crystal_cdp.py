from types import SimpleNamespace

from crystal_cdp import Crystal, build_mode_order, format_status, normalize_url
from stealth import PageStatus


def test_normalize_url():
    assert normalize_url("example.com") == "https://example.com"
    assert normalize_url("http://example.com") == "http://example.com"


def test_format_status():
    assert format_status(PageStatus.SUCCESS, None) == "success"
    assert format_status(PageStatus.ERROR, "details") == "Unexpected error (details)"


def test_build_mode_order():
    assert build_mode_order("http", auto_upgrade=True) == ["http", "headless", "headed"]
    assert build_mode_order("headless", auto_upgrade=True) == ["headless", "headed"]
    assert build_mode_order("headed", auto_upgrade=False) == ["headed"]


def test_fetch_http_success(monkeypatch):
    crystal = Crystal(proxy="direct", auto_upgrade=False)
    monkeypatch.setattr(
        crystal.proxy_manager,
        "resolve_targets",
        lambda proxy: [SimpleNamespace(name="direct", server=None)],
    )
    monkeypatch.setattr(crystal.cookie_manager, "build_cookie_header", lambda url: "")
    monkeypatch.setattr(
        crystal.http_engine,
        "fetch",
        lambda *args, **kwargs: SimpleNamespace(
            ok=True,
            status=PageStatus.SUCCESS,
            final_url="https://example.com/article",
            html="<article><h1>Story</h1><p>Hello world</p></article>",
            error=None,
        ),
    )

    result = crystal.fetch("example.com")

    assert result.ok is True
    assert result.mode_used == "http"
    assert result.proxy_used == "direct"
    assert "Story" in result.text
    assert result.url == "https://example.com/article"


def test_fetch_upgrades_to_headless(monkeypatch):
    crystal = Crystal(proxy="direct", auto_upgrade=True)
    monkeypatch.setattr(
        crystal.proxy_manager,
        "resolve_targets",
        lambda proxy: [SimpleNamespace(name="direct", server=None)],
    )
    monkeypatch.setattr(crystal.cookie_manager, "build_cookie_header", lambda url: "")
    monkeypatch.setattr(
        crystal.http_engine,
        "fetch",
        lambda *args, **kwargs: SimpleNamespace(
            ok=False,
            status=PageStatus.JAVASCRIPT_REQUIRED,
            final_url="https://example.com",
            html="Please enable JavaScript",
            error="needs_js",
        ),
    )

    class FakeBrowser:
        def launch(self):
            return None

        def fetch(self, url, timeout):
            return SimpleNamespace(
                ok=True,
                status=PageStatus.SUCCESS,
                final_url=url,
                html="<main><h1>Rendered</h1><p>done</p></main>",
                error=None,
            )

        def export_cookies(self):
            return [{"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"}]

        def close(self):
            return None

    monkeypatch.setattr(crystal, "_build_browser", lambda *args, **kwargs: FakeBrowser())

    result = crystal.fetch("https://example.com")

    assert result.ok is True
    assert result.mode_used == "headless"
    assert len(result.attempts) == 2
    assert result.attempts[0].status == PageStatus.JAVASCRIPT_REQUIRED.value
    assert result.attempts[1].status == PageStatus.SUCCESS.value


def test_build_browser_uses_profile_only_for_headed(monkeypatch):
    crystal = Crystal(
        proxy="direct",
        auto_upgrade=False,
        use_persistent_profile=True,
        profile_root="/tmp/chromium",
        profile_name="Profile 5",
    )
    monkeypatch.setattr(
        crystal.cookie_manager,
        "get_cookies_for_url",
        lambda url: [{"name": "sid", "value": "123", "domain": ".example.com", "path": "/"}],
    )

    headed_browser = crystal._build_browser("headed", None, "https://voice.google.com/u/0/calls")
    headless_browser = crystal._build_browser("headless", None, "https://example.com")

    assert headed_browser.user_data_dir == "/tmp/chromium"
    assert headed_browser.profile_name == "Profile 5"
    assert headed_browser.stealth is False
    assert headed_browser.disable_resources is False
    assert headed_browser.cookies == []
    assert headless_browser.user_data_dir is None
    assert headless_browser.stealth is True
    assert headless_browser.cookies == [{"name": "sid", "value": "123", "domain": ".example.com", "path": "/"}]


def test_build_browser_prefers_cdp_for_headed(monkeypatch):
    crystal = Crystal(
        proxy="direct",
        auto_upgrade=False,
        use_persistent_profile=True,
        profile_root="/tmp/chromium",
        profile_name="Profile 5",
        cdp_url="http://127.0.0.1:9222",
    )
    monkeypatch.setattr(
        crystal.cookie_manager,
        "get_cookies_for_url",
        lambda url: [{"name": "sid", "value": "123", "domain": ".example.com", "path": "/"}],
    )

    headed_browser = crystal._build_browser("headed", None, "https://voice.google.com/u/0/calls")

    assert headed_browser.cdp_url == "http://127.0.0.1:9222"
    assert headed_browser.user_data_dir is None
    assert headed_browser.stealth is False
    assert headed_browser.disable_resources is False
    assert headed_browser.cookies == []
