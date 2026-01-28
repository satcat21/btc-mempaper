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



