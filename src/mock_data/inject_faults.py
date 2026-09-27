"""Select and schedule the 36 distinct-site injected faults.

Ground truth produced here is restricted to generation and evaluation
(non-negotiable contract #7): callers must never forward this table's
columns into Bronze, the agent, Genie, the app, or the vector index. The
Bronze `energy_telemetry`/`work_order_history` declarations only ever see
the *symptoms* this module schedules (via ``simulate.py``/``entities.py``),
never the `injected_faults` table itself.

Every fault's ``symptom_onset_ts_utc`` precedes its
``detection_deadline_ts_utc``, which in turn leaves enough runway inside the
telemetry window for a resolving work order to open and close before the
window ends — so the Phase 3 gate (29/36 detected strictly before deadline)
is evaluable without look-ahead past the generated data.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from mock_data.config import FAULT_TYPE_SPECS, TOTAL_FAULT_SITES
from mock_data.entities import telemetry_window
from mock_data.random_streams import stream

RESOLUTION_BUFFER_DAYS = 14  # room, after the deadline, for a resolving WO to open+close


def _eligible_sites_by_component(assets: pd.DataFrame, component: str) -> list[str]:
    return sorted(assets.loc[assets["component"] == component, "site_id"].unique().tolist())


def generate_injected_faults(
    seed: int,
    sites: pd.DataFrame,
    assets: pd.DataFrame,
    reference_date: date,
    telemetry_days: int,
) -> pd.DataFrame:
    start_date, end_date = telemetry_window(reference_date, telemetry_days)
    max_lead = max(spec["lead_days"][1] for spec in FAULT_TYPE_SPECS)
    earliest_onset_offset = 20
    latest_onset_offset = telemetry_days - max_lead - RESOLUTION_BUFFER_DAYS
    if latest_onset_offset <= earliest_onset_offset:
        raise ValueError("telemetry_days too small to schedule faults with a safe resolution buffer")

    used_sites: set[str] = set()
    rows: list[dict] = []
    fault_counter = 0

    for spec in FAULT_TYPE_SPECS:
        fault_type = spec["fault_type"]
        component = spec["component"]
        candidates = [s for s in _eligible_sites_by_component(assets, component) if s not in used_sites]
        rng = stream(seed, "fault_select", fault_type)
        if len(candidates) < spec["count"]:
            raise ValueError(
                f"Not enough eligible sites with component='{component}' for fault_type="
                f"'{fault_type}' (need {spec['count']}, have {len(candidates)})"
            )
        chosen = list(rng.choice(candidates, size=spec["count"], replace=False))

        for site_id in chosen:
            used_sites.add(site_id)
            asset_row = assets[(assets["site_id"] == site_id) & (assets["component"] == component)].iloc[0]
            fault_rng = stream(seed, "fault_schedule", fault_type, site_id)
            onset_offset = int(fault_rng.integers(earliest_onset_offset, latest_onset_offset))
            onset_date = start_date + timedelta(days=onset_offset)
            onset_hour = int(fault_rng.integers(0, 24))
            lo, hi = spec["lead_days"]
            lead_days = int(fault_rng.integers(lo, hi + 1))

            from common.timeutils import pr_midnight_utc

            symptom_onset = pr_midnight_utc(onset_date) + timedelta(hours=onset_hour)
            detection_deadline = symptom_onset + timedelta(days=lead_days)
            resolution_delay_days = int(fault_rng.integers(1, RESOLUTION_BUFFER_DAYS - 1))
            resolution_ts = detection_deadline + timedelta(days=resolution_delay_days)

            fault_id = f"FAULT-{fault_counter:03d}"
            fault_counter += 1
            rows.append(
                {
                    "fault_id": fault_id,
                    "site_id": site_id,
                    "asset_id": asset_row["asset_id"],
                    "component": component,
                    "fault_type": fault_type,
                    "symptom_onset_ts_utc": symptom_onset,
                    "detection_deadline_ts_utc": detection_deadline,
                    "resolution_ts_utc": resolution_ts,
                    "resolving_wo_id": f"WO-FAULT-{fault_id}",
                }
            )

    df = pd.DataFrame(rows)
    assert df["site_id"].nunique() == TOTAL_FAULT_SITES == len(df), "faults must map to distinct sites"
    return df
