import logging
import os
import subprocess
from pathlib import Path
from typing import Any
import sys

DEFAULT_BASE_URL = "https://josephine.sobornost.net/rpkidata/rpkispools"

logger = logging.getLogger(__name__)


def _download(url: str, dest: Path) -> None:
    if dest.exists():
        logger.info("File already exists, skipping download: %s", dest)
        return

    tmp_dest = Path(f"{dest}.tmp")
    
    if tmp_dest.exists():
        logger.info("Resuming download for %s", url)
    else:
        logger.info("Downloading %s to %s", url, dest)

    cmd = ["curl", "-L", "--fail", "--progress-bar", "-C", "-", "-o", str(tmp_dest), url]
    if not sys.stdout.isatty():
        cmd.append("--silent")

    subprocess.run(cmd, check=True)

    logger.debug("Download completed: %s (%d bytes)", tmp_dest, os.path.getsize(tmp_dest))
    
    tmp_dest.replace(dest)


def _filelist(archive: Path) -> None:
    list_file = Path(f"{archive}.filelist")
    tmp_file = Path(f"{archive}.filelist.tmp")

    logger.info("Generating filelist for %s", archive)

    with tmp_file.open("w") as f:
        subprocess.run(["tar", "-tf", archive], stdout=f, check=True)

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
    download.add_argument("--filelists", action="store_true", help="Generate .filelist files after download")


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
