"""
Bitcoin Address Derivation Module

Derives Bitcoin addresses from xpub/zpub keys using pure Python implementation.
Supports both P2PKH (legacy) and P2WPKH (segwit) address formats.

"""

import hashlib
import hmac
from typing import List, Tuple, Optional
import struct


class AddressDerivation:
    """Bitcoin address derivation from extended public keys."""
    
    # Base58 alphabet
    BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    
    def __init__(self):
        """Initialize address derivation."""
        pass
    
    def _base58_decode(self, s: str) -> bytes:
        """Decode base58 string to bytes."""
        decoded = 0
        multi = 1
        s = s[::-1]
        for char in s:
            decoded += multi * self.BASE58_ALPHABET.index(char)
            multi *= 58
        
        h = f'{decoded:x}'
        if len(h) % 2:
            h = '0' + h
        res = bytes.fromhex(h)
        
        # Add leading zeros
        pad = 0
        for c in s[::-1]:
            if c == '1':
                pad += 1
            else:
                break
        
        return b'\x00' * pad + res
    
    def _base58_encode(self, b: bytes) -> str:
        """Encode bytes to base58 string."""
        # Convert bytes to integer
        decoded = int.from_bytes(b, 'big')
        
        # Convert to base58
        encoded = ''
        while decoded > 0:
            decoded, remainder = divmod(decoded, 58)
            encoded = self.BASE58_ALPHABET[remainder] + encoded
        
        # Add leading '1's for leading zeros
        for byte in b:
            if byte == 0:
                encoded = '1' + encoded
            else:
                break
        
        return encoded
    
    def _hash160(self, data: bytes) -> bytes:
        """Perform RIPEMD160(SHA256(data))."""
        sha256_hash = hashlib.sha256(data).digest()
        rmd160 = hashlib.new('ripemd160')
        rmd160.update(sha256_hash)
        return rmd160.digest()
    
    def _checksum(self, data: bytes) -> bytes:
        """Calculate 4-byte checksum for base58check encoding."""
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4]
    
    def _base58check_encode(self, version: int, payload: bytes) -> str:
        """Encode with version byte and checksum."""
        data = bytes([version]) + payload
        checksum = self._checksum(data)
        return self._base58_encode(data + checksum)
    
    def _bech32_polymod(self, values: List[int]) -> int:
        """Bech32 polymod function."""
        GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
        chk = 1
        for value in values:
            top = chk >> 25
            chk = (chk & 0x1ffffff) << 5 ^ value
            for i in range(5):
                chk ^= GEN[i] if ((top >> i) & 1) else 0
        return chk
    
    def _bech32_hrp_expand(self, hrp: str) -> List[int]:
        """Expand HRP for bech32."""
        return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]
    
    def _bech32_verify_checksum(self, hrp: str, data: List[int]) -> bool:
        """Verify bech32 checksum."""
        return self._bech32_polymod(self._bech32_hrp_expand(hrp) + data) == 1
    
    def _bech32_create_checksum(self, hrp: str, data: List[int]) -> List[int]:
        """Create bech32 checksum."""
        values = self._bech32_hrp_expand(hrp) + data
        polymod = self._bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
        return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    
    def _bech32_encode(self, hrp: str, data: List[int]) -> str:
        """Encode bech32 address."""
        BECH32_ALPHABET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
        combined = data + self._bech32_create_checksum(hrp, data)
        return hrp + '1' + ''.join([BECH32_ALPHABET[d] for d in combined])
    
    def _convertbits(self, data: List[int], frombits: int, tobits: int, pad: bool = True) -> Optional[List[int]]:
        """Convert between bit groups."""
        acc = 0
        bits = 0
        ret = []
        maxv = (1 << tobits) - 1
        max_acc = (1 << (frombits + tobits - 1)) - 1
        for value in data:
            if value < 0 or (value >> frombits):
                return None
            acc = ((acc << frombits) | value) & max_acc
            bits += frombits
            while bits >= tobits:
                bits -= tobits
                ret.append((acc >> bits) & maxv)
        if pad:
            if bits:
                ret.append((acc << (tobits - bits)) & maxv)
        elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
            return None
        return ret
    
    def _pubkey_to_p2pkh_address(self, pubkey: bytes) -> str:
        """Convert public key to P2PKH (legacy) address."""
        hash160 = self._hash160(pubkey)
        return self._base58check_encode(0x00, hash160)  # 0x00 = mainnet P2PKH
    
    def _pubkey_to_p2wpkh_address(self, pubkey: bytes) -> str:
        """Convert public key to P2WPKH (segwit) address."""
        hash160 = self._hash160(pubkey)
        converted = self._convertbits(list(hash160), 8, 5)
        if converted is None:
            raise ValueError("Failed to convert bits for bech32 encoding")
        return self._bech32_encode('bc', [0] + converted)
    
    def _point_add(self, p1: Tuple[int, int], p2: Tuple[int, int]) -> Tuple[int, int]:
        """Add two points on secp256k1 curve."""
        # secp256k1 parameters
        P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
        
        if p1 is None:
            return p2
        if p2 is None:
            return p1
        
        x1, y1 = p1
        x2, y2 = p2
        
        if x1 == x2:
            if y1 == y2:
                # Point doubling
                s = (3 * x1 * x1 * pow(2 * y1, P - 2, P)) % P
            else:
                # Points are inverses
                return None
        else:
            # Point addition
            s = ((y2 - y1) * pow(x2 - x1, P - 2, P)) % P
        
        x3 = (s * s - x1 - x2) % P
        y3 = (s * (x1 - x3) - y1) % P
        
        return (x3, y3)
    
    def _point_multiply(self, k: int, point: Tuple[int, int]) -> Tuple[int, int]:
        """Multiply point by scalar k."""
        if k == 0:
            return None
        if k == 1:
            return point
        
        result = None
        addend = point
        
        while k:
            if k & 1:
                result = self._point_add(result, addend)
            addend = self._point_add(addend, addend)
            k >>= 1
        
        return result
    
    def _derive_child_key(self, parent_key: bytes, parent_chain_code: bytes, index: int) -> Tuple[bytes, bytes]:
        """Derive child key using BIP32."""
        if index >= 2**31:
            raise ValueError("Hardened derivation not supported for public keys")
        
        # Create data for HMAC
        data = parent_key + struct.pack('>I', index)
        
        # Calculate HMAC-SHA512
        hmac_result = hmac.new(parent_chain_code, data, hashlib.sha512).digest()
        
        # Split result
        child_key_int = int.from_bytes(hmac_result[:32], 'big')
        child_chain_code = hmac_result[32:]
        
        # secp256k1 order
        N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
        
        # Parse parent public key
        if len(parent_key) == 33:
            # Compressed public key
            x = int.from_bytes(parent_key[1:], 'big')
            y_squared = (pow(x, 3, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F) + 7) % 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
            y = pow(y_squared, (0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F + 1) // 4, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F)
            if y % 2 != parent_key[0] - 2:
                y = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F - y
            parent_point = (x, y)
        else:
            raise ValueError("Invalid public key format")
        
        # Calculate child public key point
        G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
             0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)
        
        child_point = self._point_add(parent_point, self._point_multiply(child_key_int, G))
        
        if child_point is None:
            raise ValueError("Invalid child key derivation")
        
        # Compress the public key
        x, y = child_point
        prefix = 0x02 if y % 2 == 0 else 0x03
        child_public_key = bytes([prefix]) + x.to_bytes(32, 'big')
        
        return child_public_key, child_chain_code
    
    def parse_extended_key(self, extended_key: str) -> Tuple[bytes, bytes, str]:
        """
        Parse extended public key (xpub/zpub) and return public key, chain code, and format.
        
        Args:
            extended_key: Extended public key string
            
        Returns:
            Tuple of (public_key, chain_code, format)
            format is either 'p2pkh' for xpub or 'p2wpkh' for zpub
        """
        try:
            # Decode base58check
            decoded = self._base58_decode(extended_key)
            
            # Verify checksum
            payload = decoded[:-4]
            checksum = decoded[-4:]
            if self._checksum(payload) != checksum:
                raise ValueError("Invalid checksum")
            
            # Parse components
            version = struct.unpack('>I', payload[:4])[0]
            depth = payload[4]
            fingerprint = payload[5:9]
            child_number = struct.unpack('>I', payload[9:13])[0]
            chain_code = payload[13:45]
            public_key = payload[45:78]
            
            # Determine address format based on version
            if version == 0x0488B21E:  # xpub (mainnet P2PKH)
                address_format = 'p2pkh'
            elif version == 0x04B24746:  # zpub (mainnet P2WPKH)
                address_format = 'p2wpkh'
            else:
                raise ValueError(f"Unsupported extended key version: {version:08x}")
            
            return public_key, chain_code, address_format
            
        except Exception as e:
            raise ValueError(f"Failed to parse extended key: {e}")
    
    def derive_addresses(self, extended_key: str, count: int, start_index: int = 0) -> List[Tuple[str, int]]:
        """
        Derive addresses from extended public key.
        
        Args:
            extended_key: Extended public key (xpub/zpub)
            count: Number of addresses to derive
            start_index: Starting derivation index (default: 0)
            
        Returns:
            List of (address, index) tuples
        """
        try:
            public_key, chain_code, address_format = self.parse_extended_key(extended_key)
            print(f"[DEBUG] Extended key format detected: {address_format} ({extended_key[:8]}...)")
            addresses = []

            for i in range(start_index, start_index + count):
                try:
                    # Derive child key for external chain (0) and then address index
                    external_key, external_chain = self._derive_child_key(public_key, chain_code, 0)
                    child_key, _ = self._derive_child_key(external_key, external_chain, i)

                    # Generate address based on format
                    if address_format == 'p2pkh':
                        address = self._pubkey_to_p2pkh_address(child_key)
                    elif address_format == 'p2wpkh':
                        address = self._pubkey_to_p2wpkh_address(child_key)
                    else:
                        print(f"[ERROR] Unsupported address format: {address_format}")
                        continue

                    addresses.append((address, i))
                    print(f"[DEBUG] Derived address {i}: {address[:10]}...")

                except Exception as e:
                    print(f"[ERROR] Failed to derive address at index {i}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

            print(f"[DEBUG] Total addresses derived from {extended_key[:8]}...: {len(addresses)}")
            return addresses

        except Exception as e:
            print(f"[ERROR] Error deriving addresses from {extended_key[:20]}...: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def derive_addresses_range(self, extended_key: str, start_index: int, end_index: int) -> List[Tuple[str, int]]:
        """
        Derive addresses from extended public key for a specific range.
        
        Args:
            extended_key: Extended public key (xpub/zpub)
            start_index: Starting derivation index (inclusive)
            end_index: Ending derivation index (exclusive)
            
        Returns:
            List of (address, index) tuples for the range
        """
        if end_index <= start_index:
            return []
        
        count = end_index - start_index
        return self.derive_addresses(extended_key, count, start_index)
