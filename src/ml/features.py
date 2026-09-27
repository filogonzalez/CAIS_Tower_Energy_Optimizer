"""Leakage-safe feature definitions shared by training and scoring."""

from __future__ import annotations

import pandas as pd

BASELINE_FEATURES = ["it_load_kw", "hvac_load_kw", "ambient_temp_c", "network_traffic_gb", "local_hour"]
ANOMALY_FEATURES = [
    "energy_residual_z",
    "hvac_temp_ratio",
    "rectifier_slope_7d",
    "hvac_night_day_ratio",
    "outage_soc_drop_rate",
]
FAILURE_FEATURES = [
    "energy_residual_mean_7d",
    "energy_residual_max_7d",
    "anomaly_count_7d",
    "rectifier_slope_7d",
    "outage_soc_drop_rate_28d",
    "asset_age_days",
    "days_since_pm",
    "is_coastal",
    "storm_days_28d",
    "dust_days_28d",
]


def temporal_split(
    frame: pd.DataFrame, timestamp: str, label_horizon_days: int = 14
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = frame.sort_values(timestamp)
    split_index = int(len(ordered) * 0.8)
    split_ts = ordered.iloc[split_index][timestamp]
    purge_start = pd.Timestamp(split_ts) - pd.Timedelta(days=label_horizon_days)
    train = ordered[ordered[timestamp] < purge_start]
    validation = ordered[ordered[timestamp] >= split_ts]
    return train, validation


def priority_score(
    failure_risk: float,
    anomaly_score: float,
    resilience_score: float,
    cost_pressure: float,
    criticality: float,
) -> float:
    values = [failure_risk, anomaly_score, resilience_score, cost_pressure, criticality]
    bounded = [min(1.0, max(0.0, float(value))) for value in values]
    return 100.0 * (
        0.35 * bounded[0]
        + 0.25 * bounded[1]
        + 0.20 * (1 - bounded[2])
        + 0.10 * bounded[3]
        + 0.10 * bounded[4]
    )
