import hashlib

from conftest import DATE
from helpers import read_members

from rpkispool.ccr import encode_ccr, mfts_section, parse_ccr, split_manifest_instances
from rpkispool.der import TAG_SEQUENCE, encode_tlv


def first_ccr(data_dir) -> bytes:
    members = read_members(data_dir / f"{DATE}-rpkispool.tar.zst")
    return next(data for name, data in members.items() if name.endswith(".ccr"))


def test_encode_ccr_roundtrip(data_dir):
    original = first_ccr(data_dir)
    instances = split_manifest_instances(original)

    assert encode_ccr(original, [raw for _, raw in instances]) == original
    assert parse_ccr(original).manifest_hashes == {h for h, _ in instances}


def test_encode_ccr_sorts_instances_and_hashes_mis(data_dir):
    original = first_ccr(data_dir)
    instances = split_manifest_instances(original)[:2]

    reduced = encode_ccr(original, [raw for _, raw in reversed(instances)])
    parsed = split_manifest_instances(reduced)
    assert [h for h, _ in parsed] == sorted(h for h, _ in instances)

    # ManifestState.hash is the SHA-256 of the DER encoding of mis, including tag and length
    mis = encode_tlv(TAG_SEQUENCE, b"".join(raw for _, raw in parsed))
    section = mfts_section(reduced)
    assert section is not None
    assert section[-32:] == hashlib.sha256(mis).digest()
