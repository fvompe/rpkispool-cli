import gzip
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Iterator


@dataclass
class FilelistCounts:
    """
    Parsed object counts from a rpkispool filelist file,
    <vantage_point>/<repo_fqdn>[/...]

    counts[vantage_point][repo_fqdn] = number of objects for repo_fqdn at vantage_point
    """

    counts: dict[str, dict[str, int]] = field(repr=False)

    @classmethod
    def from_path(cls, path: Path) -> "FilelistCounts":
        raw: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        with gzip.open(path, "rt") as f:
            for line in f:
                parts = line.rstrip("\n").split("/", 2)
                if len(parts) < 2:
                    continue
                vantage, repo = parts[0], parts[1]
                raw[vantage][repo] += 1
        # Normalise defaultdicts to plain dicts before exposing to callers.
        return cls(counts={vp: dict(repos) for vp, repos in raw.items()})

    @cached_property
    def vantage_points(self) -> list[str]:
        """Sorted list of all vantage-point identifiers."""
        return sorted(self.counts)

    @cached_property
    def all_repos(self) -> frozenset[str]:
        """Immutable set of every repository seen across all vantage points."""
        repos: set[str] = set()
        for repo_counts in self.counts.values():
            repos.update(repo_counts)
        return frozenset(repos)

    def get(self, vantage_point: str, repo: str) -> int:
        """Object count for *repo* at *vantage_point*; 0 if not present."""
        return self.counts.get(vantage_point, {}).get(repo, 0)

    def total_objects(self, vantage_point: str) -> int:
        """Total number of objects seen by *vantage_point*."""
        return sum(self.counts.get(vantage_point, {}).values())

    def repo_count(self, vantage_point: str) -> int:
        """Number of distinct repositories seen by *vantage_point*."""
        return len(self.counts.get(vantage_point, {}))

    def repo_max(self, repo: str) -> int:
        """Highest object count for *repo* across all vantage points."""
        return max((vp_counts.get(repo, 0) for vp_counts in self.counts.values()), default=0)

    def missing_repos(self, vantage_point: str) -> list[str]:
        """Sorted list of repos in :attr:`all_repos` that are absent from *vantage_point*."""
        return sorted(self.all_repos - self.counts.get(vantage_point, {}).keys())

    def all_repo_maxes(self) -> dict[str, int]:
        """Max object count per repo across all vantage points"""
        maxes: dict[str, int] = defaultdict(int)
        for vp_counts in self.counts.values():
            for repo, n in vp_counts.items():
                if n > maxes[repo]:
                    maxes[repo] = n
        return dict(maxes)


def filelist_path(outdir: Path, date: str, archive_type: str) -> Path:
    """Return the path to a filelist file for the given output directory, date, and archive type."""
    return outdir / f"{date}-{archive_type}.tar.zst.filelist.gz"


def iterate_filelist(filelist: Path) -> Iterator[tuple[int, str]]:
    """Yield (lineno, path) pairs from a gzip-compressed filelist file."""
    with gzip.open(filelist, "rt") as f:
        for lineno, raw in enumerate(f, 1):
            yield lineno, raw.rstrip("\n")
