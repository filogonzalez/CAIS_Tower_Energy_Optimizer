#!/usr/bin/env bash
# Build a wheel for the Databricks Asset Bundle artifact.
#
# Invokes the PEP 517 build backend (setuptools.build_meta) directly instead
# of the `build` PyPI frontend (which would run with --wheel --no-isolation).
# That frontend fails in the Databricks bundle deployment environment because:
#
#   1. The system Python may not have the `build` package installed (no pip).
#   2. A local build/ directory (setuptools artifacts from a prior build) is
#      picked up as a namespace package, shadowing the real `build` module
#      which then has no __main__ and cannot be executed via `python -m`.
#
# This script only needs setuptools + wheel, which pyproject.toml's
# [build-system] already declares for no-isolation builds.
set -euo pipefail

rm -rf build dist
python -c "from setuptools.build_meta import build_wheel; build_wheel('dist')"
