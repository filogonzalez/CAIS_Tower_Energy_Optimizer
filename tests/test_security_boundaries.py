import re
from pathlib import Path

from mock_data.schemas import ALL_BRONZE_SCHEMAS


def test_ground_truth_absent_from_serving_surfaces():
    assert "injected_faults" not in ALL_BRONZE_SCHEMAS
    files = [
        Path("src/agent/uc_tools.sql"),
        Path("src/genie/trusted_assets.sql"),
        Path("src/vector_search/create_index.py"),
        Path("src/app/db.py"),
    ]
    for path in files:
        assert "injected_faults" not in path.read_text(encoding="utf-8")


def test_no_secret_literals_committed():
    token_pattern = re.compile(r"dapi[a-z0-9]{20,}", re.IGNORECASE)
    assignment_pattern = re.compile(
        r"(?:token|password|client_secret)\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE
    )
    for path in Path("src").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".sql", ".yml", ".yaml"}:
            text = path.read_text(encoding="utf-8")
            assert token_pattern.search(text) is None, path
            assert assignment_pattern.search(text) is None, path
