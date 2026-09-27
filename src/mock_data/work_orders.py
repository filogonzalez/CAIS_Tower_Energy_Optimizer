"""``work_order_history`` generator: ~10,000 rows over 18 months.

Two populations are produced and concatenated:

1. Background maintenance activity — preventive/corrective/emergency work
   orders against random site/asset pairs, unrelated to the 36 injected
   faults, giving the note-extraction pipeline (Phase 2) a realistic corpus
   to parse.
2. Exactly one *resolving* work order per injected fault (``wo_id`` equal to
   the fault's ``resolving_wo_id``), with ``site_id``/``asset_id``/
   ``component`` consistent with that fault and a close/open window that
   respects ``detection_deadline_ts_utc`` / ``resolution_ts_utc`` — the fault
   table itself is never joined into this output; only IDs already present
   on the fault row are reused so the join key is consistent, not the
   fault's ground-truth timing/type fields.

Notes are bilingual (English/Spanish) free text, matching real bilingual
field-technician records. Technician identity is hashed (never raw) per
non-negotiable contract #7 (ground truth / PII restricted to generation).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from common.timeutils import UTC

from mock_data.config import WORK_ORDER_STATUSES, WORK_ORDER_TYPES
from mock_data.entities import hash_technician
from mock_data.random_streams import stream

TECHNICIAN_NAMES = [
    "J. Rivera",
    "M. Torres",
    "L. Ortiz",
    "A. Feliciano",
    "C. Vazquez",
    "R. Colon",
    "D. Cruz",
    "S. Melendez",
    "E. Rodriguez",
    "N. Santiago",
    "P. Diaz",
    "F. Ramos",
]

PARTS_BY_COMPONENT = {
    "rectifier": ["rectifier_module", "cooling_fan", "input_fuse"],
    "battery_bank": ["battery_string", "battery_terminal", "bms_module"],
    "hvac_unit": ["compressor", "condenser_coil", "refrigerant_charge", "air_filter"],
    "generator": ["fuel_injector", "starter_motor", "alternator", "voltage_regulator"],
    "solar_array": ["solar_panel", "inverter", "mppt_controller"],
    "fuel_tank": ["fuel_sensor", "fuel_line", "tank_gasket"],
    "controller": ["controller_board", "firmware_update"],
    "antenna_system": ["antenna_mount", "jumper_cable", "grounding_kit"],
}

_ROOT_CAUSE_EN = {
    "hvac_degradation": "compressor efficiency loss consistent with worn bearings",
    "rectifier_drift": "rectifier output drifting below spec, suspect aging module",
    "battery_fade": "battery string showing reduced usable capacity on load test",
    "generator_start_failure": "generator failed to crank on automatic transfer test",
    "fuel_loss_without_runtime": "fuel level drop without matching generator runtime, checked for leak",
    "ghost_load": "IT load elevated with no matching traffic increase, controller anomaly suspected",
}
_ROOT_CAUSE_ES = {
    "hvac_degradation": "perdida de eficiencia del compresor, posible desgaste de rodamientos",
    "rectifier_drift": "salida del rectificador fuera de especificacion, modulo posiblemente envejecido",
    "battery_fade": "banco de baterias con capacidad util reducida en prueba de carga",
    "generator_start_failure": "el generador no arranco en la prueba de transferencia automatica",
    "fuel_loss_without_runtime": (
        "caida de nivel de combustible sin tiempo de generador correspondiente, se revisa fuga"
    ),
    "ghost_load": (
        "carga de TI elevada sin aumento de trafico correspondiente, se sospecha anomalia del controlador"
    ),
}

_GENERIC_NOTES_EN = [
    "routine inspection, {component} within normal parameters, {env}",
    "replaced {part} on {component} after {env}, site restored to normal",
    "preventive maintenance on {component}, cleaned and torque-checked connections, {env}",
    "responded to alarm on {component}, found {env}, cleared fault and verified operation",
    "corrective repair on {component}: {part} replaced, tested under load, {env}",
]
_GENERIC_NOTES_ES = [
    "inspeccion de rutina, {component} dentro de parametros normales, {env}",
    "se reemplazo {part} en {component} despues de {env}, sitio restablecido",
    "mantenimiento preventivo en {component}, limpieza y ajuste de conexiones, {env}",
    "se respondio a alarma en {component}, se encontro {env}, se corrigio y verifico operacion",
    "reparacion correctiva en {component}: se reemplazo {part}, probado bajo carga, {env}",
]
_ENV_PHRASES_EN = [
    "elevated ambient heat",
    "recent coastal salt exposure",
    "post-storm inspection",
    "normal operating conditions",
    "high humidity conditions",
    "dust accumulation noted",
]
_ENV_PHRASES_ES = [
    "calor ambiental elevado",
    "exposicion reciente a sal costera",
    "inspeccion post-tormenta",
    "condiciones normales de operacion",
    "condiciones de alta humedad",
    "acumulacion de polvo notada",
]


def _cost_for(rng: np.random.Generator, wo_type: str) -> float:
    if wo_type == "preventive":
        return round(float(rng.uniform(100, 400)), 2)
    if wo_type == "corrective":
        return round(float(rng.uniform(300, 1200)), 2)
    return round(float(rng.uniform(800, 3000)), 2)  # emergency


def _downtime_for(rng: np.random.Generator, wo_type: str) -> float:
    if wo_type == "preventive":
        return round(float(rng.uniform(0, 30)), 1) if rng.random() < 0.2 else 0.0
    if wo_type == "corrective":
        return round(float(rng.uniform(20, 240)), 1)
    return round(float(rng.uniform(60, 720)), 1)  # emergency


def _random_note(
    rng: np.random.Generator, component: str, part: str, fault_type: str | None
) -> tuple[str, str]:
    """Returns (text, language). ~55% Spanish, ~45% English, matching a
    bilingual field workforce.
    """
    language = "es" if rng.random() < 0.55 else "en"
    if fault_type is not None:
        root_cause = _ROOT_CAUSE_ES[fault_type] if language == "es" else _ROOT_CAUSE_EN[fault_type]
        template = (
            "trabajo de resolucion: {root_cause}. se reemplazo {part} en {component}. verificado operacional."
            if language == "es"
            else "resolution work: {root_cause}. replaced {part} on {component}. verified operational."
        )
        return template.format(
            root_cause=root_cause, part=part, component=component.replace("_", " ")
        ), language

    env = str(rng.choice(_ENV_PHRASES_ES if language == "es" else _ENV_PHRASES_EN))
    template = str(rng.choice(_GENERIC_NOTES_ES if language == "es" else _GENERIC_NOTES_EN))
    text = template.format(component=component.replace("_", " "), part=part, env=env)
    return text, language


def generate_work_order_history(
    seed: int,
    sites: pd.DataFrame,
    assets: pd.DataFrame,
    faults: pd.DataFrame,
    reference_date: date,
    work_order_months: int,
    target_count: int = 10_000,
) -> pd.DataFrame:
    window_end = datetime(
        reference_date.year, reference_date.month, reference_date.day, tzinfo=UTC
    ) + timedelta(days=1)
    window_start = window_end - timedelta(days=work_order_months * 30)

    assets_indexed = assets.reset_index(drop=True)
    rows: list[dict] = []
    rng_global = stream(seed, "work_orders_global")

    n_background = max(0, target_count - len(faults))
    asset_choice_idx = rng_global.integers(0, len(assets_indexed), size=n_background)
    for i in range(n_background):
        asset_row = assets_indexed.iloc[int(asset_choice_idx[i])]
        wo_id = f"WO-{i:06d}"
        rng = stream(seed, "wo", wo_id)
        wo_type = str(rng.choice(WORK_ORDER_TYPES, p=[0.55, 0.35, 0.10]))
        status = str(rng.choice(WORK_ORDER_STATUSES))
        span_seconds = (window_end - window_start).total_seconds()
        opened = window_start + timedelta(seconds=float(rng.uniform(0, span_seconds)))
        duration_hours = float(rng.uniform(0.5, 6)) if wo_type != "emergency" else float(rng.uniform(1, 24))
        closed = opened + timedelta(hours=duration_hours) if status == "completed" else None
        part = str(rng.choice(PARTS_BY_COMPONENT.get(asset_row["component"], ["generic_part"])))
        notes_text, notes_lang = _random_note(rng, asset_row["component"], part, fault_type=None)
        technician = str(rng.choice(TECHNICIAN_NAMES))
        rows.append(
            {
                "wo_id": wo_id,
                "site_id": asset_row["site_id"],
                "asset_id": asset_row["asset_id"],
                "component": asset_row["component"],
                "wo_type": wo_type,
                "status": status,
                "opened_ts_utc": opened,
                "closed_ts_utc": closed,
                "downtime_minutes": _downtime_for(rng, wo_type) if status == "completed" else None,
                "cost_usd": _cost_for(rng, wo_type),
                "parts_used": [part] if rng.random() < 0.7 else [],
                "technician_hash": hash_technician(seed, technician),
                "notes_raw_text": notes_text,
                "notes_language": notes_lang,
            }
        )

    for fault in faults.itertuples():
        rng = stream(seed, "wo_fault", fault.fault_id)
        part = str(rng.choice(PARTS_BY_COMPONENT.get(fault.component, ["generic_part"])))
        notes_text, notes_lang = _random_note(rng, fault.component, part, fault_type=fault.fault_type)
        technician = str(rng.choice(TECHNICIAN_NAMES))
        downtime = _downtime_for(rng, "emergency" if fault.fault_type != "hvac_degradation" else "corrective")
        rows.append(
            {
                "wo_id": fault.resolving_wo_id,
                "site_id": fault.site_id,
                "asset_id": fault.asset_id,
                "component": fault.component,
                "wo_type": "emergency" if fault.fault_type != "hvac_degradation" else "corrective",
                "status": "completed",
                "opened_ts_utc": fault.detection_deadline_ts_utc,
                "closed_ts_utc": fault.resolution_ts_utc,
                "downtime_minutes": downtime,
                "cost_usd": _cost_for(rng, "emergency"),
                "parts_used": [part],
                "technician_hash": hash_technician(seed, technician),
                "notes_raw_text": notes_text,
                "notes_language": notes_lang,
            }
        )

    df = pd.DataFrame(rows)
    df["opened_ts_utc"] = pd.to_datetime(df["opened_ts_utc"], utc=True)
    df["closed_ts_utc"] = pd.to_datetime(df["closed_ts_utc"], utc=True)
    return df
