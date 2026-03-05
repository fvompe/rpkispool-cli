"""
Verify rpkispool archive filelists against draft-snijders-rpkispool-format.
"""

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rpkispool.filelists import filelist_path, iterate_filelist

logger = logging.getLogger(__name__)

# 3.2: base64url alphabet (RFC 4648 5)
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# 3.2: ISO 8601 timestamp as used in rpkispool dated entries
# e.g. 20260302T000018Z
_ISO8601_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})T\d{6}Z$")


@dataclass
class VerifyResult:
    archive: Path
    errors: list[str] = field(default_factory=list)
    checked: int = 0

    def error(self, line: int, path: str, msg: str) -> None:
        self.errors.append(f"line {line}: {path!r}: {msg}")

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def verify_initstate_file(filelist: Path) -> VerifyResult:
    """
    Verify initstate file.

    See 3.1, draft-snijders-rpkispool-format.

    ${RPKIVIEWS_NODE_ID}/${PUBLICATION_POINT_FQDN}/path/to/object.${EXTENSION}

    """
    result = VerifyResult(archive=filelist)

    for lineno, path in iterate_filelist(filelist):
        result.checked += 1

        if path.startswith("/"):
            result.error(lineno, path, "absolute path (3.1 requires relative paths)")
            continue

        parts = path.split("/")
        if len(parts) < 3:
            result.error(lineno, path, f"too few path components ({len(parts)}); expected at least node_id/fqdn/... (3.1)")

    return result


def verify_rpkispool_file(filelist: Path) -> VerifyResult:
    """
    Verify rpkispool filelist.

    See 3.2, draft-snijders-rpkispool-format.

    static/:
    - DER-encoded RPKI objects (ROA, MFT, CRL, CER, ..)
    - Filename is SHA-256 of object content, base64url encoded (Section 5 of [RFC4648])
    - Directory hierarchy uses last few bytes of the SHA-256; in practice
        the last 4 characters of the base64url filename form the two shard
        directories (confirmed from published examples)
    - Path must have exactly 4 components: static/{X}/{Y}/{hash}

    Dated members:
    - Path: ${YEAR}/${MONTH}/${DAY}/${ISO8601}-${NODEID}.${EXTENSION}
    - Date components in directory must match those in the ISO8601 timestamp
    """
    result = VerifyResult(archive=filelist)

    for lineno, path in iterate_filelist(filelist):
        result.checked += 1

        if path.startswith("/"):
            result.error(lineno, path, "absolute path")
            continue

        parts = path.split("/")

        if parts[0] == "static":
            # 3.2 static/ entry
            if len(parts) != 4:
                result.error(lineno, path, f"static/ entry has {len(parts)} components, expected 4 (static/X/Y/hash)")
                continue

            _, shard1, shard2, name = parts

            # base64url alphabet check (RFC 4648 5)
            if not _BASE64URL_RE.match(name):
                result.error(lineno, path, "filename contains characters outside base64url alphabet (RFC 4648 5)")

            # shard consistency: last 4 chars of base64url filename = shard1+shard2
            # (derived from published examples; draft says "last few bytes of SHA-256")
            if len(name) >= 4:
                expected_shard = name[-4:-2], name[-2:]
                if (shard1, shard2) != expected_shard:
                    result.error(lineno, path, f"shard dirs {shard1!r}/{shard2!r} do not match last 4 chars of filename {name[-4:]!r}")

        else:
            # 3.2 dated entry: YEAR/MONTH/DAY/ISO8601-NODEID.EXT
            if len(parts) != 4:
                result.error(lineno, path, f"dated entry has {len(parts)} components, expected 4 (YYYY/MM/DD/filename)")
                continue

            year_dir, month_dir, day_dir, filename = parts

            # Extract the ISO8601 timestamp prefix from the filename
            dash_pos = filename.find("-")
            if dash_pos < 0:
                result.error(lineno, path, "dated filename has no '-' separator between timestamp and node ID")
                continue

            ts = filename[:dash_pos]
            m = _ISO8601_RE.match(ts)
            if not m:
                result.error(lineno, path, f"timestamp {ts!r} does not match ISO8601 format YYYYMMDDTHHMMSSz (3.2)")
                continue

            ts_year, ts_month, ts_day = m.group(1), m.group(2), m.group(3)

            # Date in directory must match date in the ISO8601 timestamp (3.2)
            if (year_dir, month_dir, day_dir) != (ts_year, ts_month, ts_day):
                result.error(lineno, path, f"directory date {year_dir}/{month_dir}/{day_dir} does not match timestamp date {ts_year}/{ts_month}/{ts_day}")

    return result


def verify_archive(outdir: Any, date: str, archive_type: str, verify_fn: Any) -> bool:
    filelist = filelist_path(outdir, date, archive_type)
    if not filelist.exists():
        logger.error("Filelist not found: %s (run 'download --filelists' first)", filelist)
        return False

    logger.info("Verifying %s", filelist)
    result = verify_fn(filelist)

    if result.ok:
        print(f"OK  {filelist.name}  ({result.checked} entries checked)")
    else:
        print(f"FAIL  {filelist.name}  ({result.checked} entries checked, {len(result.errors)} error(s))")

        for err in result.errors:
            print(f"  {err}", file=sys.stderr)

    return result.ok


def add_parser(subparsers: Any) -> None:
    verify = subparsers.add_parser("verify", help="Verify archive filelists against draft-snijders-rpkispool-format")
    verify.add_argument("--initstate", action="store_true", help="Verify only the initstate filelist")
    verify.add_argument("--rpkispool", action="store_true", help="Verify only the rpkispool filelist")


def run(args: Any) -> None:
    date = str(args.date)
    outdir = args.output_dir

    check_initstate = args.initstate
    check_rpkispool = args.rpkispool

    if not check_initstate and not check_rpkispool:
        check_initstate = True
        check_rpkispool = True

    is_ok = True

    if check_initstate:
        is_ok &= verify_archive(outdir, date, "initstate", verify_initstate_file)

    if check_rpkispool:
        is_ok &= verify_archive(outdir, date, "rpkispool", verify_rpkispool_file)

    if not is_ok:
        sys.exit(1)
