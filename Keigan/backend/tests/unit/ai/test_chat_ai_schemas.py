"""keigan/ai/chat_ai_schemas.py: the offline (mock) query writer must produce queries the validators accept as they are."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from keigan.ai.chat_ai_schemas import build_query_offline
from keigan.utils.query_safety import validate_generated_query


def test_offline_splunk_search_does_not_name_an_index_and_gets_the_index_of_the_log_source() -> None:
    generated = build_query_offline("spl", "app_service", wants_failures=True, wants_pattern=False, range_minutes=60)
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

    hardened = validate_generated_query("spl", generated.query_text, now - timedelta(hours=1), now, query_scope={"index": "payments_prod"})

    assert "index=*" not in generated.query_text
    assert hardened.query_text.startswith("search index=payments_prod ")
