#!/usr/bin/env python3
"""
Verify all proxies from the openclaw-tool proxy pool.
This is a standalone validation tool to check proxy health.
"""
import sys
from pathlib import Path
from proxy_loader import ProxyLoader

def main():
    loader = ProxyLoader(max_proxies=999)  # Load all proxies

    print("[*] Loading proxies from ~/scripts/openclaw-tool/proxy/proxy_pool.txt...")
    all_proxies = loader.load()
    print(f"[*] Total proxies available: {len(all_proxies)}")

    if not all_proxies:
        print("[-] No proxies found!")
        return 1

    print("\n[*] Validating proxies concurrently...")
    print("[*] This may take a minute...\n")

    working = loader.get_working_proxies(timeout=8)

    print(f"\n[+] Found {len(working)} working proxies out of {len(all_proxies)}:")
    for idx, proxy in enumerate(working, 1):
        print(f"  {idx}. {proxy}")

    if not working:
        print("\n[-] No working proxies found!")
        print("[*] Proxy sources may be outdated. Try refreshing:")
        print("    cd ~/scripts/openclaw-tool/proxy && npm run build:list")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
