"""
Verify rpkispool archive filelists (and optionally archive content) against draft-snijders-rpkispool-format.
"""

import base64
import hashlib
import logging
import re
import sys
import tarfile
import time
from compression.zstd import ZstdError
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from rpkispool.ccr import CCR, parse_ccr
from rpkispool.filelists import filelist_path, iterate_filelist
from rpkispool.manifest import is_manifest, manifest_file_hashes

logger = logging.getLogger(__name__)

# 3.2: base64url alphabet (RFC 4648 5)
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# 3.2: ISO 8601 timestamp as used in rpkispool dated entries
# e.g. 20260302T000018Z
_ISO8601_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})T\d{6}Z$")

# content checks: examples listed per failed check, the rest is only counted
_MAX_EXAMPLES = 10

# content checks: allowed gap between the timestamp in a .ccr filename and its producedAt
_CCR_TIME_TOLERANCE = timedelta(seconds=60)

_PROGRESS_EVERY = 250


@dataclass
class VerifyResult:
    archive: Path
    errors: list[str] = field(default_factory=list)
    checked: int = 0
    failures: dict[str, int] = field(default_factory=dict)

    def error(self, line: int, path: str, msg: str) -> None:
        self.errors.append(f"line {line}: {path!r}: {msg}")

    def failure(self, check: str, path: str, msg: str) -> None:
        """Record a failed content check; only the first few examples per check are kept."""
        n = self.failures[check] = self.failures.get(check, 0) + 1
        if n <= _MAX_EXAMPLES:
            self.errors.append(f"{check}: {path!r}: {msg}")

    def summarise_failures(self) -> None:
        for check, n in self.failures.items():
            if n > _MAX_EXAMPLES:
                self.errors.append(f"{check}: ... and {n - _MAX_EXAMPLES} more ({n} total)")

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


def _check_ccr_times(result: VerifyResult, path: str, ccr: CCR, archive_date: str) -> None:
    """
    Check the timestamps inside a .ccr against its filename and the archive date.

    - producedAt falls on the archive date
    - producedAt matches the timestamp in the filename (within _CCR_TIME_TOLERANCE)
    - mostRecentUpdate is not later than producedAt
    """
    produced = ccr.produced_at

    if produced.strftime("%Y%m%d") != archive_date:
        result.failure("ccr-date", path, f"producedAt {produced:%Y%m%dT%H%M%SZ} is not on archive date {archive_date}")

    stamp = path.rsplit("/", 1)[-1].split("-", 1)[0]
    try:
        named = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return  # malformed filename is reported by the filelist checks

    gap = abs(named - produced)
    if gap > _CCR_TIME_TOLERANCE:
        result.failure("ccr-time", path, f"producedAt {produced:%Y%m%dT%H%M%SZ} differs from filename timestamp by {int(gap.total_seconds())}s")

    if ccr.most_recent_update is not None and ccr.most_recent_update > produced:
        result.failure("ccr-time", path, f"mostRecentUpdate {ccr.most_recent_update:%Y%m%dT%H%M%SZ} is after producedAt")


def verify_rpkispool_content(archive: Path, archive_date: str, expected_ccr: int = 0, expected_static: int = 0) -> VerifyResult:
    """
    Verify the content of an rpkispool archive in a single pass.

    - static/ filenames match the SHA-256 (base64url) of the file content
    - .ccr timestamps are consistent with the filename and the archive date
    - every static/ object is referenced by a .ccr: manifests directly, other objects
      through the file list of a manifest (a CCR only lists manifest hashes)

    expected_ccr / expected_static (from the filelist, 0 if unknown) are only used to report progress.
    """
    result = VerifyResult(archive=archive)
    started = time.monotonic()

    static: dict[bytes, str] = {}  # decoded filename hash -> path
    ccr_manifests: set[bytes] = set()  # manifest hashes listed in .ccr files
    mft_files: set[bytes] = set()  # file hashes listed in manifests found in static/
    ccr_count = 0

    try:
        with tarfile.open(archive, "r|zst") as tf:
            for member in tf:
                if not member.isfile():
                    continue

                is_static = member.name.startswith("static/")
                is_ccr = member.name.endswith(".ccr")
                if not (is_static or is_ccr):
                    continue

                fileobj = tf.extractfile(member)
                assert fileobj is not None
                data = fileobj.read()
                result.checked += 1

                if is_static:
                    _check_static(result, member.name, data, static, mft_files)
                    continue

                ccr_count += 1
                try:
                    ccr = parse_ccr(data)
                except (ValueError, IndexError) as e:
                    result.failure("ccr-malformed", member.name, str(e))
                    continue

                ccr_manifests |= ccr.manifest_hashes
                _check_ccr_times(result, member.name, ccr, archive_date)

                if ccr_count % _PROGRESS_EVERY == 0:
                    _log_progress(started, ccr_count, result.checked - ccr_count, expected_ccr, expected_static)
    except (tarfile.TarError, OSError, EOFError, ZstdError) as e:
        result.errors.append(f"cannot read archive: {e}")
        return result

    if ccr_count == 0:
        result.errors.append("no .ccr files found in archive")

    for key, path in static.items():
        if key not in ccr_manifests and key not in mft_files:
            result.failure("unreferenced", path, "not referenced by any .ccr (directly or via a manifest)")

    result.summarise_failures()
    logger.info("Content verified in %s", _fmt_duration(time.monotonic() - started))
    return result


def _fmt_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s"


def _log_progress(started: float, ccr: int, static: int, expected_ccr: int, expected_static: int) -> None:
    elapsed = time.monotonic() - started
    if not expected_ccr:
        logger.info("Processed %d .ccr files, %d static objects, elapsed %s", ccr, static, _fmt_duration(elapsed))
        return

    # .ccr files dominate the data volume, so they are the best progress estimate
    done = min(ccr / expected_ccr, 1.0)
    eta = elapsed * (1 - done) / done
    logger.info(
        "Processed %d/%d .ccr files (%d%%), %d/%d static objects, elapsed %s, ETA %s",
        ccr,
        expected_ccr,
        done * 100,
        static,
        expected_static,
        _fmt_duration(elapsed),
        _fmt_duration(eta),
    )


def _count_entries(filelist: Path) -> tuple[int, int]:
    """Return the number of .ccr and static/ entries listed in an rpkispool filelist."""
    ccr = static = 0
    for _, path in iterate_filelist(filelist):
        if path.startswith("static/"):
            static += 1
        elif path.endswith(".ccr"):
            ccr += 1
    return ccr, static


def _check_static(result: VerifyResult, path: str, data: bytes, static: dict[bytes, str], mft_files: set[bytes]) -> None:
    digest = hashlib.sha256(data).digest()
    name = path.rsplit("/", 1)[-1]
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    if name == expected:
        key = digest
    else:
        result.failure("sha256", path, f"content hash is {expected}")
        try:
            key = base64.urlsafe_b64decode(name + "=" * (-len(name) % 4))
        except ValueError:
            return
        if len(key) != 32:
            return

    static[key] = path

    if is_manifest(data):
        try:
            mft_files |= manifest_file_hashes(data)
        except (ValueError, IndexError) as e:
            result.failure("manifest-malformed", path, str(e))


def _report(name: str, result: VerifyResult) -> bool:
    if result.ok:
        print(f"OK  {name}  ({result.checked} entries checked)")
    else:
        print(f"FAIL  {name}  ({result.checked} entries checked, {len(result.errors)} error(s))")

        for err in result.errors:
            print(f"  {err}", file=sys.stderr)

    return result.ok


def verify_archive(outdir: Any, date: str, archive_type: str, verify_fn: Any) -> bool:
    filelist = filelist_path(outdir, date, archive_type)
    if not filelist.exists():
        logger.error("Filelist not found: %s (run 'download --filelists' first)", filelist)
        return False

    logger.info("Verifying %s", filelist)
    return _report(filelist.name, verify_fn(filelist))


def verify_content(outdir: Path, date: str) -> bool:
    archive = outdir / f"{date}-rpkispool.tar.zst"
    if not archive.exists():
        logger.error("Archive not found: %s (run 'download' first)", archive)
        return False

    expected_ccr = expected_static = 0
    filelist = filelist_path(outdir, date, "rpkispool")
    if filelist.exists():
        expected_ccr, expected_static = _count_entries(filelist)
        logger.info("Expecting %d .ccr files and %d static objects (from %s)", expected_ccr, expected_static, filelist.name)

    logger.info("Verifying content of %s (this takes a while)", archive)
    return _report(archive.name, verify_rpkispool_content(archive, date, expected_ccr, expected_static))


def add_parser(subparsers: Any) -> None:
    verify = subparsers.add_parser("verify", help="Verify archive filelists against draft-snijders-rpkispool-format")
    verify.add_argument("--initstate", action="store_true", help="Verify only the initstate filelist")
    verify.add_argument("--rpkispool", action="store_true", help="Verify only the rpkispool filelist")
    verify.add_argument("--content", action="store_true", help="Also verify rpkispool archive content: SHA-256 names, .ccr timestamps, references (slow)")


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

    if args.content:
        is_ok &= verify_content(outdir, date)

    if not is_ok:
        sys.exit(1)
