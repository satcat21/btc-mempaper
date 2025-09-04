#!/usr/bin/env python3
"""
Session Authentication Debugging Script

This script helps identify the exact cause of rapid session timeouts
by testing various authentication scenarios and logging detailed information.
"""

import requests
import time
import json
from datetime import datetime, timedelta

class SessionDebugger:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.session = requests.Session()
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {level}: {message}")
        
    def test_server_availability(self):
        """Test if server is accessible."""
        try:
            response = requests.get(self.base_url, timeout=5)
            self.log(f"Server accessible: {response.status_code}")
            return True
        except Exception as e:
            self.log(f"Server not accessible: {e}", "ERROR")
            return False
    
    def get_session_status_detailed(self):
        """Get detailed session status with debug info."""
        try:
            response = self.session.get(f"{self.base_url}/api/session/status")
            if response.status_code == 200:
                data = response.json()
                self.log(f"Session Status Response: {json.dumps(data, indent=2)}")
                return data
            else:
                self.log(f"Session status failed: {response.status_code} - {response.text}", "ERROR")
                return None
        except Exception as e:
            self.log(f"Session status error: {e}", "ERROR")
            return None
    
    def test_login_immediate_check(self, username="admin", password="admin"):
        """Login and immediately check session status."""
        self.log("=== Testing Login + Immediate Session Check ===")
        
        # Step 1: Login
        self.log("Attempting login...")
        login_response = self.session.post(f"{self.base_url}/api/login", json={
            "username": username,
            "password": password
        })
        
        if login_response.status_code != 200:
            self.log(f"Login failed: {login_response.status_code} - {login_response.text}", "ERROR")
            return False
        
        login_data = login_response.json()
        self.log(f"Login response: {login_data}")
        
        if not login_data.get('success'):
            self.log(f"Login unsuccessful: {login_data.get('message')}", "ERROR")
            return False
        
        # Step 2: Immediate session check
        self.log("Checking session status immediately after login...")
        session_status = self.get_session_status_detailed()
        
        if not session_status:
            return False
        
        if not session_status.get('authenticated'):
            self.log("❌ CRITICAL: Session shows as not authenticated immediately after login!", "ERROR")
            return False
        else:
            self.log("✅ Session authenticated immediately after login")
        
        return True
    
    def test_session_persistence_over_time(self, test_duration_seconds=120):
        """Test if session persists over time without activity."""
        self.log(f"=== Testing Session Persistence Over {test_duration_seconds} Seconds ===")
        
        # Login first
        if not self.test_login_immediate_check():
            return False
        
        start_time = time.time()
        check_interval = 10  # Check every 10 seconds
        last_check = start_time
        
        while time.time() - start_time < test_duration_seconds:
            current_time = time.time()
            
            if current_time - last_check >= check_interval:
                elapsed = current_time - start_time
                self.log(f"Checking session status after {elapsed:.1f} seconds...")
                
                session_status = self.get_session_status_detailed()
                if not session_status:
                    self.log("Failed to get session status", "ERROR")
                    return False
                
                if not session_status.get('authenticated'):
                    self.log(f"❌ CRITICAL: Session lost after {elapsed:.1f} seconds!", "ERROR")
                    return False
                
                time_remaining = session_status.get('time_remaining', 0)
                self.log(f"✅ Session still valid - {time_remaining} seconds remaining")
                
                last_check = current_time
            
            time.sleep(1)
        
        self.log("✅ Session persisted throughout test period")
        return True
    
    def test_config_page_workflow(self):
        """Test the actual workflow: login -> config page -> save."""
        self.log("=== Testing Config Page Workflow ===")
        
        # Step 1: Login
        if not self.test_login_immediate_check():
            return False
        
        # Step 2: Get config (simulates loading config page)
        self.log("Getting config (simulating config page load)...")
        config_response = self.session.get(f"{self.base_url}/api/config")
        
        if config_response.status_code != 200:
            self.log(f"❌ Config GET failed: {config_response.status_code} - {config_response.text}", "ERROR")
            return False
        
        self.log("✅ Config loaded successfully")
        
        # Step 3: Wait 60 seconds (simulate user filling form)
        self.log("Waiting 60 seconds (simulating user filling form)...")
        for i in range(6):
            time.sleep(10)
            self.log(f"Still waiting... {(i+1)*10}/60 seconds")
        
        # Step 4: Check session before save
        self.log("Checking session before saving...")
        session_status = self.get_session_status_detailed()
        if not session_status or not session_status.get('authenticated'):
            self.log("❌ CRITICAL: Session lost during form filling!", "ERROR")
            return False
        
        # Step 5: Try to save config
        config_data = config_response.json().get('config', {})
        config_data['_test_save_timestamp'] = time.time()
        
        self.log("Attempting to save config...")
        save_response = self.session.post(f"{self.base_url}/api/config", json=config_data)
        
        if save_response.status_code != 200:
            self.log(f"❌ CRITICAL: Config save failed: {save_response.status_code} - {save_response.text}", "ERROR")
            
            # Check if it's an auth error
            if save_response.status_code == 401:
                self.log("❌ This is an authentication error - session expired!", "ERROR")
            
            return False
        
        save_data = save_response.json()
        if not save_data.get('success'):
            self.log(f"❌ Config save unsuccessful: {save_data.get('message')}", "ERROR")
            return False
        
        self.log("✅ Config saved successfully!")
        return True
    
    def test_secret_key_consistency(self):
        """Test if secret key changes between requests."""
        self.log("=== Testing Secret Key Consistency ===")
        
        # Make multiple requests and check session debug info
        secret_key_lengths = []
        
        for i in range(3):
            session_status = self.get_session_status_detailed()
            if session_status and 'debug' in session_status:
                key_length = session_status['debug'].get('app_secret_key_length', 0)
                secret_key_lengths.append(key_length)
                self.log(f"Request {i+1}: Secret key length = {key_length}")
            
            time.sleep(2)
        
        if len(set(secret_key_lengths)) == 1:
            self.log("✅ Secret key length consistent across requests")
            return True
        else:
            self.log("❌ CRITICAL: Secret key length changing between requests!", "ERROR")
            return False
    
    def run_comprehensive_debug(self):
        """Run all debug tests."""
        self.log("🔍 Starting Comprehensive Session Authentication Debug")
        self.log("=" * 80)
        
        if not self.test_server_availability():
            return False
        
        tests = [
            ("Secret Key Consistency", self.test_secret_key_consistency),
            ("Login + Immediate Check", lambda: self.test_login_immediate_check()),
            ("Config Page Workflow", self.test_config_page_workflow),
            ("Session Persistence (2 minutes)", lambda: self.test_session_persistence_over_time(120))
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            self.log(f"\n🧪 Running: {test_name}")
            try:
                result = test_func()
                results[test_name] = result
                status = "PASSED" if result else "FAILED"
                self.log(f"📊 {test_name}: {status}")
            except Exception as e:
                self.log(f"💥 {test_name}: ERROR - {e}", "ERROR")
                results[test_name] = False
        
        # Summary
        self.log("\n" + "=" * 80)
        self.log("📋 Test Results Summary:")
        for test_name, result in results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            self.log(f"  {status} {test_name}")
        
        failed_tests = [name for name, result in results.items() if not result]
        
        if failed_tests:
            self.log(f"\n❌ {len(failed_tests)} test(s) failed:")
            for test in failed_tests:
                self.log(f"   • {test}")
            self.log("\n💡 Check server logs for detailed error information")
        else:
            self.log("\n🎉 All tests passed! Session management appears to be working correctly.")
        
        return len(failed_tests) == 0

def main():
    """Main debug runner."""
    print("🔍 Mempaper Session Authentication Debugger")
    print("This script will identify the exact cause of session timeout issues.")
    print()
    
    debugger = SessionDebugger()
    success = debugger.run_comprehensive_debug()
    
    if not success:
        print("\n🎯 Next Steps:")
        print("1. Check the server logs for detailed error messages")
        print("2. Verify the server is running in the correct mode (not debug auto-reload)")
        print("3. Check if there are any issues with the secret key management")
        print("4. Consider running the server with enhanced debug logging")
    
    return success

if __name__ == "__main__":
    main()
