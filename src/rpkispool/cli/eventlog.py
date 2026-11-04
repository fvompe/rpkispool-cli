"""
Node-specific event logs from the differences between consecutive CCRs.

One line per ROA, or per ASPA, added or removed between two CCRs of the same node:

    <time> <node> <old state hash> -> <new state hash> ROA <ADD|DEL> <prefix>/<plen>[-<maxlen>] AS<asn>
    <time> <node> <old state hash> -> <new state hash> ASPA <ADD|DEL> AS<customer> PROVIDERS AS<p1>,AS<p2>

Only CCRs of the same node are compared, so every node has its own consistent stream. The streams
of all nodes are printed interleaved in archive order, which is chronological. The state hashes are
those of the ROA state for ROA lines and of the ASPA state for ASPA lines.
"""

import argparse
import base64
import ipaddress
import logging
import os
import sys
import tarfile
import time
from array import array
from bisect import bisect_left
from collections.abc import Callable
from compression.zstd import ZstdError
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from typing import Any

from rpkispool.ccr import (
    TAG_VAPS,
    TAG_VRPS,
    Aspa,
    Vrp,
    decode_aspa_set,
    decode_payload_set,
    format_aspa,
    format_vrp,
    index_payload_sets,
    payload_state,
    produced_at,
)
from rpkispool.format import fmt_duration

logger = logging.getLogger(__name__)

PROGRESS_EVERY = 250

_AS_LIMIT = (1 << 32) + 1  # AS numbers are 32 bit
_CHUNKS = 256

type Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass(frozen=True)
class Kind:
    """A kind of record in a CCR that is compared: where it is, how to decode and format its items."""

    name: str  # roa | aspa
    label: str  # ROA | ASPA
    section: int
    decode: Callable[[bytes], list[Any]]
    format: Callable[[Any], str]


ROA = Kind("roa", "ROA", TAG_VRPS, decode_payload_set, format_vrp)
ASPA = Kind("aspa", "ASPA", TAG_VAPS, decode_aspa_set, format_aspa)
KINDS = (ROA, ASPA)


@dataclass
class Filters:
    """
    Which events to print. Values of one option are alternatives, different options must all match.

    A kind is hidden if an option that does not apply to it is given: --prefix for ASPA, and
    --customer-asn / --provider-asn for ROAs. --asn applies to both.
    """

    nodes: set[str] = field(default_factory=set)
    types: set[str] = field(default_factory=set)
    asns: list[int] = field(default_factory=list)
    customer_asns: list[int] = field(default_factory=list)
    provider_asns: list[int] = field(default_factory=list)
    prefixes: list[Network] = field(default_factory=list)

    def wants(self, kind: Kind) -> bool:
        if self.types and kind.name not in self.types:
            return False
        if kind is ROA:
            return not (self.customer_asns or self.provider_asns)
        return not self.prefixes

    def matches(self, item: Vrp | Aspa) -> bool:
        if isinstance(item, Vrp):
            return (not self.asns or item.asn in self.asns) and (not self.prefixes or any(overlaps(item, net) for net in self.prefixes))
        return (
            (not self.asns or item.customer in self.asns or any(p in self.asns for p in item.providers))
            and (not self.customer_asns or item.customer in self.customer_asns)
            and (not self.provider_asns or any(p in self.provider_asns for p in item.providers))
        )

    def restrict_to(self, kind: Kind) -> list[int] | None:
        """AS numbers (the first integer of each set) the comparison can be limited to, if any."""
        if kind is ROA:
            return self.asns or None
        if not self.asns and not self.provider_asns:
            return self.customer_asns or None
        return None


def parse_asn(text: str) -> int:
    """An AS number such as 834 or AS834."""
    digits = text.upper().removeprefix("AS")
    if not digits.isdigit() or int(digits) >= _AS_LIMIT - 1:
        raise argparse.ArgumentTypeError(f"invalid AS number '{text}' (expected e.g. 834 or AS834)")
    return int(digits)


def parse_prefix(text: str) -> Network:
    """A prefix such as 78.105.0.0/16, or a single address such as 78.105.238.7."""
    try:
        return ipaddress.ip_network(text, strict=False)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"invalid prefix '{text}': {e}") from e


def overlaps(vrp: Vrp, network: Network) -> bool:
    """True if the ROA prefix contains the network or is inside it."""
    if (network.version == 4) != (vrp.afi == 1):
        return False
    bits = 32 if vrp.afi == 1 else 128
    first, last = vrp.address, vrp.address + (1 << (bits - vrp.plen))
    net_first = int(network.network_address)
    return first < net_first + network.num_addresses and net_first < last


@dataclass
class Snapshot:
    """The ROAs (or ASPAs) of one CCR: raw payload sets plus an index of them (ordered by AS number)."""

    kind: Kind
    produced_at: datetime
    state_hash: bytes
    sets: bytes
    asns: array[int]
    starts: array[int]
    ends: array[int]

    @classmethod
    def from_sets(cls, kind: Kind, produced_at: datetime, state_hash: bytes, sets: bytes) -> Snapshot:
        return cls(kind, produced_at, state_hash, sets, *index_payload_sets(sets))

    def span(self, lo: int, hi: int) -> tuple[int, int]:
        """Indexes of the payload sets with lo <= AS number < hi."""
        return bisect_left(self.asns, lo), bisect_left(self.asns, hi)

    def raw(self, first: int, last: int) -> bytes:
        """The raw bytes of the payload sets first..last-1."""
        return self.sets[self.starts[first] : self.ends[last - 1]] if last > first else b""

    def items(self, first: int, last: int) -> set[Any]:
        return {item for i in range(first, last) for item in self.kind.decode(self.sets[self.starts[i] : self.ends[i]])}


def diff(old: Snapshot, new: Snapshot, asns: list[int] | None = None) -> tuple[list[Any], list[Any]]:
    """Return the items (removed, added) between two snapshots, each sorted; only for the given AS numbers if any."""
    removed: list[Any] = []
    added: list[Any] = []

    if asns:
        ranges = [(asn, asn + 1) for asn in sorted(set(asns))]
    else:
        # chunks with about the same number of payload sets of old, so that equal chunks are skipped
        # with one comparison each and only the few differing chunks are walked set by set
        step = max(len(old.asns) // _CHUNKS, 1)
        bounds = [0, *old.asns[step::step], _AS_LIMIT]
        ranges = list(pairwise(bounds))

    for lo, hi in ranges:
        _diff_range(old, new, lo, hi, removed, added)
    return sorted(removed), sorted(added)


def _diff_range(old: Snapshot, new: Snapshot, lo: int, hi: int, removed: list[Any], added: list[Any]) -> None:
    """Collect the changes among the AS numbers lo <= AS < hi, decoding only the payload sets that differ."""
    i, i_end = old.span(lo, hi)
    j, j_end = new.span(lo, hi)
    if old.raw(i, i_end) == new.raw(j, j_end):
        return

    while i < i_end or j < j_end:
        as_old = old.asns[i] if i < i_end else _AS_LIMIT
        as_new = new.asns[j] if j < j_end else _AS_LIMIT

        if as_old < as_new:
            removed += old.items(i, i + 1)
            i += 1
        elif as_new < as_old:
            added += new.items(j, j + 1)
            j += 1
        else:
            if old.raw(i, i + 1) != new.raw(j, j + 1):
                items_old, items_new = old.items(i, i + 1), new.items(j, j + 1)
                removed += items_old - items_new
                added += items_new - items_old
            i += 1
            j += 1


def event_lines(node: str, old: Snapshot, new: Snapshot, filters: Filters | None = None) -> list[str]:
    """
    The log lines for the change from old to new.

    ROAs: all DEL lines, then all ADD lines. ASPAs: by customer AS, so that the DEL and the ADD
    of a changed ASPA are next to each other; a change is kept whole if the old or the new ASPA
    matches the filters.
    """
    filters = filters or Filters()
    removed, added = diff(old, new, filters.restrict_to(new.kind))

    events = [("DEL", item) for item in removed] + [("ADD", item) for item in added]
    if new.kind is ASPA:
        customers = {item.customer for _, item in events if filters.matches(item)}
        events = sorted((event for event in events if event[1].customer in customers), key=lambda event: event[1].customer)  # stable: DEL before ADD
    else:
        events = [event for event in events if filters.matches(event[1])]

    prefix = f"{new.produced_at:%Y%m%dT%H%M%SZ} {node} {_b64(old.state_hash)} -> {_b64(new.state_hash)} {new.kind.label}"
    return [f"{prefix} {action} {new.kind.format(item)}" for action, item in events]


def _b64(digest: bytes) -> str:
    return base64.b64encode(digest).decode().rstrip("=")


def run(args: Any) -> None:
    archive = args.output_dir / f"{args.date}-rpkispool.tar.zst"
    if not archive.exists():
        logger.error("Archive not found: %s (run 'download' first)", archive)
        sys.exit(1)

    filters = Filters(set(args.node), set(args.type), args.asn, args.customer_asn, args.provider_asn, args.prefix)
    kinds = [kind for kind in KINDS if filters.wants(kind)]
    if not kinds:
        logger.error("The given options select no events (--prefix only applies to ROAs, --customer-asn and --provider-asn only to ASPAs)")
        sys.exit(2)

    logger.info("Reading .ccr files from %s", archive)
    try:
        _stream_events(archive, filters, kinds)
    except BrokenPipeError:
        # the reader (e.g. head) went away: leave quietly
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
    except (tarfile.TarError, OSError, EOFError, ZstdError) as e:
        logger.error("Cannot read archive: %s", e)
        sys.exit(1)


def _stream_events(archive: Any, filters: Filters, kinds: list[Kind]) -> None:
    previous: dict[tuple[str, str], Snapshot] = {}  # (node, kind) -> snapshot
    last_time: dict[str, datetime] = {}
    started = time.monotonic()
    ccr_count = event_count = 0

    with tarfile.open(archive, "r|zst") as tf:
        for member in tf:
            if not (member.isfile() and member.name.endswith(".ccr")):
                continue

            node = member.name.rsplit("-", 1)[-1].removesuffix(".ccr")
            if filters.nodes and node not in filters.nodes:
                continue  # the data of this member is not even read

            fileobj = tf.extractfile(member)
            assert fileobj is not None
            data = fileobj.read()
            ccr_count += 1

            try:
                produced = produced_at(data)
                if node in last_time and produced <= last_time[node]:
                    logger.warning("Skipping %s: not later than the previous CCR of %s", member.name, node)
                    continue
                last_time[node] = produced

                lines: list[str] = []
                for kind in kinds:
                    lines += _kind_events(node, kind, data, produced, previous, filters, member.name)
            except (ValueError, IndexError) as e:
                logger.warning("Skipping malformed %s: %s", member.name, e)
                continue

            if lines:
                event_count += len(lines)
                sys.stdout.write("\n".join(lines) + "\n")

            if ccr_count % PROGRESS_EVERY == 0:
                logger.info("Processed %d .ccr files, %d events, elapsed %s", ccr_count, event_count, fmt_duration(time.monotonic() - started))

    logger.info("Processed %d .ccr files, %d events in %s", ccr_count, event_count, fmt_duration(time.monotonic() - started))


def _kind_events(
    node: str, kind: Kind, data: bytes, produced: datetime, previous: dict[tuple[str, str], Snapshot], filters: Filters, name: str
) -> list[str]:
    state = payload_state(data, kind.section)
    if state is None:
        (logger.warning if kind is ROA else logger.debug)("%s has no %s state", name, kind.label)
        return []

    sets, state_hash = state
    old = previous.get((node, kind.name))
    if old is not None and old.state_hash == state_hash:
        old.produced_at = produced  # nothing changed, keep the index
        return []

    snapshot = Snapshot.from_sets(kind, produced, state_hash, sets)
    previous[(node, kind.name)] = snapshot
    return event_lines(node, old, snapshot, filters) if old is not None else []


def add_parser(subparsers: Any) -> None:
    eventlog = subparsers.add_parser("eventlog", help="Print ROA and ASPA add/delete events between consecutive CCRs of each node")
    eventlog.add_argument("--node", action="append", default=[], metavar="NAME", help="Only events of this node (repeatable)")
    eventlog.add_argument("--type", action="append", default=[], choices=[kind.name for kind in KINDS], help="Only this kind of events (repeatable)")
    eventlog.add_argument(
        "--asn",
        action="append",
        default=[],
        type=parse_asn,
        metavar="ASN",
        help="Only events involving this AS: ROA origin, ASPA customer or provider, e.g. 834 or AS834 (repeatable)",
    )
    eventlog.add_argument("--customer-asn", action="append", default=[], type=parse_asn, metavar="ASN", help="Only ASPAs of this customer AS (repeatable)")
    eventlog.add_argument(
        "--provider-asn",
        action="append",
        default=[],
        type=parse_asn,
        metavar="ASN",
        help="Only ASPAs that list this AS as a provider, before or after the change (repeatable)",
    )
    eventlog.add_argument(
        "--prefix",
        action="append",
        default=[],
        type=parse_prefix,
        metavar="PREFIX",
        help="Only ROAs whose prefix contains or is inside PREFIX; an address matches the ROAs covering it (repeatable)",
    )
