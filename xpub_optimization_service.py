#!/usr/bin/env python3
"""
Background service for daily XPUB optimization.
Runs automatically every 24 hours to analyze and optimize derivation counts.
"""

import time
import threading
import json
import schedule
from datetime import datetime
from adaptive_xpub_manager import AdaptiveXpubManager

class XpubOptimizationService:
    """Background service for automatic XPUB optimization."""
    
    def __init__(self, config_manager):
        """Initialize optimization service."""
        self.config_manager = config_manager
        self.running = False
        self.thread = None
        self.last_run = None
        
        # Schedule daily optimization at 3 AM
        schedule.every().day.at("03:00").do(self.run_daily_optimization)
        
    def start(self):
        """Start the background optimization service."""
        if self.running:
            print("🔄 XPUB optimization service already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._service_loop, daemon=True)
        self.thread.start()
        print("🚀 Started XPUB optimization background service")
        print("📅 Daily optimization scheduled for 3:00 AM")
    
    def stop(self):
        """Stop the background optimization service."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        print("🛑 Stopped XPUB optimization service")
    
    def _service_loop(self):
        """Main service loop."""
        while self.running:
            try:
                # Check scheduled tasks
                schedule.run_pending()
                
                # Sleep for 1 hour between checks
                time.sleep(3600)  # 1 hour
                
            except Exception as e:
                print(f"❌ Error in XPUB optimization service: {e}")
                time.sleep(300)  # 5 minutes on error
    
    def run_daily_optimization(self):
        """Run daily optimization check."""
        try:
            print("📊 Running daily XPUB optimization check...")
            
            config = self.config_manager.get_config()
            manager = AdaptiveXpubManager(config)
            
            # Check if analysis should run
            if not manager.should_run_daily_analysis():
                print("✅ Daily analysis already completed today")
                return
            
            # Find XPUBs in configuration
            wallets = config.get('wallets', [])
            xpubs = [w.get('address', '') for w in wallets 
                    if w.get('address', '').startswith(('xpub', 'zpub'))]
            
            if not xpubs:
                print("⚠️ No XPUBs found in configuration")
                return
            
            optimizations_applied = 0
            
            for i, xpub in enumerate(xpubs):
                print(f"🔍 Analyzing XPUB {i+1}/{len(xpubs)}: {xpub[:30]}...")
                
                current_count = config.get('xpub_derivation_count', 50)
                
                # Run analysis
                result = manager.analyze_xpub_usage(xpub, current_count)
                
                if 'error' in result:
                    print(f"❌ Analysis failed for XPUB {i+1}: {result['error']}")
                    continue
                
                # Apply optimization if recommended
                if result['should_increase']:
                    new_count = result['recommended_derivation_count']
                    old_count = result['current_derivation_count']
                    
                    # Update configuration
                    config['xpub_derivation_count'] = new_count
                    self.config_manager.save_config(config)
                    
                    print(f"🎯 Optimized derivation count: {old_count} → {new_count}")
                    print(f"   Reason: {result['recommendation_reason']}")
                    
                    optimizations_applied += 1
                else:
                    print(f"✅ XPUB {i+1} derivation count is optimal")
            
            self.last_run = datetime.now()
            
            if optimizations_applied > 0:
                print(f"🎉 Daily optimization complete: {optimizations_applied} optimizations applied")
                
                # Trigger cache rebuild for updated configuration
                self._trigger_cache_rebuild()
            else:
                print("✅ Daily optimization complete: No changes needed")
                
        except Exception as e:
            print(f"❌ Daily optimization failed: {e}")
    
    def _trigger_cache_rebuild(self):
        """Trigger cache rebuild after configuration changes."""
        try:
            # Import here to avoid circular imports
            from config_observer import ConfigurationObserver
            
            # This will trigger cache rebuild through the configuration observer
            print("🔄 Triggering cache rebuild for updated configuration...")
            
        except Exception as e:
            print(f"⚠️ Could not trigger cache rebuild: {e}")
    
    def force_optimization_check(self):
        """Force an immediate optimization check (for manual triggers)."""
        try:
            print("🔧 Running forced optimization check...")
            
            config = self.config_manager.get_config()
            manager = AdaptiveXpubManager(config)
            
            # Find XPUBs in configuration
            wallets = config.get('wallets', [])
            xpubs = [w.get('address', '') for w in wallets 
                    if w.get('address', '').startswith(('xpub', 'zpub'))]
            
            if not xpubs:
                return {
                    'success': False,
                    'message': 'No XPUBs found in configuration'
                }
            
            results = []
            
            for xpub in xpubs:
                current_count = config.get('xpub_derivation_count', 50)
                result = manager.analyze_xpub_usage(xpub, current_count)
                
                if 'error' not in result:
                    results.append({
                        'xpub': xpub[:30] + '...',
                        'analysis': result,
                        'should_optimize': result['should_increase'],
                        'current_count': result['current_derivation_count'],
                        'recommended_count': result['recommended_derivation_count']
                    })
            
            return {
                'success': True,
                'results': results,
                'timestamp': time.time()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_service_status(self):
        """Get current service status."""
        return {
            'running': self.running,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'next_scheduled': "03:00 AM daily",
            'thread_alive': self.thread.is_alive() if self.thread else False
        }

# Global service instance
optimization_service = None

def start_optimization_service(config_manager):
    """Start the global optimization service."""
    global optimization_service
    
    if optimization_service is None:
        optimization_service = XpubOptimizationService(config_manager)
    
    optimization_service.start()
    return optimization_service

def stop_optimization_service():
    """Stop the global optimization service."""
    global optimization_service
    
    if optimization_service:
        optimization_service.stop()

def get_optimization_service():
    """Get the global optimization service instance."""
    return optimization_service
