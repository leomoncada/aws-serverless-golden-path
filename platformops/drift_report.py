"""Renders DRIFT.md from the ServiceStatus list that check_drift produces.

Nothing here calls cruft. "Days behind" is the distance in days between a
service's template version and the current template version, both defined in
docs/TEMPLATE-VERSION.md. It is not a distance from today, so this file's
output changes when the template moves and at no other time.

The mean lag this produces is the platform team's product metric. Without
it, "we have a golden path" is unfalsifiable.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    repo: str
    template_sha: str
    behind: bool
    days_behind: int
    # True when the tool could not determine whether the service is behind
    # (no reference HEAD, or no recorded commit). Added after the original
    # five fields, with a default, so existing positional callers (Task 8's
    # tests included) are unaffected. An unknown entry must never be
    # silently reported as "current": that would hide the one case this
    # dashboard exists to catch, the case where drift cannot be verified.
    unknown: bool = False
    # Why the check was inconclusive. Empty when unknown is False. Carried so
    # a caller can tell "this checkout cannot see the history" apart from
    # "the recorded commit was rewritten out from under us", which need
    # different repairs.
    unknown_reason: str = ""


def build_report(entries: list[ServiceStatus]) -> str:
    if not entries:
        return "# Template drift\n\nNo services are registered yet.\n"

    behind = [e for e in entries if e.behind and not e.unknown]
    unknown = [e for e in entries if e.unknown]
    evaluable = [e for e in entries if not e.unknown]

    # Unknown entries have no verified age; folding them in as 0 days would
    # understate drift, so they are excluded from both the sum and the count.
    mean_lag = (sum(e.days_behind for e in evaluable) / len(evaluable)) if evaluable else 0.0

    summary = f"{len(entries)} service(s) registered, {len(behind)} behind the current template"
    summary += f", {len(unknown)} unknown." if unknown else "."
    lag_line = f"Mean lag: {mean_lag:.1f} days"
    lag_line += " (unknown entries excluded)." if unknown else "."

    lines = [
        "# Template drift",
        "",
        summary,
        lag_line,
        "",
        "| Service | Repository | Template | Status | Days behind |",
        "|---|---|---|---|---|",
    ]
    for e in sorted(entries, key=lambda x: (x.unknown, -x.days_behind, x.name)):
        if e.unknown:
            status = "unknown"
        elif e.behind:
            status = "behind"
        else:
            status = "current"
        lines.append(
            f"| {e.name} | `{e.repo}` | `{e.template_sha}` | {status} | {e.days_behind} |"
        )
    lines.append("")
    return "\n".join(lines)
