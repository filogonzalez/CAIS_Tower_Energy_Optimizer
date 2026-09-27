from datetime import date

import pandas as pd
from mock_data.entities import generate_equipment_assets, generate_sites
from mock_data.telemetry import generate_energy_telemetry


class Tariffs:
    grid_price_usd_per_kwh = 0.28
    diesel_price_usd_per_gal = 1.10
    diesel_emissions_kg_co2_per_gal = 2.68
    diesel_gal_per_kwh = 0.088


def test_hourly_telemetry_is_bounded_and_balanced():
    reference = date(2026, 9, 26)
    sites = generate_sites(42, 1, reference)
    assets = generate_equipment_assets(42, sites, reference)
    frame = generate_energy_telemetry(
        42, sites, assets, pd.DataFrame(), pd.DataFrame(), reference, 2, Tariffs()
    )
    assert len(frame) == 48
    assert frame.battery_soc_pct.between(0, 100).all()
    assert (frame[["grid_kwh", "generator_kwh", "battery_discharge_kwh", "solar_kwh"]] >= 0).all().all()
    assert frame[["site_id", "ts_utc"]].drop_duplicates().shape[0] == 48
