"""
Cut a small, consistent test fixture out of the first members of real rpkispool and initstate archives.

    uv run python tools/make_fixtures.py [--archives work/archives] [--date 20261103] [--out tests/fixtures/20261103]

rpkispool: the first few .ccr files and the static/ objects before them. A few tiny manifests and the
files they list are kept, and the .ccr files are rewritten to list only those manifests, so verify passes.
initstate: the first few repositories (the archive is sorted by repository) for all vantage points,
a few objects each. Some repositories are naturally missing at some vantage points.

Only the start of each archive is read and nothing is extracted to disk. Output is deterministic.
"""

import argparse
import base64
import gzip
import io
import tarfile
from pathlib import Path

from rpkispool.ccr import encode_ccr, split_manifest_instances
from rpkispool.manifest import is_manifest, manifest_file_hashes

N_CCR = 3
N_MANIFESTS = 12
MAX_FILES = 5  # only manifests listing at most this many files are candidates
N_REPOS = 6
OBJECTS_PER_REPO = 3  # per vantage point


def key_of(path: str) -> bytes:
    """Hash encoded in a static/ filename."""
    name = path.rsplit("/", 1)[-1]
    return base64.urlsafe_b64decode(name + "=" * (-len(name) % 4))


def read(tf: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    fileobj = tf.extractfile(member)
    assert fileobj is not None
    return fileobj.read()


def write_archive(path: Path, members: dict[str, bytes]) -> None:
    """Write members sorted by name with fixed metadata, plus the matching filelist."""
    with tarfile.open(path, "w:zst") as tf:
        for name, data in sorted(members.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))

    with gzip.GzipFile(f"{path}.filelist.gz", "wb", mtime=0) as gz:
        gz.write("".join(f"{name}\n" for name in sorted(members)).encode())


def rpkispool_members(archive: Path) -> dict[str, bytes]:
    ccrs: dict[str, bytes] = {}
    static: dict[bytes, tuple[str, bytes]] = {}

    with tarfile.open(archive, "r|zst") as tf:
        for m in tf:
            if not m.isfile():
                continue
            if m.name.endswith(".ccr"):
                ccrs[m.name] = read(tf, m)
                if len(ccrs) == N_CCR:
                    break
            elif m.name.startswith("static/"):
                static[key_of(m.name)] = m.name, read(tf, m)

    in_all_ccrs = set.intersection(*({h for h, _ in split_manifest_instances(d)} for d in ccrs.values()))
    candidates = []
    for key, (_, data) in static.items():
        if key in in_all_ccrs and is_manifest(data):
            files = manifest_file_hashes(data)
            if len(files) <= MAX_FILES and files <= static.keys():
                candidates.append((len(files), key, files))

    chosen = sorted(candidates)[:N_MANIFESTS]
    if len(chosen) < N_MANIFESTS:
        raise SystemExit(f"only {len(chosen)} usable manifests in the first {len(static)} static objects")

    keep = {key for _, key, _ in chosen}.union(*(files for _, _, files in chosen))
    members = {static[key][0]: static[key][1] for key in keep}

    selected = {key for _, key, _ in chosen}
    for name, data in ccrs.items():
        members[name] = encode_ccr(data, [raw for h, raw in split_manifest_instances(data) if h in selected])
    return members


def initstate_members(archive: Path) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    repos: list[str] = []
    per_repo: dict[str, int] = {}

    with tarfile.open(archive, "r|zst") as tf:
        for m in tf:
            if not m.isfile():
                continue
            vp, _, rest = m.name.partition("/")
            repo = rest.partition("/")[0]
            if repo not in repos:
                if len(repos) == N_REPOS:
                    break
                repos.append(repo)
            key = f"{vp}/{repo}"
            per_repo[key] = per_repo.get(key, 0) + 1
            if per_repo[key] <= OBJECTS_PER_REPO:
                members[m.name] = read(tf, m)
    return members


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--archives", type=Path, default=Path("work/archives"))
    parser.add_argument("--date", default="20261103")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    out = args.out or Path("tests/fixtures") / args.date
    out.mkdir(parents=True, exist_ok=True)

    initstate = args.archives / f"{args.date}-initstate.tar.zst"
    write_archive(out / initstate.name, initstate_members(initstate))

    rpkispool = args.archives / f"{args.date}-rpkispool.tar.zst"
    write_archive(out / rpkispool.name, rpkispool_members(rpkispool))


if __name__ == "__main__":
    main()
