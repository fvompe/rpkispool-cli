import base64
import random
import re

import pytest
from conftest import DATE
from helpers import read_members, write_members

from rpkispool.ccr import (
    Vrp,
    aspa_payload_state,
    decode_aspa_set,
    decode_payload_set,
    encode_aspa_payload_set,
    encode_ccr,
    encode_roa_payload_set,
    format_aspa,
    format_vrp,
    parse_ccr,
    produced_at,
    roa_payload_state,
    split_manifest_instances,
)
from rpkispool.cli.eventlog import ASPA, ROA, Snapshot, diff, event_lines
from rpkispool.main import main

LINE = re.compile(r"^\d{8}T\d{6}Z \S+ \S+ -> \S+ ROA (ADD|DEL) \S+ AS\d+$")


def template_ccr(data_dir) -> bytes:
    members = read_members(data_dir / f"{DATE}-rpkispool.tar.zst")
    return next(data for name, data in sorted(members.items()) if name.endswith(".ccr"))


def make_ccr(template: bytes, stamp: str, sets: list[bytes], aspa_sets: list[bytes] | None = None) -> bytes:
    """A CCR with the manifests of template, produced at stamp (YYYYMMDDTHHMMSSZ) and the given ROA and ASPA payload sets."""
    old = f"{parse_ccr(template).produced_at:%Y%m%d%H%M%SZ}".encode()
    new = stamp.replace("T", "").encode()
    ccr = encode_ccr(template, [raw for _, raw in split_manifest_instances(template)], sets, aspa_sets)
    return ccr.replace(old, new, 1)  # same length, so the DER lengths stay valid


def snapshot(template: bytes, stamp: str, sets: list[bytes]) -> Snapshot:
    data = make_ccr(template, stamp, sets)
    state = roa_payload_state(data)
    assert state is not None
    return Snapshot.from_sets(ROA, produced_at(data), state[1], state[0])


def aspa_snapshot(template: bytes, stamp: str, aspas: dict[int, list[int]]) -> Snapshot:
    data = make_ccr(template, stamp, [], [encode_aspa_payload_set(customer, providers) for customer, providers in aspas.items()])
    state = aspa_payload_state(data)
    assert state is not None
    return Snapshot.from_sets(ASPA, produced_at(data), state[1], state[0])


OLD_SETS = [
    (1, [("10.0.0.0/8", None)]),
    (2, [("192.0.2.0/24", None)]),
    (3, [("198.51.100.0/24", None)]),
]
NEW_SETS = [
    (1, [("10.0.0.0/8", None)]),
    (2, [("192.0.2.0/24", None), ("2001:db8::/32", 48)]),
    (4, [("203.0.113.0/24", None)]),
]


def encode(sets):
    return [encode_roa_payload_set(asn, prefixes) for asn, prefixes in sets]


def test_payload_set_roundtrip():
    raw = encode_roa_payload_set(64500, [("10.0.0.0/8", 24), ("192.0.2.0/24", None), ("2001:db8::/32", 48), ("2001:67c:64:ffff:0:19e:1e8:581b/128", None)])
    vrps = decode_payload_set(raw)

    assert [format_vrp(v) for v in vrps] == [
        "10.0.0.0/8-24 AS64500",
        "192.0.2.0/24 AS64500",
        "2001:67c:64:ffff:0:19e:1e8:581b/128 AS64500",  # addresses are in ascending order
        "2001:db8::/32-48 AS64500",
    ]
    assert vrps[0] == Vrp(1, 10 << 24, 8, 24, 64500)


def test_as0_and_odd_prefix_length():
    vrps = decode_payload_set(encode_roa_payload_set(0, [("1.119.212.0/22", None)]))
    assert [format_vrp(v) for v in vrps] == ["1.119.212.0/22 AS0"]


def test_event_lines_lists_deletions_before_additions(data_dir):
    template = template_ccr(data_dir)
    old = snapshot(template, "20261103T000100Z", encode(OLD_SETS))
    new = snapshot(template, "20261103T000200Z", encode(NEW_SETS))

    lines = event_lines("miso", old, new)
    prefix = f"20261103T000200Z miso {base64.b64encode(old.state_hash).decode().rstrip('=')} -> {base64.b64encode(new.state_hash).decode().rstrip('=')} ROA"
    assert lines == [
        f"{prefix} DEL 198.51.100.0/24 AS3",
        f"{prefix} ADD 203.0.113.0/24 AS4",
        f"{prefix} ADD 2001:db8::/32-48 AS2",
    ]


def test_eventlog_compares_only_ccrs_of_the_same_node(capsys, data_dir):
    template = template_ccr(data_dir)
    same = encode(OLD_SETS)
    changed = encode(NEW_SETS)
    ccrs = {
        "2026/11/03/20261103T000100Z-a.ccr": make_ccr(template, "20261103T000100Z", same),
        "2026/11/03/20261103T000200Z-b.ccr": make_ccr(template, "20261103T000200Z", changed),  # first of b: no events
        "2026/11/03/20261103T000300Z-a.ccr": make_ccr(template, "20261103T000300Z", changed),  # a changed
        "2026/11/03/20261103T000400Z-b.ccr": make_ccr(template, "20261103T000400Z", changed),  # b unchanged
        "2026/11/03/20261103T000500Z-a.ccr": make_ccr(template, "20261103T000500Z", changed),  # a unchanged
    }
    write_members(data_dir / f"{DATE}-rpkispool.tar.zst", {**ccrs, "static/aa/bb/not-a-ccr": b"ignored"})

    main(["--output-dir", str(data_dir), "--date", DATE, "eventlog"])
    lines = capsys.readouterr().out.splitlines()

    assert len(lines) == 3
    assert all(LINE.match(line) for line in lines)
    assert all(line.startswith("20261103T000300Z a ") for line in lines)
    old_hash = roa_payload_state(ccrs["2026/11/03/20261103T000100Z-a.ccr"])
    assert old_hash is not None
    assert base64.b64encode(old_hash[1]).decode().rstrip("=") in lines[0]


def test_diff_matches_a_naive_set_difference(data_dir):
    rng = random.Random(1)
    template = template_ccr(data_dir)

    def random_sets():
        sets = {}
        for asn in rng.sample(range(70_000), 300) + [4_294_967_295]:
            prefixes = [(f"10.{rng.randrange(256)}.{rng.randrange(256)}.0/24", rng.choice([None, 24, 28])) for _ in range(rng.randrange(1, 4))]
            if rng.random() < 0.3:
                prefixes.append((f"2001:db8:{rng.randrange(0x10000):x}::/48", None))
            sets[asn] = prefixes
        return sets

    old_sets = random_sets()
    new_sets = {asn: prefixes for asn, prefixes in old_sets.items() if rng.random() > 0.05}  # some ASes removed
    for asn in list(new_sets)[:40]:
        new_sets[asn] = new_sets[asn] + [(f"192.0.{rng.randrange(256)}.0/24", None)]  # some ASes changed
    new_sets.update({asn: prefixes for asn, prefixes in random_sets().items() if asn not in old_sets})  # some ASes added

    old = snapshot(template, "20261103T000100Z", encode(old_sets.items()))
    new = snapshot(template, "20261103T000200Z", encode(new_sets.items()))

    def all_vrps(sets):
        return {v for raw in encode(sets.items()) for v in decode_payload_set(raw)}

    removed, added = diff(old, new)
    assert removed == sorted(all_vrps(old_sets) - all_vrps(new_sets))
    assert added == sorted(all_vrps(new_sets) - all_vrps(old_sets))
    assert removed and added


OLD_ASPAS = {43: [293], 64500: [100]}
NEW_ASPAS = {43: [293, 400], 65000: [1, 2]}  # 43 gets a provider, 64500 is removed, 65000 is new


def two_nodes_archive(data_dir, aspa=False):
    """Nodes a and b both change from OLD_SETS to NEW_SETS (a at 0300, b at 0400), and their ASPAs if aspa."""
    template = template_ccr(data_dir)
    old, new = encode(OLD_SETS), encode(NEW_SETS)
    old_aspa = [encode_aspa_payload_set(c, p) for c, p in OLD_ASPAS.items()] if aspa else None
    new_aspa = [encode_aspa_payload_set(c, p) for c, p in NEW_ASPAS.items()] if aspa else None
    ccrs = {
        "2026/11/03/20261103T000100Z-a.ccr": make_ccr(template, "20261103T000100Z", old, old_aspa),
        "2026/11/03/20261103T000200Z-b.ccr": make_ccr(template, "20261103T000200Z", old, old_aspa),
        "2026/11/03/20261103T000300Z-a.ccr": make_ccr(template, "20261103T000300Z", new, new_aspa),
        "2026/11/03/20261103T000400Z-b.ccr": make_ccr(template, "20261103T000400Z", new, new_aspa),
    }
    write_members(data_dir / f"{DATE}-rpkispool.tar.zst", ccrs)


def eventlog(capsys, data_dir, *args):
    main(["--output-dir", str(data_dir), "--date", DATE, "eventlog", *args])
    return [line.split(" ", 1)[1].replace(" -> ", " ").split() for line in capsys.readouterr().out.splitlines()]


def events(rows):
    """(node, ADD|DEL, ROA) from parsed rows: node, old hash, new hash, 'ROA', action, prefix, AS."""
    return [(r[0], r[4], f"{r[5]} {r[6]}") for r in rows]


def test_filters_without_filters_print_everything(capsys, data_dir):
    two_nodes_archive(data_dir)
    assert len(eventlog(capsys, data_dir)) == 6


def test_filter_by_node(capsys, data_dir):
    two_nodes_archive(data_dir)
    assert {r[0] for r in eventlog(capsys, data_dir, "--node", "b")} == {"b"}
    assert {r[0] for r in eventlog(capsys, data_dir, "--node", "a", "--node", "b")} == {"a", "b"}
    assert eventlog(capsys, data_dir, "--node", "nope") == []


def test_filter_by_asn(capsys, data_dir):
    two_nodes_archive(data_dir)
    assert events(eventlog(capsys, data_dir, "--asn", "3")) == [("a", "DEL", "198.51.100.0/24 AS3"), ("b", "DEL", "198.51.100.0/24 AS3")]
    assert len(eventlog(capsys, data_dir, "--asn", "AS4", "--asn", "as2")) == 4  # AS4 added, AS2 changed, on both nodes
    assert eventlog(capsys, data_dir, "--asn", "1") == []  # AS1 did not change


def test_filter_by_prefix_overlap(capsys, data_dir):
    two_nodes_archive(data_dir)
    assert {r[5] for r in eventlog(capsys, data_dir, "--prefix", "2001:db8::/32")} == {"2001:db8::/32-48"}
    assert {r[5] for r in eventlog(capsys, data_dir, "--prefix", "2001:db8::1")} == {"2001:db8::/32-48"}  # an address matches the ROA covering it
    assert {r[5] for r in eventlog(capsys, data_dir, "--prefix", "198.0.0.0/8")} == {"198.51.100.0/24"}  # ROA inside the prefix
    assert eventlog(capsys, data_dir, "--prefix", "10.0.0.0/8") == []  # that ROA did not change


def test_filters_are_combined(capsys, data_dir):
    two_nodes_archive(data_dir)
    assert events(eventlog(capsys, data_dir, "--node", "a", "--asn", "2", "--prefix", "2001:db8::/32")) == [("a", "ADD", "2001:db8::/32-48 AS2")]


def test_invalid_filter_values_are_rejected(data_dir):
    for args in (["--asn", "x"], ["--asn", "4294967296"], ["--prefix", "not-a-prefix"]):
        with pytest.raises(SystemExit) as e:
            main(["--output-dir", str(data_dir), "--date", DATE, "eventlog", *args])
        assert e.value.code == 2


def test_aspa_roundtrip():
    raw = encode_aspa_payload_set(64500, [400, 293, 293])
    assert decode_aspa_set(raw)[0].providers == (293, 400)  # sorted and unique
    assert format_aspa(decode_aspa_set(raw)[0]) == "AS64500 PROVIDERS AS293,AS400"
    assert format_aspa(decode_aspa_set(encode_aspa_payload_set(7, [0]))[0]) == "AS7 PROVIDERS AS0"


def test_aspa_event_lines_are_grouped_by_customer(data_dir):
    template = template_ccr(data_dir)
    old = aspa_snapshot(template, "20261103T000100Z", OLD_ASPAS)
    new = aspa_snapshot(template, "20261103T000200Z", NEW_ASPAS)

    prefix = f"20261103T000200Z miso {base64.b64encode(old.state_hash).decode().rstrip('=')} -> {base64.b64encode(new.state_hash).decode().rstrip('=')} ASPA"
    assert event_lines("miso", old, new) == [
        f"{prefix} DEL AS43 PROVIDERS AS293",
        f"{prefix} ADD AS43 PROVIDERS AS293,AS400",
        f"{prefix} DEL AS64500 PROVIDERS AS100",
        f"{prefix} ADD AS65000 PROVIDERS AS1,AS2",
    ]


def aspa_lines(capsys, data_dir, *args):
    """(node, 'ASPA DEL AS43 PROVIDERS AS293') for each output line."""
    main(["--output-dir", str(data_dir), "--date", DATE, "eventlog", *args])
    return [(line.split()[1], line.split(" -> ", 1)[1].split(" ", 1)[1]) for line in capsys.readouterr().out.splitlines()]


def test_eventlog_prints_roa_and_aspa_events(capsys, data_dir):
    two_nodes_archive(data_dir, aspa=True)
    lines = aspa_lines(capsys, data_dir)
    assert sum(1 for _, text in lines if text.startswith("ROA ")) == 6
    assert sum(1 for _, text in lines if text.startswith("ASPA ")) == 8  # 4 per node
    assert aspa_lines(capsys, data_dir, "--type", "aspa") == [line for line in lines if line[1].startswith("ASPA ")]
    assert aspa_lines(capsys, data_dir, "--type", "roa") == [line for line in lines if line[1].startswith("ROA ")]


def test_asn_matches_roa_origin_and_aspa_customer_or_provider(capsys, data_dir):
    two_nodes_archive(data_dir, aspa=True)
    assert {text for _, text in aspa_lines(capsys, data_dir, "--asn", "4")} == {"ROA ADD 203.0.113.0/24 AS4"}
    assert {text for _, text in aspa_lines(capsys, data_dir, "--asn", "400")} == {"ASPA DEL AS43 PROVIDERS AS293", "ASPA ADD AS43 PROVIDERS AS293,AS400"}  # provider
    assert {text for _, text in aspa_lines(capsys, data_dir, "--asn", "65000")} == {"ASPA ADD AS65000 PROVIDERS AS1,AS2"}  # customer


def test_customer_and_provider_filters_select_aspas_only(capsys, data_dir):
    two_nodes_archive(data_dir, aspa=True)
    assert {text for _, text in aspa_lines(capsys, data_dir, "--customer-asn", "64500")} == {"ASPA DEL AS64500 PROVIDERS AS100"}
    assert len(aspa_lines(capsys, data_dir, "--provider-asn", "400")) == 4  # a changed ASPA is kept whole, on both nodes
    assert len(aspa_lines(capsys, data_dir, "--customer-asn", "43", "--provider-asn", "400")) == 4
    assert aspa_lines(capsys, data_dir, "--customer-asn", "64500", "--provider-asn", "400") == []
    assert all(text.startswith("ASPA ") for _, text in aspa_lines(capsys, data_dir, "--provider-asn", "1"))


def test_prefix_selects_roas_only(capsys, data_dir):
    two_nodes_archive(data_dir, aspa=True)
    assert all(text.startswith("ROA ") for _, text in aspa_lines(capsys, data_dir, "--prefix", "198.0.0.0/8"))
    assert aspa_lines(capsys, data_dir, "--prefix", "198.0.0.0/8", "--asn", "3") != []


def test_options_that_select_nothing_are_an_error(data_dir):
    two_nodes_archive(data_dir, aspa=True)
    for args in (["--prefix", "10.0.0.0/8", "--type", "aspa"], ["--prefix", "10.0.0.0/8", "--provider-asn", "1"]):
        with pytest.raises(SystemExit) as e:
            main(["--output-dir", str(data_dir), "--date", DATE, "eventlog", *args])
        assert e.value.code == 2
