"""
Verify the initstate filelist.
"""

import logging

from rpkispool.cli.verify.base import Context, VerifyResult, missing_input
from rpkispool.filelists import filelist_path, iterate_filelist

logger = logging.getLogger(__name__)


class InitstateFilelist:
    """
    Verify initstate file.

    See 3.1, draft-snijders-rpkispool-format.

    ${RPKIVIEWS_NODE_ID}/${PUBLICATION_POINT_FQDN}/path/to/object.${EXTENSION}

    """

    def verify(self, ctx: Context) -> VerifyResult:
        filelist = filelist_path(ctx.outdir, ctx.date, "initstate")
        if not filelist.exists():
            return missing_input(filelist, "download --filelists")

        logger.info("Verifying %s", filelist)
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
