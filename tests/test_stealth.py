from stealth import (
    PageStatus,
    _safe_lower,
    detect_html_status,
    detect_page_status,
    detect_turnstile_type,
    make_google_referer,
)


def test_make_google_referer():
    assert make_google_referer("https://example.com/path") == "https://www.google.com/search?q=site:example.com"


def test_safe_lower():
    assert _safe_lower("HeLLo") == "hello"
    assert _safe_lower(None) == ""


class MockPage:
    def __init__(self, title_val="", url_val="", content_val=""):
        self._title = title_val
        self._url = url_val
        self._content = content_val

    def title(self):
        return self._title

    @property
    def url(self):
        return self._url

    def content(self):
        return self._content


def test_detect_html_status():
    assert detect_html_status("Please enable JavaScript", "https://example.com", 200) == PageStatus.JAVASCRIPT_REQUIRED
    assert detect_html_status("checking your browser", "https://example.com", 503) == PageStatus.CLOUDFLARE_TURNSTILE
    assert detect_html_status("error 1020", "https://example.com", 403) == PageStatus.CLOUDFLARE_BLOCK
    assert detect_html_status("ok", "https://example.com", 429) == PageStatus.RATE_LIMITED
    assert detect_html_status("ok", "https://example.com", 200) == PageStatus.SUCCESS


def test_detect_page_status():
    page = MockPage(title_val="Just a moment...", content_val="checking your browser")
    assert detect_page_status(page) == PageStatus.CLOUDFLARE_TURNSTILE


def test_detect_turnstile_type():
    assert detect_turnstile_type("cf_turnstile") == "embedded"
    assert detect_turnstile_type("<title>just a moment</title> verifying you are human") == "interactive"
    assert detect_turnstile_type("<title>just a moment</title> challenge-form") == "non-interactive"
    assert detect_turnstile_type("random stuff") is None
