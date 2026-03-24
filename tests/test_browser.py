from unittest.mock import MagicMock

from browser import Browser
from stealth import PageStatus


def test_browser_init():
    browser = Browser(proxy="http://1.2.3.4:8080", verbose=True, headless=True)
    assert browser.proxy == "http://1.2.3.4:8080"
    assert browser.verbose is True
    assert browser.headless is True
    assert browser.stealth is True


def test_browser_launch(monkeypatch):
    browser = Browser(cookies=[{"name": "sid", "value": "1", "domain": ".example.com", "path": "/"}])

    page = MagicMock()
    context = MagicMock()
    context.new_page.return_value = page
    chromium_browser = MagicMock()
    chromium_browser.new_context.return_value = context
    playwright = MagicMock()
    playwright.chromium.launch.return_value = chromium_browser
    sync_api = MagicMock()
    sync_api.start.return_value = playwright

    resource_filter_calls = []
    stealth_calls = []
    monkeypatch.setattr("browser.sync_playwright", lambda: sync_api)
    monkeypatch.setattr("browser.enable_resource_filter", lambda page_arg: resource_filter_calls.append(page_arg))
    monkeypatch.setattr("browser.inject_stealth_scripts", lambda page_arg: stealth_calls.append(page_arg))

    browser.launch()

    chromium_browser.new_context.assert_called_once()
    context.add_cookies.assert_called_once()
    assert resource_filter_calls == [page]
    assert stealth_calls == [page]
    browser.close()


def test_browser_launch_with_persistent_profile(monkeypatch):
    browser = Browser(user_data_dir="/tmp/chromium", profile_name="Profile 7")

    page = MagicMock()
    context = MagicMock()
    context.new_page.return_value = page
    playwright = MagicMock()
    playwright.chromium.launch_persistent_context.return_value = context
    sync_api = MagicMock()
    sync_api.start.return_value = playwright

    resource_filter_calls = []
    stealth_calls = []
    monkeypatch.setattr("browser.persistent_profile_sync_playwright", lambda: sync_api)
    monkeypatch.setattr("browser.enable_resource_filter", lambda page_arg: resource_filter_calls.append(page_arg))
    monkeypatch.setattr("browser.inject_stealth_scripts", lambda page_arg: stealth_calls.append(page_arg))

    browser.launch()

    playwright.chromium.launch.assert_not_called()
    playwright.chromium.launch_persistent_context.assert_called_once()
    _, kwargs = playwright.chromium.launch_persistent_context.call_args
    assert kwargs["user_data_dir"] == "/tmp/chromium"
    assert "--profile-directory=Profile 7" in kwargs["args"]
    assert resource_filter_calls == [page]
    assert stealth_calls == [page]
    browser.close()


def test_browser_launch_with_cdp(monkeypatch):
    browser = Browser(cdp_url="http://127.0.0.1:9222")

    page = MagicMock()
    context = MagicMock()
    context.new_page.return_value = page
    chromium_browser = MagicMock()
    chromium_browser.contexts = [context]
    playwright = MagicMock()
    playwright.chromium.connect_over_cdp.return_value = chromium_browser
    sync_api = MagicMock()
    sync_api.start.return_value = playwright

    resource_filter_calls = []
    stealth_calls = []
    monkeypatch.setattr("browser.sync_playwright", lambda: sync_api)
    monkeypatch.setattr("browser.enable_resource_filter", lambda page_arg: resource_filter_calls.append(page_arg))
    monkeypatch.setattr("browser.inject_stealth_scripts", lambda page_arg: stealth_calls.append(page_arg))

    browser.launch()

    playwright.chromium.connect_over_cdp.assert_called_once_with("http://127.0.0.1:9222")
    chromium_browser.close.assert_not_called()
    assert resource_filter_calls == [page]
    assert stealth_calls == [page]
    browser.close()
    page.close.assert_called_once()


def test_browser_fetch(monkeypatch):
    browser = Browser(headless=True)
    page = MagicMock()
    browser._page = page

    response = MagicMock()
    response.status = 200
    page.goto.return_value = response
    page.content.return_value = "<main>Hello</main>"
    page.title.return_value = "Hello"
    page.url = "https://example.com"

    monkeypatch.setattr("browser.detect_page_status", lambda *args, **kwargs: PageStatus.SUCCESS)

    result = browser.fetch("https://example.com")

    assert result.ok is True
    assert result.status == PageStatus.SUCCESS
    assert result.final_url == "https://example.com"
