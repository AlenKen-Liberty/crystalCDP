import pytest
from stealth import (
    make_google_referer,
    _safe_lower,
    detect_page_status,
    detect_turnstile_type,
    PageStatus,
)

def test_make_google_referer():
    assert make_google_referer("https://example.com/path") == "https://www.google.com/search?q=site:example.com"
    assert make_google_referer("invalid_url") == "https://www.google.com/search?q=site:invalid_url"

def test_safe_lower():
    assert _safe_lower("HeLLo") == "hello"
    assert _safe_lower(None) == ""

class MockPage:
    def __init__(self, title_val="", url_val="", content_val=""):
        self._title = title_val
        self._url = url_val
        self._content = content_val

    def title(self): return self._title
    
    @property
    def url(self): return self._url
    
    def content(self): return self._content

def test_detect_page_status():
    page = MockPage(title_val="Just a moment...", content_val="checking your browser")
    assert detect_page_status(page) == PageStatus.CLOUDFLARE_TURNSTILE

    page = MockPage(title_val="Access denied")
    assert detect_page_status(page) == PageStatus.CLOUDFLARE_BLOCK

    page = MockPage()
    assert detect_page_status(page, 403) == PageStatus.IP_BLOCKED
    assert detect_page_status(page, 429) == PageStatus.RATE_LIMITED
    assert detect_page_status(page, 500) == PageStatus.ERROR
    assert detect_page_status(page, 200) == PageStatus.SUCCESS

def test_detect_turnstile_type():
    assert detect_turnstile_type("cf_turnstile") == "embedded"
    assert detect_turnstile_type("<title>just a moment</title> verifying you are human") == "interactive"
    assert detect_turnstile_type("<title>just a moment</title> challenge-form") == "non-interactive"
    assert detect_turnstile_type("random stuff") is None
