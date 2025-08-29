#!/usr/bin/env python3
"""
Debug script for wallet balance calculation issues
"""

import time
from datetime import datetime

def analyze_balance_calculation_logs(log_content):
    """Analyze logs for balance calculation flow"""
    
    lines = log_content.split('\n')
    events = []
    
    # Track balance calculation events
    for line in lines:
        if any(keyword in line for keyword in [
            "OPTIMIZED] Starting optimized balance",
            "OPTIMIZED] Performing full address scan",
            "OPTIMIZED] Gap limit enabled",
            "OPTIMIZED] Using gap limit detection",
            "OPTIMIZED] Gap limit scan completed",
            "CACHE] Found cached gap limit",
            "FRESH] No cached gap limit",
            "BLOCKING] Gap limit detection",
            "Enhanced gap limit detection",
            "STARTUP] No cached balance available",
            "PARALLEL] Starting balance calculation",
            "PARALLEL] completed"
        ]):
            try:
                timestamp = line.split()[2]
                events.append((timestamp, line))
            except:
                events.append(("--:--:--", line))
    
    print("🔍 Balance Calculation Flow Analysis")
    print("=" * 80)
    
    current_wallet = None
    
    for timestamp, event in events:
        # Extract wallet identifier
        if "zpub6rrfVgQUrywTwGz4" in event:
            wallet = "Wallet_1"
        elif "zpub6rEoKKBKD7dEcBo6" in event:
            wallet = "Wallet_2"  
        elif "xpub6CTx4Z7keRBhj1aD" in event:
            wallet = "Wallet_3"
        else:
            wallet = current_wallet or "Unknown"
        
        if wallet != current_wallet:
            print(f"\n📱 === {wallet} ===")
            current_wallet = wallet
            
        if "STARTUP] No cached balance available" in event:
            print(f"❌ {timestamp}: RETURNS 0 - {event.split(': ', 1)[1] if ': ' in event else event}")
        elif "OPTIMIZED] Starting optimized balance" in event:
            print(f"🎯 {timestamp}: Starting balance calculation")
        elif "OPTIMIZED] Performing full address scan" in event:
            print(f"🔍 {timestamp}: Full scan initiated")
        elif "OPTIMIZED] Gap limit scan completed" in event:
            print(f"✅ {timestamp}: {event.split(': ', 1)[1] if ': ' in event else event}")
        elif "Enhanced gap limit detection" in event:
            print(f"🚀 {timestamp}: Gap limit detection started")
        elif "CACHE] Found cached gap limit" in event:
            print(f"💾 {timestamp}: Using cached results")
        elif "FRESH] No cached gap limit" in event:
            print(f"🔍 {timestamp}: Running fresh detection")
        elif "PARALLEL] completed" in event:
            if "0 BTC" in event:
                print(f"💸 {timestamp}: ❌ ZERO BALANCE - {event.split(': ', 1)[1] if ': ' in event else event}")
            else:
                print(f"💰 {timestamp}: ✅ POSITIVE BALANCE - {event.split(': ', 1)[1] if ': ' in event else event}")
        else:
            print(f"📋 {timestamp}: {event.split(': ', 1)[1] if ': ' in event else event}")

def diagnose_issues():
    """Show diagnostic questions and solutions"""
    
    print(f"""
🔍 **Diagnostic Questions**:

1. **Why are all wallets returning 0 BTC?**
   - Are we seeing "STARTUP] No cached balance available" → This means startup_mode=True
   - Should see "OPTIMIZED] Performing full address scan" → This means real calculation
   
2. **Is gap limit detection running?**
   - Should see "Enhanced gap limit detection for..." 
   - Should see "Gap limit scan completed in X.Xs → Y addresses"
   - If not, async cache might be interfering
   
3. **Are we using cached vs fresh results?**
   - "CACHE] Found cached gap limit" → Using cached addresses
   - "FRESH] No cached gap limit" → Running fresh detection
   
4. **Is blocking mechanism working?**
   - "BLOCKING] Starting exclusive gap limit detection"
   - "BLOCKING] Completed gap limit detection"

🔧 **Potential Issues & Solutions**:

**Issue 1: startup_mode=True during image generation**
- ✅ FIXED: Changed render_dual_images(startup_mode=False)

**Issue 2: Async cache only has 20 addresses**  
- ❓ POTENTIAL: Wallets with balance beyond address 20 won't be found
- 🔧 SOLUTION: Gap limit detection should override async cache

**Issue 3: Multiple concurrent balance calculations**
- ✅ FIXED: Added blocking mechanism with _gap_limit_lock
- ✅ FIXED: Added _active_gap_limit_detection tracking

**Issue 4: Gap limit cache conflict**
- ❓ POTENTIAL: Async cache uses "{xpub}:{count}" but gap limit uses "{xpub}:gap_limit:{count}"
- 🔧 SOLUTION: Gap limit should find no cache and run fresh detection

🚀 **Expected Fix Results**:
- ✅ "OPTIMIZED] Performing full address scan" for each wallet
- ✅ "Enhanced gap limit detection" for each wallet (if no cache)
- ✅ "Gap limit scan completed" with >20 addresses for wallets with balances
- ✅ Positive balance calculations for funded wallets

📊 **Next Steps**:
1. Deploy the fixed mempaper_app.py (startup_mode=False for image generation)
2. Deploy the enhanced wallet_balance_api.py (blocking + better logging)
3. Restart service and monitor logs for gap limit detection activity
4. Check if wallets show positive balances after gap limit detection completes
""")

if __name__ == "__main__":
    print(f"🕐 Debug analysis started at {datetime.now().strftime('%H:%M:%S')}")
    
    diagnose_issues()
    
    print(f"""
🧪 **Test Commands**:

# Deploy fixes and restart
sudo systemctl restart mempaper.service

# Monitor detailed balance calculation logs  
journalctl -u mempaper.service -f --since "3 seconds ago" | grep -E "(OPTIMIZED|STARTUP|PARALLEL|Enhanced|BLOCKING)"

# Check if gap limit detection actually runs
journalctl -u mempaper.service -f --since "3 seconds ago" | grep -E "(Enhanced gap limit|Gap limit scan completed)"

# Monitor for positive balance results
journalctl -u mempaper.service -f --since "3 seconds ago" | grep -E "(completed.*BTC)"

Expected: Each wallet should show gap limit detection and positive balance!
""")
    
    print(f"🕐 Debug analysis completed at {datetime.now().strftime('%H:%M:%S')}")
