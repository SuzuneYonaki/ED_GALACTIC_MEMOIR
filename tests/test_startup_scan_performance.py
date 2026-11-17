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
