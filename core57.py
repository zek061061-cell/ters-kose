"""Focused 57-league runtime helpers."""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).with_name("data")
CORE57_PATH = DATA_DIR / "riskbudur_57_catalog.json"


def load_core57() -> list[dict]:
    payload = json.loads(CORE57_PATH.read_text(encoding="utf-8"))
    return payload.get("leagues", [])


def core57_ids() -> set[str]:
    return {row["league_id"] for row in load_core57()}


def filter_coverage(report: dict) -> dict:
    ids = core57_ids()
    rows = [row for row in report.get("leagues", []) if row.get("league_id") in ids]
    return {
        "summary": {
            "leagues": len(rows),
            "ok_leagues": sum(row.get("status") == "OK" for row in rows),
            "historical_matches": sum(int(row.get("historical_matches") or 0) for row in rows),
            "future_matches": sum(int(row.get("future_matches") or 0) for row in rows),
            "with_history": sum(int(row.get("historical_matches") or 0) > 0 for row in rows),
            "with_future": sum(int(row.get("future_matches") or 0) > 0 for row in rows),
        },
        "leagues": rows,
    }
