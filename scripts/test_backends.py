#!/usr/bin/env python3
"""Test connectivity to all inference backends defined in configs/backends.yml."""

import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

import yaml


def check_backend(name: str, config: dict) -> tuple[bool, str]:
    """Check if a backend is reachable. Returns (ok, message)."""
    url = config["url"].rstrip("/") + config.get("health_endpoint", "/v1/models")
    try:
        req = Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, f"{name}: OK ({url})"
            return False, f"{name}: HTTP {resp.status} ({url})"
    except URLError as e:
        return False, f"{name}: UNREACHABLE - {e.reason} ({url})"
    except Exception as e:
        return False, f"{name}: ERROR - {e} ({url})"


def main() -> int:
    """Test all backends."""
    config_path = Path(__file__).parent.parent / "configs" / "backends.yml"
    if not config_path.exists():
        print(f"ERROR: {config_path} not found")
        return 1

    with open(config_path) as f:
        config = yaml.safe_load(f)

    backends = config.get("backends", {})
    results = []

    for name, backend in backends.items():
        ok, msg = check_backend(name, backend)
        results.append((ok, msg))
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {msg}")

    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} backends reachable")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
