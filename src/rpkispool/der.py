"""
Minimal DER reader: just enough to walk CCR and manifest structures without dependencies.
"""

TAG_INTEGER = 0x02
TAG_BIT_STRING = 0x03
TAG_OCTET_STRING = 0x04
TAG_GENERALIZED_TIME = 0x18
TAG_SEQUENCE = 0x30


def read_tlv(buf: bytes, pos: int) -> tuple[int, int, int]:
    """
    Read the TLV header at pos and return (tag, value_start, length).

    The value occupies buf[value_start : value_start + length]; the next TLV starts right after it.
    Raises ValueError on truncated or indefinite-length encodings.
    """
    if pos + 2 > len(buf):
        raise ValueError(f"truncated TLV header at offset {pos}")

    tag = buf[pos]
    length = buf[pos + 1]
    start = pos + 2

    if length & 0x80:
        n = length & 0x7F
        if n == 0 or start + n > len(buf):
            raise ValueError(f"bad length encoding at offset {pos}")
        length = int.from_bytes(buf[start : start + n], "big")
        start += n

    if start + length > len(buf):
        raise ValueError(f"TLV at offset {pos} overruns buffer")

    return tag, start, length


def expect(buf: bytes, pos: int, tag: int) -> tuple[int, int]:
    """Read the TLV at pos, require it to have the given tag, and return (value_start, length)."""
    got, start, length = read_tlv(buf, pos)
    if got != tag:
        raise ValueError(f"expected tag {tag:#04x} at offset {pos}, got {got:#04x}")
    return start, length
