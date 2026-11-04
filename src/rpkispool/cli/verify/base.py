"""
Shared types for verifiers.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# examples listed per failed check, the rest is only counted
MAX_EXAMPLES = 10


@dataclass
class Context:
    outdir: Path
    date: str


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
        if n <= MAX_EXAMPLES:
            self.errors.append(f"{check}: {path!r}: {msg}")

    def summarise_failures(self) -> None:
        for check, n in self.failures.items():
            if n > MAX_EXAMPLES:
                self.errors.append(f"{check}: ... and {n - MAX_EXAMPLES} more ({n} total)")

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


class Verifier(Protocol):
    """One verification run over a downloaded file; add new verifiers to VERIFIERS in __init__.py."""

    def verify(self, ctx: Context) -> VerifyResult: ...


def missing_input(path: Path, hint: str) -> VerifyResult:
    """Result for a verifier whose input file does not exist."""
    result = VerifyResult(archive=path)
    result.errors.append(f"not found (run '{hint}' first)")
    return result
