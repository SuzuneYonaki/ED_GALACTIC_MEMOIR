import sqlite3
from pathlib import Path
from app.db.database import init_db
from app.parser.journal_parser import JournalParser


def test_modified_system_addresses_tracking():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    parser = JournalParser(db_conn=conn)

    assert hasattr(parser, "modified_system_addresses")
    assert len(parser.modified_system_addresses) == 0

    location_line = '{"timestamp":"2026-11-17T12:00:00Z","event":"Location","StarSystem":"Sol","SystemAddress":10477373803,"StarPos":[0.0,0.0,0.0]}'
    parser.process_journal_line(location_line)
    parser.flush_dirty_systems()

    assert 10477373803 in parser.modified_system_addresses


def test_fulltext_search_removed_from_startup_scan_and_triggers():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    trigs = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='search_documents'"
    ).fetchall()
    assert len(trigs) == 0, "Legacy FTS5 triggers must be removed"

    api_text = Path("app/server/api.py").read_text(encoding="utf-8")
    assert "rebuild_search_index" not in api_text
    assert "ensure_search_index" not in api_text
    assert "safe_sync_system_search_index" not in api_text
