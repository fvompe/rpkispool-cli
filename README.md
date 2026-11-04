# RPKISpool CLI

RPKISpool-CLI is a tiny command-line utility to work with RPKISpool materialization files.

The goal of this project is to provide easy and convenient interface to work with RPKISpool materialization files as defined in [draft-snijders-rpkispool-format](https://datatracker.ietf.org/doc/draft-snijders-rpkispool-format/).

## Core assumptions

- Minimal dependencies: We use as few python features and libraries as possible to make the tool portable and maintainbale in next 10 years

## Requirements 

- Python 3.15 or higher
- astral-sh/uv (for development only)
- tar with zstd support

## Features

Following features are supported:

- Downloading materialization files (`download` command)
- Validating consistency of downloaded initspool and rpkispool files (`verify` command)

## Commands

By default `rpkispool-cli` will operate on yesterday's date and store downloaded files in `work/archives` directory.

First of all

1) download the materialization files using `download` command.
2) use sub-commands to work with the downloaded files (e.g. `verify`, `coverage`)

```bash
$ rpkispool-cli --help
usage: rpkispool-cli [-h] [--date YYYYMMDD] [--output-dir DIR] [--verbose] {download} ...

RPKISpool CLI tool

positional arguments:
  {download}
    download        Download RPKI spool archives

options:
  -h, --help        show this help message and exit
  --date YYYYMMDD   Date to operate on (default: yesterday)
  --output-dir DIR  Output directory (default: work/archives)
  --verbose, -v     Increase verbosity
```

### Downloading materialization files (rpkispool-cli download)

```bash
$ rpkispool-cli download --help
usage: rpkispool-cli download [-h] [--base-url URL] [--initstate] [--rpkispool] [--filelists]

options:
  -h, --help      show this help message and exit
  --base-url URL  Base URL for downloads (default: https://josephine.sobornost.net/rpkidata/rpkispools)
  --initstate     Download only the initstate archive
  --rpkispool     Download only the rpkispool archive
  --filelists     Generate .filelist files after download
```

Example:

```bash
$ rpkispool-cli --output-dir download --date 20260202 download --filelists
```

Note, that generating filelists is needed to operate with other commands, e.g. `verify` and `coverage`.

On commodity hardware, generating filelist for a single archive takes around 15 minutes. 

```bash
$ rpkispool-cli download --filelists
2026-03-05 17:51:33,469 INFO: File already exists, skipping download: work/archives/20260302-initstate.tar.zst
2026-03-05 17:51:33,470 INFO: Generating filelist for work/archives/20260302-initstate.tar.zst
2026-03-05 17:56:26,081 INFO: Filelist generated: work/archives/20260302-initstate.tar.zst.filelist.gz
2026-03-05 17:56:26,082 INFO: File already exists, skipping download: work/archives/20260302-rpkispool.tar.zst
2026-03-05 17:56:26,083 INFO: Generating filelist for work/archives/20260302-rpkispool.tar.zst
2026-03-05 18:06:23,363 INFO: Filelist generated: work/archives/20260302-rpkispool.tar.zst.filelist.gz
```

### Verifying filelists (rpkispool-cli verify)

Verification is performed against the requirements of [draft-snijders-rpkispool-format](https://datatracker.ietf.org/doc/draft-snijders-rpkispool-format/).

```bash
$ rpkispool-cli verify --help
usage: rpkispool-cli verify [-h] [--initstate] [--rpkispool] [--content]

options:
  -h, --help   show this help message and exit
  --initstate  Verify only the initstate filelist
  --rpkispool  Verify only the rpkispool filelist
  --content    Also verify rpkispool archive content: SHA-256 names, .ccr timestamps, references (slow)
```

Example:

```bash
$ rpkispool-cli verify
2026-03-05 18:07:26,999 INFO: Verifying work/archives/20260302-initstate.tar.zst.filelist.gz
OK  20260302-initstate.tar.zst.filelist.gz  (6029082 entries checked)
2026-03-05 18:07:37,029 INFO: Verifying work/archives/20260302-rpkispool.tar.zst.filelist.gz
OK  20260302-rpkispool.tar.zst.filelist.gz  (212111 entries checked)
```

### Getting coverage (rpkispool-cli coverage)

```bash
$ rpkispool-cli coverage --help
usage: rpkispool-cli coverage [-h] {vantage-points,repositories,missing} ...

positional arguments:
  {vantage-points,repositories,missing}
    vantage-points      Per-vantage-point object and repo counts
    repositories        Per-repository coverage matrix across vantage points
    missing             List repositories missing at each vantage point (repo<TAB>vantage-point)

options:
  -h, --help            show this help message and exit
```

```bash
$ rpkispool-cli coverage vantage-points
2026-11-04 19:17:26,388 INFO: Loading work/archives/20261103-initstate.tar.zst.filelist.gz
Vantage point  Objects  Repos  Missing repos
---------------------------------------------------------------------------------------------------------------------
ams1           572,451     76  2: rpki-pp.com, rsync.prefixlogic.com
ams3           572,417     76  2: rpki-pp.com, rsync.prefixlogic.com
ams4           572,498     78  -
ams5           572,457     78  -
blr1           572,451     78  -
blr2           571,809     60  18: alias.rpki-measurement.site, krill.cxy.hk, krill.peravix.group, ... +15 more
cpt1           572,457     78  -
dus1           572,451     76  2: rpki-pp.com, rsync.prefixlogic.com
miso           572,451     76  2: rpki-pp.com, rsync.prefixlogic.com
nyc1           572,451     76  2: rpki-pp.com, rsync.prefixlogic.com
pek1           572,498     78  -
rix1           572,443     78  -
syd1           572,446     78  -
syd2           571,797     60  18: alias.rpki-measurement.site, krill.cxy.hk, krill.peravix.group, ... +15 more
yyz1           572,449     75  3: alias.rpki-measurement.site, rpki-pp.com, rsync.prefixlogic.com
zia1           513,044     66  12: krill.47272.net, krill.dacs.utwente.nl, krill.peering.ee.columbia.edu, ... +9 more
zur1           572,446     78  -

Total vantage points : 17
Total unique repos   : 78
```

The `Missing repos` column shows the number of missing repositories and the first three names. Use `--full` to list all of them, or `coverage missing` for a flat list per repository and vantage point.

`coverage missing` prints one `repository<TAB>vantage-point` pair per line for every gap, which is easy to pipe into `grep`, `sort` or `diff`. Add `--fail` to exit with status 1 when any gap exists (e.g. in cron or CI).

```bash
$ rpkispool-cli coverage missing
krill.rg.net	blr1
krill.rg.net	blr2
```

#### Content verification (`verify --content`)

By default `verify` only reads the filelists. With `--content` it also reads the whole `rpkispool` archive once and checks:

- every `static/` filename is the base64url SHA-256 of the file content
- every `.ccr` is consistent with its filename and the archive date: `producedAt` is on the archive date, matches the timestamp in the filename (within 60 seconds), and is not earlier than `mostRecentUpdate`
- every `static/` object is referenced by a `.ccr`. A CCR lists manifests only, so manifests must be listed in a `.ccr` directly and all other objects (CRLs, certificates, ROAs, ...) in the file list of a manifest

This reads about 70 GB of decompressed data for a daily archive and takes around 10 minutes. It uses Python's built-in zstd support, so no external `zstd` or `tar` is needed for this step.

## Installation

Using astralsh/uv it's really easy to install the CLI tool from the source code.

Clone this repository and then run:

```bash
uv tool install -e .
```

This will

- install `rpkispool-cli` globally for the current user
- sources are referenced as python-editable, referencing current source code

## Development

```
uv sync

uv run rpkispool-cli --help
```

## Tests

To run tests, use

```
uv run pytest
```

## Authors

- Fedor Vompe
- Job Snijders