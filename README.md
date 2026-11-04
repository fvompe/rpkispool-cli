# rpkispool-cli

**rpkispool-cli** is a command-line utility to work with RPKISpool materialization files.

The goal of this project is to provide easy and convenient interface to work with RPKISpool materialization files as defined in [draft-snijders-rpkispool-format](https://datatracker.ietf.org/doc/draft-snijders-rpkispool-format/).

## Core Philosophy

- We prefer Python's standard library and a small, carefully selected set of external dependencies.
- We avoid unnecessary language features, frameworks, and abstractions.

**Rationale**: Keep the tool portable, simple to maintain, and reliable over a 10-year lifespan.

## Requirements 

- Python 3.15 or higher
- astral-sh/uv (for development only)
- tar with zstd support (to generate filelists)

## Features

Following features are supported:

- Downloading materialization files (`download` command)
- Validating consistency of downloaded initspool and rpkispool files (`verify` command)
- Reporting repository coverage across vantage points (`coverage` command)

## Commands

By default `rpkispool-cli` operates on yesterday's date (change with `--date YYYYMMDD`) 
and stores files in `work/archives` (change with `--output-dir DIR`).

| Command                  | Documentation                      |
| ------------------------ | ---------------------------------- |
| `rpkispool-cli download` | [doc/download.md](doc/download.md) |
| `rpkispool-cli verify`   | [doc/verify.md](doc/verify.md)     |
| `rpkispool-cli coverage` | [doc/coverage.md](doc/coverage.md) |

Typical session:

```bash
$ rpkispool-cli --date 20261103 download
$ rpkispool-cli --date 20261103 verify
$ rpkispool-cli --date 20261103 coverage vantage-points
```

Use `rpkispool-cli --help` and `rpkispool-cli <command> --help` for all options. 

The repository also has a `Makefile` with these as targets, see `make download`, `make verify`, `make coverage`.

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