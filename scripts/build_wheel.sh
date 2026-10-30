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
# [build-system] already declares for no-isolation builds. Bundle builds can
# run outside an activated virtualenv, so select an interpreter that actually
# has those backend dependencies instead of assuming `python` does.
set -euo pipefail

python_candidates=()
if [[ -n "${PYTHON:-}" ]]; then
  python_candidates+=("${PYTHON}")
fi
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  python_candidates+=("${VIRTUAL_ENV}/bin/python")
fi
python_candidates+=(".venv/bin/python" "python3" "python")

python_bin=""
for candidate in "${python_candidates[@]}"; do
  if command -v "${candidate}" >/dev/null 2>&1 \
    && "${candidate}" -c "import setuptools.build_meta, wheel" >/dev/null 2>&1; then
    python_bin="${candidate}"
    break
  fi
done

if [[ -z "${python_bin}" ]]; then
  echo "No Python interpreter with setuptools and wheel is available." >&2
  exit 1
fi

rm -rf build dist
"${python_bin}" -c "from setuptools.build_meta import build_wheel; build_wheel('dist')"
