import sqlite3
import pytest
from app.db.database import init_db
from app.parser.journal_parser import JournalParser
from app.services.search_service import ensure_search_index, safe_sync_system_search_index


def test_modified_system_addresses_tracking():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    parser = JournalParser(db_conn=conn)

    assert hasattr(parser, "modified_system_addresses")
    assert len(parser.modified_system_addresses) == 0

    # Simulate Location line
    location_line = '{"timestamp":"2026-11-17T12:00:00Z","event":"Location","StarSystem":"Sol","SystemAddress":10477373803,"StarPos":[0.0,0.0,0.0]}'
    parser.process_journal_line(location_line)
    parser.flush_dirty_systems()

    assert 10477373803 in parser.modified_system_addresses


def test_incremental_search_index_startup_flow():
    conn = sqlite3.connect(":memory:")
    init_db(conn)

    # 1. Insert a system
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO systems (system_address, star_system, visit_count) VALUES (?, ?, ?)",
        (1001, "Colonia", 1)
    )
    conn.commit()

    # Initial state: search_documents is empty
    count = cur.execute("SELECT COUNT(*) FROM search_documents").fetchone()[0]
    assert count == 0

    # First run: ensure_search_index builds index
    ensure_search_index(conn)
    count = cur.execute("SELECT COUNT(*) FROM search_documents").fetchone()[0]
    assert count > 0

    # Second run without changes: ensure_search_index does not rebuild
    # Verify by checking doc count remains valid
    ensure_search_index(conn)
    count2 = cur.execute("SELECT COUNT(*) FROM search_documents").fetchone()[0]
    assert count2 == count

    # Incremental update on modified system:
    safe_sync_system_search_index(conn, 1001)
    count3 = cur.execute("SELECT COUNT(*) FROM search_documents").fetchone()[0]
    assert count3 == count


def test_rebuild_search_index_restores_fts_triggers_and_searches():
    from pathlib import Path
    from app.services.search_service import rebuild_search_index, search_fulltext

    conn = sqlite3.connect(":memory:")
    init_db(conn)
    cur = conn.cursor()
    cur.execute("INSERT INTO systems (system_address, star_system, visit_count) VALUES (?, ?, ?)", (5001, "Beagle Point", 1))
    cur.execute("INSERT INTO bodies (system_address, body_name, body_id, planet_class) VALUES (?, ?, ?, ?)", (5001, "Beagle Point 2", 2, "Earthlike body"))
    conn.commit()

    count = rebuild_search_index(conn)
    assert count >= 2

    # Check triggers restored
    trigs = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='search_documents'"
    ).fetchall()
    trig_names = {r[0] for r in trigs}
    assert {"search_docs_ai", "search_docs_ad", "search_docs_au"}.issubset(trig_names)

    # Check search works
    res = search_fulltext(conn, "Beagle")
    assert res["total"] >= 1

    # Check api.py sets 99% while updating search index
    api_text = Path("app/server/api.py").read_text(encoding="utf-8")
    assert 'scan_state["percent"] = 99' in api_text
