"""Traffic Monitor addon: opt-in EDSM Traffic API (EDDN aggregated) lookup & SQLite cache.

Disabled by default (enabled_by_default=false, requires_network=true) per v0.9.1
privacy & offline safety guarantees. Never performs outbound network requests
from GET cache endpoints or when disabled.
"""

import json
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.database import get_db_connection
from app.services.edsm.constants import REQUEST_DELAY_SEC, USER_AGENT

EDSM_TRAFFIC_API = "https://www.edsm.net/api-system-v1/traffic"

_rate_lock = threading.Lock()
_last_request_ts = 0.0


def ensure_traffic_table(conn: sqlite3.Connection) -> None:
    """Ensures the addon-local SQLite cache table exists without touching core schema migrations."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS system_traffic_cache (
            system_address INTEGER PRIMARY KEY,
            star_system TEXT NOT NULL,
            traffic_total INTEGER DEFAULT 0,
            traffic_week INTEGER DEFAULT 0,
            traffic_day INTEGER DEFAULT 0,
            breakdown_json TEXT,
            fetched_at TEXT
        )
        """
    )
    conn.commit()


def _normalize_breakdown(raw_breakdown: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_breakdown, dict):
        return []
    items: List[Dict[str, Any]] = []
    for ship_name, count_val in raw_breakdown.items():
        name = str(ship_name or "").strip()
        if not name:
            continue
        try:
            cnt = int(count_val)
        except (ValueError, TypeError):
            continue
        if cnt > 0:
            items.append({"ship": name, "count": cnt})
    items.sort(key=lambda x: (-x["count"], x["ship"]))
    return items[:20]


def get_cached_traffic(conn: sqlite3.Connection, system_address: int) -> Dict[str, Any]:
    """Reads cached traffic metrics for a star system purely from local SQLite."""
    ensure_traffic_table(conn)
    row = conn.execute(
        """
        SELECT system_address, star_system, traffic_total, traffic_week, traffic_day,
               breakdown_json, fetched_at
        FROM system_traffic_cache
        WHERE system_address = ?
        """,
        (system_address,),
    ).fetchone()
    if not row:
        return {"cached": False, "system_address": system_address}

    try:
        breakdown = json.loads(row["breakdown_json"]) if row["breakdown_json"] else []
        if not isinstance(breakdown, list):
            breakdown = []
    except Exception:
        breakdown = []

    return {
        "cached": True,
        "system_address": row["system_address"],
        "star_system": row["star_system"],
        "total": int(row["traffic_total"] or 0),
        "week": int(row["traffic_week"] or 0),
        "day": int(row["traffic_day"] or 0),
        "breakdown": breakdown,
        "fetched_at": row["fetched_at"],
    }


def _fetch_edsm_traffic_raw(star_system: str) -> Dict[str, Any]:
    global _last_request_ts
    with _rate_lock:
        elapsed = time.monotonic() - _last_request_ts
        if elapsed < REQUEST_DELAY_SEC:
            time.sleep(REQUEST_DELAY_SEC - elapsed)
        _last_request_ts = time.monotonic()

    resp = requests.get(
        EDSM_TRAFFIC_API,
        params={"systemName": star_system},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, dict) else {}


def sync_system_traffic(
    conn: sqlite3.Connection, system_address: int, star_system: str
) -> Dict[str, Any]:
    """Fetches EDSM Traffic stats for `star_system` and persists them in `system_traffic_cache`."""
    ensure_traffic_table(conn)
    try:
        data = _fetch_edsm_traffic_raw(star_system)
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "system_address": system_address,
            "star_system": star_system,
        }

    traffic_obj = data.get("traffic") if isinstance(data.get("traffic"), dict) else {}
    try:
        total = max(0, int(traffic_obj.get("total") or 0))
    except (ValueError, TypeError):
        total = 0
    try:
        week = max(0, int(traffic_obj.get("week") or 0))
    except (ValueError, TypeError):
        week = 0
    try:
        day = max(0, int(traffic_obj.get("day") or 0))
    except (ValueError, TypeError):
        day = 0

    breakdown = _normalize_breakdown(data.get("breakdown"))
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn.execute(
        """
        INSERT INTO system_traffic_cache (
            system_address, star_system, traffic_total, traffic_week, traffic_day,
            breakdown_json, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(system_address) DO UPDATE SET
            star_system = excluded.star_system,
            traffic_total = excluded.traffic_total,
            traffic_week = excluded.traffic_week,
            traffic_day = excluded.traffic_day,
            breakdown_json = excluded.breakdown_json,
            fetched_at = excluded.fetched_at
        """,
        (
            system_address,
            star_system,
            total,
            week,
            day,
            json.dumps(breakdown, ensure_ascii=False),
            fetched_at,
        ),
    )
    conn.commit()

    return {
        "status": "ok",
        "cached": True,
        "system_address": system_address,
        "star_system": star_system,
        "total": total,
        "week": week,
        "day": day,
        "breakdown": breakdown,
        "fetched_at": fetched_at,
    }


def register(ctx) -> None:
    router = APIRouter()

    @router.get("/systems/{system_address}/traffic")
    def get_system_traffic_cache(system_address: int):
        """Returns locally cached EDSM/EDDN traffic metrics (no outbound network calls)."""
        with closing(get_db_connection()) as conn:
            return JSONResponse(get_cached_traffic(conn, system_address))

    @router.post("/systems/{system_address}/traffic_sync")
    def sync_system_traffic_endpoint(system_address: int):
        """Manually fetches and caches EDSM Traffic stats for the specified system."""
        with closing(get_db_connection()) as conn:
            row = conn.execute(
                "SELECT star_system FROM systems WHERE system_address = ?",
                (system_address,),
            ).fetchone()
            if not row or not row["star_system"]:
                return JSONResponse({"error": "System not found"}, status_code=404)
            result = sync_system_traffic(conn, system_address, row["star_system"])
        status_code = 502 if result.get("status") == "error" else 200
        return JSONResponse(result, status_code=status_code)

    ctx.add_api_router(router, prefix="/api")
