import pytest
from pathlib import Path
from proxy_loader import ProxyLoader

@pytest.fixture
def mock_proxy_file(tmp_path):
    pool_file = tmp_path / "proxy_pool.txt"
    pool_file.write_text("1.1.1.1:8080\n# comment\nhttp://2.2.2.2:3128\n", encoding="utf-8")
    return pool_file

def test_proxy_loader_load(mock_proxy_file):
    loader = ProxyLoader(pool_file=mock_proxy_file)
    proxies = loader.load()
    assert proxies == ["http://1.1.1.1:8080", "http://2.2.2.2:3128"]

def test_proxy_loader_load_missing_file(tmp_path):
    loader = ProxyLoader(pool_file=tmp_path / "nonexistent.txt")
    assert loader.load() == []

def test_quick_validate_success(mocker):
    loader = ProxyLoader()
    mocker.patch.object(loader, "_get_local_ip", return_value="10.0.0.1")
    
    # Mock requests.get
    mock_resp = mocker.Mock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"origin": "10.0.0.2"}
    mocker.patch("requests.get", return_value=mock_resp)
    
    assert loader.quick_validate("http://proxy:8080") is True

def test_quick_validate_fail_non_anonymous(mocker):
    loader = ProxyLoader()
    mocker.patch.object(loader, "_get_local_ip", return_value="10.0.0.1")
    
    # Mock requests.get returning the original IP
    mock_resp = mocker.Mock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"origin": "10.0.0.1"}
    mocker.patch("requests.get", return_value=mock_resp)
    
    assert loader.quick_validate("http://proxy:8080") is False

def test_quick_validate_fail_request(mocker):
    loader = ProxyLoader()
    mocker.patch.object(loader, "_get_local_ip", return_value="10.0.0.1")
    
    mocker.patch("requests.get", side_effect=Exception("Timeout"))
    assert loader.quick_validate("http://proxy:8080") is False

def test_get_working_proxies(mocker, mock_proxy_file):
    loader = ProxyLoader(pool_file=mock_proxy_file, max_proxies=1)
    
    # Mock quick_validate to return True for the first proxy and False for setup
    # Actually, let's just mock it to return True always
    mocker.patch.object(loader, "quick_validate", return_value=True)
    
    working = loader.get_working_proxies()
    # It should return at most max_proxies
    assert len(working) == 1
