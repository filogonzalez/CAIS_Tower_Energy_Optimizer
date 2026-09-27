"""Train component-level 14-day corrective/emergency failure risk."""

from __future__ import annotations

import argparse

import mlflow
import pandas as pd
from config.settings import get_settings
from mlflow import MlflowClient
from mlflow.models import infer_signature
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score
from validation.spark import get_spark

from ml.features import FAILURE_FEATURES, temporal_split


def train_failure_model(frame: pd.DataFrame, experiment_name: str | None = None) -> dict:
    eligible = frame[frame["has_complete_14d_label"] == 1].dropna(
        subset=FAILURE_FEATURES + ["failure_within_14d"]
    )
    train, validation = temporal_split(eligible, "feature_ts_utc", label_horizon_days=14)
    model = HistGradientBoostingClassifier(random_state=42, max_iter=150, max_leaf_nodes=16)
    model.fit(train[FAILURE_FEATURES], train["failure_within_14d"])
    probability = model.predict_proba(validation[FAILURE_FEATURES])[:, 1]
    predicted = probability >= 0.5
    precision, recall, f1, _ = precision_recall_fscore_support(
        validation["failure_within_14d"], predicted, average="binary", zero_division=0
    )
    metrics = {
        "roc_auc": float(roc_auc_score(validation["failure_within_14d"], probability)),
        "average_precision": float(average_precision_score(validation["failure_within_14d"], probability)),
        "precision_at_0_5": float(precision),
        "recall_at_0_5": float(recall),
        "f1_at_0_5": float(f1),
        "training_rows": int(len(train)),
        "validation_rows": int(len(validation)),
        "positive_labels": int(eligible["failure_within_14d"].sum()),
    }
    if experiment_name:
        mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name="failure-risk-14d") as run:
        mlflow.log_metrics(metrics)
        mlflow.log_params({"feature_version": "v1", "label_horizon_days": 14, "purge_days": 14})
        mlflow.sklearn.log_model(
            model,
            "failure_risk",
            signature=infer_signature(
                train[FAILURE_FEATURES], model.predict_proba(train[FAILURE_FEATURES])[:, 1]
            ),
            input_example=train[FAILURE_FEATURES].head(5),
        )
        metrics["run_id"] = run.info.run_id
    return {"model": model, "metrics": metrics}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-table")
    args = parser.parse_args()
    settings = get_settings()
    spark = get_spark()
    table = args.input_table or settings.table_ml("training_failure_features")
    result = train_failure_model(
        spark.table(table).toPandas(), f"/{settings.bundle_name}/{settings.target}/failure"
    )  # type: ignore[name-defined]
    if result["metrics"]["positive_labels"] <= 0 or result["metrics"]["average_precision"] <= 0:
        raise RuntimeError("Failure-risk validation gate failed; refusing champion promotion")
    mlflow.set_registry_uri("databricks-uc")
    model_name = settings.table_ml("failure_risk")
    registered = mlflow.register_model(f"runs:/{result['metrics']['run_id']}/failure_risk", model_name)
    MlflowClient().set_registered_model_alias(model_name, "champion", registered.version)
    print(result["metrics"])


if __name__ == "__main__":
    main()
