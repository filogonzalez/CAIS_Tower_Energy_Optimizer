"""Central configuration for the Tower Energy Optimizer bundle.

Every customer, catalog, tariff, and endpoint identifier is resolved from
Databricks Asset Bundle variables — surfaced to jobs/tasks as ``TEO_*``
environment variables (see ``databricks.yml``) — never hardcoded here and
never written to disk. Local development uses the same defaults the bundle
declares for the ``dev`` target, so scripts behave identically whether they
are invoked from a job or from a developer's shell.

No secret, token, or password is read, held, or written by this module.
Databricks/Lakebase authentication is handled exclusively by
``src/common/databricks_auth.py`` via the Databricks SDK's ``Config``/
``WorkspaceClient``, which resolve credentials from the environment
(``DATABRICKS_HOST``/``DATABRICKS_TOKEN``, a CLI profile, or an attached
compute identity) — this module never touches that credential material.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def validate_identifier(name: str, value: str) -> str:
    """Guard against SQL-injection-shaped configuration for UC identifiers.

    Every catalog/schema/volume/table-name-fragment that ends up interpolated
    into SQL (rather than passed as a bind parameter) must pass through here.
    """
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(
            f"Configured identifier '{name}'={value!r} is not a safe UC/SQL "
            "identifier. Expected [A-Za-z_][A-Za-z0-9_]{0,127}."
        )
    return value


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"TEO_{name}", default)


def _env_str(name: str, default: str) -> str:
    val = _env(name)
    return val if val is not None else default


def _env_int(name: str, default: int) -> int:
    val = _env(name)
    return int(val) if val is not None else default


def _env_float(name: str, default: float) -> float:
    val = _env(name)
    return float(val) if val is not None else default


@dataclass(frozen=True)
class Settings:
    """Resolved runtime configuration. Immutable once constructed.

    Construct with :func:`get_settings` (cached) or ``Settings()`` directly
    (e.g. in tests, to bypass environment resolution via explicit kwargs).
    """

    # --- Bundle identity -------------------------------------------------
    bundle_name: str = "tower_energy_pr"
    target: str = field(default_factory=lambda: _env_str("TARGET", "dev"))
    brand: str = field(default_factory=lambda: _env_str("BRAND", "IslaNet Telecom"))
    brand_locale_secondary: str = field(default_factory=lambda: _env_str("BRAND_LOCALE_SECONDARY", "es"))

    # --- Unity Catalog namespace ------------------------------------------
    catalog: str = field(default_factory=lambda: _env_str("CATALOG", "tower_energy_optimizer"))
    schema_raw: str = field(default_factory=lambda: _env_str("SCHEMA_RAW", "raw_telemetry"))
    schema_curated: str = field(default_factory=lambda: _env_str("SCHEMA_CURATED", "curated"))
    schema_analytics: str = field(default_factory=lambda: _env_str("SCHEMA_ANALYTICS", "analytics"))
    schema_ml: str = field(default_factory=lambda: _env_str("SCHEMA_ML", "ml"))
    schema_agents: str = field(default_factory=lambda: _env_str("SCHEMA_AGENTS", "agents"))
    volume_name: str = field(default_factory=lambda: _env_str("VOLUME_NAME", "mock_data"))

    # --- Reproducibility ---------------------------------------------------
    seed: int = field(default_factory=lambda: _env_int("SEED", 42))
    # ISO date (YYYY-MM-DD) frozen into the generation manifest. When unset,
    # generation resolves and freezes "yesterday in America/Puerto_Rico" once,
    # at generation start, and every downstream job reads it from the
    # manifest rather than recomputing "yesterday" independently.
    reference_date_override: str | None = field(default_factory=lambda: _env("REFERENCE_DATE"))

    # --- Scale (Phase 1 data contracts) ------------------------------------
    site_count: int = field(default_factory=lambda: _env_int("SITE_COUNT", 300))
    telemetry_days: int = field(default_factory=lambda: _env_int("TELEMETRY_DAYS", 180))
    work_order_months: int = field(default_factory=lambda: _env_int("WORK_ORDER_MONTHS", 18))
    fault_site_count: int = field(default_factory=lambda: _env_int("FAULT_SITE_COUNT", 36))
    storm_start_offset_days: int = field(default_factory=lambda: _env_int("STORM_START_OFFSET_DAYS", 95))
    storm_duration_days: int = field(default_factory=lambda: _env_int("STORM_DURATION_DAYS", 3))
    dust_start_offset_days: int = field(default_factory=lambda: _env_int("DUST_START_OFFSET_DAYS", 40))
    dust_duration_days: int = field(default_factory=lambda: _env_int("DUST_DURATION_DAYS", 7))

    # --- Tariffs / economics (demo assumptions, not customer-verified) ----
    grid_price_usd_per_kwh: float = field(default_factory=lambda: _env_float("GRID_PRICE", 0.28))
    diesel_price_usd_per_gal: float = field(default_factory=lambda: _env_float("DIESEL_PRICE", 1.10))
    diesel_emissions_kg_co2_per_gal: float = field(
        default_factory=lambda: _env_float("DIESEL_EMISSIONS_FACTOR", 2.68)
    )
    diesel_gal_per_kwh: float = field(default_factory=lambda: _env_float("DIESEL_BURN_RATE", 0.088))
    hvac_capex_usd: float = field(default_factory=lambda: _env_float("HVAC_CAPEX_USD", 8_000.0))
    rectifier_capex_usd: float = field(default_factory=lambda: _env_float("RECTIFIER_CAPEX_USD", 5_500.0))
    battery_capex_usd: float = field(default_factory=lambda: _env_float("BATTERY_CAPEX_USD", 18_000.0))
    solar_capex_usd: float = field(default_factory=lambda: _env_float("SOLAR_CAPEX_USD", 32_000.0))
    retrofit_annual_maintenance_pct: float = field(
        default_factory=lambda: _env_float("RETROFIT_ANNUAL_MAINTENANCE_PCT", 0.02)
    )

    # --- Model serving / endpoints (names only, discovered/validated before
    # binding — see src/common/databricks_auth.py:assert_endpoint_available)
    extraction_llm_endpoint: str = field(
        default_factory=lambda: _env_str("EXTRACTION_LLM_ENDPOINT", "databricks-claude-haiku-4-5")
    )
    # Note extraction backend: "python_udf" (default) drives a pandas-UDF
    # that POSTs directly to the model-serving invocation URL with a
    # secret-scope bearer token — used because this workspace's ai_query
    # resolves the legacy serving-endpoint registry and 404s even though
    # direct HTTP calls from the driver/executors succeed. "ai_query" is
    # kept as an optional documented fallback for workspaces where the SQL
    # path works, selectable without a code change.
    note_extraction_backend: str = field(
        default_factory=lambda: _env_str("NOTE_EXTRACTION_BACKEND", "python_udf")
    )
    gateway_secret_scope: str = field(
        default_factory=lambda: _env_str("GATEWAY_SECRET_SCOPE", "apps-secret-scope")
    )
    gateway_secret_key: str = field(default_factory=lambda: _env_str("GATEWAY_SECRET_KEY", "apps-secret-key"))
    agent_llm_endpoint: str = field(
        default_factory=lambda: _env_str("AGENT_LLM_ENDPOINT", "databricks-claude-sonnet-4-5")
    )
    agent_llm_fallback_endpoint: str = field(
        default_factory=lambda: _env_str("AGENT_LLM_FALLBACK_ENDPOINT", "databricks-claude-haiku-4-5")
    )
    embedding_endpoint: str = field(
        default_factory=lambda: _env_str("EMBEDDING_ENDPOINT", "databricks-gte-large-en")
    )
    vector_search_endpoint: str = field(
        default_factory=lambda: _env_str("VECTOR_SEARCH_ENDPOINT", "teo_vs_endpoint")
    )
    agent_serving_endpoint: str = field(
        default_factory=lambda: _env_str("AGENT_SERVING_ENDPOINT", "teo_maintenance_agent")
    )
    genie_space_name: str = field(
        default_factory=lambda: _env_str("GENIE_SPACE_NAME", "Tower Energy Optimizer")
    )
    app_name: str = field(default_factory=lambda: _env_str("APP_NAME", "tower-energy-cockpit"))
    warehouse_id: str | None = field(default_factory=lambda: _env("WAREHOUSE_ID"))

    # --- Lakebase (operational Postgres) -----------------------------------
    lakebase_instance_name: str = field(default_factory=lambda: _env_str("LAKEBASE_INSTANCE", "teo-lakebase"))
    lakebase_database: str = field(default_factory=lambda: _env_str("LAKEBASE_DATABASE", "teo"))

    # --- Governance groups (names only; membership managed in the workspace)
    engineering_group: str = field(default_factory=lambda: _env_str("ENGINEERING_GROUP", "teo-engineering"))
    analyst_group: str = field(default_factory=lambda: _env_str("ANALYST_GROUP", "teo-analysts"))
    field_manager_group: str = field(
        default_factory=lambda: _env_str("FIELD_MANAGER_GROUP", "teo-field-managers")
    )
    finance_group: str = field(default_factory=lambda: _env_str("FINANCE_GROUP", "teo-finance"))
    approver_group: str = field(default_factory=lambda: _env_str("APPROVER_GROUP", "teo-approvers"))

    def __post_init__(self) -> None:
        for attr in (
            "catalog",
            "schema_raw",
            "schema_curated",
            "schema_analytics",
            "schema_ml",
            "schema_agents",
            "volume_name",
        ):
            validate_identifier(attr, getattr(self, attr))
        if self.target not in {"dev", "demo"}:
            raise ValueError(f"Unknown bundle target '{self.target}' (expected 'dev' or 'demo')")
        if self.site_count <= 0 or self.telemetry_days <= 0 or self.work_order_months <= 0:
            raise ValueError("site_count/telemetry_days/work_order_months must be positive")
        if self.fault_site_count > self.site_count:
            raise ValueError("fault_site_count cannot exceed site_count")
        if self.storm_duration_days <= 0 or self.dust_duration_days <= 0:
            raise ValueError("storm/dust durations must be positive")
        if self.grid_price_usd_per_kwh <= 0 or self.diesel_price_usd_per_gal <= 0:
            raise ValueError("tariff prices must be positive")
        if self.diesel_emissions_kg_co2_per_gal <= 0 or self.diesel_gal_per_kwh <= 0:
            raise ValueError("diesel emissions/burn-rate factors must be positive")

    # -- convenience accessors ------------------------------------------------
    def qualify(self, schema: str, table: str) -> str:
        """Return a fully-qualified ``catalog.schema.table`` name, validated."""
        validate_identifier("schema", schema)
        validate_identifier("table", table)
        return f"{self.catalog}.{schema}.{table}"

    @property
    def volume_path(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema_raw}/{self.volume_name}"

    def table_raw(self, name: str) -> str:
        return self.qualify(self.schema_raw, name)

    def table_curated(self, name: str) -> str:
        return self.qualify(self.schema_curated, name)

    def table_analytics(self, name: str) -> str:
        return self.qualify(self.schema_analytics, name)

    def table_ml(self, name: str) -> str:
        return self.qualify(self.schema_ml, name)

    def table_agents(self, name: str) -> str:
        return self.qualify(self.schema_agents, name)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings, resolved once from the environment."""
    return Settings()
