#!/usr/bin/env python3
from proxy_manager import ProxyManager


def main() -> int:
    manager = ProxyManager()
    snapshot = manager.health_snapshot()
    print("[*] Crystal CDP egress health")
    print(f"  - WARP  : {'up' if snapshot['warp'] else 'down'}")
    print(f"  - Mac   : {'up' if snapshot['mac'] else 'down'}")
    print(f"  - Direct: {'up' if snapshot['direct'] else 'down'}")
    print("\n[*] Auto chain")
    for index, target in enumerate(manager.resolve_targets("auto"), start=1):
        print(f"  {index}. {target.name}: {target.server or 'direct'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
