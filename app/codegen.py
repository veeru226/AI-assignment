"""Short-code generation.

Design: the database auto-increment id is the source of uniqueness (no collision
retries, no coordination between app instances). To keep codes from being
enumerable (id 1 -> "0000001", id 2 -> "0000002"), the id is passed through a
keyed Feistel permutation over a 40-bit domain before Base62 encoding. A
permutation is a bijection, so uniqueness is preserved, and the output is always
exactly 7 Base62 characters (2**40 < 62**7).
"""
import hashlib
import hmac

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE = len(ALPHABET)
CODE_LENGTH = 7
_HALF_BITS = 20
_HALF_MASK = (1 << _HALF_BITS) - 1
MAX_ID = (1 << (2 * _HALF_BITS)) - 1
_ROUNDS = 4


def base62_encode(value: int, width: int = CODE_LENGTH) -> str:
    """Encode a non-negative integer as Base62, left-padded with the zero character to width."""
    if value < 0:
        raise ValueError("value must be non-negative")
    chars = []
    while value:
        value, rem = divmod(value, BASE)
        chars.append(ALPHABET[rem])
    return "".join(reversed(chars)).rjust(width, ALPHABET[0])


def base62_decode(code: str) -> int:
    """Decode a Base62 string to an integer, raising ValueError on invalid characters."""
    value = 0
    for ch in code:
        idx = ALPHABET.find(ch)
        if idx < 0:
            raise ValueError(f"invalid base62 character: {ch!r}")
        value = value * BASE + idx
    return value


class CodeGenerator:
    def __init__(self, secret: str):
        """Derive the Feistel round key from the secret."""
        self._key = hashlib.sha256(secret.encode()).digest()

    def _round(self, round_no: int, half: int) -> int:
        """Return the keyed HMAC-based round function output for one Feistel half."""
        digest = hmac.new(self._key, bytes([round_no]) + half.to_bytes(3, "big"), hashlib.sha256).digest()
        return int.from_bytes(digest[:3], "big") & _HALF_MASK

    def encode(self, link_id: int) -> str:
        """Map a link id to its obfuscated 7-character Base62 short code."""
        if not 0 <= link_id <= MAX_ID:
            raise ValueError(f"id out of range (max {MAX_ID})")
        left, right = link_id >> _HALF_BITS, link_id & _HALF_MASK
        for r in range(_ROUNDS):
            left, right = right, left ^ self._round(r, right)
        return base62_encode((left << _HALF_BITS) | right)

    def decode(self, code: str) -> int:
        """Invert encode(): recover the link id from a short code, raising ValueError if out of range."""
        value = base62_decode(code)
        if value > MAX_ID:
            raise ValueError("code out of range")
        left, right = value >> _HALF_BITS, value & _HALF_MASK
        for r in reversed(range(_ROUNDS)):
            left, right = right ^ self._round(r, left), left
        return (left << _HALF_BITS) | right
