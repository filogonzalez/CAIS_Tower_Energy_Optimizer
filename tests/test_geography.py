from datetime import date

from mock_data.entities import generate_sites
from mock_data.geo import is_on_land


def test_all_generated_coordinates_are_on_land_and_deterministic():
    first = generate_sites(42, 300, date(2026, 9, 26))
    second = generate_sites(42, 300, date(2026, 9, 26))
    assert first.equals(second)
    assert all(is_on_land(row.longitude, row.latitude) for row in first.itertuples())
    assert set(first.region) == {"Metro", "North", "South", "East", "West", "Central", "Islands"}
