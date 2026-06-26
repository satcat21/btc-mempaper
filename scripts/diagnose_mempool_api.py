#!/usr/bin/env python3
"""
Mempool API Diagnostics Tool

Tests which REST API endpoints are available on your mempool instance
to determine if it's a full Mempool.space backend or just Electrs.
"""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from requests.auth import HTTPBasicAuth
from managers.config_manager import ConfigManager
from utils.technical_config import build_mempool_api_url


def test_mempool_endpoints():
    """Test which endpoints are available on the configured mempool instance."""

    print("🔍 Mempool API Diagnostics Tool")
    print("=" * 60)

    config_manager = ConfigManager()
    config = config_manager.get_current_config()

    mempool_host    = config.get("mempool_host", "127.0.0.1")
    mempool_port    = config.get("mempool_rest_port", 4081)
    mempool_use_https = config.get("mempool_use_https", False)
    mempool_verify_ssl = config.get("mempool_verify_ssl", True)
    username        = config.get("mempool_username", "")
    password        = config.get("mempool_password", "")
    auth = HTTPBasicAuth(username, password) if username and password else None

    base_url = build_mempool_api_url(mempool_host, mempool_port, mempool_use_https)

    print(f"\n📡 Testing mempool instance: {base_url}")
    print(f"   Host: {mempool_host}  Port: {mempool_port}  HTTPS: {mempool_use_https}")
    if auth:
        print(f"   Auth: user '{username}'")
    print()

    endpoints = [
        ("Block height",        "/blocks/tip/height",               True),
        ("Block hash",          "/blocks/tip/hash",                 True),
        ("Price data",          "/v1/prices",                       True),
        ("Fee recommendations", "/v1/fees/recommended",             True),
        ("Network hashrate",    "/v1/mining/hashrate/1m",           True),
        ("Difficulty adjust",   "/v1/difficulty-adjustment",        False),
        ("Mempool info",        "/mempool",                         False),
        ("Address stats",       "/address/1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf Na", False),
    ]
    # Fix up the address (split above to avoid line length)
    endpoints[-1] = ("Address stats (wallet monitoring)", "/address/1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", False)

    results = {}
    col = 38

    print("📊 Endpoint Test Results:")
    print("-" * 60)

    for name, path, required in endpoints:
        url = base_url + path
        t0 = time.time()
        try:
            r = requests.get(url, timeout=10, verify=mempool_verify_ssl, auth=auth)
            latency = round((time.time() - t0) * 1000)
            if r.status_code == 200:
                status = f"✅ OK  ({latency} ms)"
                results[name] = True
            elif r.status_code == 401:
                status = "🔑 Unauthorized (check credentials)"
                results[name] = False
            elif r.status_code == 404:
                status = "❌ Not found (404)"
                results[name] = False
            else:
                status = f"⚠️  HTTP {r.status_code}"
                results[name] = False
        except requests.exceptions.Timeout:
            status = "⏱️  Timeout"
            results[name] = False
        except requests.exceptions.ConnectionError as e:
            status = f"🔌 Connection failed"
            results[name] = False
        except Exception as e:
            status = f"❌ {type(e).__name__}"
            results[name] = False

        req_tag = " [required]" if required else ""
        label = f"{name}{req_tag}"
        print(f"  {label:<{col}} {status}")

    print()
    print("=" * 60)
    print("🔎 ANALYSIS:")
    print("=" * 60)

    core_ok = results.get("Block height") and results.get("Price data") and results.get("Fee recommendations")
    if core_ok:
        print("✅ Core endpoints (block, price, fees) are working.")
    else:
        missing = [n for n in ("Block height", "Price data", "Fee recommendations") if not results.get(n)]
        print(f"❌ Core endpoints failing: {', '.join(missing)}")
        print("   Check that mempool is running and the host/port config is correct.")

    if results.get("Address stats (wallet monitoring)"):
        print("✅ Address endpoint available — wallet monitoring will work.")
    else:
        print("\n❌ WALLET MONITORING NOT SUPPORTED")
        print("   Your mempool instance does not provide the /api/address/ endpoint.")
        print()
        print("🔧 COMMON FIXES:")
        print()
        print("1. Check Mempool backend Electrum connection:")
        print("   sudo nano /home/mempool/mempool/backend/mempool-config.json")
        print('   Ensure "ELECTRUM": { "HOST": "127.0.0.1", "PORT": 50001, "TLS_ENABLED": false }')
        print("   Then restart: sudo systemctl restart mempool")
        print()
        print("2. Use public Mempool.space API temporarily:")
        print("   mempool_host: mempool.space  |  mempool_use_https: true  |  mempool_rest_port: 443")
        print("   (Public API has rate limits.)")
        print()
        print("3. Disable wallet monitoring: set show_wallet_balances_block: false in config")

    if not results.get("Network hashrate"):
        print("\n⚠️  Network hashrate endpoint unavailable — network stats block may show '…'.")

    print()


if __name__ == "__main__":
    test_mempool_endpoints()
