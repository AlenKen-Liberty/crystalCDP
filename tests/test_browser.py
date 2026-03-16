import pytest
from browser import Browser
from stealth import PageStatus
from unittest.mock import MagicMock

def test_browser_init():
    b = Browser(proxy="http://1.2.3.4:8080", verbose=True)
    assert b.proxy == "http://1.2.3.4:8080"
    assert b.verbose is True
    assert b.stealth is True
    assert b.profile_name == "Default"

def test_browser_launch_and_close(mocker):
    b = Browser()
    
    # Mock playwright
    mock_pw = mocker.patch("browser.sync_playwright")
    mock_pw_instance = MagicMock()
    mock_pw.return_value.start.return_value = mock_pw_instance
    
    mocker.patch.object(b, "kill_existing")
    
    b.launch()
    assert b._pw is not None
    assert b._context is not None
    
    b.close()
    assert b._pw is None
    assert b._context is None

def test_browser_navigate(mocker):
    b = Browser()
    
    # Setup mock context and page
    b._context = MagicMock()
    mock_page = MagicMock()
    b._context.pages = [mock_page]
    mock_page.is_closed.return_value = False
    
    mock_response = MagicMock()
    mock_response.status = 200
    mock_page.goto.return_value = mock_response
    
    # Mock stealth
    mocker.patch("browser.inject_stealth_scripts")
    mocker.patch("browser.detect_page_status", return_value=PageStatus.SUCCESS)
    
    status, detail = b.navigate("https://example.com")
    assert status == PageStatus.SUCCESS
    assert detail is None
    mock_page.goto.assert_called_once()
