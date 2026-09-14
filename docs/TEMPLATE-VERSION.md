# What "the current template version" means

One definition, in one file, because three of them used to coexist in this
repository and they disagreed about the committed example service. Everything
that measures drift here points at this page: `platformops/check_drift.py`,
`platformops/drift_report.py`, the root `Makefile`'s `drift-demo` target,
[`docs/adr/0004-drift-strategy.md`](adr/0004-drift-strategy.md) and the
generated service's own README.

## The definition

**A template version is a commit that touches `template/`.** Nothing else is.

- **The current template version** is the newest commit reachable from this
  repository's HEAD that touches `template/`:
  `git log -1 --format=%H -- template`.
- **A service's template version** is the newest commit that touches
  `template/` and is an ancestor of the commit its `.cruft.json` recorded:
  `git log -1 --format=%H <recorded commit> -- template`.
- **A service is behind** when those two commits differ. The lag reported in
  [`DRIFT.md`](../DRIFT.md) is the number of days between those two commits'
  dates.

Both sides of the comparison are therefore the same kind of thing: a commit
that actually changed the template. That is the property the old code was
missing.

## Why the resolution step on the recorded commit is needed

`cruft` writes the template repository's HEAD into `.cruft.json` at generation
time, whatever that commit touched. Generate a service one commit after a
README fix and `.cruft.json` records the README commit, which is not a template
version at all. Comparing that raw SHA against the newest template-touching
commit reports a service that was generated seconds ago as `behind`, and
`apply_drift_updates` then runs a `cruft update` with nothing to merge.

Resolving the recorded commit to the newest template-touching commit beneath it
answers the question actually being asked: which version of the template is
this service's code made of? A service generated from a README commit is made
of the template as it stood at the last commit that changed the template, so
that is the version it is on.

## Why the lag is a distance between two commits, not a distance from now

`days_behind` used to be `now - the recorded commit's date`, which made
`DRIFT.md` a file whose contents changed every 24 hours while nothing about the
services changed. Since the dashboard is committed and
`tests/test_docs.py::test_committed_drift_md_matches_what_the_tool_currently_produces`
asserts the committed file equals what the tool produces, a wall-clock field
meant the suite would go red once a day, forever, with no code change. It also
conflated two different things: a template nobody has changed in a year does
not put every service a year behind.

The lag is now the distance between the service's template version and the
current template version, measured in days of template history. It changes only
when the template moves, which is exactly when `DRIFT.md` is supposed to change.

## What `cruft check` answers, and why it is not this

`cruft check` compares `.cruft.json`'s recorded commit against the **template
repository's HEAD**. It reports a service out of date after any commit to this
repository: a README edit, an ADR, a fix to the drift code itself. That is not
what drift means here, so the dashboard does not use it and this repository
does not treat its verdict as the authority on whether a service is behind.

The two answers are allowed to differ, and knowing which is which matters:

| Question | Answered by |
|---|---|
| Has the template itself changed since this service was generated? | `DRIFT.md` / `python -m platformops.check_drift` |
| Was this service generated from the tip of the template repository? | `cruft check` |

`cruft update` is still the mechanism that fixes drift, and it updates a
service to the template repository's HEAD. After it runs, the service's
recorded commit is HEAD, which resolves to the newest template-touching commit,
which is the current template version. So the two definitions converge exactly
where it matters: on a service that has just been brought up to date, both say
current.

## Shallow clones

All of this is `git log` over real history. In a clone made with `--depth 1`
the single fetched commit appears to add every file in the repository,
including `template/`, so "the newest commit touching `template/`" resolves to
HEAD and every service reads as behind. `check_drift` detects a shallow
repository and reports `unknown` rather than that wrong answer, and both
workflows check out with `fetch-depth: 0` so the question does not arise in CI.
`make demo` needs full history for the same reason and says so when it does not
have it.

## Why this repository only allows merge commits

Squash and rebase merging are disabled in the repository settings, and that is
a consequence of everything above rather than a style preference.

A generated service records, in its `.cruft.json`, the commit it was generated
from. Squash and rebase both rewrite a branch's commits, so that recorded SHA
stops being reachable from the default branch the moment such a merge lands.
The drift check then cannot resolve the service's template version, and the
committed dashboard no longer matches what the tool produces.

It fails in a particularly unhelpful way. The orphaned commit survives in the
local object store of whoever performed the merge, so it resolves fine there
and the tests pass. A fresh clone fetches only reachable history, so CI sees a
service it cannot place and reports it as unknown. Green locally, red in CI,
with no code difference between them.

Two defences, because the setting alone is not enough:

- `_is_reachable` in `platformops/check_drift.py` checks reachability BEFORE
  resolving the recorded commit, so a laptop with a dangling object and a fresh
  clone reach the same answer.
- When the check is inconclusive, the reason travels with the result, and
  `tests/test_docs.py` uses it to name the correct repair: regenerate the
  example fixture, which is not the same as regenerating the dashboard.

If you ever need to rewrite history on this repository, regenerate the fixture
afterwards with `SERVICE=orders-ingest SANDBOX=examples make new` and commit the
result alongside a refreshed `DRIFT.md`.

