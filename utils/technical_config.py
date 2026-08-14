"""
Technical Configuration Module

This module contains hardcoded technical settings that rarely need user modification.
These values follow industry standards and best practices for Bitcoin wallet scanning
and display rendering.

Version: 1.0
"""

import os
from urllib.parse import quote

from utils.tor_recovery import current_identity


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


# Known public mempool onion services, offered as presets in the config UI.
# The user can always type their own address instead — self-hosted mempool
# instances commonly run behind their own hidden service.
#
# Verify any address here against the operator's own site before trusting it.
# A v3 onion address *is* the service's public key plus a checksum, so a
# corrupted one fails to connect rather than silently reaching an impostor.
MEMPOOL_ONION_PRESETS = [
    {
        "id": "official",
        "label": "mempool.space (official)",
        "host": "mempoolhqx4isw62xs7abwphsq7ldayuidyx2v2oethdhhj6mlo2r6ad.onion",
        "use_https": False,   # onion services carry their own encryption
        "port": 80,
    },
]

MEMPOOL_DEFAULT_ONION = MEMPOOL_ONION_PRESETS[0]["host"]

# Onion addresses that used to be listed above and have since been replaced.
#
# The preset list ships in code, so a software update always carries the current
# address — but a user who already picked the old one has it saved in
# config.json, which updates never touch. Listing the retired address here lets
# validate_config() migrate those installs on the next save or startup, instead
# of silently leaving them pointed at a dead service.
#
# When the official address changes: move the old value into this set and put
# the new one in MEMPOOL_ONION_PRESETS. Nothing else needs to change.
MEMPOOL_ONION_SUPERSEDED = {
    # "oldaddress....onion",
}


def normalize_host(host):
    """Strip scheme, path and trailing slash from a pasted URL.

    mempool_host holds a bare hostname — the scheme comes from
    mempool_use_https and build_mempool_api_url() appends /api. Users
    understandably paste a whole URL, which would otherwise produce
    "http://http://host//api".
    """
    h = str(host or "").strip()
    if not h:
        return ""
    for scheme in ("http://", "https://"):
        if h.lower().startswith(scheme):
            h = h[len(scheme):]
            break
    return h.split("/", 1)[0].strip()


def is_onion_host(host):
    """True when host is a Tor hidden service address."""
    return normalize_host(host).lower().endswith(".onion")


def build_mempool_proxies(config):
    """Build a requests-style proxy dict for reaching the mempool host over Tor.

    Returns None when Tor routing is off, so callers can pass the result straight
    through to requests without branching.

    Scoped deliberately to mempool traffic only. Tor refuses to route private
    addresses, so applying this process-wide would break Bitaxe polling on the
    LAN — see the Bitaxe client, which never receives these proxies.

    socks5h (rather than socks5) hands hostname resolution to the proxy, which
    is required for .onion names: the local resolver cannot resolve them.

    The credentials are not authentication — tor's SOCKS port has none. They
    select a circuit: IsolateSOCKSAuth is on by default, so changing the
    username moves subsequent requests onto a fresh path. tor_recovery owns
    when that happens; here we only stamp whatever the current identity is.
    """
    if not config or not config.get("mempool_use_tor", False):
        return None

    host = config.get("tor_socks_host", "127.0.0.1") or "127.0.0.1"
    port = config.get("tor_socks_port", 9050) or 9050
    user, password = current_identity()
    endpoint = f"socks5h://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}"
    return {"http": endpoint, "https": endpoint}


def apply_tor_identity(proxies):
    """Restamp a proxies dict with the current circuit identity.

    For callers that built their proxies once and kept them: a rotation has to
    reach them too, or they carry on down the path that just failed. Returns
    the input untouched when Tor is off.
    """
    if not proxies:
        return proxies

    user, password = current_identity()
    userinfo = f"{quote(user, safe='')}:{quote(password, safe='')}@"
    restamped = {}
    for scheme, endpoint in proxies.items():
        head, _, tail = str(endpoint).partition("://")
        if not tail:
            restamped[scheme] = endpoint
            continue
        # Drop any identity already in there before stamping the current one.
        restamped[scheme] = f"{head}://{userinfo}{tail.rpartition('@')[2]}"
    return restamped


# How long a request routed through Tor may take to reach the point where the
# server answers. Tor sets this floor, not us:
#
#   - After a run of circuit timeouts, tor discards what it learned about the
#     network and resets its adaptive CircuitBuildTimeout to the conservative
#     60 s default ("Resetting timeout to 60000ms" in tor's log).
#   - A failed circuit is not a failed request. Tor retries on a fresh path and
#     only gives up at SocksTimeout, 120 s by default.
#
# A client deadline under those two numbers aborts attempts tor is still
# working on, and does it forever, so a merely slow network reads as a total
# outage until circuits happen to get fast again. Observed on 2026-08-14: a
# 60 s WebSocket deadline and 20 s REST deadlines against a 60 s circuit
# timeout kept a device offline for three and a half hours while tor was
# connecting the whole time.
TOR_CONNECT_TIMEOUT = 130


def build_mempool_ws_proxy_kwargs(config):
    """Proxy kwargs for websocket-client's run_forever().

    Mirrors build_mempool_proxies() for the WebSocket path. Returns {} when Tor
    is off so callers can splat it unconditionally.

    http_proxy_timeout is set explicitly because python-socks otherwise applies
    its own 60 s default — see TOR_CONNECT_TIMEOUT for why that number is the
    wrong one.
    """
    if not config or not config.get("mempool_use_tor", False):
        return {}

    return {
        "proxy_type": "socks5h",
        "http_proxy_host": config.get("tor_socks_host", "127.0.0.1") or "127.0.0.1",
        "http_proxy_port": int(config.get("tor_socks_port", 9050) or 9050),
        "http_proxy_timeout": TOR_CONNECT_TIMEOUT,
        # Circuit selection, not authentication — see build_mempool_proxies().
        # The kwargs are rebuilt for every reconnect, so a rotation between
        # attempts puts the next one on a different path.
        "http_proxy_auth": current_identity(),
    }


def mempool_request_timeout(base, proxies):
    """requests timeout for a mempool call, widened when it goes over Tor.

    Returns base unchanged for a LAN or clearnet instance, where the call sites'
    own numbers are right, and a (connect, read) pair over Tor.

    Splitting the two matters: reaching an onion costs a circuit build and a
    descriptor lookup, which is what needs the long deadline, while data over
    an already-established circuit is merely slow rather than minutes-slow. A
    single scaled scalar would have to be as long as the connect budget and
    would then let a stalled transfer hold the caller for two minutes.
    """
    if not proxies:
        return base
    return (TOR_CONNECT_TIMEOUT, max(base * 3, 30))


def build_mempool_api_url(host, port, use_https=False):
    """
    Build a mempool API base URL, handling domain vs IP and standard ports.
    
    Args:
        host: Hostname or IP address
        port: Port number (str or int)
        use_https: Whether to use HTTPS
        
    Returns:
        Base URL string like "https://mempool.example.com/api"
    """
    protocol = "https" if use_https else "http"
    port_str = str(port)
    is_domain = "." in host and not host.replace(".", "").isdigit()
    
    if is_domain and port_str in ("80", "443"):
        return f"{protocol}://{host}/api"
    return f"{protocol}://{host}:{port_str}/api"


# Device native resolution, width x height in landscape orientation.
# Shared: the config layer validates display_width/height against it and
# the renderer sizes output from it. Two copies kept in sync by a comment
# is a divergence waiting to happen.
DEVICE_DIMENSIONS = {
    "epd13in3E": (1600, 1200),
    "epd13in3k": (1600, 1200),
    "epd7in3f":  (800,  480),
    "waveshare_epd.epd13in3E": (1600, 1200),
    "waveshare_epd.epd13in3k": (1600, 1200),
    "waveshare_epd.epd7in3f":  (800,  480),
    "waveshare_epd.epd5in83_v2": (648, 480),
    "waveshare_epd.epd4in2":   (400, 300),
    "waveshare_epd.epd2in7":   (264, 176),
    "inky.auto":               (600, 448),
    "inky.impression":         (600, 448),
    "inky.what_red":           (400, 300),
    "inky.what_yellow":        (400, 300),
    "inky.what_black":         (400, 300),
    "omni_epd.mock":           (800, 600),
}
