"""Markdown rendering of a `DataCenterStatus` (extension §105-109) — the
same plain-markdown convention `reporting/` uses for the core research
engine's reports, rather than a separate web-dashboard dependency this
project doesn't otherwise need (no web framework is in `pyproject.toml`;
`pae data-center status` prints this straight to the terminal, or a
caller can redirect it to a file like any other `pae` report).
"""
from __future__ import annotations

from prop_alpha.data_center.status import DataCenterStatus

_NA = "not available"


def _fmt(value, suffix: str = "") -> str:
    return _NA if value is None else f"{value}{suffix}"


def render_status_markdown(status: DataCenterStatus) -> str:
    lines: list[str] = []
    lines.append("# Data Center Status")
    lines.append("")
    lines.append(f"- Timestamp: {status.timestamp.isoformat()}")
    lines.append(f"- Overall status: **{status.overall_status}**")
    lines.append(f"- Data source: **{status.data_source}**")
    lines.append("")

    lines.append("## Futures Feed")
    if status.futures_feed is None:
        lines.append(f"_{_NA}_")
    else:
        f = status.futures_feed
        lines.append(f"- Provider / instrument: {f.provider} / {f.instrument}")
        lines.append(f"- Connection state: {f.connection_state.value}")
        lines.append(f"- Messages received: {f.messages_received}")
        lines.append(f"- Messages/sec: {f.messages_per_second:.2f}")
        lines.append(f"- Sequence gaps: {f.sequence_gaps}")
        lines.append(f"- Last message age: {_fmt(f.last_message_age_seconds, 's')}")
    lines.append("")

    lines.append("## Options Feed")
    if status.options_feed is None:
        lines.append(f"_{_NA}_")
    else:
        o = status.options_feed
        lines.append(f"- Connected: {o.connected} / Authenticated: {o.authenticated}")
        lines.append(f"- Last update: {_fmt(o.last_update)}")
        lines.append(f"- Latency: {_fmt(o.latency_ms, 'ms')}")
        lines.append(f"- Error rate: {o.error_rate:.2%}")
        lines.append(f"- Data age: {_fmt(o.data_age_seconds, 's')}")
        metrics = ", ".join(o.available_metrics) if o.available_metrics else "none"
        lines.append(f"- Available metrics: {metrics}")
    lines.append("")

    lines.append("## Data Quality")
    if status.quality is None:
        lines.append(f"_{_NA}_")
    else:
        q = status.quality
        lines.append(f"- Score: {q.score:.1f} ({q.severity})")
        failed = q.failed_checks()
        if failed:
            lines.append("- Failed checks:")
            for check in failed:
                lines.append(f"  - {check.name}: {check.n_violations}/{check.n_checked} ({check.violation_rate:.2%})")
        else:
            lines.append("- Failed checks: none")
    lines.append("")

    lines.append("## Cross-Market Sync")
    lines.append(f"- Sync time difference: {_fmt(status.sync_time_difference_ms, 'ms')}")
    lines.append("")

    lines.append("## Market State")
    if status.market_state_completeness is None:
        lines.append(f"_{_NA}_")
    else:
        lines.append(f"- Completeness: {status.market_state_completeness:.0%}")
    lines.append("")

    lines.append("## Issues")
    if status.issues:
        for issue in status.issues:
            lines.append(f"- {issue}")
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"
