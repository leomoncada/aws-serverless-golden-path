# 0004: The drift strategy

## Context

A golden path that only scaffolds new services is half the problem. The
other half, and the one this repository treats as its differentiator, is
what happens to services already generated once the template changes.
Without an answer, "we have a golden path" is a claim about day one only.

`cruft` already solves the mechanics: a generated service's `.cruft.json`
records the template commit it came from; `cruft check` compares that commit
against the template's current state; `cruft update` computes the diff
between them and applies it to the generated service as a three-way merge,
preserving local edits made since generation.

## Decision

Drift is handled in three parts, implemented in `platformops/`:

- **Detection.** `platformops/check_drift.py` reads `platformops/registry.yaml`,
  runs the equivalent of `cruft check` against each registered service's
  recorded commit and the template's current HEAD, and produces a
  `ServiceStatus` per service (current, behind, or unknown when no reference
  commit or HEAD can be determined).
- **Update.** `platformops/apply_drift_updates.py` runs `cruft update
  --skip-apply-ask --allow-untracked-files` for every service reported
  behind, via a list argument vector (never an interpolated shell string),
  so a service name cannot inject shell syntax.
- **Measurement.** `platformops/drift_report.py` builds `DRIFT.md`: a
  per-service table (template commit, status, days behind) and a mean lag
  across evaluable services. `.github/workflows/drift.yml` runs this on a
  schedule and opens a pull request through `peter-evans/create-pull-request`
  with whatever `cruft update` produced.

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
