"""Frozen site/window fault-detection acceptance metrics."""

from __future__ import annotations

import pandas as pd


def evaluate_fault_gate(
    scores: pd.DataFrame, faults: pd.DataFrame, all_site_ids: set[str], threshold: float
) -> dict:
    flagged = scores[scores.anomaly_score >= threshold]
    detected = faults.merge(flagged, on="site_id", how="left")
    before_deadline = detected["score_ts_utc"].notna() & (
        detected["score_ts_utc"] < detected["detection_deadline_ts_utc"]
    )
    detected_sites = int(detected.loc[before_deadline, "site_id"].nunique())
    fault_sites = set(faults.site_id)
    healthy_sites = all_site_ids - fault_sites
    healthy_flagged = set(flagged.site_id) & healthy_sites
    false_positive_rate = len(healthy_flagged) / max(1, len(healthy_sites))
    by_type = (
        detected.assign(detected_before_deadline=before_deadline)
        .groupby("fault_type")["detected_before_deadline"]
        .agg(["sum", "count"])
        .assign(recall=lambda value: value["sum"] / value["count"])
        .reset_index()
        .to_dict("records")
    )
    return {
        "threshold": threshold,
        "fault_sites": len(fault_sites),
        "detected_before_deadline": detected_sites,
        "healthy_sites": len(healthy_sites),
        "healthy_flagged": len(healthy_flagged),
        "healthy_false_positive_rate": false_positive_rate,
        "per_type": by_type,
        "passed": detected_sites >= 29 and false_positive_rate < 0.05,
    }
