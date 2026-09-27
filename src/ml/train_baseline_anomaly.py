"""Train expected-energy regression and residual IsolationForest models."""

from __future__ import annotations

import argparse

import mlflow
import numpy as np
import pandas as pd
from config.settings import get_settings
from mlflow import MlflowClient
from mlflow.models import infer_signature
from sklearn.ensemble import GradientBoostingRegressor, IsolationForest
from sklearn.metrics import mean_absolute_error, r2_score
from validation.spark import get_spark

from ml.features import ANOMALY_FEATURES, BASELINE_FEATURES, temporal_split


def train_models(frame: pd.DataFrame, experiment_name: str | None = None) -> dict:
    healthy = frame[(frame["known_fault_window"] == 0) & (frame["served_load_kwh"].notna())].copy()
    train, validation = temporal_split(healthy, "ts_utc", label_horizon_days=1)
    baseline = GradientBoostingRegressor(random_state=42, n_estimators=120, max_depth=3)
    baseline.fit(train[BASELINE_FEATURES], train["served_load_kwh"])
    predictions = baseline.predict(validation[BASELINE_FEATURES])
    metrics = {
        "baseline_mae": float(mean_absolute_error(validation["served_load_kwh"], predictions)),
        "baseline_r2": float(r2_score(validation["served_load_kwh"], predictions)),
        "training_rows": int(len(train)),
        "validation_rows": int(len(validation)),
    }
    residual_std = max(
        float(np.std(train["served_load_kwh"] - baseline.predict(train[BASELINE_FEATURES]))), 1e-6
    )
    anomaly_training = frame.dropna(subset=ANOMALY_FEATURES)
    anomaly = IsolationForest(random_state=42, contamination=0.03, n_estimators=200)
    anomaly.fit(anomaly_training[ANOMALY_FEATURES])
    if experiment_name:
        mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name="energy-baseline-anomaly") as run:
        mlflow.log_metrics(metrics)
        mlflow.log_params({"feature_version": "v1", "random_seed": 42, "residual_std": residual_std})
        mlflow.sklearn.log_model(
            baseline,
            "energy_baseline",
            signature=infer_signature(train[BASELINE_FEATURES], baseline.predict(train[BASELINE_FEATURES])),
            input_example=train[BASELINE_FEATURES].head(5),
        )
        mlflow.sklearn.log_model(
            anomaly,
            "energy_anomaly",
            signature=infer_signature(
                anomaly_training[ANOMALY_FEATURES],
                anomaly.decision_function(anomaly_training[ANOMALY_FEATURES]),
            ),
            input_example=anomaly_training[ANOMALY_FEATURES].head(5),
        )
        metrics["run_id"] = run.info.run_id
    return {"baseline": baseline, "anomaly": anomaly, "metrics": metrics, "residual_std": residual_std}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-table")
    args = parser.parse_args()
    settings = get_settings()
    spark = get_spark()
    table = args.input_table or settings.table_ml("training_energy_features")
    frame = spark.table(table).toPandas()  # type: ignore[name-defined]
    result = train_models(frame, f"/{settings.bundle_name}/{settings.target}/energy")
    if result["metrics"]["baseline_r2"] < 0.5:
        raise RuntimeError("Baseline validation gate failed; refusing champion promotion")
    mlflow.set_registry_uri("databricks-uc")
    client = MlflowClient()
    baseline_name = settings.table_ml("energy_baseline")
    anomaly_name = settings.table_ml("energy_anomaly")
    baseline_version = mlflow.register_model(
        f"runs:/{result['metrics']['run_id']}/energy_baseline", baseline_name
    )
    anomaly_version = mlflow.register_model(
        f"runs:/{result['metrics']['run_id']}/energy_anomaly", anomaly_name
    )
    client.set_registered_model_alias(baseline_name, "champion", baseline_version.version)
    client.set_registered_model_alias(anomaly_name, "champion", anomaly_version.version)
    print(result["metrics"])


if __name__ == "__main__":
    main()
