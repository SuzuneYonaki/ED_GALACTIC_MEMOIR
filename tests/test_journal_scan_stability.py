import sqlite3
from pathlib import Path
from app.db.database import init_db
from app.parser.journal_parser import JournalParser


def test_parse_all_journals_retries_on_db_lock(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    parser = JournalParser(db_conn=conn)

    # Create 3 dummy journal files
    for idx in range(1, 4):
        f = tmp_path / f"Journal.2026-11-20T00000{idx}.01.log"
        f.write_text(
            f'{{"timestamp":"2026-11-20T00:00:0{idx}Z","event":"Location","StarSystem":"Sys{idx}","SystemAddress":{1000+idx},"StarPos":[0,0,0]}}\n',
            encoding="utf-8",
        )

    orig_parse = parser.parse_file
    attempts = {"file2": 0}

    def flaky_parse(filepath, progress_callback=None):
        if "000002" in str(filepath):
            attempts["file2"] += 1
            if attempts["file2"] <= 2:
                raise sqlite3.OperationalError("database is locked")
        return orig_parse(filepath, progress_callback=progress_callback)

    parser.parse_file = flaky_parse
    count = parser.parse_all_journals(str(tmp_path))

    assert count == 3
    assert attempts["file2"] == 3
    rows = conn.execute("SELECT star_system FROM systems ORDER BY system_address").fetchall()
    assert [r[0] for r in rows] == ["Sys1", "Sys2", "Sys3"]


def test_parse_all_journals_continues_after_single_file_error(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    parser = JournalParser(db_conn=conn)

    for idx in range(1, 4):
        f = tmp_path / f"Journal.2026-11-20T00000{idx}.01.log"
        f.write_text(
            f'{{"timestamp":"2026-11-20T00:00:0{idx}Z","event":"Location","StarSystem":"Sys{idx}","SystemAddress":{2000+idx},"StarPos":[0,0,0]}}\n',
            encoding="utf-8",
        )

    orig_parse = parser.parse_file

    def error_on_second(filepath, progress_callback=None):
        if "000002" in str(filepath):
            raise RuntimeError("corrupted file simulation")
        return orig_parse(filepath, progress_callback=progress_callback)

    parser.parse_file = error_on_second
    count = parser.parse_all_journals(str(tmp_path))

    assert count == 3
    rows = conn.execute("SELECT star_system FROM systems ORDER BY system_address").fetchall()
    assert [r[0] for r in rows] == ["Sys1", "Sys3"]


def test_force_rescan_ui_and_error_reporting():
    modals = Path("app/ui/components/modals.html").read_text(encoding="utf-8")
    assert 'id="btn-modal-force-rescan"' in modals

    app_js = Path("app/ui/js/app.js").read_text(encoding="utf-8")
    assert "/api/scan_now?force=true" in app_js
    assert "scan_error_title" in app_js

    i18n_js = Path("app/ui/js/i18n.js").read_text(encoding="utf-8")
    for key in ("btn_modal_force_rescan", "confirm_force_rescan", "scan_error_title"):
        assert i18n_js.count(f"{key}:") == 2


def test_parse_all_journals_chunk_rollback_and_retry(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    parser = JournalParser(db_conn=conn)

    for idx in range(1, 5):
        f = tmp_path / f"Journal.2026-11-24T00000{idx}.01.log"
        f.write_text(
            f'{{"timestamp":"2026-11-24T00:00:0{idx}Z","event":"FSDJump","StarSystem":"ChunkSys{idx}","SystemAddress":{3000+idx},"StarPos":[{idx},0,0]}}\n',
            encoding="utf-8",
        )

    orig_parse = parser.parse_file
    state = {"file2_calls": 0}

    def flaky_second(filepath, progress_callback=None):
        if "000002" in str(filepath):
            state["file2_calls"] += 1
            if state["file2_calls"] == 1:
                raise sqlite3.OperationalError("database is locked")
        return orig_parse(filepath, progress_callback=progress_callback)

    parser.parse_file = flaky_second
    count = parser.parse_all_journals(str(tmp_path), chunk_size=2)

    assert count == 4
    assert state["file2_calls"] == 2
    rows = conn.execute("SELECT star_system, visit_count FROM systems ORDER BY system_address").fetchall()
    # visit_count must be 1 (no double-counting from chunk rollback & retry)
    assert [(r[0], r[1]) for r in rows] == [
        ("ChunkSys1", 1),
        ("ChunkSys2", 1),
        ("ChunkSys3", 1),
        ("ChunkSys4", 1),
    ]
