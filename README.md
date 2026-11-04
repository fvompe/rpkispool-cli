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
- Reporting repository coverage across vantage points (`coverage` command)

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

### Verifying downloads (rpkispool-cli verify)

Verifies the filelists and the content of the rpkispool archive against [draft-snijders-rpkispool-format](https://datatracker.ietf.org/doc/draft-snijders-rpkispool-format/). Everything is verified by default, use `--no-initstate`, `--no-rpkispool` or `--no-content` to skip parts.

```bash
$ rpkispool-cli verify --no-content
```

See [doc/verify.md](doc/verify.md) for details.

### Getting coverage (rpkispool-cli coverage)

Reports which repositories each vantage point saw, based on the initstate filelist.

```bash
$ rpkispool-cli coverage vantage-points
```

Subcommands: `vantage-points`, `repositories`, `missing`. See [doc/coverage.md](doc/coverage.md) for details.

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