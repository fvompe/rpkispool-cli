"""
Verify rpkispool archive filelists (and optionally archive content) against draft-snijders-rpkispool-format.
"""

import sys
from typing import Any

from rpkispool.cli.verify.base import Context, Verifier, VerifyResult
from rpkispool.cli.verify.content import ContentVerifier
from rpkispool.cli.verify.initstate import InitstateFilelist
from rpkispool.cli.verify.rpkispool import RpkispoolFilelist


def _report(result: VerifyResult) -> bool:
    name = result.archive.name
    if result.ok:
        print(f"OK  {name}  ({result.checked} entries checked)")
    else:
        print(f"FAIL  {name}  ({result.checked} entries checked, {len(result.errors)} error(s))")

        for err in result.errors:
            print(f"  {err}", file=sys.stderr)

    return result.ok


def _select(args: Any) -> list[Verifier]:
    """Pick verifiers from the command line flags; everything runs unless disabled with --no-*."""
    verifiers: list[Verifier] = []
    if not args.no_initstate:
        verifiers.append(InitstateFilelist())
    if not args.no_rpkispool:
        verifiers.append(RpkispoolFilelist())
    if not args.no_content:
        verifiers.append(ContentVerifier())
    return verifiers


def add_parser(subparsers: Any) -> None:
    verify = subparsers.add_parser("verify", help="Verify archive filelists and content against draft-snijders-rpkispool-format")
    verify.add_argument("--no-initstate", action="store_true", help="Skip the initstate filelist checks")
    verify.add_argument("--no-rpkispool", action="store_true", help="Skip the rpkispool filelist checks")
    verify.add_argument("--no-content", action="store_true", help="Skip the rpkispool archive content checks (SHA-256 names, .ccr timestamps, references; slow)")


def run(args: Any) -> None:
    verifiers = _select(args)
    if not verifiers:
        sys.exit("Nothing to verify: all checks are disabled")

    ctx = Context(outdir=args.output_dir, date=str(args.date))

    is_ok = True
    for verifier in verifiers:
        is_ok &= _report(verifier.verify(ctx))

    if not is_ok:
        sys.exit(1)
