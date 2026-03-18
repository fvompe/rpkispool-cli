"""
Terminal formatting utilities: ANSI colours and table rendering.
"""

import os
import sys
from typing import Callable

# ANSI colour codes are disabled when stdout is not a TTY or NO_COLOR is set
COLOUR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
GREEN = "\033[32m" if COLOUR else ""
RED = "\033[31m" if COLOUR else ""
YELLOW = "\033[33m" if COLOUR else ""
RESET = "\033[0m" if COLOUR else ""


def colour_cell(cell: str, n: int, repo_max_n: int) -> str:
    if n == 0:
        return f"{RED}{cell}{RESET}"
    if n == repo_max_n:
        return f"{GREEN}{cell}{RESET}"
    return f"{YELLOW}{cell}{RESET}"


def calc_column_widths(headers: list[str], rows: list[list[str]]) -> list[int]:
    """
    Return the minimum column widths needed to fit both headers and all cell
    values. Each width is max(header_len, widest_cell_in_column).
    """
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    return widths


def print_table(
    headers: list[str],
    rows: list[list[str]],
    alignments: list[str] | None = None,
    col_sep: str = "  ",
    cell_formatter: Callable[[int, int, str], str] | None = None,
) -> None:
    """
    Print a formatted table.

    Column widths are computed to fit the widest cell in each column, including headers.

    Args:
        headers: Column header labels.
        rows: Table data; each inner list must have the same length as headers.
        alignments: Per-column alignment character ('<', '>', or '^').
            Defaults to '<' (left-align) for every column.
        col_sep: String inserted between adjacent columns. Default is two spaces.
        cell_formatter: Optional callable (row_idx, col_idx, formatted_cell) -> str
            applied to each data cell after width-alignment formatting.
            Use this to wrap cells with ANSI colour codes without disturbing
            column widths. Header cells are never passed through this callable.
    """
    if alignments is None:
        alignments = ["<"] * len(headers)

    widths = calc_column_widths(headers, rows)

    def _fmt(cells: list[str], row_idx: int | None = None) -> str:
        parts = []
        for col_idx, (cell, align, width) in enumerate(zip(cells, alignments, widths)):
            formatted = f"{cell:{align}{width}}"
            if row_idx is not None and cell_formatter is not None:
                formatted = cell_formatter(row_idx, col_idx, formatted)
            parts.append(formatted)
        return col_sep.join(parts)

    header_line = _fmt(headers)
    print(header_line)
    print("-" * len(header_line))
    for row_idx, row in enumerate(rows):
        print(_fmt(row, row_idx))
