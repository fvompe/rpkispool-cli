import argparse
import gzip
import logging
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://josephine.sobornost.net/rpkidata/rpkispools"

logger = logging.getLogger(__name__)


CHUNK_SIZE = 1024 * 1024
TIMEOUT = 60


def _fetch(url: str, tmp_dest: Path) -> None:
    """Fetch url into tmp_dest, continuing from its current size when possible."""
    offset = tmp_dest.stat().st_size if tmp_dest.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}

    try:
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        if e.code == 416:
            tmp_dest.unlink()
            raise OSError(f"Cannot resume {tmp_dest}, partial file removed, please rerun") from e
        raise

    with resp:
        if resp.status != 206:
            offset = 0  # no resume support, start over
        length = resp.headers.get("Content-Length")
        total = offset + int(length) if length else None
        done = offset
        tty = sys.stderr.isatty()

        with open(tmp_dest, "ab" if offset else "wb") as f:
            while chunk := resp.read(CHUNK_SIZE):
                f.write(chunk)
                done += len(chunk)
                if tty and total:
                    sys.stderr.write(f"\r{done * 100 / total:5.1f}%  {done >> 20} / {total >> 20} MiB")
        if tty and total:
            sys.stderr.write("\n")

    if total is not None and done != total:
        raise OSError(f"Incomplete download of {url}: {done} of {total} bytes")


def _download(url: str, dest: Path) -> None:
    if dest.exists():
        logger.info("File already exists, skipping download: %s", dest)
        return

    tmp_dest = Path(f"{dest}.tmp")

    if tmp_dest.exists():
        logger.info("Resuming download for %s", url)
    else:
        logger.info("Downloading %s to %s", url, dest)

    _fetch(url, tmp_dest)

    logger.debug("Download completed: %s (%d bytes)", tmp_dest, os.path.getsize(tmp_dest))

    tmp_dest.replace(dest)


def _filelist(archive: Path) -> None:
    list_file = Path(f"{archive}.filelist.gz")

    if list_file.exists():
        logger.info("Filelist already exists, skipping generation: %s", list_file)
        return

    tmp_file = Path(f"{archive}.filelist.gz.tmp")

    logger.info("Generating filelist for %s", archive)

    with gzip.open(tmp_file, "wb") as gz:
        proc = subprocess.Popen(["tar", "-tf", archive], stdout=subprocess.PIPE)
        assert proc.stdout is not None
        for chunk in proc.stdout:
            gz.write(chunk)
        proc.wait()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, "tar")

    logger.info("Filelist generated: %s", list_file)

    tmp_file.replace(list_file)


def add_parser(subparsers: Any) -> None:
    download = subparsers.add_parser("download", help="Download RPKI spool archives")
    download.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        metavar="URL",
        help=f"Base URL for downloads (default: {DEFAULT_BASE_URL})",
    )
    download.add_argument("--initstate", action="store_true", help="Download only the initstate archive")
    download.add_argument("--rpkispool", action="store_true", help="Download only the rpkispool archive")
    download.add_argument("--filelists", action=argparse.BooleanOptionalAction, default=True, help="Generate .filelist files after download (default: yes)")


def run(args: Any) -> None:
    date = args.date  # RPKIDate instance
    outdir = args.output_dir
    outdir.mkdir(parents=True, exist_ok=True)

    targets = ["initstate", "rpkispool"]
    if args.initstate:
        targets = ["initstate"]
    elif args.rpkispool:
        targets = ["rpkispool"]

    url_base = f"{args.base_url}/{date.year}/{date.month}/{date.day}"

    for target in targets:
        filename = f"{date}-{target}.tar.zst"
        url = f"{url_base}/{filename}"
        dest = Path(outdir) / filename

        _download(url, dest)
        if args.filelists:
            _filelist(dest)
