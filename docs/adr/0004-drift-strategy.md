# 0004: The drift strategy

## Context

A golden path that only scaffolds new services is half the problem. The
other half, and the one this repository treats as its differentiator, is
what happens to services already generated once the template changes.
Without an answer, "we have a golden path" is a claim about day one only.

`cruft` already solves the mechanics: a generated service's `.cruft.json`
records the commit it came from; `cruft check` compares that commit against
the template repository's HEAD; `cruft update` computes the diff between
them and applies it to the generated service as a three-way merge,
preserving local edits made since generation.

What cruft does not settle is what "current" means, and this repository
needed that settled. Three incompatible answers had grown up beside each
other: `check_drift` used the newest commit touching `template/`, `cruft
check` uses repo HEAD, and `.cruft.json` records repo HEAD at generation
time, whatever that commit touched. They disagreed about the one committed
example service, so the dashboard and `cruft check` could give opposite
answers about it, and a service generated today could be reported behind the
moment it was created.

**One definition, one page:
[`docs/TEMPLATE-VERSION.md`](../TEMPLATE-VERSION.md).** A template version is
a commit that touches `template/`. The current template version is the
newest one under HEAD; a service's template version is the newest one under
the commit its `.cruft.json` recorded; a service is behind when those two
differ, and the lag is the distance in days between those two commits rather
than a distance from today. That page is what `platformops/check_drift.py`,
`platformops/drift_report.py`, the root `Makefile` and the generated
service's README all point at, and it records what `cruft check` answers
instead and why the two are allowed to differ.

## Decision

Drift is handled in three parts, implemented in `platformops/`:

- **Detection.** `platformops/check_drift.py` reads `platformops/registry.yaml`
  and compares each registered service's template version against the current
  one, as defined in [`docs/TEMPLATE-VERSION.md`](../TEMPLATE-VERSION.md),
  producing a `ServiceStatus` per service (current, behind, or unknown when
  neither can be resolved). It does not shell out to cruft: it reads the
  recorded commit and asks `git log`, which is why it can answer a question
  `cruft check` does not.
- **Update.** `platformops/apply_drift_updates.py` runs `cruft update
  --skip-apply-ask --allow-untracked-files` for every service reported
  behind, via a list argument vector (never an interpolated shell string),
  so a service name cannot inject shell syntax.
- **Measurement.** `platformops/drift_report.py` builds `DRIFT.md`: a
  per-service table (template version, status, days behind) and a mean lag
  across evaluable services. `.github/workflows/drift.yml` runs this on a
  schedule and opens a pull request through `peter-evans/create-pull-request`
  with whatever `cruft update` produced.

The update step runs **before** the dashboard step, and that order is
asserted by `tests/test_workflows.py`. `cruft update` refuses to run against
a dirty tree, and the tree it asks git about is the whole repository, not the
service directory it was pointed at; `--allow-untracked-files` forgives only
untracked files, and `DRIFT.md` is tracked. Writing the dashboard first
therefore made every subsequent `cruft update` refuse, so the workflow failed
in exactly the situation it exists for: a service actually being behind.
`apply_drift_updates` now also refuses to start against a dirty tree, with
the reason, rather than leaving cruft's refusal to be decoded.

The registry (`platformops/registry.yaml`) is a plain YAML file listing each
service's name, repository and path. In a real organization this would be
the Backstage catalog; here it is a file, and the README says which is
which.

## Consequences

- Drift is detectable and measurable without a human manually diffing every
  generated service against the template by hand.
- The mean lag in `DRIFT.md` is the platform team's product metric: it is
  the number that makes "we have a golden path" falsifiable.
- An entry the tool cannot evaluate (no `.cruft.json` commit recorded, or no
  resolvable template HEAD) is reported as `unknown`, never folded in as
  `current` or as zero days behind, so an inconclusive check cannot silently
  read as a clean one.

## What this does not solve

- **Heavily diverged services can conflict, and resolve badly.** A three-way
  merge is not magic: a service whose generated files have been edited
  extensively since generation can produce a merge conflict on `cruft
  update`, and in the worst case a merge that applies without conflict
  markers but produces something subtly wrong. The workflow opens a pull
  request specifically so a human reviews the diff before it merges; nothing
  in this design merges automatically to `main`.
- **Terraform resource renames are not mergeable at all.** A template change
  that renames a Terraform resource (or moves it to a different module path)
  changes its address in state. `cruft update`'s three-way merge operates on
  file text, not on Terraform state; it cannot emit the `moved` block, or
  perform the state surgery (`terraform state mv`), that such a rename
  needs. That case has to be handled by hand, service by service, and is out
  of scope for this mechanism.
- **The registry is a file, not a catalog.** `platformops/registry.yaml` has
  no validation that an entry's path actually contains a service, no access
  control, and no relationship to whatever a real organization's system of
  record considers the source of truth for what services exist. It is
  adequate for one committed example; it does not scale into a real fleet
  without becoming, in effect, the Backstage catalog it currently stands in
  for.
- **`cruft update` needs the recorded template reference to actually be
  reachable.** `examples/orders-ingest/.cruft.json` records `"template":
  "https://github.com/leomoncada/aws-serverless-golden-path"` rather than a
  local path, so `cruft update` resolves it identically on any machine or CI
  runner, unlike an earlier draft of this fixture that recorded the author's
  own absolute filesystem path and therefore only worked on that one laptop.
  That said, `cruft update` only runs at all for a service `check_drift.py`
  reports as behind, which cannot happen until a future commit changes
  `template/`, by which point this repository has to already be pushed for
  the scheduled `drift.yml` workflow to be running in the first place. Until
  then, this reference is correct but unexercised, the same honest category
  as the AWS path and the Backstage adapter.
