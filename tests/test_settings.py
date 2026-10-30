from config.settings import Settings, validate_identifier


def test_default_contracts():
    settings = Settings(reference_date_override="2026-09-26")
    assert settings.catalog == "tower_energy_optimizer"
    assert settings.seed == 42
    assert settings.site_count == 300
    assert settings.volume_path.endswith("/raw_telemetry/mock_data")


def test_rejects_unsafe_identifier():
    try:
        validate_identifier("catalog", "bad;drop table x")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe identifier accepted")
