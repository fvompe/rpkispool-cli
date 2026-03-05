# RPKISpool CLI

RPKISpool-CLI is a tiny command-line utility to work with RPKISpool materialization files.

The goal of this project is to provide easy and convenient interface to work with RPKISpool materialization files as defined in [draft-snijders-rpkispool-format](https://datatracker.ietf.org/doc/draft-snijders-rpkispool-format/).

## Core assumptions

- Minimal dependencies: We use as few python features and libraries as possible to make the tool portable and maintainbale in next 10 years

## Requirements 

- Python 3.10 or higher
- astral-sh/uv (for development only)
- tar with zstd support
- curl

## Features

Following features are supported:

- Downloading materialization files (`download` command)
- Validating consistency of downloaded initspool and rpkispool files (`verify` command)

## Commands

By default `rpkispool-cli` will operate on yesterday's date and store downloaded files in `work/archives` directory.

First of all

1) download the materialization files using `download` command.
2) use sub-commands to work with the downloaded files (e.g. `verify`, `summary`)

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
rpkispool-cli --output-dir download --date 20260202 download --filelists
```

Note, that generating filelists is needed to operate with other commands, e.g. `verify` and `summary`.

On commodity hardware, generating filelist for a single archive takes around 15 minutes. 

```bash
rpkispool-cli download --filelists
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
usage: rpkispool-cli verify [-h] [--initstate] [--rpkispool]

options:
  -h, --help   show this help message and exit
  --initstate  Verify only the initstate filelist
  --rpkispool  Verify only the rpkispool filelist
```

Example:

```bash
uv run rpkispool-cli verify
2026-03-05 18:07:26,999 INFO: Verifying work/archives/20260302-initstate.tar.zst.filelist.gz
OK  20260302-initstate.tar.zst.filelist.gz  (6029082 entries checked)
2026-03-05 18:07:37,029 INFO: Verifying work/archives/20260302-rpkispool.tar.zst.filelist.gz
OK  20260302-rpkispool.tar.zst.filelist.gz  (212111 entries checked)
```

### Getting summary (rpkispool-cli summary)

```bash
$ rpkispool-cli summary --help
usage: rpkispool-cli summary [-h] {vantage-points,repositories} ...

positional arguments:
  {vantage-points,repositories}
    vantage-points      Per-vantage-point object and repo counts
    repositories        Per-repository coverage matrix across vantage points

options:
  -h, --help            show this help message and exit
```

```
$ rpkispool-cli summary vantage-points
2026-03-06 19:32:31,453 INFO: Loading work/archives/20260302-initstate.tar.zst.filelist.gz
Vantage point     Objects   Repos  Missing repos
------------------------------------------------
ams1              502,508      59  krill.uta.ng, repodepot.wildtky.com, rki.plasmanodes.com, rpki.gxt.network, rsync.rpki.tianhai.link
blr1              502,548      63  krill.rg.net
blr2              502,131      55  krill.rg.net, repo.rpki.space, rpki-rsync.warpnet.xyz, rpki.admin.freerangecloud.com, rpki.gns.net.br, rpki.gxt.network, rpki.ruinet.work, rpki.sailx.co, rsync.rpki.tianhai.link
dus1              502,501      59  krill.uta.ng, repodepot.wildtky.com, rki.plasmanodes.com, rpki.gxt.network, rsync.rpki.tianhai.link
miso              502,505      58  krill.rg.net, krill.uta.ng, repodepot.wildtky.com, rki.plasmanodes.com, rpki.gxt.network, rsync.rpki.tianhai.link
nyc1              502,503      59  krill.uta.ng, repodepot.wildtky.com, rki.plasmanodes.com, rpki.gxt.network, rsync.rpki.tianhai.link
sng1              502,504      58  krill.rg.net, krill.uta.ng, repodepot.wildtky.com, rki.plasmanodes.com, rpki.gxt.network, rsync.rpki.tianhai.link
syd1              502,558      63  krill.rg.net
syd2              502,130      55  krill.rg.net, repo.rpki.space, rpki-rsync.warpnet.xyz, rpki.admin.freerangecloud.com, rpki.gns.net.br, rpki.gxt.network, rpki.ruinet.work, rpki.sailx.co, rsync.rpki.tianhai.link
yyz1              502,499      58  krill.rg.net, krill.uta.ng, repodepot.wildtky.com, rki.plasmanodes.com, rpki.gxt.network, rsync.rpki.tianhai.link
zur1              502,558      63  krill.rg.net
zur2              502,137      55  krill.rg.net, repo.rpki.space, repodepot.wildtky.com, rpki.admin.freerangecloud.com, rpki.gns.net.br, rpki.gxt.network, rpki.ruinet.work, rpki.sailx.co, rsync.rpki.tianhai.link

Total vantage points : 12
Total unique repos   : 64
```

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