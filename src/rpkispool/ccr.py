"""
Minimal parser for Canonical Cache Representation (CCR) files, only the parts needed for verification.

ContentInfo ::= SEQUENCE { contentType OID, content [0] EXPLICIT CanonicalCacheRepresentation }

CanonicalCacheRepresentation ::= SEQUENCE {
    version     [0] INTEGER DEFAULT 0,
    hashAlg     DigestAlgorithmIdentifier,
    producedAt  GeneralizedTime,
    mfts        [1] ManifestState OPTIONAL,
    ... }

ManifestState ::= SEQUENCE {
    mis                SEQUENCE OF ManifestInstance,    -- each starts with the manifest hash
    mostRecentUpdate   GeneralizedTime,
    hash               OCTET STRING }
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from rpkispool.der import TAG_GENERALIZED_TIME, TAG_OCTET_STRING, TAG_SEQUENCE, expect, read_tlv

_TAG_MFTS = 0xA1
_TAG_CONTENT = 0xA0


@dataclass
class CCR:
    produced_at: datetime
    most_recent_update: datetime | None
    manifest_hashes: set[bytes]


def parse_time(raw: bytes) -> datetime:
    """Parse a DER GeneralizedTime such as b'20261103000012Z'."""
    return datetime.strptime(raw.decode("ascii"), "%Y%m%d%H%M%SZ").replace(tzinfo=UTC)


def parse_ccr(data: bytes) -> CCR:
    """Parse a CCR; raises ValueError (or IndexError) on malformed input."""
    pos, _ = expect(data, 0, TAG_SEQUENCE)  # ContentInfo
    start, length = expect(data, pos, 0x06)  # contentType
    pos, _ = expect(data, start + length, _TAG_CONTENT)
    pos, length = expect(data, pos, TAG_SEQUENCE)  # CanonicalCacheRepresentation
    end = pos + length

    produced_at: datetime | None = None
    most_recent_update: datetime | None = None
    hashes: set[bytes] = set()

    while pos < end:
        tag, start, length = read_tlv(data, pos)

        if tag == TAG_GENERALIZED_TIME and produced_at is None:
            produced_at = parse_time(data[start : start + length])
        elif tag == _TAG_MFTS:
            most_recent_update = _parse_manifest_state(data, start, hashes)

        pos = start + length

    if produced_at is None:
        raise ValueError("producedAt not found")

    return CCR(produced_at, most_recent_update, hashes)


def _parse_manifest_state(data: bytes, pos: int, hashes: set[bytes]) -> datetime:
    pos, _ = expect(data, pos, TAG_SEQUENCE)  # ManifestState
    pos, length = expect(data, pos, TAG_SEQUENCE)  # mis
    end = pos + length

    while pos < end:
        _, start, length = read_tlv(data, pos)  # ManifestInstance
        hash_start, hash_len = expect(data, start, TAG_OCTET_STRING)
        if hash_len != 32:
            raise ValueError(f"manifest hash has {hash_len} bytes, expected 32")
        hashes.add(data[hash_start : hash_start + hash_len])
        pos = start + length

    start, length = expect(data, pos, TAG_GENERALIZED_TIME)  # mostRecentUpdate
    return parse_time(data[start : start + length])
