import pytest
from platformops.drift_report import ServiceStatus, build_report

def test_report_lists_each_service_with_its_template_version():
    md = build_report([
        ServiceStatus("orders-ingest", "leomoncada/orders-ingest", "abc1234", False, 0),
    ])
    assert "orders-ingest" in md
    assert "abc1234" in md

def test_services_behind_the_template_are_marked():
    md = build_report([
        ServiceStatus("orders-ingest", "leomoncada/orders-ingest", "abc1234", True, 12),
    ])
    assert "behind" in md.lower()
    assert "12" in md

def test_report_states_the_mean_lag():
    md = build_report([
        ServiceStatus("a", "o/a", "sha1", True, 10),
        ServiceStatus("b", "o/b", "sha2", True, 20),
        ServiceStatus("c", "o/c", "sha3", False, 0),
    ])
    assert "10.0" in md, "mean lag over three services with 10, 20 and 0 days is 10.0"

def test_empty_registry_produces_a_report_rather_than_crashing():
    md = build_report([])
    assert "No services" in md

def test_an_unknown_entry_is_shown_as_unknown_not_current():
    md = build_report([
        ServiceStatus("a", "o/a", "sha1", False, 0, unknown=True),
    ])
    row = [line for line in md.splitlines() if line.startswith("| a ")]
    assert row, f"no table row for service 'a' in:\n{md}"
    assert "unknown" in row[0]
    assert "current" not in row[0]

def test_unknown_entries_are_excluded_from_the_mean_lag_not_counted_as_zero():
    md = build_report([
        ServiceStatus("a", "o/a", "sha1", True, 10),
        ServiceStatus("b", "o/b", "sha2", False, 0, unknown=True),
    ])
    # Folding the unknown entry in as 0 days would give a mean of 5.0 and
    # understate drift; excluding it gives 10.0, the true mean of what could
    # actually be evaluated.
    assert "10.0" in md
    assert "5.0" not in md
