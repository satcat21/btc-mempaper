"""
Technical Configuration Module

This module contains hardcoded technical settings that rarely need user modification.
These values follow industry standards and best practices for Bitcoin wallet scanning
and display rendering.

Version: 1.0
"""

import os


class TechnicalConfig:
    """
    Technical configuration with industry-standard defaults.
    These settings are rarely changed and are better handled in code.
    """
    
    # === Font Configuration ===
    # Standard font paths - fallback to system fonts if custom fonts not available
    FONT_REGULAR = "static/fonts/Roboto-Regular.ttf"
    FONT_BOLD = "static/fonts/Roboto-Bold.ttf"
    
    # Date font sizing - optimized for most e-paper displays
    DATE_FONT_MAX_SIZE = 48  # Large enough for readability
    DATE_FONT_MIN_SIZE = 24  # Minimum readable size
    
    # === Display Configuration ===
    # Block height display area - optimized for standard layouts
    BLOCK_HEIGHT_AREA = 180  # Pixels - works well with most display sizes
    
    # === Network Configuration ===
    # Network outage tolerance before stopping reconnection attempts (in minutes)
    NETWORK_OUTAGE_TOLERANCE_MINUTES = 30  # 30 minutes is reasonable for temporary outages
    
    # === XPUB/ZPUB Wallet Scanning Configuration ===
    # These values follow BIP-44 standards and industry best practices
    
    # Address derivation count - standard range for wallet scanning
    XPUB_DERIVATION_COUNT = 50  # Industry standard for initial scan
    
    # Gap limit settings - BIP-44 recommendation is 20
    XPUB_GAP_LIMIT_LAST_N = 20  # BIP-44 standard gap limit
    XPUB_GAP_LIMIT_INCREMENT = 20  # Efficient batch size for expansion
    
    # Bootstrap search settings - optimized for performance
    XPUB_BOOTSTRAP_MAX_ADDRESSES = 200  # Reasonable upper limit
    XPUB_BOOTSTRAP_INCREMENT = 20  # Efficient batch processing
    
    # Always enable advanced features for better wallet detection
    XPUB_ENABLE_GAP_LIMIT = True  # Essential for complete wallet scanning
    XPUB_ENABLE_BOOTSTRAP_SEARCH = True  # Essential for finding active wallets
    
    @staticmethod
    def get_font_path(font_type="regular"):
        """
        Get the absolute path to font files with fallback handling.
        
        Args:
            font_type (str): "regular" or "bold"
            
        Returns:
            str: Path to font file, or empty string if not found
        """
        if font_type == "bold":
            font_path = TechnicalConfig.FONT_BOLD
        else:
            font_path = TechnicalConfig.FONT_REGULAR
            
        # Check if custom font exists
        if os.path.exists(font_path):
            return font_path
            
        # Return empty string to let the system handle font fallback
        return ""
    
    @staticmethod
    def get_xpub_config():
        """
        Get all XPUB-related configuration as a dictionary.
        
        Returns:
            dict: Complete XPUB configuration
        """
        return {
            'xpub_derivation_count': TechnicalConfig.XPUB_DERIVATION_COUNT,
            'xpub_enable_gap_limit': TechnicalConfig.XPUB_ENABLE_GAP_LIMIT,
            'xpub_gap_limit_last_n': TechnicalConfig.XPUB_GAP_LIMIT_LAST_N,
            'xpub_gap_limit_increment': TechnicalConfig.XPUB_GAP_LIMIT_INCREMENT,
            'xpub_enable_bootstrap_search': TechnicalConfig.XPUB_ENABLE_BOOTSTRAP_SEARCH,
            'xpub_bootstrap_max_addresses': TechnicalConfig.XPUB_BOOTSTRAP_MAX_ADDRESSES,
            'xpub_bootstrap_increment': TechnicalConfig.XPUB_BOOTSTRAP_INCREMENT,
        }
    
    @staticmethod
    def get_display_config():
        """
        Get all display-related configuration as a dictionary.
        
        Returns:
            dict: Complete display configuration
        """
        return {
            'font_regular': TechnicalConfig.get_font_path("regular"),
            'font_bold': TechnicalConfig.get_font_path("bold"),
            'date_font_max_size': TechnicalConfig.DATE_FONT_MAX_SIZE,
            'date_font_min_size': TechnicalConfig.DATE_FONT_MIN_SIZE,
            'block_height_area': TechnicalConfig.BLOCK_HEIGHT_AREA,
        }
    
    @staticmethod
    def get_network_config():
        """
        Get all network-related configuration as a dictionary.
        
        Returns:
            dict: Complete network configuration
        """
        return {
            'network_outage_tolerance_minutes': TechnicalConfig.NETWORK_OUTAGE_TOLERANCE_MINUTES,
        }
    
    @staticmethod
    def get_all_technical_settings():
        """
        Get all technical settings as a single dictionary.
        
        Returns:
            dict: All technical configuration values
        """
        config = {}
        config.update(TechnicalConfig.get_xpub_config())
        config.update(TechnicalConfig.get_display_config())
        config.update(TechnicalConfig.get_network_config())
        return config
    
    @staticmethod
    def log_technical_settings():
        """Log the current technical settings for debugging."""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("🔧 Technical Configuration Loaded:")
        logger.info(f"  📱 XPUB derivation count: {TechnicalConfig.XPUB_DERIVATION_COUNT}")
        logger.info(f"  📱 Gap limit: {TechnicalConfig.XPUB_GAP_LIMIT_LAST_N}")
        logger.info(f"  📱 Bootstrap max: {TechnicalConfig.XPUB_BOOTSTRAP_MAX_ADDRESSES}")
        logger.info(f"  🖥️  Block height area: {TechnicalConfig.BLOCK_HEIGHT_AREA}px")
        logger.info(f"  🖥️  Date font range: {TechnicalConfig.DATE_FONT_MIN_SIZE}-{TechnicalConfig.DATE_FONT_MAX_SIZE}px")
        logger.info(f"  🌐 Network outage tolerance: {TechnicalConfig.NETWORK_OUTAGE_TOLERANCE_MINUTES} minutes")
