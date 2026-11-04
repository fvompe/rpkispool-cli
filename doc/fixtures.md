# Test fixtures

`tests/fixtures/<date>/` holds about 64 KB cut from the real archives, so the tests run the real `verify` and `coverage` code without the multi-GB downloads. Regenerate it with:

```bash
$ make fixtures      # reads work/archives, writes tests/fixtures/20261103, takes a few seconds
```

`tools/make_fixtures.py` reads only the start of each archive (nothing is extracted to disk) and is deterministic.

- **rpkispool:** the first 3 `.ccr` files and the `static/` objects before them. The 12 smallest manifests that appear in all of those `.ccr` files are kept with the files they list, and the `.ccr` files are rewritten to list only those manifests, so every check in `verify` passes.
- **initstate:** the first 6 repositories (the archive is sorted by repository) for all vantage points, 3 objects each. Some of them are missing at some vantage points, so `coverage` has gaps to report.

The sizes are constants at the top of the script. For another day pass `--date` and update `DATE` in `tests/conftest.py`.

If the archive format changes, the format knowledge is in `src/rpkispool/der.py`, `ccr.py` and `manifest.py`. Change those, then regenerate: `test_verify.py::test_fixture_is_valid` fails when the fixture and the verifiers disagree.
