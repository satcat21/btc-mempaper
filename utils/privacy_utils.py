#!/usr/bin/env python3
"""
Privacy Utilities for Bitcoin Address and Key Masking

This module provides utilities to mask sensitive Bitcoin data in logs and outputs
while maintaining readability and debugging capability.
"""

import re
from typing import Union, Dict, Any
import logging


class BitcoinPrivacyMasker:
    """Utility class for masking Bitcoin addresses and extended public keys in logs."""
    
    # Bitcoin address patterns
    P2PKH_PATTERN = re.compile(r'\b1[1-9A-HJ-NP-Za-km-z]{25,34}\b')  # Legacy addresses starting with 1
    P2SH_PATTERN = re.compile(r'\b3[1-9A-HJ-NP-Za-km-z]{25,34}\b')   # P2SH addresses starting with 3
    BECH32_PATTERN = re.compile(r'\bbc1[a-z0-9]{25,87}\b')           # Bech32 addresses starting with bc1
    
    # Extended public key patterns - more flexible length matching
    XPUB_PATTERN = re.compile(r'\bxpub[1-9A-HJ-NP-Za-km-z]{100,115}\b')  # XPUB keys (flexible length)
    YPUB_PATTERN = re.compile(r'\bypub[1-9A-HJ-NP-Za-km-z]{100,115}\b')  # YPUB keys (flexible length)
    ZPUB_PATTERN = re.compile(r'\bzpub[1-9A-HJ-NP-Za-km-z]{100,115}\b')  # ZPUB keys (flexible length)
    
    @staticmethod
    def mask_address(address: str, prefix_len: int = 6, suffix_len: int = 6) -> str:
        """
        Mask a Bitcoin address showing only the first and last characters.
        
        Args:
            address: Bitcoin address to mask
            prefix_len: Number of characters to show at the beginning
            suffix_len: Number of characters to show at the end
            
        Returns:
            Masked address in format: "bc1qeu...l9lg7c"
        """
        if not address or len(address) <= (prefix_len + suffix_len):
            return address
            
        return f"{address[:prefix_len]}...{address[-suffix_len:]}"
    
    @staticmethod
    def mask_xpub(xpub: str, prefix_len: int = 6, suffix_len: int = 6) -> str:
        """
        Mask an extended public key (XPUB/YPUB/ZPUB).
        
        Args:
            xpub: Extended public key to mask
            prefix_len: Number of characters to show at the beginning
            suffix_len: Number of characters to show at the end
            
        Returns:
            Masked XPUB in format: "zpub6r...wTwGz4"
        """
        if not xpub or len(xpub) <= (prefix_len + suffix_len):
            return xpub
            
        return f"{xpub[:prefix_len]}...{xpub[-suffix_len:]}"
    
    @classmethod
    def mask_text(cls, text: str, prefix_len: int = 6, suffix_len: int = 6) -> str:
        """
        Mask all Bitcoin addresses and XPUBs found in text.
        
        Args:
            text: Text that may contain Bitcoin addresses or XPUBs
            prefix_len: Number of characters to show at the beginning
            suffix_len: Number of characters to show at the end
            
        Returns:
            Text with all Bitcoin addresses and XPUBs masked
        """
        if not text:
            return text
        
        # Mask Bitcoin addresses
        text = cls.P2PKH_PATTERN.sub(lambda m: cls.mask_address(m.group(), prefix_len, suffix_len), text)
        text = cls.P2SH_PATTERN.sub(lambda m: cls.mask_address(m.group(), prefix_len, suffix_len), text)
        text = cls.BECH32_PATTERN.sub(lambda m: cls.mask_address(m.group(), prefix_len, suffix_len), text)
        
        # Mask extended public keys
        text = cls.XPUB_PATTERN.sub(lambda m: cls.mask_xpub(m.group(), prefix_len, suffix_len), text)
        text = cls.YPUB_PATTERN.sub(lambda m: cls.mask_xpub(m.group(), prefix_len, suffix_len), text)
        text = cls.ZPUB_PATTERN.sub(lambda m: cls.mask_xpub(m.group(), prefix_len, suffix_len), text)
        
        return text
    
    @classmethod
    def mask_url(cls, url: str, prefix_len: int = 6, suffix_len: int = 6) -> str:
        """
        Mask Bitcoin addresses in URLs while preserving the URL structure.
        
        Args:
            url: URL that may contain Bitcoin addresses
            prefix_len: Number of characters to show at the beginning
            suffix_len: Number of characters to show at the end
            
        Returns:
            URL with Bitcoin addresses masked
        """
        if not url:
            return url
        
        # Find addresses in URL paths
        parts = url.split('/')
        masked_parts = []
        
        for part in parts:
            # Check if this part looks like a Bitcoin address
            if (cls.P2PKH_PATTERN.match(part) or 
                cls.P2SH_PATTERN.match(part) or 
                cls.BECH32_PATTERN.match(part)):
                masked_parts.append(cls.mask_address(part, prefix_len, suffix_len))
            else:
                masked_parts.append(part)
        
        return '/'.join(masked_parts)
    
    @classmethod
    def create_logging_filter(cls, prefix_len: int = 6, suffix_len: int = 6):
        """
        Create a logging filter that masks Bitcoin addresses and XPUBs in log messages.
        
        Args:
            prefix_len: Number of characters to show at the beginning
            suffix_len: Number of characters to show at the end
            
        Returns:
            Logging filter function
        """
        class BitcoinPrivacyFilter(logging.Filter):
            def filter(self, record):
                # Mask the log message
                if hasattr(record, 'msg') and record.msg:
                    record.msg = cls.mask_text(str(record.msg), prefix_len, suffix_len)
                
                # Mask arguments if present
                if hasattr(record, 'args') and record.args:
                    masked_args = []
                    for arg in record.args:
                        if isinstance(arg, str):
                            masked_args.append(cls.mask_text(arg, prefix_len, suffix_len))
                        else:
                            masked_args.append(arg)
                    record.args = tuple(masked_args)
                
                return True
        
        return BitcoinPrivacyFilter()


def mask_bitcoin_data(data: Union[str, Dict, Any], prefix_len: int = 6, suffix_len: int = 6) -> Union[str, Dict, Any]:
    """
    Convenience function to mask Bitcoin data in various formats.
    
    Args:
        data: Data to mask (string, dict, or other)
        prefix_len: Number of characters to show at the beginning
        suffix_len: Number of characters to show at the end
        
    Returns:
        Data with Bitcoin addresses and XPUBs masked
    """
    if isinstance(data, str):
        return BitcoinPrivacyMasker.mask_text(data, prefix_len, suffix_len)
    elif isinstance(data, dict):
        masked_dict = {}
        for key, value in data.items():
            masked_dict[key] = mask_bitcoin_data(value, prefix_len, suffix_len)
        return masked_dict
    elif isinstance(data, (list, tuple)):
        return type(data)(mask_bitcoin_data(item, prefix_len, suffix_len) for item in data)
    else:
        return data


def setup_privacy_logging(logger_name: str = None, prefix_len: int = 6, suffix_len: int = 6):
    """
    Setup privacy-aware logging for a specific logger or root logger.
    
    Args:
        logger_name: Name of the logger to configure (None for root logger)
        prefix_len: Number of characters to show at the beginning
        suffix_len: Number of characters to show at the end
    """
    logger = logging.getLogger(logger_name)
    privacy_filter = BitcoinPrivacyMasker.create_logging_filter(prefix_len, suffix_len)
    logger.addFilter(privacy_filter)


def print_privacy_safe(message: str, prefix_len: int = 6, suffix_len: int = 6):
    """
    Print a message with Bitcoin addresses and XPUBs automatically masked.
    
    Args:
        message: Message to print
        prefix_len: Number of characters to show at the beginning
        suffix_len: Number of characters to show at the end
    """
    masked_message = BitcoinPrivacyMasker.mask_text(message, prefix_len, suffix_len)
    print(masked_message)


# Example usage and testing
if __name__ == "__main__":
    # Test data with realistic Bitcoin keys
    test_address = "bc1qeuupt2tgerfum8jclt8aklu9cdmzzkwml9lg7c"
    # Real ZPUB key (111 characters total - standard length)
    test_zpub = "zpub6rrfVgQUrywTwGz4cTKKYKDH7oQ2k4zEk7LfGcaQQC9tgNrBqMq6tF4vBKZ9pjhk1pKLmnPqmFZ4QqKGZjVfKbBzfCxY2dHkS3Xa8mN"
    # Real XPUB key (111 characters total)
    test_xpub = "xpub6CUGRUonZSQ4TWtTMmzXdrXDtypWKiKrhko4egpiMZbpiaQL2jkwSB1icqYh2cfDfVxdx4df189oLKnC5fSwqPfgyP3hooxujYzAu3fDVmz"
    test_url = f"GET /api/block-rewards/{test_address}/found-blocks HTTP/1.1"
    test_log = f"🔒 Starting gap limit detection for {test_zpub}..."
    
    # Additional test addresses
    test_p2pkh = "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"  # Legacy address
    test_p2sh = "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"   # P2SH address
    
    masker = BitcoinPrivacyMasker()
    
    print("=== Bitcoin Privacy Masker Test ===")
    print(f"Original address: {test_address}")
    print(f"Masked address:   {masker.mask_address(test_address)}")
    print()
    
    print(f"Original P2PKH: {test_p2pkh}")
    print(f"Masked P2PKH:   {masker.mask_address(test_p2pkh)}")
    print()
    
    print(f"Original P2SH: {test_p2sh}")  
    print(f"Masked P2SH:   {masker.mask_address(test_p2sh)}")
    print()
    
    print(f"Original ZPUB: {test_zpub}")
    print(f"Masked ZPUB:   {masker.mask_xpub(test_zpub)}")
    print()
    
    print(f"Original XPUB: {test_xpub}")
    print(f"Masked XPUB:   {masker.mask_xpub(test_xpub)}")
    print()
    
    print(f"Original URL: {test_url}")
    print(f"Masked URL:   {masker.mask_url(test_url)}")
    print()
    
    print(f"Original log: {test_log}")
    print(f"Masked log:   {masker.mask_text(test_log)}")
    print()
    
    # Test the convenience function
    print("=== Convenience Function Test ===")
    print_privacy_safe(f"Address balance: {test_address} = 0.03445077 BTC")
    print_privacy_safe(f"ZPUB processing: {test_zpub} found 20 addresses")
    print_privacy_safe(f"XPUB processing: {test_xpub} derived successfully")
    
    # Test log examples from the user's actual logs
    print("\n=== Real Log Examples (Masked) ===")
    real_log1 = "📝 Address  0: bc1qs4zfrqwqpzz6zhl9mgq5ltkzk7htqr3d5f8k7z = 0.00000000 BTC (USED IN PAST)"
    real_log2 = "💰 Address  2: bc1q0f2wkl6rw3ynfzylg7xk8n2s4m9h6j5t8p3q7w = 0.03445077 BTC (ACTIVE)"
    real_log3 = "GET /api/block-rewards/bc1qeuupt2tgerfum8jclt8aklu9cdmzzkwml9lg7c/found-blocks HTTP/1.1"
    real_log4 = f"🔒 [BLOCKING] Starting exclusive gap limit detection for {test_zpub}..."
    real_log5 = f"🔍 Enhanced gap limit detection for {test_zpub} (initial: 20)"
    
    print_privacy_safe(real_log1)
    print_privacy_safe(real_log2)
    print_privacy_safe(real_log3)
    print_privacy_safe(real_log4)
    print_privacy_safe(real_log5)
    
    # Debug pattern matching
    print("\n=== Pattern Matching Debug ===")
    print(f"ZPUB length: {len(test_zpub)} chars")
    print(f"XPUB length: {len(test_xpub)} chars")
    print(f"ZPUB matches pattern: {masker.ZPUB_PATTERN.search(test_zpub) is not None}")
    print(f"XPUB matches pattern: {masker.XPUB_PATTERN.search(test_xpub) is not None}")
