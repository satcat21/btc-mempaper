"""
Mempool API Integration Module

This module handles all interactions with the Bitcoin mempool API including:
- Block height and hash retrieval
- REST API communication
- Error handling and fallbacks
"""

import time

import requests
from requests.auth import HTTPBasicAuth
from utils.technical_config import (build_mempool_api_url, apply_tor_identity,
                                    mempool_request_timeout)
from utils.tor_recovery import tor_recovery


# /v1/fees/recommended is the rounded view: it floors every tier at 1 sat/vB and
# reports whole numbers, so a mempool clearing at 0.4 and one clearing at 1.4
# both read "1". /v1/fees/precise is the same computation without that floor and
# rounding - three decimals, down to 0.001 - which is the difference between a
# quiet week and a busy one whenever blocks clear below 1 sat/vB.
#
# The endpoint arrived in mempool v2.5, so an older self-hosted backend answers
# 404 and we fall back to the rounded numbers. That verdict is remembered rather
# than re-tested on every poll, but only for an hour, so upgrading the backend
# starts showing decimals without restarting the device.
PRECISE_FEE_REPROBE = 3600


def quantize_fee(value):
    """Round one fee to the precision that is actually acted on.

    Three decimals move on nearly every poll, and every change invalidates the
    pre-rendered image and costs an e-ink refresh - so precision nobody can read
    would be paid for in screen refreshes. A tenth is as fine as the label gets
    below 10 sat/vB, and above that a tenth is noise. Rates under 0.1 keep all
    three decimals, since rounding those to a tenth would flatten a relay
    minimum to either 0.1 or nothing.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return value
    if v >= 10:
        return int(round(v))
    if v >= 0.1:
        return round(v, 1)
    return round(v, 3)


class MempoolAPI:
    """Handles communication with Bitcoin mempool API."""
    
    def __init__(self, host="127.0.0.1", port="4081", use_https=False, verify_ssl=True,
                 username=None, password=None, proxies=None):
        self.host = host
        self.port = port
        self.use_https = use_https
        self.verify_ssl = verify_ssl
        self.username = username
        self.password = password
        self.auth = HTTPBasicAuth(username, password) if username and password else None
        # None when Tor routing is off — requests treats that as "no proxy".
        self.proxies = proxies
        self.base_url = build_mempool_api_url(host, port, use_https)

        # None until the first fee call learns whether this backend serves
        # /v1/fees/precise; False is re-probed after PRECISE_FEE_REPROBE.
        self._precise_fees = None
        self._precise_probed_at = 0.0

        # Fallback values for when API is unavailable
        self.fallback_data = {
            "block_height": 0,
            "block_hash": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
        }

    def _timeout(self, base):
        """Timeout for one call: the number below on a LAN, widened over Tor.

        The per-call numbers stay tuned for a LAN or clearnet instance, and
        mempool_request_timeout() holds the Tor reasoning in one place.
        """
        return mempool_request_timeout(base, self.proxies)

    def _get(self, url, base_timeout):
        """GET one mempool endpoint, reporting the outcome to the Tor ladder.

        Every call goes through here so that "has anything reached the mempool
        host lately" has a single answer, and so a circuit rotation reaches a
        client that was handed its proxies once at construction.

        Any HTTP response counts as success, including an error status: the
        ladder repairs the transport, and a 500 proves the transport worked.
        """
        over_tor = bool(self.proxies)
        try:
            response = requests.get(
                url, timeout=self._timeout(base_timeout), verify=self.verify_ssl,
                auth=self.auth, proxies=apply_tor_identity(self.proxies))
        except requests.RequestException:
            if over_tor:
                tor_recovery.record_failure("mempool REST", over_tor)
            raise
        if over_tor:
            tor_recovery.record_success()
        return response

    def get_tip_height(self):
        """
        Get the current blockchain tip height.
        
        Returns:
            int: Block height as integer (or 0 if failed)
        """
        try:
            url = f"{self.base_url}/blocks/tip/height"
            response = self._get(url, 5)
            response.raise_for_status()
            height_str = response.text.strip()
            
            # If height is 0, try to recover using tip hash
            if str(height_str) == "0":
                 print("⚠️ Tip height is 0, attempting recovery via tip hash...")
                 tip_hash = self.get_tip_hash()
                 if tip_hash and tip_hash != self.fallback_data["block_hash"]:
                     recovered_height = self.get_height_from_hash(tip_hash)
                     if str(recovered_height) != "0":
                         return int(recovered_height)
            
            return int(height_str)
        except (requests.RequestException, ValueError) as e:
            print(f"Error fetching block height: {e}")
            return int(self.fallback_data["block_height"])
    
    def get_tip_hash(self):
        """
        Get the current blockchain tip hash.
        
        Returns:
            str: Block hash as string
        """
        try:
            url = f"{self.base_url}/blocks/tip/hash"
            response = self._get(url, 5)
            response.raise_for_status()
            return response.text.strip()
        except requests.RequestException as e:
            print(f"Error fetching block hash: {e}")
            return self.fallback_data["block_hash"]
    
    def get_height_from_hash(self, block_hash):
        """
        Get block height for a specific block hash.
        
        Args:
            block_hash (str): The hash of the block to query
            
        Returns:
            int: Block height as integer, or 0 if failed
        """
        try:
            url = f"{self.base_url}/block/{block_hash}"
            response = self._get(url, 5)
            response.raise_for_status()
            data = response.json()
            return int(data.get("height", 0))
        except Exception as e:
            print(f"Error fetching block details for hash {block_hash}: {e}")
            return 0

    def get_current_block_info(self):
        """
        Get both current block height and hash.
        
        Returns:
            dict: Dictionary containing 'block_height' and 'block_hash'
        """
        try:
            height = self.get_tip_height()
            block_hash = self.get_tip_hash()
            
            # Correction logic: If height is 0 but hash is valid (not genesis/fallback),
            # assume height fetch failed and try to look it up via hash
            fallback_hash = self.fallback_data["block_hash"]
            if (height == 0 or height is None) and block_hash and block_hash != fallback_hash and block_hash != "0":
                 print(f"⚠️ Height is 0 but have valid hash {block_hash[:8]}... - Attempting recovery via block details")
                 recovered_height = self.get_height_from_hash(block_hash)
                 if recovered_height != 0:
                     print(f"✅ Recovered block height: {recovered_height}")
                     height = recovered_height
            
            # Format hash for display: first 6 + last 6 characters with grouping
            hash_first = block_hash[:6]
            hash_last = block_hash[-6:]
            # Group characters in pairs
            hash_first_grouped = ' '.join([hash_first[i:i+2] for i in range(0, len(hash_first), 2)])
            hash_last_grouped = ' '.join([hash_last[i:i+2] for i in range(0, len(hash_last), 2)])
            hash_display = f"{hash_first_grouped} ... {hash_last_grouped}"
            
            return {
                "block_height": height,
                "block_hash": block_hash
            }
        except Exception as e:
            print(f"Error getting block info, using fallback: {e}")
            return self.fallback_data.copy()
    
    def format_block_height(self, raw_height):
        """
        Format block height for display (add thousand separators).
        
        Args:
            raw_height (str): Raw block height string
            
        Returns:
            str: Formatted block height
        """
        try:
            height_int = int(raw_height)
            return f"{height_int:,}".replace(",", ".")
        except (ValueError, TypeError):
            return str(raw_height)
    
    def _fetch_fees(self, path):
        """One fee endpoint, decoded. Raises like any other call in here."""
        response = self._get(f"{self.base_url}{path}", 10)
        response.raise_for_status()
        return response.json()

    def _try_precise_fees(self):
        """Sub-1 sat/vB tiers, or None if this backend does not serve them."""
        if self._precise_fees is False and (
                time.time() - self._precise_probed_at) < PRECISE_FEE_REPROBE:
            return None
        try:
            fees = self._fetch_fees("/v1/fees/precise")
        except requests.HTTPError:
            # Backend predates the endpoint. Transport failures deliberately
            # do not land here - they say nothing about what it supports, and
            # are left to fail the fallback call the same way they always have.
            if self._precise_fees is not False:
                print("ℹ️ Mempool backend has no /v1/fees/precise — fees stay whole numbers")
            self._precise_fees = False
            self._precise_probed_at = time.time()
            return None
        self._precise_fees = True
        return fees

    def get_fee_recommendations(self):
        """
        Get current fee recommendations from mempool API.

        Prefers the unrounded tiers so a mempool clearing below 1 sat/vB reads
        as what it is, and quantizes them to display precision - see
        quantize_fee() for why the extra decimals are not carried further.

        Returns:
            dict: Fee recommendations or None if failed
        """
        try:
            fees = self._try_precise_fees()
            if fees is None:
                fees = self._fetch_fees("/v1/fees/recommended")
        except requests.RequestException as e:
            print(f"Error fetching fee recommendations: {e}")
            return None
        return {tier: quantize_fee(value) for tier, value in fees.items()}

    def get_configured_fee(self, fee_parameter="minimumFee"):
        """
        Get the fee value for the specified parameter.

        Args:
            fee_parameter (str): Which fee parameter to use (fastestFee, halfHourFee, hourFee, economyFee, minimumFee)

        Returns:
            float: Fee in sat/vB, a fraction when the mempool is clearing below
                   1 sat/vB, or None if failed
        """
        fees = self.get_fee_recommendations()
        if fees:
            fee_value = fees.get(fee_parameter, 1)
            print(f"💾 Fee info: {fee_value} sat/vB ({fee_parameter})")
            return fee_value
        return None

    def get_hashrate_and_difficulty(self):
        """
        Get current network hashrate and difficulty from mempool API.

        Returns:
            dict: {'currentHashrate': float (H/s), 'currentDifficulty': float} or None if failed
        """
        try:
            url = f"{self.base_url}/v1/mining/hashrate/1m"
            response = self._get(url, 10)
            response.raise_for_status()
            data = response.json()
            return {
                "currentHashrate": data.get("currentHashrate", 0),
                "currentDifficulty": data.get("currentDifficulty", 0),
            }
        except requests.RequestException as e:
            print(f"Error fetching hashrate/difficulty: {e}")
            return None

    def get_network_stats(self):
        """
        Get the combined network stats used by the network and halving blocks.

        Merges hashrate/difficulty with the difficulty-adjustment fields so every
        caller sees the same shape. `adjustedTimeAvg` is mempool's noise-corrected
        block pace; `epochRemainingBlocks` is how far the current difficulty epoch
        still has to run. Both are needed for a stable halving estimate.

        The two lookups fail independently, since they feed different blocks. A missing
        difficulty adjustment still renders hashrate and leaves the halving estimate on
        the 600 s target; a missing hashrate sets an error marker so the network block
        skips itself, while the halving keeps whatever pace fields did arrive.

        Returns:
            dict, or None if both lookups failed.
        """
        hd = self.get_hashrate_and_difficulty()
        da = self.get_difficulty_adjustment() or {}
        if not hd and not da:
            return None
        stats = {
            "timeAvg": da.get("timeAvg", 600000),
            "adjustedTimeAvg": da.get("adjustedTimeAvg"),
            "epochRemainingBlocks": da.get("remainingBlocks"),
        }
        if hd:
            stats["currentHashrate"] = hd.get("currentHashrate", 0)
            stats["currentDifficulty"] = hd.get("currentDifficulty", 0)
        else:
            stats["error"] = "hashrate unavailable"
        return stats

    def get_difficulty_adjustment(self):
        """
        Get difficulty adjustment info including average block time for current epoch.

        Returns:
            dict with keys: timeAvg (ms per block), remainingBlocks, estimatedRetargetDate, etc.
            or None if failed
        """
        try:
            url = f"{self.base_url}/v1/difficulty-adjustment"
            response = self._get(url, 10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching difficulty adjustment: {e}")
            return None
