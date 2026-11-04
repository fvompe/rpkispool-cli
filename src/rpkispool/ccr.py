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
import ipaddress
from array import array
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NamedTuple

from rpkispool.der import TAG_BIT_STRING, TAG_GENERALIZED_TIME, TAG_INTEGER, TAG_OCTET_STRING, TAG_SEQUENCE, encode_tlv, expect, read_tlv

_TAG_MFTS = 0xA1
TAG_VRPS = 0xA2
TAG_VAPS = 0xA3
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


def produced_at(data: bytes) -> datetime:
    """Return producedAt of a CCR, reading only its header (parse_ccr also decodes all manifests)."""
    _, pos, end = _ccr_body(data)
    while pos < end:
        tag, start, length = read_tlv(data, pos)
        if tag == TAG_GENERALIZED_TIME:
            return parse_time(data[start : start + length])
        pos = start + length
    raise ValueError("producedAt not found")


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


def encode_ccr(template: bytes, instances: list[bytes], roa_payload_sets: list[bytes] | None = None, aspa_payload_sets: list[bytes] | None = None) -> bytes:
    """
    Build a reduced CCR from a template CCR and raw ManifestInstance encodings.

    The contentType, version, hashAlg and producedAt of the template are kept verbatim, as is
    mostRecentUpdate. The vrps, vaps, tas and rks sections are dropped (only one section is
    required), unless roa_payload_sets or aspa_payload_sets (raw ROAPayloadSet and ASPAPayloadSet
    encodings) are given: they become the vrps and vaps sections. Instances are sorted by hash and ManifestState.hash is the SHA-256 of the DER
    encoding of mis, including its tag and length; ROAPayloadState.hash is computed the same way
    over rps.
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
    sections = head + encode_tlv(_TAG_MFTS, state_tlv)
    if roa_payload_sets is not None:
        sections += _encode_payload_state(TAG_VRPS, roa_payload_sets)
    if aspa_payload_sets is not None:
        sections += _encode_payload_state(TAG_VAPS, aspa_payload_sets)

    body = encode_tlv(TAG_SEQUENCE, sections)
    return encode_tlv(TAG_SEQUENCE, content_type + encode_tlv(_TAG_CONTENT, body))


def _encode_payload_state(section: int, sets: list[bytes]) -> bytes:
    """The vrps or vaps section: sets ordered by AS number, hash = SHA-256 of the DER encoding of the sets."""
    ordered = sorted(sets, key=_payload_set_asn)
    sets_tlv = encode_tlv(TAG_SEQUENCE, b"".join(ordered))
    state = encode_tlv(TAG_SEQUENCE, sets_tlv + encode_tlv(TAG_OCTET_STRING, hashlib.sha256(sets_tlv).digest()))
    return encode_tlv(section, state)


class Vrp(NamedTuple):
    """A validated ROA payload: address family (1 IPv4, 2 IPv6), address as integer, lengths and AS."""

    afi: int
    address: int
    plen: int
    maxlen: int
    asn: int


def payload_state(data: bytes, section: int) -> tuple[bytes, bytes] | None:
    _, pos, end = _ccr_body(data)
    while pos < end:
        tag, start, length = read_tlv(data, pos)
        if tag == section:
            state, _ = expect(data, start, TAG_SEQUENCE)  # ROAPayloadState or ASPAPayloadState
            sets_start, sets_len = expect(data, state, TAG_SEQUENCE)  # rps or aps
            hash_start, hash_len = expect(data, sets_start + sets_len, TAG_OCTET_STRING)
            if hash_len != 32:
                raise ValueError(f"payload state hash has {hash_len} bytes, expected 32")
            return data[sets_start : sets_start + sets_len], data[hash_start : hash_start + hash_len]
        pos = start + length
    return None


def roa_payload_state(data: bytes) -> tuple[bytes, bytes] | None:
    """Return (contents of rps, ROAPayloadState.hash) of a CCR, or None if it has no vrps section."""
    return payload_state(data, TAG_VRPS)


def aspa_payload_state(data: bytes) -> tuple[bytes, bytes] | None:
    """Return (contents of aps, ASPAPayloadState.hash) of a CCR, or None if it has no vaps section."""
    return payload_state(data, TAG_VAPS)


def index_payload_sets(rps: bytes) -> tuple[array[int], array[int], array[int]]:
    """
    Return (asn, start, end) arrays for the ROAPayloadSets in the contents of rps.

    This is the hot loop for large CCRs (60k+ sets), so the headers are parsed inline.
    """
    asns: array[int] = array("Q")
    starts: array[int] = array("Q")
    ends: array[int] = array("Q")

    pos, size = 0, len(rps)
    while pos < size:
        length = rps[pos + 1]
        body = pos + 2
        if length & 0x80:
            n = length & 0x7F
            length = int.from_bytes(rps[body : body + n], "big")
            body += n
        end = body + length
        if rps[pos] != TAG_SEQUENCE or rps[body] != TAG_INTEGER or end > size:
            raise ValueError(f"bad ROAPayloadSet at offset {pos}")
        as_len = rps[body + 1]
        asns.append(int.from_bytes(rps[body + 2 : body + 2 + as_len], "big"))
        starts.append(pos)
        ends.append(end)
        pos = end
    return asns, starts, ends


def _payload_set_asn(raw: bytes) -> int:
    _, start, _ = read_tlv(raw, 0)
    as_start, as_len = expect(raw, start, TAG_INTEGER)
    return int.from_bytes(raw[as_start : as_start + as_len], "big")


def decode_payload_set(raw: bytes) -> list[Vrp]:
    """Decode one raw ROAPayloadSet into its VRPs."""
    start, _ = expect(raw, 0, TAG_SEQUENCE)
    as_start, as_len = expect(raw, start, TAG_INTEGER)
    asn = int.from_bytes(raw[as_start : as_start + as_len], "big")
    pos, length = expect(raw, as_start + as_len, TAG_SEQUENCE)  # ipAddrBlocks
    end = pos + length

    vrps = []
    while pos < end:
        _, family, family_len = read_tlv(raw, pos)  # ROAIPAddressFamily
        afi_start, afi_len = expect(raw, family, TAG_OCTET_STRING)
        afi = int.from_bytes(raw[afi_start : afi_start + afi_len], "big")
        if afi not in (1, 2):
            raise ValueError(f"unsupported address family {afi}")
        size = 4 if afi == 1 else 16

        addr_pos, addr_len = expect(raw, afi_start + afi_len, TAG_SEQUENCE)  # addresses
        addr_end = addr_pos + addr_len
        while addr_pos < addr_end:
            _, entry, entry_len = read_tlv(raw, addr_pos)  # ROAIPAddress
            bits_start, bits_len = expect(raw, entry, TAG_BIT_STRING)
            unused = raw[bits_start]
            octets = raw[bits_start + 1 : bits_start + bits_len]
            plen = len(octets) * 8 - unused
            if len(octets) > size or unused > 7:
                raise ValueError("bad address bit string")
            address = int.from_bytes(octets + bytes(size - len(octets)), "big")

            maxlen = plen
            next_pos = bits_start + bits_len
            if next_pos < entry + entry_len:
                max_start, max_len = expect(raw, next_pos, TAG_INTEGER)
                maxlen = int.from_bytes(raw[max_start : max_start + max_len], "big")

            vrps.append(Vrp(afi, address, plen, maxlen, asn))
            addr_pos = entry + entry_len
        pos = family + family_len
    return vrps


def format_vrp(vrp: Vrp) -> str:
    """Format as 'prefix/plen[-maxlen] AS<asn>', e.g. '169.40.38.0/23-24 AS834'."""
    size = 4 if vrp.afi == 1 else 16
    text = f"{ipaddress.ip_address(vrp.address.to_bytes(size, 'big'))}/{vrp.plen}"
    if vrp.maxlen != vrp.plen:
        text += f"-{vrp.maxlen}"
    return f"{text} AS{vrp.asn}"


def _encode_int(value: int) -> bytes:
    return encode_tlv(TAG_INTEGER, value.to_bytes((value.bit_length() + 8) // 8, "big"))


def encode_roa_payload_set(asn: int, prefixes: list[tuple[str, int | None]]) -> bytes:
    """Encode a ROAPayloadSet from (prefix, maxlen) pairs such as ('10.0.0.0/8', 24); maxlen None means the prefix length."""
    blocks = []
    for afi, size in ((1, 4), (2, 16)):
        entries = []
        for text, maxlen in prefixes:
            net = ipaddress.ip_network(text)
            if net.max_prefixlen != size * 8:
                continue
            nbytes = (net.prefixlen + 7) // 8
            bits = bytes([-net.prefixlen % 8]) + net.network_address.packed[:nbytes]
            entry = encode_tlv(TAG_BIT_STRING, bits)
            if maxlen is not None and maxlen != net.prefixlen:
                entry += _encode_int(maxlen)
            entries.append(((net.network_address.packed, net.prefixlen), encode_tlv(TAG_SEQUENCE, entry)))
        if entries:
            addresses = encode_tlv(TAG_SEQUENCE, b"".join(raw for _, raw in sorted(entries)))
            blocks.append(encode_tlv(TAG_SEQUENCE, encode_tlv(TAG_OCTET_STRING, afi.to_bytes(2, "big")) + addresses))
    return encode_tlv(TAG_SEQUENCE, _encode_int(asn) + encode_tlv(TAG_SEQUENCE, b"".join(blocks)))


class Aspa(NamedTuple):
    """An ASPA: a customer AS and the complete, ascending list of its providers."""

    customer: int
    providers: tuple[int, ...]


def decode_aspa_set(raw: bytes) -> list[Aspa]:
    """Decode one raw ASPAPayloadSet (as a one-element list, like decode_payload_set)."""
    start, _ = expect(raw, 0, TAG_SEQUENCE)
    customer_start, customer_len = expect(raw, start, TAG_INTEGER)
    customer = int.from_bytes(raw[customer_start : customer_start + customer_len], "big")
    pos, length = expect(raw, customer_start + customer_len, TAG_SEQUENCE)  # providers
    end = pos + length

    providers = []
    while pos < end:
        provider_start, provider_len = expect(raw, pos, TAG_INTEGER)
        providers.append(int.from_bytes(raw[provider_start : provider_start + provider_len], "big"))
        pos = provider_start + provider_len
    return [Aspa(customer, tuple(providers))]


def format_aspa(aspa: Aspa) -> str:
    """Format as 'AS<customer> PROVIDERS AS<p1>,AS<p2>', e.g. 'AS43 PROVIDERS AS293,AS400'."""
    return f"AS{aspa.customer} PROVIDERS {','.join(f'AS{p}' for p in aspa.providers)}"


def encode_aspa_payload_set(customer: int, providers: list[int]) -> bytes:
    """Encode an ASPAPayloadSet; providers are sorted and made unique as the draft requires."""
    return encode_tlv(TAG_SEQUENCE, _encode_int(customer) + encode_tlv(TAG_SEQUENCE, b"".join(_encode_int(p) for p in sorted(set(providers)))))
