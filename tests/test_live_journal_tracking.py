import sqlite3
import tempfile
import os
import time
from pathlib import Path
from app.parser.journal_parser import JournalParser
from app.parser.watcher import JournalWatcher
from app.db.database import init_db

def test_live_dispatch_commits_before_event_callback():
    """
    Assert that when is_live=True, any event dispatched to event_callback has already
    been flushed and committed to the database, ensuring other DB connections see it immediately.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        # Initialize schema
        writer_conn = sqlite3.connect(str(db_path))
        writer_conn.row_factory = sqlite3.Row
        init_db(writer_conn, force=True)

        reader_conn = sqlite3.connect(str(db_path))
        reader_conn.row_factory = sqlite3.Row

        received_events = []

        def on_event(event_name, data):
            # In event callback (which triggers WebSocket to client):
            # Verify that reader_conn can immediately query the newly inserted system and bodies!
            sys_addr = data.get("SystemAddress")
            if event_name == "FSDJump":
                cur = reader_conn.cursor()
                cur.execute("SELECT star_system FROM systems WHERE system_address = ?", (sys_addr,))
                row = cur.fetchone()
                assert row is not None, f"Reader DB connection could not find system {sys_addr} at event dispatch time!"
                assert row["star_system"] == "Test System Prime"
            elif event_name == "Scan":
                cur = reader_conn.cursor()
                cur.execute("SELECT body_name FROM bodies WHERE system_address = ?", (sys_addr,))
                row = cur.fetchone()
                assert row is not None, f"Reader DB connection could not find scanned body for system {sys_addr}!"
                assert row["body_name"] == "Test Planet A"

            received_events.append((event_name, sys_addr))

        parser = JournalParser(db_conn=writer_conn, event_callback=on_event, is_live=True)

        # 1. Process FSDJump line
        jump_line = (
            '{"timestamp":"2026-11-17T06:00:00Z","event":"FSDJump","SystemAddress":99887766,'
            '"StarSystem":"Test System Prime","StarPos":[100.0, 20.0, -50.0],"SystemEconomy":"$economy_Agri;"}'
        )
        parser.process_journal_line(jump_line)

        # 2. Process Scan line
        scan_line = (
            '{"timestamp":"2026-11-17T06:01:00Z","event":"Scan","ScanType":"Detailed","SystemAddress":99887766,'
            '"BodyName":"Test Planet A","BodyID":1,"DistanceFromArrivalLS":120.5,"PlanetClass":"High metal content body"}'
        )
        parser.process_journal_line(scan_line)

        assert len(received_events) == 2
        assert received_events[0] == ("FSDJump", 99887766)
        assert received_events[1] == ("Scan", 99887766)

        writer_conn.close()
        reader_conn.close()

def test_watcher_detects_appended_lines():
    """
    Test that JournalWatcher captures appended lines and commits them in live mode.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_dir = Path(tmpdir) / "journals"
        journal_dir.mkdir()
        log_file = journal_dir / "Journal.2026-11-17T000000.01.log"

        # Create initial log with header
        log_file.write_text('{"timestamp":"2026-11-17T00:00:00Z","event":"Fileheader","part":1}\n', encoding="utf-8")

        events_caught = []
        def on_event(name, data):
            events_caught.append((name, data.get("SystemAddress")))

        watcher = JournalWatcher(
            journal_dirs=[journal_dir],
            interval=0.1,
            on_event_callback=on_event
        )

        watcher.start()
        try:
            # Wait for watcher to initialize
            time.sleep(0.3)

            # Append FSDJump line
            with open(log_file, "a", encoding="utf-8") as f:
                f.write('{"timestamp":"2026-11-17T00:05:00Z","event":"FSDJump","SystemAddress":11223344,"StarSystem":"Watcher Dest System","StarPos":[0,0,0]}\n')

            # Wait for watcher to pick up and process
            timeout = 3.0
            start = time.time()
            while time.time() - start < timeout:
                if any(e[0] == "FSDJump" and e[1] == 11223344 for e in events_caught):
                    break
                time.sleep(0.1)

            assert any(e[0] == "FSDJump" and e[1] == 11223344 for e in events_caught), (
                f"Watcher did not catch appended FSDJump within {timeout}s: {events_caught}"
            )
        finally:
            watcher.stop()
            watcher.join(timeout=2.0)
