"""
Mock Mempool API for Development and Testing

This module provides a mock implementation of the mempool API for development
purposes when you don't have access to a local mempool instance.
"""

import random
import time
from datetime import datetime


class MockMempoolAPI:
    """Mock mempool API that provides fake but realistic data for testing."""
    
    def __init__(self, ip="mock", rest_port="mock"):
        """Initialize mock mempool API."""
        self.ip = ip
        self.rest_port = rest_port
        self.base_url = "mock://mempool.api"
        
        # Simulated current block data
        self.current_block_height = 850000 + random.randint(0, 1000)
        self.current_block_hash = self._generate_mock_hash()
        
        # Mock fee data
        self.fees = {
            "fastestFee": random.randint(25, 50),
            "halfHourFee": random.randint(15, 30),
            "hourFee": random.randint(8, 20),
            "economyFee": random.randint(3, 10),
            "minimumFee": 1
        }
        
        print("🧪 Mock Mempool API initialized")
        print(f"   📊 Mock block height: {self.current_block_height}")
        print(f"   🏷️  Mock block hash: {self.current_block_hash[:16]}...")
        print(f"   💰 Mock fees: {self.fees}")
    
    def _generate_mock_hash(self):
        """Generate a realistic-looking Bitcoin block hash."""
        return "000000000000000" + "".join([random.choice('0123456789abcdef') for _ in range(49)])
    
    def get_tip_height(self):
        """Get mock current blockchain tip height."""
        # Occasionally increment the block height to simulate new blocks
        if random.random() < 0.1:  # 10% chance of new block
            self.current_block_height += 1
            self.current_block_hash = self._generate_mock_hash()
            print(f"🧪 Mock: New block simulated - Height: {self.current_block_height}")
        
        return str(self.current_block_height)
    
    def get_tip_hash(self):
        """Get mock current blockchain tip hash."""
        return self.current_block_hash
    
    def get_current_block_info(self):
        """Get mock current block information."""
        return {
            "block_height": self.get_tip_height(),
            "block_hash": self.get_tip_hash()
        }
    
    def format_block_height(self, raw_height):
        """Format block height with commas."""
        try:
            height_int = int(raw_height)
            return f"{height_int:,}"
        except (ValueError, TypeError):
            return "Unknown"
    
    def shorten_hash(self, full_hash):
        """Shorten hash for display."""
        if len(full_hash) >= 16:
            return full_hash[:8] + "..." + full_hash[-8:]
        return full_hash
    
    def get_fee_recommendations(self):
        """Get mock fee recommendations."""
        # Add some randomness to fees to simulate market changes
        variance = 0.1  # 10% variance
        mock_fees = {}
        for fee_type, base_value in self.fees.items():
            variance_factor = 1 + random.uniform(-variance, variance)
            mock_fees[fee_type] = max(1, int(base_value * variance_factor))
        
        return mock_fees
    
    def get_minimum_fee(self):
        """Get mock minimum fee."""
        return self.fees["minimumFee"]
    
    def get_configured_fee(self, fee_parameter="minimumFee"):
        """Get mock configured fee value."""
        fees = self.get_fee_recommendations()
        fee_value = fees.get(fee_parameter, 1)
        print(f"🧪 Mock: Fee for {fee_parameter}: {fee_value} sat/vB")
        return fee_value


def patch_mempool_api_for_development():
    """Patch the real MempoolAPI class to use mock data in development."""
    import mempool_api
    
    # Store original class
    mempool_api._OriginalMempoolAPI = mempool_api.MempoolAPI
    
    # Replace with mock
    mempool_api.MempoolAPI = MockMempoolAPI
    
    print("🧪 Mempool API patched with mock implementation for development")


def restore_mempool_api():
    """Restore the original MempoolAPI class."""
    import mempool_api
    
    if hasattr(mempool_api, '_OriginalMempoolAPI'):
        mempool_api.MempoolAPI = mempool_api._OriginalMempoolAPI
        delattr(mempool_api, '_OriginalMempoolAPI')
        print("🧪 Original Mempool API restored")


if __name__ == "__main__":
    # Test the mock API
    print("🧪 Testing Mock Mempool API")
    print("=" * 40)
    
    mock_api = MockMempoolAPI()
    
    print(f"Block Height: {mock_api.get_tip_height()}")
    print(f"Block Hash: {mock_api.get_tip_hash()}")
    print(f"Formatted Height: {mock_api.format_block_height(mock_api.get_tip_height())}")
    print(f"Short Hash: {mock_api.shorten_hash(mock_api.get_tip_hash())}")
    print(f"Fee Recommendations: {mock_api.get_fee_recommendations()}")
    print(f"Economy Fee: {mock_api.get_configured_fee('economyFee')}")
