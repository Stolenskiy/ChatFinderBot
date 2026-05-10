from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class KeywordAnalyticsCollector:
    def __init__(self, analytics_dir: str) -> None:
        self._analytics_dir = Path(analytics_dir)
        self._analytics_dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self._analytics_dir / "keyword_query_events.jsonl"
        self._summary_path = self._analytics_dir / "keyword_summary.json"

    def record_query_event(self, payload: dict) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with self._events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

        keyword = payload.get("keyword")
        if keyword:
            self._update_keyword_summary(keyword=keyword, payload=payload)

    def _update_keyword_summary(self, keyword: str, payload: dict) -> None:
        summary = self._load_summary()
        stats = summary.setdefault(
            keyword,
            {
                "keyword": keyword,
                "executions": 0,
                "raw_chat_total": 0,
                "accepted_hit_total": 0,
                "new_unique_hit_total": 0,
                "duplicate_hit_total": 0,
                "searches_with_new_hits": 0,
                "last_seen_at": None,
            },
        )

        stats["executions"] += 1
        stats["raw_chat_total"] += int(payload.get("raw_chat_count", 0))
        stats["accepted_hit_total"] += int(payload.get("accepted_hit_count", 0))
        stats["new_unique_hit_total"] += int(payload.get("new_unique_hit_count", 0))
        stats["duplicate_hit_total"] += int(payload.get("duplicate_hit_count", 0))
        if int(payload.get("new_unique_hit_count", 0)) > 0:
            stats["searches_with_new_hits"] += 1
        stats["last_seen_at"] = datetime.now(timezone.utc).isoformat()
        stats["avg_new_unique_hits"] = round(stats["new_unique_hit_total"] / stats["executions"], 4)
        stats["new_hit_rate"] = round(stats["searches_with_new_hits"] / stats["executions"], 4)

        with self._summary_path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)

    def _load_summary(self) -> dict:
        if not self._summary_path.exists():
            return {}
        with self._summary_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
