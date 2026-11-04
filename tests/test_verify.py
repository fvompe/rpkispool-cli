import base64
import hashlib

import pytest
from conftest import DATE
from helpers import read_members, write_members

from rpkispool.cli.verify.base import Context
from rpkispool.cli.verify.content import ContentVerifier
from rpkispool.cli.verify.initstate import InitstateFilelist
from rpkispool.cli.verify.rpkispool import RpkispoolFilelist


def verify(verifier, data_dir):
    return verifier.verify(Context(data_dir, DATE))


def mutate_rpkispool(data_dir, edit):
    archive = data_dir / f"{DATE}-rpkispool.tar.zst"
    members = read_members(archive)
    edit(members)
    write_members(archive, members)


def first_name(members, prefix="", suffix=""):
    return next(n for n in sorted(members) if n.startswith(prefix) and n.endswith(suffix))


@pytest.mark.parametrize("verifier", [InitstateFilelist(), RpkispoolFilelist(), ContentVerifier()], ids=["initstate", "rpkispool", "content"])
def test_fixture_is_valid(data_dir, verifier):
    result = verify(verifier, data_dir)
    assert result.ok, result.errors
    assert result.checked > 0


def test_corrupt_static_object(data_dir):
    def edit(members):
        name = first_name(members, prefix="static/")
        members[name] = members[name][:-1] + bytes([members[name][-1] ^ 1])

    mutate_rpkispool(data_dir, edit)
    result = verify(ContentVerifier(), data_dir)
    assert result.failures["sha256"] == 1


def test_unreferenced_static_object(data_dir):
    def edit(members):
        data = b"not referenced by anything"
        b64 = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        members[f"static/{b64[-4:-2]}/{b64[-2:]}/{b64}"] = data

    mutate_rpkispool(data_dir, edit)
    result = verify(ContentVerifier(), data_dir)
    assert result.failures == {"unreferenced": 1}


def test_malformed_ccr(data_dir):
    def edit(members):
        members[first_name(members, suffix=".ccr")] = b"junk"

    mutate_rpkispool(data_dir, edit)
    result = verify(ContentVerifier(), data_dir)
    assert result.failures["ccr-malformed"] == 1


def test_ccr_timestamp_differs_from_filename(data_dir):
    def edit(members):
        name = first_name(members, suffix=".ccr")
        # 23:59:59 on the archive date, far from the producedAt in the file
        stamp = name.rsplit("/", 1)[-1].split("-")[0]
        members[name.replace(stamp, f"{DATE}T235959Z")] = members.pop(name)

    mutate_rpkispool(data_dir, edit)
    result = verify(ContentVerifier(), data_dir)
    assert result.failures["ccr-time"] == 1


def test_missing_archive_is_reported(tmp_path):
    result = verify(ContentVerifier(), tmp_path)
    assert not result.ok
