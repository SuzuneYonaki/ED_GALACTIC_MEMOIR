"""
User Data Backup Service (Export / Import)
Handles portable JSON export and import of user-created data that cannot be
reconstructed from Elite Dangerous journal logs:
- body_bookmarks (bookmarks, aliases, markdown notes)
- surface_mining_sites (planetary mining coordinates, minerals, notes)
- systems.shared_notes (system-level shared/memo notes)
"""
from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List, Set

from app.config import APP_VERSION
from app.services.search_service import safe_sync_system_search_index

USER_DATA_FORMAT = "ed_galactic_memoir_user_data"
USER_DATA_SCHEMA_VERSION = 1
MAX_IMPORT_ITEMS_PER_SECTION = 50000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(val: Any, max_len: int = 100000) -> str:
    if val is None:
        return ""
    s = str(val)
    return s[:max_len] if len(s) > max_len else s


def export_user_data(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Exports all user-created bookmarks, notes, and mining sites as a portable dict."""
    cur = conn.cursor()

    # 1. Bookmarks & body notes
    cur.execute("""
        SELECT system_address, body_id, body_name, star_system,
               alias_name, note_markdown, created_at, updated_at
        FROM body_bookmarks
        ORDER BY updated_at DESC, id ASC
    """)
    bookmarks = [
        {
            "system_address": int(r[0]),
            "body_id": int(r[1]),
            "body_name": r[2] or "",
            "star_system": r[3] or "",
            "alias_name": r[4] or "",
            "note_markdown": r[5] or "",
            "created_at": r[6] or "",
            "updated_at": r[7] or "",
        }
        for r in cur.fetchall()
    ]

    # 2. Surface mining sites
    cur.execute("""
        SELECT system_address, star_system, body_id, body_name,
               latitude, longitude, hotspot, minerals, note, created_at, updated_at
        FROM surface_mining_sites
        ORDER BY updated_at DESC, id ASC
    """)
    mining_sites = [
        {
            "system_address": int(r[0]),
            "star_system": r[1] or "",
            "body_id": int(r[2]) if r[2] is not None else None,
            "body_name": r[3] or "",
            "latitude": float(r[4]),
            "longitude": float(r[5]),
            "hotspot": r[6] or "",
            "minerals": r[7] or "",
            "note": r[8] or "",
            "created_at": r[9] or "",
            "updated_at": r[10] or "",
        }
        for r in cur.fetchall()
    ]

    # 3. System-level notes (non-empty shared_notes)
    cur.execute("""
        SELECT system_address, star_system, shared_notes
        FROM systems
        WHERE shared_notes IS NOT NULL AND TRIM(shared_notes) != ''
        ORDER BY star_system ASC
    """)
    system_notes = [
        {
            "system_address": int(r[0]),
            "star_system": r[1] or "",
            "shared_notes": r[2] or "",
        }
        for r in cur.fetchall()
    ]

    return {
        "format": USER_DATA_FORMAT,
        "schema_version": USER_DATA_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "exported_at": _now_iso(),
        "bookmarks": bookmarks,
        "mining_sites": mining_sites,
        "system_notes": system_notes,
    }


def _import_bookmarks(
    cur: sqlite3.Cursor,
    items: List[Any],
    conflict_mode: str,
    modified_systems: Set[int],
) -> Dict[str, int]:
    stats = {"added": 0, "updated": 0, "skipped": 0}
    now = _now_iso()

    for raw in items[:MAX_IMPORT_ITEMS_PER_SECTION]:
        if not isinstance(raw, dict):
            stats["skipped"] += 1
            continue
        try:
            sys_addr = int(raw["system_address"])
            body_id = int(raw["body_id"])
        except (KeyError, TypeError, ValueError):
            stats["skipped"] += 1
            continue

        body_name = _safe_str(raw.get("body_name"), 500)
        star_system = _safe_str(raw.get("star_system"), 500)
        if not body_name or not star_system:
            stats["skipped"] += 1
            continue

        alias_name = _safe_str(raw.get("alias_name"), 500)
        note_markdown = _safe_str(raw.get("note_markdown"), 200000)
        created_at = _safe_str(raw.get("created_at"), 64) or now
        updated_at = _safe_str(raw.get("updated_at"), 64) or now

        cur.execute(
            "SELECT id FROM body_bookmarks WHERE system_address = ? AND body_id = ?",
            (sys_addr, body_id),
        )
        existing = cur.fetchone()

        if existing:
            if conflict_mode == "overwrite":
                cur.execute(
                    """
                    UPDATE body_bookmarks
                    SET body_name = ?, star_system = ?, alias_name = ?,
                        note_markdown = ?, updated_at = ?
                    WHERE system_address = ? AND body_id = ?
                    """,
                    (body_name, star_system, alias_name, note_markdown, updated_at, sys_addr, body_id),
                )
                stats["updated"] += 1
                modified_systems.add(sys_addr)
            else:
                stats["skipped"] += 1
        else:
            cur.execute(
                """
                INSERT INTO body_bookmarks (
                    system_address, body_id, body_name, star_system,
                    alias_name, note_markdown, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (sys_addr, body_id, body_name, star_system, alias_name, note_markdown, created_at, updated_at),
            )
            stats["added"] += 1
            modified_systems.add(sys_addr)

    return stats


def _import_mining_sites(
    cur: sqlite3.Cursor,
    items: List[Any],
    conflict_mode: str,
    modified_systems: Set[int],
) -> Dict[str, int]:
    stats = {"added": 0, "updated": 0, "skipped": 0}
    now = _now_iso()

    for raw in items[:MAX_IMPORT_ITEMS_PER_SECTION]:
        if not isinstance(raw, dict):
            stats["skipped"] += 1
            continue
        try:
            sys_addr = int(raw["system_address"])
            lat = float(raw["latitude"])
            lon = float(raw["longitude"])
        except (KeyError, TypeError, ValueError):
            stats["skipped"] += 1
            continue

        body_id = None
        if raw.get("body_id") is not None:
            try:
                body_id = int(raw["body_id"])
            except (TypeError, ValueError):
                stats["skipped"] += 1
                continue

        star_system = _safe_str(raw.get("star_system"), 500)
        body_name = _safe_str(raw.get("body_name"), 500)
        hotspot = _safe_str(raw.get("hotspot"), 500)
        minerals = _safe_str(raw.get("minerals"), 2000)
        note = _safe_str(raw.get("note"), 50000)
        created_at = _safe_str(raw.get("created_at"), 64) or now
        updated_at = _safe_str(raw.get("updated_at"), 64) or now

        # Match existing site by coordinates (tolerance ~1e-4 deg) & body
        cur.execute(
            """
            SELECT id FROM surface_mining_sites
            WHERE system_address = ?
              AND COALESCE(body_id, -1) = COALESCE(?, -1)
              AND ABS(latitude - ?) < 0.0001
              AND ABS(longitude - ?) < 0.0001
              AND minerals = ?
            LIMIT 1
            """,
            (sys_addr, body_id, lat, lon, minerals),
        )
        existing = cur.fetchone()

        if existing:
            if conflict_mode == "overwrite":
                cur.execute(
                    """
                    UPDATE surface_mining_sites
                    SET star_system = ?, body_name = ?, hotspot = ?, note = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (star_system, body_name, hotspot, note, updated_at, existing[0]),
                )
                stats["updated"] += 1
                modified_systems.add(sys_addr)
            else:
                stats["skipped"] += 1
        else:
            cur.execute(
                """
                INSERT INTO surface_mining_sites (
                    system_address, star_system, body_id, body_name,
                    latitude, longitude, hotspot, minerals, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (sys_addr, star_system, body_id, body_name, lat, lon, hotspot, minerals, note, created_at, updated_at),
            )
            stats["added"] += 1
            modified_systems.add(sys_addr)

    return stats


def _import_system_notes(
    cur: sqlite3.Cursor,
    items: List[Any],
    conflict_mode: str,
    modified_systems: Set[int],
) -> Dict[str, int]:
    stats = {"updated": 0, "skipped": 0}

    for raw in items[:MAX_IMPORT_ITEMS_PER_SECTION]:
        if not isinstance(raw, dict):
            stats["skipped"] += 1
            continue
        try:
            sys_addr = int(raw["system_address"])
        except (KeyError, TypeError, ValueError):
            stats["skipped"] += 1
            continue

        note_text = _safe_str(raw.get("shared_notes"), 100000).strip()
        if not note_text:
            stats["skipped"] += 1
            continue

        cur.execute("SELECT shared_notes FROM systems WHERE system_address = ?", (sys_addr,))
        row = cur.fetchone()
        if not row:
            # System does not exist in this local DB yet
            stats["skipped"] += 1
            continue

        existing_note = (row[0] or "").strip()
        if existing_note and conflict_mode != "overwrite":
            stats["skipped"] += 1
            continue

        cur.execute(
            "UPDATE systems SET shared_notes = ? WHERE system_address = ?",
            (note_text, sys_addr),
        )
        stats["updated"] += 1
        modified_systems.add(sys_addr)

    return stats


def import_user_data(
    conn: sqlite3.Connection,
    payload: Dict[str, Any],
    conflict_mode: str = "skip",
) -> Dict[str, Any]:
    """
    Imports user data from a previously exported JSON dict.
    conflict_mode: 'skip' (keep existing records) or 'overwrite' (replace matching records).
    """
    if not isinstance(payload, dict):
        raise ValueError("Invalid backup payload: expected JSON object")

    fmt = payload.get("format")
    if fmt != USER_DATA_FORMAT:
        raise ValueError(f"Unsupported backup format: {fmt!r}")

    version = payload.get("schema_version")
    if version != USER_DATA_SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {version!r}")

    mode = "overwrite" if conflict_mode == "overwrite" else "skip"
    bookmarks_list = payload.get("bookmarks") or []
    mining_list = payload.get("mining_sites") or []
    notes_list = payload.get("system_notes") or []

    if not isinstance(bookmarks_list, list) or not isinstance(mining_list, list) or not isinstance(notes_list, list):
        raise ValueError("Invalid backup structure: sections must be lists")

    cur = conn.cursor()
    modified_systems: Set[int] = set()

    bm_stats = _import_bookmarks(cur, bookmarks_list, mode, modified_systems)
    mining_stats = _import_mining_sites(cur, mining_list, mode, modified_systems)
    notes_stats = _import_system_notes(cur, notes_list, mode, modified_systems)

    conn.commit()

    # Sync full-text search index for modified systems
    for sys_addr in modified_systems:
        safe_sync_system_search_index(conn, sys_addr)

    return {
        "status": "ok",
        "conflict_mode": mode,
        "bookmarks": bm_stats,
        "mining_sites": mining_stats,
        "system_notes": notes_stats,
    }
