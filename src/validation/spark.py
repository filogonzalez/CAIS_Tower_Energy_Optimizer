"""Spark session accessor that works in jobs and Databricks Connect."""

from pyspark.sql import SparkSession


def get_spark() -> SparkSession:
    return SparkSession.builder.getOrCreate()
