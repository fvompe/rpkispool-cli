"""
Minimal parser for RPKI manifests (RFC 9286), only to list the hashes of the files they reference.

ContentInfo -> [0] -> SignedData { version, digestAlgorithms, encapContentInfo { eContentType, [0] { OCTET STRING { Manifest } } }, ... }

Manifest ::= SEQUENCE { version [0] DEFAULT 0, manifestNumber, thisUpdate, nextUpdate, fileHashAlg, fileList SEQUENCE OF FileAndHash }
FileAndHash ::= SEQUENCE { file IA5String, hash BIT STRING }
"""

from rpkispool.der import TAG_BIT_STRING, TAG_OCTET_STRING, TAG_SEQUENCE, expect, read_tlv

# id-ct-rpkiManifest 1.2.840.113549.1.9.16.1.26
_MFT_OID = bytes.fromhex("2a864886f70d010910011a")

_TAG_SET = 0x31
_TAG_EXPLICIT_0 = 0xA0


def is_manifest(data: bytes) -> bool:
    """Cheap check: the manifest eContentType OID appears near the start of a manifest CMS object."""
    return data.find(_MFT_OID, 0, 400) >= 0


def manifest_file_hashes(data: bytes) -> set[bytes]:
    """Return the SHA-256 hashes of all files listed in a manifest; raises ValueError on malformed input."""
    pos, _ = expect(data, 0, TAG_SEQUENCE)  # ContentInfo
    start, length = expect(data, pos, 0x06)  # contentType
    pos, _ = expect(data, start + length, _TAG_EXPLICIT_0)
    pos, _ = expect(data, pos, TAG_SEQUENCE)  # SignedData

    start, length = expect(data, pos, 0x02)  # version
    start, length = expect(data, start + length, _TAG_SET)  # digestAlgorithms
    pos, _ = expect(data, start + length, TAG_SEQUENCE)  # EncapsulatedContentInfo
    start, length = expect(data, pos, 0x06)  # eContentType
    pos, _ = expect(data, start + length, _TAG_EXPLICIT_0)
    pos, _ = expect(data, pos, TAG_OCTET_STRING)
    pos, length = expect(data, pos, TAG_SEQUENCE)  # Manifest
    end = pos + length

    last = None
    while pos < end:
        tag, start, length = read_tlv(data, pos)
        last = (tag, start, length)
        pos = start + length

    if last is None or last[0] != TAG_SEQUENCE:
        raise ValueError("fileList not found")

    hashes: set[bytes] = set()
    pos = last[1]
    list_end = pos + last[2]

    while pos < list_end:
        start, length = expect(data, pos, TAG_SEQUENCE)  # FileAndHash
        name_start, name_len = expect(data, start, 0x16)  # file name
        hash_start, hash_len = expect(data, name_start + name_len, TAG_BIT_STRING)
        if hash_len != 33:
            raise ValueError("file hash is not a SHA-256 digest")
        hashes.add(data[hash_start + 1 : hash_start + hash_len])  # skip unused-bits byte
        pos = start + length

    return hashes
