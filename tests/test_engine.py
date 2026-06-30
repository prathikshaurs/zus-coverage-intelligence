"""
Test suite for the Coverage Intelligence engine.

These tests do two jobs:
  1. Guard the engine's math (rates, anomaly z-scores, ADT signal).
  2. Confirm the engine actually *finds the injected problems* in the synthetic
     data, the equivalent of a real analyst proving their detection works against
     a known ground truth before trusting it on live data.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

import pandas as pd
import pytest
from generate_data import generate
from coverage_engine import CoverageEngine


@pytest.fixture(scope="module")
def bundle():
    return generate(n_patients=3000, seed=7)


@pytest.fixture(scope="module")
def engine(bundle):
    return CoverageEngine(bundle["coverage"], bundle["adt"], bundle["meta"])


def test_coverage_rate_in_valid_range(engine):
    o = engine.overall()
    assert 0 <= o["coverage_rate"] <= 100
    assert o["humans"] == 3000
    assert o["total_pulls"] > 0


def test_by_dimension_covers_all_groups(engine):
    by_net = engine.by("network")
    assert set(by_net["network"]) == {
        "Carequality", "CommonWell", "QHIN-eHX",
        "Surescripts", "Quest", "Labcorp"}
    # rates must be sorted ascending (worst first, for triage)
    assert by_net["coverage_rate"].is_monotonic_increasing


def test_matrix_shape(engine):
    m = engine.matrix("state", "network")
    assert m.shape[1] == 6  # 6 networks as columns
    assert (m.fillna(0) >= 0).all().all()


def test_detects_injected_geographic_outage(engine, bundle):
    """The TX/QHIN-eHX outage must surface as the most severe anomaly."""
    anomalies = engine.detect_anomalies()
    assert len(anomalies) > 0
    top = anomalies.iloc[0]
    assert top["state"] == bundle["meta"]["degraded_state"]
    assert top["network"] == bundle["meta"]["degraded_network"]
    assert top["z"] <= -2.0


def test_detects_new_customer_sparse_coverage(engine, bundle):
    """Evergreen Nephrology states should appear among flagged anomalies."""
    anomalies = engine.detect_anomalies()
    flagged_states = set(anomalies["state"])
    evergreen_states = {"TN", "KY", "NC", "VA"}
    assert flagged_states & evergreen_states


def test_detects_thin_payload_config_issue(engine):
    """Thin DocumentReference payloads must be caught by the quality scan."""
    issues = engine.detect_quality_issues()
    thin = [i for i in issues if i["type"] == "thin_payload"]
    assert len(thin) > 0
    assert all("DocumentReference" in i["scope"] for i in thin)


def test_narratives_have_action_and_hypothesis(engine):
    anomalies = engine.detect_anomalies()
    narrated = engine.narrate(anomalies)
    for n in narrated:
        assert n["hypothesis"]
        assert n["recommended_action"]
        assert n["category"] in {"connectivity", "configuration", "participation_gap"}


def test_adt_noise_reduction_is_meaningful(engine):
    s = engine.adt_signal()
    assert s["total_alerts"] > 0
    assert 0 < s["actionable_alerts"] < s["total_alerts"]
    assert s["noise_reduction_pts"] > 30  # noisy push data, real reduction


def test_report_bundle_is_complete(engine):
    rep = engine.build_report()
    for key in ["overall", "by_customer", "by_network", "by_data_type",
                "by_state", "anomalies", "quality_issues", "adt_signal"]:
        assert key in rep


def test_first_party_vs_network_split(bundle):
    """DATA_SOURCE semantics: NULL = first-party, NOT NULL = network."""
    p = bundle["patients"]
    first_party = p[p["data_source"].isna()]
    network = p[p["data_source"].notna()]
    assert len(first_party) > 0
    assert len(network) > len(first_party)  # more network copies than first-party
