# rpkispool-cli eventlog

Prints the changes of ROAs and ASPAs seen by each node as an event log. Every `.ccr` in the rpkispool archive is a snapshot of one node's validated state. For every pair of consecutive CCRs **of the same node**, the command prints one line per ROA that was removed (`DEL`) or added (`ADD`), and the same for ASPAs. CCRs of different nodes are never compared with each other, so each node has its own consistent stream. The streams of all nodes are printed together in time order.

```bash
$ rpkispool-cli --date 20261103 eventlog
20261103T000656Z ams4 49+hybMIc4hORDkqaasuR5taJPNVRf/Zh4rtQHHUwCA -> gdiCg2kcLqoAmCAEPtdm90J0c+zCQjiZc/oEdyD+UD0 ROA DEL 5.199.50.0/23-24 AS834
20261103T000656Z ams4 49+hybMIc4hORDkqaasuR5taJPNVRf/Zh4rtQHHUwCA -> gdiCg2kcLqoAmCAEPtdm90J0c+zCQjiZc/oEdyD+UD0 ROA ADD 2a04:4e41:80::/48 AS394192
```

The command reads `<date>-rpkispool.tar.zst`, so run `download` first. The log goes to stdout, progress and warnings to stderr:

```bash
$ rpkispool-cli --date 20261103 eventlog > eventlog-20261103.txt
$ rpkispool-cli --date 20261103 eventlog | grep ' AS834'
```

## Line format

```
<time> <node> <old state hash> -> <new state hash> ROA  <ADD|DEL> <prefix>/<plen>[-<maxlen>] AS<asn>
<time> <node> <old state hash> -> <new state hash> ASPA <ADD|DEL> AS<customer> PROVIDERS AS<p1>,AS<p2>,...
```

- `time`: when the newer CCR was produced (`producedAt`), `YYYYMMDDTHHMMSSZ`.
- `node`: the node id from the CCR filename.
- the two hashes: the hash of the older and of the newer state (base64, no padding), so the lines of a change belong together and consecutive changes chain (`new` of one is `old` of the next). ROA lines carry the hashes of the ROA state and ASPA lines those of the ASPA state, each type has its own chain.

### ROA lines

One line per ROA: `prefix/plen`, and `-maxlen` only if the maximum length is larger than the prefix length (`169.40.38.0/23-24`), then the origin AS. IPv6 addresses are compressed. For each pair of CCRs the `DEL` lines come first, then the `ADD` lines, both sorted by address. A changed ROA (for example another origin AS for the same prefix) appears as a `DEL` and an `ADD`.

### ASPA lines

An ASPA lists **all** providers of a customer AS, and route validation treats that list as complete. An event is therefore about the whole ASPA of a customer, not about single providers: the line shows the customer and its complete provider list in ascending order (`PROVIDERS AS0` means the customer has no providers).

```
<time> <node> <old> -> <new> ASPA ADD AS65000 PROVIDERS AS1,AS2        a new ASPA
<time> <node> <old> -> <new> ASPA DEL AS64500 PROVIDERS AS100          an ASPA that was removed
<time> <node> <old> -> <new> ASPA DEL AS43 PROVIDERS AS293             a changed ASPA: the old list ...
<time> <node> <old> -> <new> ASPA ADD AS43 PROVIDERS AS293,AS400       ... and the new list
```

A changed ASPA is a `DEL` with the old list followed directly by an `ADD` with the new list, the same way a changed ROA is a `DEL` and an `ADD`. ASPA lines are ordered by customer AS, so the two lines of a change are always next to each other.

## Options

```bash
$ rpkispool-cli eventlog --help
usage: rpkispool-cli eventlog [-h] [--node NAME] [--type {roa,aspa}]
                              [--asn ASN] [--customer-asn ASN]
                              [--provider-asn ASN] [--prefix PREFIX]

options:
  -h, --help          show this help message and exit
  --node NAME         Only events of this node (repeatable)
  --type {roa,aspa}   Only this kind of events (repeatable)
  --asn ASN           Only events involving this AS: ROA origin, ASPA customer
                      or provider, e.g. 834 or AS834 (repeatable)
  --customer-asn ASN  Only ASPAs of this customer AS (repeatable)
  --provider-asn ASN  Only ASPAs that list this AS as a provider, before or
                      after the change (repeatable)
  --prefix PREFIX     Only ROAs whose prefix contains or is inside PREFIX; an
                      address matches the ROAs covering it (repeatable)
```

Without options all events of all nodes are printed. The date is the global `--date YYYYMMDD` (or `RPKISPOOL_DATE`) and the archive directory the global `--output-dir`.

| Option | Selects |
|---|---|
| `--node NAME` | only the stream of this node. The data of the other nodes' CCRs is not read |
| `--type roa\|aspa` | only this kind of events |
| `--asn ASN` | events involving this AS in any role: the origin of a ROA, the customer or a provider of an ASPA. `834` and `AS834` are the same |
| `--customer-asn ASN` | only ASPAs of this customer AS |
| `--provider-asn ASN` | only ASPAs that list this AS as a provider, in the old or in the new list |
| `--prefix PREFIX` | only ROAs whose prefix overlaps `PREFIX`: equal to it, inside it or containing it. An address such as `78.105.238.7` selects the ROAs that cover it |

- Options can be repeated: values of the same option are alternatives, and different options must all match.
- `--prefix` applies to ROAs only, `--customer-asn` and `--provider-asn` to ASPAs only. An option that does not apply to a kind hides that kind, so `--prefix 10.0.0.0/8` shows only ROA lines and `--provider-asn 293` only ASPA lines. `--asn` applies to both. If the options leave nothing to show (for example `--prefix` together with `--type aspa`) the command stops with an error.
- A changed ASPA is kept whole: if the old or the new ASPA of a customer matches, both lines are shown.
- The hashes on each line are always those of the complete state of the two CCRs, whatever the options. A filtered log is therefore a subset of the full log, and the old hash of a line still matches the new hash of the previous change, with the lines you filtered out missing in between.

```bash
$ rpkispool-cli --date 20261103 eventlog --node miso --asn 834
$ rpkispool-cli --date 20261103 eventlog --type aspa --provider-asn 293
$ rpkispool-cli --date 20261103 eventlog --customer-asn 43 --customer-asn 64500
$ rpkispool-cli --date 20261103 eventlog --prefix 78.105.0.0/16 --prefix 5.199.48.0/20
```

## How it works

- Nothing is printed for the first CCR of a node in the archive, because there is nothing to compare it with. Changes across midnight need the previous day's archive and are not reported.
- If two consecutive CCRs of a node have the same state hash for a kind, nothing is printed for it.
- The ROAs and the ASPAs of a CCR are grouped by AS number (origin AS, customer AS), ordered by AS number. The two snapshots are compared in chunks of the same size, equal chunks are skipped with one comparison, and only the sets that changed are decoded. This keeps a day (about 2,900 CCRs of 25 MB each) manageable.
- A CCR is a snapshot, so a ROA or ASPA that is added and withdrawn between two snapshots is not seen. The interval between the CCRs of a node ranges from about 2 minutes to half an hour or more, depending on the node.
- Only ROAs and ASPAs are reported.
- Malformed CCRs and CCRs that are not later than the previous one of the same node are skipped with a warning.
