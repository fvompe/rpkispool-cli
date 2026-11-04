# rpkispool-cli coverage

Shows how complete the initstate archive is: which repositories each vantage point has, and how many objects. A repository is "missing" at a vantage point if some other vantage point has objects for it but this one has none.

All subcommands read the initstate filelist (`<date>-initstate.tar.zst.filelist.gz`), so run `download --filelists` first.

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

``` bash
$ rpkispool-cli coverage vantage-points --help
usage: rpkispool-cli coverage vantage-points [-h] [--full]

options:
  -h, --help  show this help message and exit
  --full      List all missing repos instead of a short summary
```

# rpkispool-cli coverage vantage-points

One row per vantage point: the number of objects, the number of repositories, and the repositories it is missing. By default the missing repositories are shortened to a count plus the first three names; use `--full` to list all of them.

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

# rpkispool-cli coverage repositories

This command show coverage matrix across vantage points for each repository. 

A cell is

- `ok` if the vantage point has as many objects as the best one for that repository
- `--` if it has none
-  `-N` if it has N objects fewer

Cells are coloured on a terminal.

```bash
$ rpkispool-cli --date 20261103 coverage repositories
2026-11-04 20:36:38,321 INFO: Loading work/archives/20261103-initstate.tar.zst.filelist.gz
Repository                          ams1  ams3  ams4  ams5  blr1  blr2  cpt1  dus1  miso  nyc1  pek1  rix1  syd1  syd2  yyz1   zia1   zur1
------------------------------------------------------------------------------------------------------------------------------------------
akane.maru.co.jp                     ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok     ok     ok
alias.rpki-measurement.site          ok    ok    ok    ok    ok    --    ok    ok    ok    ok    ok    ok    ok    --    --     ok     ok
ca.nat.moe                           ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok     ok     ok
ca.rg.net                            ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok     ok     ok
...
rsync.prefixlogic.com                --    --    ok    ok    ok    --    ok    --    --    --    ok    ok    ok    --    --     ok     ok
rsync.proxy-arp.network              ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok     ok     ok
rsync.rp.ki                          ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok     ok     ok
rsync.rpki.tianhai.link              ok    ok    ok    ok    ok    --    ok    ok    ok    ok    ok    ok    ok    --    ok     ok     ok
sakuya.nat.moe                       ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok     ok     ok
ta                                   ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok    ok     ok     ok

  ok = present (full)  -- = missing  -N = present but N objects fewer than max
```

# rpkispool-cli coverage missing

The gaps as a flat list, one `repository<TAB>vantage-point` pair per line, sorted by repository. 

It is meant for scripts, e.g. to pipe into `grep`, `sort` or `diff`. With `--fail` the exit status is 1 when any gap exists.
```bash
$ rpkispool-cli --date 20261103 coverage missing
2026-11-04 20:37:53,116 INFO: Loading work/archives/20261103-initstate.tar.zst.filelist.gz
alias.rpki-measurement.site     blr2
alias.rpki-measurement.site     syd2
alias.rpki-measurement.site     yyz1
krill.47272.net zia1
krill.cxy.hk    blr2
krill.cxy.hk    syd2
...
```
