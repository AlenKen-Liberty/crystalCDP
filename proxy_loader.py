from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

import requests
import urllib3

# Disable insecure request warnings when verifying proxies without SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROXY_POOL_FILE = Path.home() / "scripts" / "openclaw-tool" / "proxy" / "proxy_pool.txt"


class ProxyLoader:
    """Loads and validates proxies from a local pool file."""
    
    def __init__(self, pool_file: Path = PROXY_POOL_FILE, max_proxies: int = 5) -> None:
        """
        Initialize the ProxyLoader.
        
        Args:
            pool_file: Path to the file containing proxy list.
            max_proxies: Maximum number of working proxies to return.
        """
        self.pool_file = pool_file
        self.max_proxies = max_proxies
        self._local_ip_cache: Optional[str] = None

    def load(self) -> List[str]:
        """
        Load proxy URLs from the pool file.
        
        Returns:
            A list of proxy URLs (with scheme added if missing).
        """
        if not self.pool_file.exists():
            return []
        proxies: List[str] = []
        for line in self.pool_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "://" not in line:
                line = f"http://{line}"
            proxies.append(line)
        return proxies

    def _get_local_ip(self, timeout: int = 5) -> Optional[str]:
        """Get the current machine's public IP address to prevent using non-anonymous proxies."""
        if self._local_ip_cache is not None:
            return self._local_ip_cache
        try:
            resp = requests.get("https://httpbin.org/ip", timeout=timeout, verify=False)
            if resp.ok:
                data = resp.json()
                ip = data.get("origin")
                if isinstance(ip, str):
                    ip = ip.split(",")[0].strip()
                    self._local_ip_cache = ip
                    return ip
        except Exception:
            pass
        return None

    def quick_validate(self, proxy: str, timeout: int = 5) -> bool:
        """
        Quickly validate if a proxy is working and anonymous.
        
        Args:
            proxy: The proxy URL to test.
            timeout: Request timeout in seconds.
            
        Returns:
            True if the proxy works and hides the local IP, False otherwise.
        """
        try:
            local_ip = self._get_local_ip(timeout=timeout)
            resp = requests.get(
                "https://httpbin.org/ip",
                timeout=timeout,
                proxies={"http": proxy, "https": proxy},
                verify=False
            )
            if not resp.ok:
                return False
            data = resp.json()
            origin = data.get("origin")
            if not isinstance(origin, str):
                return False
            proxy_ip = origin.split(",")[0].strip()
            if local_ip and proxy_ip == local_ip:
                return False
            return True
        except Exception:
            return False

    def get_working_proxies(self, timeout: int = 5) -> List[str]:
        """
        Concurrently validate proxies and return a list of working ones.
        
        Args:
            timeout: Timeout for each proxy validation request.
            
        Returns:
            List of validated working proxy URLs up to max_proxies.
        """
        proxies = self.load()
        if not proxies:
            return []
        working: List[str] = []
        max_workers = min(8, len(proxies))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self.quick_validate, proxy, timeout): proxy for proxy in proxies}
            for future in as_completed(future_map):
                proxy = future_map[future]
                try:
                    ok = future.result()
                except Exception:
                    ok = False
                if ok:
                    working.append(proxy)
                if self.max_proxies and len(working) >= self.max_proxies:
                    break
        return working
