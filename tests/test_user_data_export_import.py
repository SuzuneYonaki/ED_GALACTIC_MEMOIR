import sqlite3
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.db.database import init_db
from app.services.user_data_service import (
    USER_DATA_FORMAT,
    USER_DATA_SCHEMA_VERSION,
    export_user_data,
    import_user_data,
)
from app.services.search_service import search_fulltext


def _setup_in_memory_db():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


def test_export_and_import_skip_and_overwrite():
    src_conn = _setup_in_memory_db()
    now = datetime.now(timezone.utc).isoformat()
    cur = src_conn.cursor()

    # Seed source DB
    cur.execute(
        "INSERT INTO systems (system_address, star_system, visit_count, shared_notes) VALUES (?, ?, ?, ?)",
        (1001, "Sol", 5, "Home system memo"),
    )
    cur.execute(
        """
        INSERT INTO body_bookmarks (
            system_address, body_id, body_name, star_system,
            alias_name, note_markdown, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (1001, 3, "Earth", "Sol", "Homeworld", "Nice blue marble", now, now),
    )
    cur.execute(
        """
        INSERT INTO surface_mining_sites (
            system_address, star_system, body_id, body_name,
            latitude, longitude, hotspot, minerals, note, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (1001, "Sol", 4, "Moon", 10.5, -20.25, "Platinum", "Platinum, Gold", "Rich spot", now, now),
    )
    src_conn.commit()

    exported = export_user_data(src_conn)
    assert exported["format"] == USER_DATA_FORMAT
    assert exported["schema_version"] == USER_DATA_SCHEMA_VERSION
    assert len(exported["bookmarks"]) == 1
    assert len(exported["mining_sites"]) == 1
    assert len(exported["system_notes"]) == 1

    # Import into fresh DB that already has Sol (with different notes)
    dst_conn = _setup_in_memory_db()
    dcur = dst_conn.cursor()
    dcur.execute(
        "INSERT INTO systems (system_address, star_system, visit_count, shared_notes) VALUES (?, ?, ?, ?)",
        (1001, "Sol", 1, "Existing note"),
    )
    dcur.execute(
        """
        INSERT INTO body_bookmarks (
            system_address, body_id, body_name, star_system,
            alias_name, note_markdown, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (1001, 3, "Earth", "Sol", "OldAlias", "OldNote", now, now),
    )
    dst_conn.commit()

    # 1. Test conflict_mode = 'skip'
    res_skip = import_user_data(dst_conn, exported, conflict_mode="skip")
    assert res_skip["bookmarks"] == {"added": 0, "updated": 0, "skipped": 1}
    assert res_skip["mining_sites"] == {"added": 1, "updated": 0, "skipped": 0}
    assert res_skip["system_notes"] == {"updated": 0, "skipped": 1}

    # Verify old bookmark and note preserved
    row_bm = dcur.execute(
        "SELECT alias_name, note_markdown FROM body_bookmarks WHERE system_address = 1001 AND body_id = 3"
    ).fetchone()
    assert tuple(row_bm) == ("OldAlias", "OldNote")
    row_sys = dcur.execute("SELECT shared_notes FROM systems WHERE system_address = 1001").fetchone()
    assert row_sys[0] == "Existing note"

    # 2. Test conflict_mode = 'overwrite'
    res_ow = import_user_data(dst_conn, exported, conflict_mode="overwrite")
    assert res_ow["bookmarks"] == {"added": 0, "updated": 1, "skipped": 0}
    assert res_ow["mining_sites"] == {"added": 0, "updated": 1, "skipped": 0}
    assert res_ow["system_notes"] == {"updated": 1, "skipped": 0}

    row_bm2 = dcur.execute(
        "SELECT alias_name, note_markdown FROM body_bookmarks WHERE system_address = 1001 AND body_id = 3"
    ).fetchone()
    assert tuple(row_bm2) == ("Homeworld", "Nice blue marble")
    row_sys2 = dcur.execute("SELECT shared_notes FROM systems WHERE system_address = 1001").fetchone()
    assert row_sys2[0] == "Home system memo"

    # 3. Verify search index synced
    search_res = search_fulltext(dst_conn, "Homeworld")
    assert search_res["total"] >= 1


def test_import_validation_errors():
    conn = _setup_in_memory_db()
    with pytest.raises(ValueError):
        import_user_data(conn, {"format": "wrong_format", "schema_version": 1})
    with pytest.raises(ValueError):
        import_user_data(conn, {"format": USER_DATA_FORMAT, "schema_version": 999})


def test_user_data_api_endpoints(tmp_path, monkeypatch):
    from app.server import api as api_module

    test_db = tmp_path / "test_user_data.db"
    monkeypatch.setattr(api_module, "DB_PATH", test_db, raising=False)
    import app.db.database as db_module
    monkeypatch.setattr(db_module, "DB_PATH", test_db)

    conn = db_module.get_db_connection()
    db_module.init_db(conn)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO body_bookmarks (system_address, body_id, body_name, star_system, alias_name, note_markdown, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (2002, 1, "Colonia 1", "Colonia", "Base", "Colonia memo", now, now),
    )
    conn.commit()
    conn.close()

    client = TestClient(api_module.app, base_url="http://127.0.0.1:8000")

    # Export
    r_exp = client.get("/api/user_data/export")
    assert r_exp.status_code == 200
    assert "attachment;" in r_exp.headers.get("content-disposition", "")
    exported_json = r_exp.json()
    assert len(exported_json["bookmarks"]) == 1

    # Import into cleared DB
    conn2 = db_module.get_db_connection()
    conn2.execute("DELETE FROM body_bookmarks")
    conn2.commit()
    conn2.close()

    r_imp = client.post("/api/user_data/import", json={"data": exported_json, "conflict_mode": "skip"})
    assert r_imp.status_code == 200
    res_json = r_imp.json()
    assert res_json["bookmarks"]["added"] == 1

    # Invalid import
    r_bad = client.post("/api/user_data/import", json={"data": {"format": "bad"}, "conflict_mode": "skip"})
    assert r_bad.status_code == 400
