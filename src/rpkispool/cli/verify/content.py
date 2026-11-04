"""
Verify the content of the rpkispool archive.

Reading the archive is expensive, so ContentVerifier makes a single pass and hands every
static/ object and every parsed .ccr to a list of small checks. To add a content check,
subclass ContentCheck and add it to ContentVerifier.verify.
"""

import base64
import hashlib
import logging
import tarfile
import time
from compression.zstd import ZstdError
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rpkispool.ccr import CCR, parse_ccr
from rpkispool.cli.verify.base import Context, VerifyResult, missing_input
from rpkispool.filelists import filelist_path, iterate_filelist
from rpkispool.format import fmt_duration
from rpkispool.manifest import is_manifest, manifest_file_hashes

logger = logging.getLogger(__name__)

# allowed gap between the timestamp in a .ccr filename and its producedAt
CCR_TIME_TOLERANCE = timedelta(seconds=60)

PROGRESS_EVERY = 250


class ContentCheck:
    """A check fed by the single pass over the archive; override the hooks it needs."""

    def __init__(self, result: VerifyResult) -> None:
        self.result = result

    def on_static(self, path: str, data: bytes) -> None:
        pass

    def on_ccr(self, path: str, ccr: CCR) -> None:
        pass

    def finish(self) -> None:
        pass


class StaticHashCheck(ContentCheck):
    """static/ filenames are the base64url SHA-256 of the file content."""

    def on_static(self, path: str, data: bytes) -> None:
        name = path.rsplit("/", 1)[-1]
        expected = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        if name != expected:
            self.result.failure("sha256", path, f"content hash is {expected}")


class CcrTimeCheck(ContentCheck):
    """
    .ccr timestamps are consistent with the filename and the archive date.

    - producedAt falls on the archive date
    - producedAt matches the timestamp in the filename (within CCR_TIME_TOLERANCE)
    - mostRecentUpdate is not later than producedAt
    """

    def __init__(self, result: VerifyResult, archive_date: str) -> None:
        super().__init__(result)
        self.archive_date = archive_date

    def on_ccr(self, path: str, ccr: CCR) -> None:
        produced = ccr.produced_at

        if produced.strftime("%Y%m%d") != self.archive_date:
            self.result.failure("ccr-date", path, f"producedAt {produced:%Y%m%dT%H%M%SZ} is not on archive date {self.archive_date}")

        stamp = path.rsplit("/", 1)[-1].split("-", 1)[0]
        try:
            named = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            return  # malformed filename is reported by the filelist checks

        gap = abs(named - produced)
        if gap > CCR_TIME_TOLERANCE:
            self.result.failure("ccr-time", path, f"producedAt {produced:%Y%m%dT%H%M%SZ} differs from filename timestamp by {int(gap.total_seconds())}s")

        if ccr.most_recent_update is not None and ccr.most_recent_update > produced:
            self.result.failure("ccr-time", path, f"mostRecentUpdate {ccr.most_recent_update:%Y%m%dT%H%M%SZ} is after producedAt")


class ReferenceCheck(ContentCheck):
    """
    Every static/ object is referenced by a .ccr.

    A CCR lists manifest hashes only, so manifests must be listed in a .ccr directly and
    all other objects (CRLs, certificates, ROAs, ...) in the file list of a manifest.
    """

    def __init__(self, result: VerifyResult) -> None:
        super().__init__(result)
        self.static: dict[bytes, str] = {}  # decoded filename hash -> path
        self.ccr_manifests: set[bytes] = set()  # manifest hashes listed in .ccr files
        self.mft_files: set[bytes] = set()  # file hashes listed in manifests found in static/

    def on_static(self, path: str, data: bytes) -> None:
        name = path.rsplit("/", 1)[-1]
        try:
            key = base64.urlsafe_b64decode(name + "=" * (-len(name) % 4))
        except ValueError:
            return
        if len(key) != 32:
            return  # bad filename is reported by the filelist checks

        self.static[key] = path

        if is_manifest(data):
            try:
                self.mft_files |= manifest_file_hashes(data)
            except (ValueError, IndexError) as e:
                self.result.failure("manifest-malformed", path, str(e))

    def on_ccr(self, path: str, ccr: CCR) -> None:
        self.ccr_manifests |= ccr.manifest_hashes

    def finish(self) -> None:
        for key, path in self.static.items():
            if key not in self.ccr_manifests and key not in self.mft_files:
                self.result.failure("unreferenced", path, "not referenced by any .ccr (directly or via a manifest)")


class ContentVerifier:
    """Single pass over {date}-rpkispool.tar.zst running all content checks."""

    def verify(self, ctx: Context) -> VerifyResult:
        archive = ctx.outdir / f"{ctx.date}-rpkispool.tar.zst"
        if not archive.exists():
            return missing_input(archive, "download")

        expected_ccr = expected_static = 0
        filelist = filelist_path(ctx.outdir, ctx.date, "rpkispool")
        if filelist.exists():
            expected_ccr, expected_static = _count_entries(filelist)
            logger.info("Expecting %d .ccr files and %d static objects (from %s)", expected_ccr, expected_static, filelist.name)

        logger.info("Verifying content of %s (this takes a while)", archive)
        result = VerifyResult(archive=archive)
        checks = [StaticHashCheck(result), CcrTimeCheck(result, ctx.date), ReferenceCheck(result)]
        started = time.monotonic()
        ccr_count = 0

        try:
            with tarfile.open(archive, "r|zst") as tf:
                for member in tf:
                    if not member.isfile():
                        continue

                    is_static = member.name.startswith("static/")
                    if not (is_static or member.name.endswith(".ccr")):
                        continue

                    fileobj = tf.extractfile(member)
                    assert fileobj is not None
                    data = fileobj.read()
                    result.checked += 1

                    if is_static:
                        for check in checks:
                            check.on_static(member.name, data)
                        continue

                    ccr_count += 1
                    try:
                        ccr = parse_ccr(data)
                    except (ValueError, IndexError) as e:
                        result.failure("ccr-malformed", member.name, str(e))
                        continue

                    for check in checks:
                        check.on_ccr(member.name, ccr)

                    if ccr_count % PROGRESS_EVERY == 0:
                        _log_progress(started, ccr_count, result.checked - ccr_count, expected_ccr, expected_static)
        except (tarfile.TarError, OSError, EOFError, ZstdError) as e:
            result.errors.append(f"cannot read archive: {e}")
            return result

        if ccr_count == 0:
            result.errors.append("no .ccr files found in archive")

        for check in checks:
            check.finish()

        result.summarise_failures()
        logger.info("Content verified in %s", fmt_duration(time.monotonic() - started))
        return result


def _log_progress(started: float, ccr: int, static: int, expected_ccr: int, expected_static: int) -> None:
    elapsed = time.monotonic() - started
    if not expected_ccr:
        logger.info("Processed %d .ccr files, %d static objects, elapsed %s", ccr, static, fmt_duration(elapsed))
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
        fmt_duration(elapsed),
        fmt_duration(eta),
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
