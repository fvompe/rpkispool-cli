"""
Summary commands for rpkispool archives.

Subcommands:
  vantage-points   Level-1 summary: one row per vantage point
  repositories     Level-2 matrix:  one row per repository, columns per vantage point
"""

import logging
import sys
from typing import Any

from rpkispool.filelists import FilelistCounts, filelist_path
from rpkispool.format import GREEN, RED, RESET, YELLOW, colour_cell, print_table

logger = logging.getLogger(__name__)


def cmd_vantage_points(args: Any) -> None:
    filelist = filelist_path(args.output_dir, str(args.date), "initstate")
    if not filelist.exists():
        logger.error("Filelist not found: %s (run 'download --filelists' first)", filelist)
        sys.exit(1)

    logger.info("Loading %s", filelist)
    data = FilelistCounts.from_path(filelist)

    vantage_points = data.vantage_points

    headers = ["Vantage point", "Objects", "Repos", "Missing repos"]

    rows = []
    for vp in vantage_points:
        missing_repos = ", ".join(data.missing_repos(vp)) or "-"

        rows.append(
            [
                vp,
                f"{data.total_objects(vp):,}",
                str(data.repo_count(vp)),
                missing_repos,
            ]
        )

    print_table(headers, rows, alignments=["<", ">", ">", "<"])

    print()
    print(f"Total vantage points : {len(vantage_points)}")
    print(f"Total unique repos   : {len(data.all_repos)}")


def format_coverage_cell(n: int, max_n: int) -> str:
    """Return the plain-text label for a repository coverage cell: ok / -- / -N."""
    if n == 0:
        return "--"
    if n == max_n:
        return "ok"
    return f"-{max_n - n}"


def cmd_repositories(args: Any) -> None:
    filelist = filelist_path(args.output_dir, str(args.date), "initstate")
    if not filelist.exists():
        logger.error("Filelist not found: %s (run 'download --filelists' first)", filelist)
        sys.exit(1)

    logger.info("Loading %s", filelist)
    data = FilelistCounts.from_path(filelist)

    vantage_points = data.vantage_points
    repos = sorted(data.all_repos)
    repo_max = data.all_repo_maxes()

    headers = ["Repository"] + vantage_points
    rows = []

    for repo in repos:
        row = [repo]
        for vp in vantage_points:
            count = data.get(vp, repo)
            row.append(format_coverage_cell(count, repo_max[repo]))
        rows.append(row)

    def colour_row_cell(row_idx: int, col_idx: int, formatted: str) -> str:
        if col_idx == 0:
            return formatted
        repo = repos[row_idx]
        n = data.get(vantage_points[col_idx - 1], repo)
        return colour_cell(formatted, n, repo_max[repo])

    print_table(
        headers,
        rows,
        alignments=["<"] + ["^"] * len(vantage_points),
        cell_formatter=colour_row_cell,
    )

    print()
    legend = f"  {GREEN}ok{RESET} = present (full)  {RED}--{RESET} = missing"
    legend += f"  {YELLOW}-N{RESET} = present but N objects fewer than max"
    print(legend)


def add_parser(subparsers: Any) -> None:
    summary = subparsers.add_parser("summary", help="Summarise initstate archive coverage")
    sub = summary.add_subparsers(dest="summary_command")
    sub.required = True

    sub.add_parser("vantage-points", help="Per-vantage-point object and repo counts")
    sub.add_parser("repositories", help="Per-repository coverage matrix across vantage points")


def run(args: Any) -> None:
    if args.summary_command == "vantage-points":
        cmd_vantage_points(args)
    elif args.summary_command == "repositories":
        cmd_repositories(args)
    else:
        raise ValueError(f"Unknown summary command: {args.summary_command}")
