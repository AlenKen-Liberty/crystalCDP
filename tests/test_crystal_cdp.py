import pytest
from crystal_cdp import normalize_url, format_status
from stealth import PageStatus

def test_normalize_url():
    assert normalize_url("example.com") == "https://example.com"
    assert normalize_url("http://example.com") == "http://example.com"
    assert normalize_url("https://example.com") == "https://example.com"

def test_format_status():
    assert format_status(PageStatus.SUCCESS, None) == "success"
    assert format_status(PageStatus.ERROR, "details") == "Unexpected error (details)"
    # detail "timeout" is ignored
    assert format_status(PageStatus.TIMEOUT, "timeout") == "Connection timeout"
