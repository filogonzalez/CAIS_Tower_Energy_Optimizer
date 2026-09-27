from datetime import UTC, datetime

from common.timeutils import format_pr_display, puerto_rico_date


def test_utc_to_ast_date_boundary():
    timestamp = datetime(2026, 9, 27, 2, 0, tzinfo=UTC)
    assert puerto_rico_date(timestamp).isoformat() == "2026-09-26"
    assert "AST" in format_pr_display(timestamp)
