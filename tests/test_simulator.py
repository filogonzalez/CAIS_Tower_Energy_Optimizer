from connect.resilience_simulator import calculate_roi, calculate_site_scenario


def test_battery_only_and_late_fuel_cases():
    battery_only = calculate_site_scenario(5, 20, 0, 0, 0.088, 12, 4)
    assert battery_only["time_to_dark_hours"] == 4
    assert battery_only["unserved_kwh"] == 40
    late_fuel = calculate_site_scenario(5, 5, 5, 1, 0.1, 24, 12)
    assert late_fuel["fuel_truck_required"] is True
    assert late_fuel["time_to_dark_hours"] >= 0


def test_nonpositive_savings_has_no_payback():
    assert calculate_roi(10_000, 100, 0.02)["payback_years"] is None
