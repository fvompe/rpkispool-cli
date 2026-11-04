import io
import tarfile
from pathlib import Path


def read_members(archive: Path) -> dict[str, bytes]:
    members = {}
    with tarfile.open(archive, "r|zst") as tf:
        for m in tf:
            fileobj = tf.extractfile(m)
            if fileobj is not None:
                members[m.name] = fileobj.read()
    return members


def write_members(archive: Path, members: dict[str, bytes]) -> None:
    with tarfile.open(archive, "w:zst") as tf:
        for name, data in sorted(members.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
