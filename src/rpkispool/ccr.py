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

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from rpkispool.der import TAG_GENERALIZED_TIME, TAG_OCTET_STRING, TAG_SEQUENCE, encode_tlv, expect, read_tlv

_TAG_MFTS = 0xA1
_TAG_CONTENT = 0xA0
# vrps, vaps, tas, rks: sections dropped from reduced CCRs
_TAGS_DROPPED = (0xA2, 0xA3, 0xA4, 0xA5)


@dataclass
class CCR:
    produced_at: datetime
    most_recent_update: datetime | None
    manifest_hashes: set[bytes]


def parse_time(raw: bytes) -> datetime:
    """Parse a DER GeneralizedTime such as b'20261103000012Z'."""
    return datetime.strptime(raw.decode("ascii"), "%Y%m%d%H%M%SZ").replace(tzinfo=UTC)


def _ccr_body(data: bytes) -> tuple[bytes, int, int]:
    """Return the raw contentType TLV and the (start, end) of the CanonicalCacheRepresentation content."""
    pos, _ = expect(data, 0, TAG_SEQUENCE)  # ContentInfo
    start, length = expect(data, pos, 0x06)  # contentType
    content_type = data[pos : start + length]
    pos, _ = expect(data, start + length, _TAG_CONTENT)
    pos, length = expect(data, pos, TAG_SEQUENCE)  # CanonicalCacheRepresentation
    return content_type, pos, pos + length


def parse_ccr(data: bytes) -> CCR:
    """Parse a CCR; raises ValueError (or IndexError) on malformed input."""
    _, pos, end = _ccr_body(data)

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


def mfts_section(data: bytes) -> bytes | None:
    """Return the raw [1] ManifestState section of a CCR, or None if it has none."""
    _, pos, end = _ccr_body(data)
    while pos < end:
        tag, start, length = read_tlv(data, pos)
        if tag == _TAG_MFTS:
            return data[pos : start + length]
        pos = start + length
    return None


def _instance_hash(raw: bytes) -> bytes:
    _, start, _ = read_tlv(raw, 0)
    hash_start, hash_len = expect(raw, start, TAG_OCTET_STRING)
    return raw[hash_start : hash_start + hash_len]


def split_manifest_instances(data: bytes) -> list[tuple[bytes, bytes]]:
    """Return (hash, raw DER of the ManifestInstance) for every manifest in a CCR, in file order."""
    section = mfts_section(data)
    if section is None:
        return []

    pos, _ = expect(section, 0, _TAG_MFTS)
    pos, _ = expect(section, pos, TAG_SEQUENCE)  # ManifestState
    pos, length = expect(section, pos, TAG_SEQUENCE)  # mis
    end = pos + length

    out = []
    while pos < end:
        _, start, length = read_tlv(section, pos)
        raw = section[pos : start + length]
        out.append((_instance_hash(raw), raw))
        pos = start + length
    return out


def encode_ccr(template: bytes, instances: list[bytes]) -> bytes:
    """
    Build a reduced CCR from a template CCR and raw ManifestInstance encodings.

    The contentType, version, hashAlg and producedAt of the template are kept verbatim, as is
    mostRecentUpdate. The vrps, vaps, tas and rks sections are dropped (only one section is
    required). Instances are sorted by hash and ManifestState.hash is the SHA-256 of the DER
    encoding of mis, including its tag and length.
    """
    content_type, pos, end = _ccr_body(template)

    head = b""
    most_recent_update = None
    while pos < end:
        tag, start, length = read_tlv(template, pos)
        if tag == _TAG_MFTS:
            state, _ = expect(template, start, TAG_SEQUENCE)
            mis, mis_len = expect(template, state, TAG_SEQUENCE)
            time_pos = mis + mis_len
            _, time_start, time_len = read_tlv(template, time_pos)
            most_recent_update = template[time_pos : time_start + time_len]
        elif tag not in _TAGS_DROPPED:
            head += template[pos : start + length]
        pos = start + length

    if most_recent_update is None:
        raise ValueError("template has no manifest state")

    hashes = [_instance_hash(raw) for raw in instances]
    if len(set(hashes)) != len(hashes):
        raise ValueError("duplicate manifest instances")

    mis_tlv = encode_tlv(TAG_SEQUENCE, b"".join(raw for _, raw in sorted(zip(hashes, instances))))
    state_tlv = encode_tlv(TAG_SEQUENCE, mis_tlv + most_recent_update + encode_tlv(TAG_OCTET_STRING, hashlib.sha256(mis_tlv).digest()))
    body = encode_tlv(TAG_SEQUENCE, head + encode_tlv(_TAG_MFTS, state_tlv))
    return encode_tlv(TAG_SEQUENCE, content_type + encode_tlv(_TAG_CONTENT, body))
