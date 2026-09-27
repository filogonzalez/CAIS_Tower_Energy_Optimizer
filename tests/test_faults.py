from datetime import date

from mock_data.entities import generate_equipment_assets, generate_sites, generate_work_order_history
from mock_data.inject_faults import generate_injected_faults


def test_36_causal_faults_and_resolving_work_orders():
    reference = date(2026, 9, 26)
    sites = generate_sites(42, 300, reference)
    assets = generate_equipment_assets(42, sites, reference)
    faults = generate_injected_faults(42, sites, assets, reference, 180)
    orders = generate_work_order_history(42, sites, assets, faults, reference, 18, target_count=200)
    assert len(faults) == faults.site_id.nunique() == 36
    assert (faults.symptom_onset_ts_utc < faults.detection_deadline_ts_utc).all()
    assert set(faults.resolving_wo_id).issubset(set(orders.wo_id))
