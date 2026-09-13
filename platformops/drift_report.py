"""Builds DRIFT.md from cruft check results.

The number this produces is the platform team's product metric. Without it,
"we have a golden path" is unfalsifiable.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    repo: str
    template_sha: str
    behind: bool
    days_behind: int


def build_report(entries: list[ServiceStatus]) -> str:
    if not entries:
        return "# Template drift\n\nNo services are registered yet.\n"

    behind = [e for e in entries if e.behind]
    mean_lag = sum(e.days_behind for e in entries) / len(entries)

    lines = [
        "# Template drift",
        "",
        f"{len(entries)} service(s) registered, {len(behind)} behind the current template.",
        f"Mean lag: {mean_lag:.1f} days.",
        "",
        "| Service | Repository | Template | Status | Days behind |",
        "|---|---|---|---|---|",
    ]
    for e in sorted(entries, key=lambda x: (-x.days_behind, x.name)):
        status = "behind" if e.behind else "current"
        lines.append(
            f"| {e.name} | `{e.repo}` | `{e.template_sha}` | {status} | {e.days_behind} |"
        )
    lines.append("")
    return "\n".join(lines)
