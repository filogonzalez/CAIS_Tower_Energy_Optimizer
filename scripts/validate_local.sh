#!/usr/bin/env bash
set -euo pipefail

python -m compileall -q src tests
python -m pytest -q
python -m ruff check src tests
python -m mypy src/common src/config src/mock_data src/ml/features.py src/connect/resilience_simulator.py
