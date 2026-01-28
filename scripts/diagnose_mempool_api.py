#!/usr/bin/env python3
"""
Mempool API Diagnostics Tool

Tests which REST API endpoints are available on your mempool instance
to determine if it's a full Mempool.space backend or just Electrs.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from managers.config_manager import ConfigManager

def test_mempool_endpoints():
    """Test which endpoints are available on the configured mempool instance."""
    
    print("🔍 Mempool API Diagnostics Tool")
    print("=" * 60)
    
    # Load configuration
    config_manager = ConfigManager()
    config = config_manager.get_current_config()
    
    mempool_host = config.get("mempool_host", "127.0.0.1")
    mempool_port = config.get("mempool_rest_port", 4081)
    mempool_use_https = config.get("mempool_use_https", False)
    mempool_verify_ssl = config.get("mempool_verify_ssl", True)
    
    protocol = "https" if mempool_use_https else "http"
    is_domain = "." in mempool_host and not mempool_host.replace(".", "").isdigit()
    
    if is_domain and ((mempool_use_https and str(mempool_port) in ["443", "80"]) or 
                      (not mempool_use_https and str(mempool_port) in ["80", "443"])):
        base_url = f"{protocol}://{mempool_host}/api"
    else:
        base_url = f"{protocol}://{mempool_host}:{mempool_port}/api"
    
    print(f"\n📡 Testing mempool instance: {base_url}")
    print(f"   Host: {mempool_host}")
    print(f"   Port: {mempool_port}")
    print(f"   HTTPS: {mempool_use_https}")
    print(f"   Verify SSL: {mempool_verify_ssl}")
    print()
    
    # Test endpoints
    endpoints = {
        "Block height": "/blocks/tip/height",
        "Block hash": "/blocks/tip/hash",
        "Address stats (REQUIRED for wallet monitoring)": "/address/1Q2TWHE3GMdB6BZKafqwxXtWAWgFt5Jvm3",  # First BTC transaction address (Hal Finney)
        "Fee recommendations": "/v1/fees/recommended",
        "Mempool info": "/mempool"
    }
    
    results = {}
    
    for name, endpoint in endpoints.items():
        url = base_url + endpoint
        try:
            response = requests.get(url, timeout=10, verify=mempool_verify_ssl)
            if response.status_code == 200:
                results[name] = "✅ Available"
            elif response.status_code == 404:
                results[name] = "❌ Not Found (404)"
            else:
                results[name] = f"⚠️ Error ({response.status_code})"
        except requests.exceptions.Timeout:
            results[name] = "⏱️ Timeout"
        except requests.exceptions.ConnectionError:
            results[name] = "🔌 Connection Failed"
        except Exception as e:
            results[name] = f"❌ Error: {type(e).__name__}"
    
    print("📊 Endpoint Test Results:")
    print("-" * 60)
    for name, result in results.items():
        print(f"{result} {name}")
    print()
    
    # Analyze results
    print("=" * 60)
    print("🔎 ANALYSIS:")
    print("=" * 60)
    
    if "✅" in results["Address stats (REQUIRED for wallet monitoring)"]:
        print("✅ Full Mempool.space REST API detected!")
        print("   Your instance supports wallet monitoring.")
    else:
        print("❌ WALLET MONITORING NOT SUPPORTED")
        print()
        print("Your mempool instance does NOT provide the /api/address/ endpoint.")
        print()
        print("🔧 COMMON FIXES:")
        print()
        print("1. Check Mempool backend Electrum connection:")
        print("   sudo nano /home/mempool/mempool/backend/mempool-config.json")
        print("   Ensure ELECTRUM.TLS_ENABLED is set to false:")
        print('   "ELECTRUM": {')
        print('     "HOST": "127.0.0.1",')
        print('     "PORT": 50001,')
        print('     "TLS_ENABLED": false')
        print('   }')
        print("   Then restart: sudo systemctl restart mempool")
        print()
        print("2. If Mempool.space backend not installed:")
        print("   https://github.com/mempool/mempool")
        print("   This provides the complete REST API.")
        print()
        print("3. Use public Mempool.space API temporarily:")
        print("   Set mempool_host: 'mempool.space'")
        print("   Set mempool_use_https: true")
        print("   Set mempool_rest_port: 443")
        print("   (Note: Public API has rate limits)")
        print()
        print("4. Disable wallet monitoring:")
        print("   Set show_wallet_balances_block: false in config")
        print()
    
    if "✅" in results["Block height"] and "✅" in results["Block hash"]:
        print("\n✅ Block monitoring endpoints working correctly.")
    
    print()

if __name__ == "__main__":
    test_mempool_endpoints()
