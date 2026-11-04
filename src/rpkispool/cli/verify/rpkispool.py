"""
Verify the rpkispool filelist.
"""

import logging
import re

from rpkispool.cli.verify.base import Context, VerifyResult, missing_input
from rpkispool.filelists import filelist_path, iterate_filelist

logger = logging.getLogger(__name__)

# 3.2: base64url alphabet (RFC 4648 5)
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# 3.2: ISO 8601 timestamp as used in rpkispool dated entries
# e.g. 20260302T000018Z
_ISO8601_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})T\d{6}Z$")


class RpkispoolFilelist:
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

    def verify(self, ctx: Context) -> VerifyResult:
        filelist = filelist_path(ctx.outdir, ctx.date, "rpkispool")
        if not filelist.exists():
            return missing_input(filelist, "download --filelists")

        logger.info("Verifying %s", filelist)
        result = VerifyResult(archive=filelist)

        for lineno, path in iterate_filelist(filelist):
            result.checked += 1

            if path.startswith("/"):
                result.error(lineno, path, "absolute path")
                continue

            parts = path.split("/")

            if parts[0] == "static":
                self._static_entry(result, lineno, path, parts)
            else:
                self._dated_entry(result, lineno, path, parts)

        return result

    @staticmethod
    def _static_entry(result: VerifyResult, lineno: int, path: str, parts: list[str]) -> None:
        # 3.2 static/ entry
        if len(parts) != 4:
            result.error(lineno, path, f"static/ entry has {len(parts)} components, expected 4 (static/X/Y/hash)")
            return

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

    @staticmethod
    def _dated_entry(result: VerifyResult, lineno: int, path: str, parts: list[str]) -> None:
        # 3.2 dated entry: YEAR/MONTH/DAY/ISO8601-NODEID.EXT
        if len(parts) != 4:
            result.error(lineno, path, f"dated entry has {len(parts)} components, expected 4 (YYYY/MM/DD/filename)")
            return

        year_dir, month_dir, day_dir, filename = parts

        # Extract the ISO8601 timestamp prefix from the filename
        dash_pos = filename.find("-")
        if dash_pos < 0:
            result.error(lineno, path, "dated filename has no '-' separator between timestamp and node ID")
            return

        ts = filename[:dash_pos]
        m = _ISO8601_RE.match(ts)
        if not m:
            result.error(lineno, path, f"timestamp {ts!r} does not match ISO8601 format YYYYMMDDTHHMMSSz (3.2)")
            return

        ts_year, ts_month, ts_day = m.group(1), m.group(2), m.group(3)

        # Date in directory must match date in the ISO8601 timestamp (3.2)
        if (year_dir, month_dir, day_dir) != (ts_year, ts_month, ts_day):
            result.error(lineno, path, f"directory date {year_dir}/{month_dir}/{day_dir} does not match timestamp date {ts_year}/{ts_month}/{ts_day}")
