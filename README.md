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

## Commands

By default `rpkispool-cli` will operate on yesterday's date and store downloaded files in `work/archives` directory.

First of all

1) download the materialization files using `download` command.
2) use sub-commands to work with the downloaded files (e.g. `verify`, `summary`)

```bash
uv run rpkispool-cli --help
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
uv run rpkispool-cli download --help
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


## Installation

Using astralsh/uv it's really easy to install the CLI tool from the source code.

Clone this repository and then run:

```bash
uv tool install -e .
```

This will install rpkispool-cli in your environment and reference this sources.

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