# rpkispool-cli verify

Verification is performed against the requirements of [draft-snijders-rpkispool-format](https://datatracker.ietf.org/doc/draft-snijders-rpkispool-format/).

```bash
$ rpkispool-cli verify --help
usage: rpkispool-cli verify [-h] [--no-initstate] [--no-rpkispool] [--no-content]

options:
  -h, --help      show this help message and exit
  --no-initstate  Skip the initstate filelist checks
  --no-rpkispool  Skip the rpkispool filelist checks
  --no-content    Skip the rpkispool archive content checks (SHA-256 names, .ccr timestamps, references; slow)
```

By default everything is verified:

- filelists 
- content of the rpkispool archive.

Example:

```bash
$ rpkispool-cli verify --no-content
2026-03-05 18:07:26,999 INFO: Verifying work/archives/20260302-initstate.tar.zst.filelist.gz
OK  20260302-initstate.tar.zst.filelist.gz  (6029082 entries checked)
2026-03-05 18:07:37,029 INFO: Verifying work/archives/20260302-rpkispool.tar.zst.filelist.gz
OK  20260302-rpkispool.tar.zst.filelist.gz  (212111 entries checked)
```

## Content verification

Unless `--no-content` is given, `verify` also reads the whole `rpkispool` archive once and checks:

- every `static/` filename is the base64url SHA-256 of the file content
- every `.ccr` is consistent with its filename and the archive date: `producedAt` is on the archive date, matches the timestamp in the filename (within 60 seconds), and is not earlier than `mostRecentUpdate`
- every `static/` object is referenced by a `.ccr`. A CCR lists manifests only, so manifests must be listed in a `.ccr` directly and all other objects (CRLs, certificates, ROAs, ...) in the file list of a manifest

This reads about 70 GB of decompressed data for a daily archive and takes around 10 minutes. It uses Python's built-in zstd support, so no external `zstd` or `tar` is needed for this step.

## Reporting

Each verifier prints one line, `OK` or `FAIL`, followed on stderr by the failures. The exit status is 1 if anything failed.

For content checks only the first 10 examples of each failed check are listed, followed by `... and N more (N total)`. The check names are:

| Check                | Meaning                                                                                       |
| -------------------- | --------------------------------------------------------------------------------------------- |
| `sha256`             | `static/` filename does not match the SHA-256 of the content                                  |
| `ccr-date`           | `producedAt` is not on the archive date                                                       |
| `ccr-time`           | `producedAt` differs from the filename timestamp, or `mostRecentUpdate` is after `producedAt` |
| `ccr-malformed`      | a `.ccr` could not be parsed                                                                  |
| `manifest-malformed` | a manifest in `static/` could not be parsed                                                   |
| `unreferenced`       | a `static/` object is not referenced by any `.ccr`, directly or via a manifest                |

If an input file is missing, the verifier reports it as a failure and tells you which command to run first.
