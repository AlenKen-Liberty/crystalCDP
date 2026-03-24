import socket
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse


DEFAULT_WARP_PROXY = "socks5h://127.0.0.1:40000"
DEFAULT_MAC_PROXY = "http://100.122.10.34:8888"


@dataclass(frozen=True)
class ProxyTarget:
    name: str
    server: Optional[str]

    @property
    def label(self) -> str:
        return self.name if self.name != "custom" else (self.server or "custom")


class ProxyManager:
    def __init__(
        self,
        warp_proxy: str = DEFAULT_WARP_PROXY,
        mac_proxy: str = DEFAULT_MAC_PROXY,
        health_timeout: float = 1.5,
    ) -> None:
        self.warp_proxy = warp_proxy
        self.mac_proxy = mac_proxy
        self.health_timeout = health_timeout

    def resolve_targets(self, proxy: Optional[str] = "auto") -> List[ProxyTarget]:
        proxy_value = (proxy or "auto").strip()
        lowered = proxy_value.lower()
        if lowered == "auto":
            return self._resolve_auto_targets()
        if lowered == "warp":
            return [ProxyTarget("warp", self.warp_proxy)]
        if lowered == "mac":
            return [ProxyTarget("mac", self.mac_proxy)]
        if lowered == "direct":
            return [ProxyTarget("direct", None)]
        return [ProxyTarget("custom", proxy_value)]

    def health_snapshot(self) -> dict:
        return {
            "warp": self.is_available(self.warp_proxy),
            "mac": self.is_available(self.mac_proxy),
            "direct": True,
        }

    def is_available(self, proxy_url: Optional[str]) -> bool:
        if not proxy_url:
            return True
        parsed = urlparse(proxy_url)
        host = parsed.hostname
        if not host:
            return False
        port = parsed.port
        if port is None:
            port = 1080 if parsed.scheme.startswith("socks") else 80
        try:
            with socket.create_connection((host, port), timeout=self.health_timeout):
                return True
        except OSError:
            return False

    def should_use_curl(self, proxy_url: Optional[str]) -> bool:
        if not proxy_url:
            return True
        scheme = (urlparse(proxy_url).scheme or "").lower()
        return scheme.startswith("socks")

    def _resolve_auto_targets(self) -> List[ProxyTarget]:
        targets: List[ProxyTarget] = []
        if self.is_available(self.warp_proxy):
            targets.append(ProxyTarget("warp", self.warp_proxy))
        if self.is_available(self.mac_proxy):
            targets.append(ProxyTarget("mac", self.mac_proxy))
        targets.append(ProxyTarget("direct", None))
        return targets
