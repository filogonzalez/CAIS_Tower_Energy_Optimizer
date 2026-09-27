#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <databricks-profile> [dev|demo]" >&2
  exit 2
fi

profile="$1"
target="${2:-dev}"

databricks bundle validate --strict -t "$target" --profile "$profile"
databricks bundle deploy -t "$target" --profile "$profile"

echo "Bundle deployed. Run acceptance in order:"
echo "  databricks bundle run generate_mock_data -t $target --profile $profile"
echo "  databricks bundle run energy_pipeline -t $target --profile $profile"
echo "  databricks bundle run train_models -t $target --profile $profile"
echo "  databricks bundle run deploy_agent -t $target --profile $profile"
echo "  databricks bundle run daily_refresh -t $target --profile $profile"
echo "  databricks bundle run run_simulator -t $target --profile $profile"
echo "  databricks bundle run setup_genie -t $target --profile $profile"
