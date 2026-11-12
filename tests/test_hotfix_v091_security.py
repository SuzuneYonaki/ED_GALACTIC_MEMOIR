import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.config as app_config
from app.db.database import get_db_connection
from app.parser.journal_parser import JournalParser
from app.server.api import app
from app.services.export_service import calculate_package_signature, generate_standalone_html
from app.services.tts_service import TTSService


@pytest.fixture
def client():
    return TestClient(app)


def test_cors_and_origin_enforcement_c1(client):
    r_ext = client.get("/api/check_update", headers={"Origin": "https://evil.example"})
    assert r_ext.headers.get("access-control-allow-origin") != "*"
    assert r_ext.headers.get("access-control-allow-origin") != "https://evil.example"
    assert r_ext.headers.get("access-control-allow-credentials") != "true"
    assert r_ext.headers.get("x-content-type-options") == "nosniff"
    assert r_ext.headers.get("x-frame-options") == "SAMEORIGIN"

    r_local = client.get("/api/check_update", headers={"Origin": "http://127.0.0.1:8686"})
    assert r_local.headers.get("access-control-allow-origin") == "http://127.0.0.1:8686"
    assert r_local.headers.get("access-control-allow-credentials") != "true"

    for bad_origin in ("https://evil.example", "null", "http://localhost.evil.example"):
        r_csrf_origin = client.post(
            "/api/app_settings",
            json={"language": "en"},
            headers={"Origin": bad_origin},
        )
        assert r_csrf_origin.status_code == 403

    r_csrf_referer = client.post(
        "/api/app_settings",
        json={"language": "en"},
        headers={"Referer": "https://evil.example/exploit.html"},
    )
    assert r_csrf_referer.status_code == 403


def test_host_header_dns_rebinding_blocked_c1b(client):
    r_bad_host = client.get("/api/check_update", headers={"Host": "attacker.example"})
    assert r_bad_host.status_code == 403

    r_bad_host_port = client.get("/api/systems", headers={"Host": "127.0.0.1.attacker.example:8686"})
    assert r_bad_host_port.status_code == 403

    r_good_host = client.get("/api/check_update", headers={"Host": "127.0.0.1:8686"})
    assert r_good_host.status_code == 200


def test_websocket_rejects_external_origin_c1(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/live", headers={"Origin": "https://evil.example"}):
            pass
    assert exc_info.value.code == 1008


def test_reveal_file_blocks_outside_allowed_dirs_m1(client):
    sys_root = os.environ.get("SystemRoot", str(Path("/etc")))
    target = str(Path(sys_root) / "System32" / "cmd.exe") if os.name == "nt" else "/etc/passwd"
    assert client.post("/api/system/reveal-file", json={"file_path": target}).status_code == 403

    # Path traversal out of EXPORTS_DIR must be rejected
    traversal = str(app_config.EXPORTS_DIR / ".." / ".." / "outside.txt")
    assert client.post("/api/system/reveal-file", json={"file_path": traversal}).status_code == 403

    # Allowed file inside EXPORTS_DIR invokes explorer with list args (shell=False)
    allowed_file = app_config.EXPORTS_DIR / "test_reveal_ok.txt"
    allowed_file.write_text("ok", encoding="utf-8")
    with patch("addons.export_share.addon.subprocess.Popen") as mock_popen:
        res = client.post("/api/system/reveal-file", json={"file_path": str(allowed_file)})
        assert res.status_code == 200
        assert mock_popen.call_count == 1
        args, kwargs = mock_popen.call_args
        assert isinstance(args[0], list)
        assert kwargs.get("shell") is False


def test_import_package_valid_succeeds_and_tampered_rejected_m2(client):
    sys_addr = 999888777111
    pkg = {
        "format": "ED_JOURNAL_ANALYZER_PACKAGE_V1",
        "metadata": {
            "version": "1.0",
            "cmdr_name": "ValidTester",
            "exported_at": "2026-01-01T00:00:00Z",
            "system_count": 1,
        },
        "systems": [
            {
                "system_address": sys_addr,
                "star_system": "Tamper Check System",
                "main_star_type": "G",
                "bodies": [
                    {
                        "body_id": 1,
                        "body_name": "Tamper Check System 1",
                        "planet_class": "Rocky body",
                        "atmosphere": "Thin Neon",
                    }
                ],
                "surface_mining": [],
                "bookmarks": [],
                "rings": [],
            }
        ],
    }
    pkg["signature"] = calculate_package_signature(pkg["systems"], pkg["metadata"]["cmdr_name"])

    # Untampered signed package imports cleanly (200)
    r_ok = client.post(
        "/api/import/package/execute",
        json={"package": pkg, "overwrite": True, "consent_token": True},
    )
    assert r_ok.status_code == 200, r_ok.text

    # Tampering star_system invalidates signature (400)
    tampered_sys = json.loads(json.dumps(pkg))
    tampered_sys["systems"][0]["star_system"] = "Evil Overwritten System"
    r_tamper_sys = client.post(
        "/api/import/package/execute",
        json={"package": tampered_sys, "overwrite": True, "consent_token": True},
    )
    assert r_tamper_sys.status_code == 400
    assert "改ざん" in r_tamper_sys.json()["error"] or "mismatch" in r_tamper_sys.json()["error"].lower()

    # Tampering secondary body field (atmosphere) ALSO invalidates checksum (400)
    tampered_atmo = json.loads(json.dumps(pkg))
    tampered_atmo["systems"][0]["bodies"][0]["atmosphere"] = "<img src=x onerror=alert(1)>"
    r_tamper_atmo = client.post(
        "/api/import/package/execute",
        json={"package": tampered_atmo, "overwrite": True, "consent_token": True},
    )
    assert r_tamper_atmo.status_code == 400
    assert "改ざん" in r_tamper_atmo.json()["error"] or "mismatch" in r_tamper_atmo.json()["error"].lower()


def test_standalone_html_tooltip_dom_xss_safe_b2():
    xss_breakout = '</SCRIPT ><img src=x onerror=window.__xss=1>'
    xss_attr = '<img src=x onerror=alert(1)>'
    sys_data = {
        "system_address": 123456,
        "star_system": f"Test {xss_breakout}",
        "main_star_type": "G",
        "star_pos_x": 0.0,
        "star_pos_y": 0.0,
        "star_pos_z": 0.0,
    }
    bodies = [
        {
            "body_id": 0,
            "body_name": f"Star {xss_breakout}",
            "star_type": f"G{xss_attr}",
            "distance_from_arrival_ls": 0.0,
        },
        {
            "body_id": 1,
            "body_name": f"Planet {xss_attr}",
            "planet_class": f"Rocky {xss_attr}",
            "atmosphere_composition": [
                {"Name": f"Oxygen {xss_attr}", "Percent": 21.0},
            ],
            "distance_from_arrival_ls": 120.0,
        },
        {
            # Ring pseudo-body with planet_class=None must not crash export
            "body_id": 2,
            "body_name": "Planet Ring",
            "planet_class": None,
            "atmosphere_composition": {f"Nitrogen {xss_breakout}": 78.0},
            "distance_from_arrival_ls": 120.5,
        },
        {
            # Non-string planet_class (malformed/corrupt row) must not crash export
            "body_id": 3,
            "body_name": "Numeric Class Body",
            "planet_class": 5,
            "distance_from_arrival_ls": 250.0,
        },
    ]
    out_html = generate_standalone_html(
        sys_data,
        bodies,
        [],
        [{"body_id": 1, "alias_name": "BM", "note_markdown": xss_breakout}],
        cmdr_name=f"Cmdr {xss_attr}",
    )
    assert "tooltip.innerHTML" not in out_html
    assert "tooltip.replaceChildren()" in out_html
    # Even inside the JSON script block, '<' must be escaped so </SCRIPT > cannot break out
    assert "</SCRIPT" not in out_html
    assert "<img src=x" not in out_html
    # Only the 2 intended closing </script> tags may exist (JSON block + inline orrery script)
    assert out_html.lower().count("</script") == 2


def test_frontend_xss_sinks_escaped_b1():
    node_exe = shutil.which("node")
    if not node_exe:
        pytest.skip("Node.js not installed")

    ui_dir = Path(__file__).resolve().parent.parent / "app" / "ui" / "js"
    # Verify all iconLabel / effectiveIconLabel HTML interpolations use escapeHtml
    for js_file, token in (
        ("app.js", "${escapeHtml(iconLabel)}"),
        ("mining_view.js", "${escapeHtml(iconLabel)}"),
        ("system_map.js", "${escapeHtml(effectiveIconLabel)}"),
    ):
        src = (ui_dir / js_file).read_text(encoding="utf-8")
        assert token in src, f"Missing {token} in {js_file}"

    script = f"""
    const fs = require('fs');
    const utilsCode = fs.readFileSync({json.dumps(str(ui_dir / 'utils.js'))}, 'utf8');
    const sysListCode = fs.readFileSync({json.dumps(str(ui_dir / 'system_list.js'))}, 'utf8');
    const sysMapCode = fs.readFileSync({json.dumps(str(ui_dir / 'system_map.js'))}, 'utf8');
    const inspectorCode = fs.readFileSync({json.dumps(str(ui_dir / 'inspector.js'))}, 'utf8');
    const xss = '<img src=x onerror=window.__xss=1>';
    const elems = {{}};
    const mkEl = (id) => ({{
      id,
      className: '',
      dataset: {{}},
      style: {{}},
      value: '',
      children: [],
      classList: {{ add(){{}}, remove(){{}}, contains(){{ return false; }} }},
      setAttribute(k, v) {{ this[k] = v; }},
      addEventListener() {{}},
      appendChild(c) {{ this.children.push(c); }},
      querySelector: (s) => mkEl(s),
      querySelectorAll: () => [],
      innerText: '',
      textContent: '',
      innerHTML: ''
    }});
    global.window = global;
    global.localStorage = {{ getItem: () => null, setItem() {{}} }};
    global.document = {{
      getElementById: (id) => (elems[id] = elems[id] || mkEl(id)),
      createElement: (tag) => mkEl(tag),
      querySelector: (s) => mkEl(s),
      querySelectorAll: () => []
    }};
    global.t = (k) => k;
    global.currentLang = 'en';
    global.getAppLang = () => 'en';
    global.getModuleSettings = () => ({{ exobiology: true, rhino: true }});
    global.generateLandmarkDistanceBadges = () => [];
    global.getLocalizedAnomalyTexts = (a) => ({{ label: a.tag || '', tooltip: a.desc || '' }});
    global.formatCredits = (v) => String(v || 0);
    global.state = {{
      systems: [{{
        system_address: 777001,
        star_system: 'Sys ' + xss,
        main_star_type: 'G' + xss,
        visit_count: 1,
        scanned_bodies: 1,
        total_bodies: 1,
        bookmarks: [{{ body_id: 1, alias_name: 'Alias ' + xss, body_name: 'Body ' + xss, note_snippet: 'Note ' + xss }}]
      }}],
      selectedSystem: {{ system_address: 777001, star_system: 'Sys ' + xss }},
      selectedBody: {{
        system_address: 777001,
        body_id: 1,
        body_name: 'Planet ' + xss,
        planet_class: 'Rocky ' + xss,
        reserve_level: 'UnkRes ' + xss,
        rings: JSON.stringify([{{
          Name: 'Ring ' + xss,
          RingClass: 'eRingClass_PureEvil' + xss,
          InnerRad: 1000000,
          OuterRad: 2000000,
          MassMT: 500
        }}])
      }},
      currentSystemData: {{ system: {{ system_address: 777001, star_system: 'Sys ' + xss }}, bodies: [] }}
    }};
    eval(utilsCode);
    eval(sysListCode);
    eval(sysMapCode);
    eval(inspectorCode);

    renderSystemList();
    renderBodyInspector();
    const beltEl = createSysMapBodyElement({{
      body_id: 'belt-1',
      body_name: 'Belt ' + xss,
      isAsteroidBelt: true,
      ring_class: 'eRingClass_BeltEvil' + xss,
      reserve_level: 'UnkRes ' + xss,
      rings_list: [{{ Name: 'Belt ' + xss, RingClass: 'eRingClass_BeltEvil' + xss }}]
    }}, 'planet', 'Sys ' + xss);
    const ringEl = createSysMapBodyElement({{
      body_id: 2,
      body_name: 'Ringed ' + xss,
      star_type: xss,
      rings_list: [{{ Name: 'Ring ' + xss, RingClass: 'eRingClass_RingEvil' + xss }}]
    }}, 'planet', 'Sys ' + xss);

    const ringsHtml = (elems['inspect-rings-list'] || {{}}).innerHTML || '';
    const collectHtml = (el) => {{
      if (!el) return '';
      let out = el.innerHTML || '';
      if (Array.isArray(el.children)) {{
        for (const ch of el.children) out += collectHtml(ch);
      }}
      return out;
    }};
    const rendered = [
      ...elems['system-list'].children.map(collectHtml),
      ...Object.values(elems).map(collectHtml),
      collectHtml(beltEl),
      collectHtml(ringEl)
    ].join('\\n');
    const iconEscaped = escapeHtml(getBodyIconLabel({{ star_type: xss }}));
    console.log(JSON.stringify({{
      ringsRendered: ringsHtml.length > 0,
      hasRawXss: rendered.includes('<img src=x'),
      iconEscapedSafe: !iconEscaped.includes('<img src=x')
    }}));
    """
    proc = subprocess.run([node_exe, "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"Node script failed:\n{proc.stderr}"
    res = json.loads(proc.stdout.strip())
    assert res["ringsRendered"] is True
    assert res["hasRawXss"] is False
    assert res["iconEscapedSafe"] is True


def test_app_settings_whitelist_and_validation_m3(client):
    r_bad_key = client.post("/api/app_settings", json={"__proto__": {"polluted": True}})
    assert r_bad_key.status_code == 400

    r_bad_lang = client.post("/api/app_settings", json={"language": "xx"})
    assert r_bad_lang.status_code == 400

    sys_root = os.environ.get("SystemRoot", "/etc")
    r_bad_dir = client.post("/api/app_settings", json={"journal_dir": sys_root})
    assert r_bad_dir.status_code == 400

    r_ok = client.post("/api/app_settings", json={"language": "en"})
    assert r_ok.status_code == 200
    assert r_ok.json()["settings"]["language"] == "en"


def test_import_png_rejects_oversized_upload_m4(client):
    oversized = b"A" * (10 * 1024 * 1024 + 64)
    r = client.post(
        "/api/import/png",
        files={"file": ("big.png", oversized, "image/png")},
    )
    assert r.status_code == 413


def test_journal_parser_survives_poison_lines_and_reraises_operational_error_h1(tmp_path):
    conn = get_db_connection()
    parser = JournalParser(db_conn=conn, is_live=False)

    for bad in ("[]", '"string"', "1234", "null", "{not valid json"):
        parser.process_journal_line(bad)

    malformed_signals = json.dumps({
        "event": "SAASignalsFound",
        "SystemAddress": 123456789,
        "BodyID": 1,
        "BodyName": "Poison Test 1",
        "Signals": [123, None, "bad_entry", {"Type": "$SAA_SignalType_Biological;", "Count": "NaN"}],
        "Genuses": [42, None, {"Genus": "$Codex_Ent_Stratum_Genus_Name;"}],
    })
    parser.process_journal_line(malformed_signals)

    jfile = tmp_path / "Journal.2026-01-01T000000.01.log"
    lines = [
        "[]",
        json.dumps({"event": "SAASignalsFound", "SystemAddress": 987654321, "BodyID": 2, "Signals": ["bad"]}),
        json.dumps({
            "timestamp": "2026-01-01T00:01:00Z",
            "event": "FSDJump",
            "StarSystem": "Poison Survive Alpha",
            "SystemAddress": 98765432101,
            "StarPos": [0.0, 0.0, 0.0],
        }),
    ]
    jfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    parser.parse_file(str(jfile))

    row = conn.execute(
        "SELECT star_system FROM systems WHERE system_address = ?",
        (98765432101,),
    ).fetchone()
    assert row is not None
    assert row["star_system"] == "Poison Survive Alpha"

    # H-1b: Transient sqlite3.OperationalError must rollback partial writes, keep offset at 0,
    # and NOT double-count earlier lines on retry.
    jfile2 = tmp_path / "Journal.2026-01-02T000000.01.log"
    multi_lines = [
        json.dumps({"timestamp": "2026-01-02T00:00:00Z", "event": "FSDJump", "StarSystem": "LockSys0", "SystemAddress": 98765432200}),
        json.dumps({"timestamp": "2026-01-02T00:01:00Z", "event": "FSDJump", "StarSystem": "LockSys1", "SystemAddress": 98765432201}),
        json.dumps({"timestamp": "2026-01-02T00:02:00Z", "event": "FSDJump", "StarSystem": "LockSys2", "SystemAddress": 98765432202}),
    ]
    jfile2.write_text("\n".join(multi_lines) + "\n", encoding="utf-8")

    orig_process = parser.process_journal_line
    call_idx = {"n": 0}

    def fail_on_third(line_str):
        call_idx["n"] += 1
        if call_idx["n"] == 3:
            raise sqlite3.OperationalError("database is locked")
        return orig_process(line_str)

    with patch.object(parser, "process_journal_line", side_effect=fail_on_third):
        with pytest.raises(sqlite3.OperationalError):
            parser.parse_file(str(jfile2))

    pf_row = conn.execute("SELECT last_line_offset FROM parsed_files WHERE filename = ?", (jfile2.name,)).fetchone()
    assert pf_row is None

    # Retry succeeds and each system has visit_count == 1 (ZERO double counting!)
    parser.parse_file(str(jfile2))
    for addr in (98765432200, 98765432201, 98765432202):
        srow = conn.execute("SELECT visit_count FROM systems WHERE system_address = ?", (addr,)).fetchone()
        assert srow is not None
        assert srow["visit_count"] == 1

    # Deterministic non-lock OperationalError on line 2 must quarantine after 3 retries and still process line 3
    jfile3 = tmp_path / "Journal.2026-01-03T000000.01.log"
    det_lines = [
        json.dumps({"timestamp": "2026-01-03T00:00:00Z", "event": "FSDJump", "StarSystem": "DetSys0", "SystemAddress": 98765432300}),
        json.dumps({"timestamp": "2026-01-03T00:01:00Z", "event": "FSDJump", "StarSystem": "DetSys1", "SystemAddress": 98765432301}),
        json.dumps({"timestamp": "2026-01-03T00:02:00Z", "event": "FSDJump", "StarSystem": "DetSys2", "SystemAddress": 98765432302}),
    ]
    jfile3.write_text("\n".join(det_lines) + "\n", encoding="utf-8")

    def fail_det_second(line_str):
        if "DetSys1" in line_str:
            raise sqlite3.OperationalError("no such column: broken_col")
        return orig_process(line_str)

    with patch.object(parser, "process_journal_line", side_effect=fail_det_second):
        for _ in range(3):
            with pytest.raises(sqlite3.OperationalError):
                parser.parse_file(str(jfile3))
        # 4th attempt quarantines line 2 cleanly and commits DetSys0 + DetSys2 with visit_count == 1
        parser.parse_file(str(jfile3))

    assert conn.execute("SELECT visit_count FROM systems WHERE system_address = 98765432300").fetchone()["visit_count"] == 1
    assert conn.execute("SELECT visit_count FROM systems WHERE system_address = 98765432301").fetchone() is None
    assert conn.execute("SELECT visit_count FROM systems WHERE system_address = 98765432302").fetchone()["visit_count"] == 1

    # R4-2: Mid-file Rhino mining site save MUST NOT commit early and cause duplicate visit_count on lock retry
    jfile4 = tmp_path / "Journal.2026-01-04T000000.01.log"
    mining_lines = [
        json.dumps({"timestamp": "2026-01-04T00:00:00Z", "event": "FSDJump", "StarSystem": "MidCommitSys0", "SystemAddress": 98765432400}),
        json.dumps({"timestamp": "2026-01-04T00:01:00Z", "event": "Touchdown", "StarSystem": "MidCommitSys0", "SystemAddress": 98765432400, "Body": "MidCommitSys0 1", "BodyID": 1, "Latitude": 12.34, "Longitude": 56.78}),
        json.dumps({"timestamp": "2026-01-04T00:02:00Z", "event": "LaunchSRV", "SRVType": "testbuggy"}),
        json.dumps({"timestamp": "2026-01-04T00:03:00Z", "event": "MaterialCollected", "Category": "Raw", "Name": "iron", "Name_Localised": "Iron", "Count": 1}),
        json.dumps({"timestamp": "2026-01-04T00:04:00Z", "event": "FSDJump", "StarSystem": "MidCommitSys1", "SystemAddress": 98765432401}),
    ]
    jfile4.write_text("\n".join(mining_lines) + "\n", encoding="utf-8")

    def fail_on_last_jump(line_str):
        if "MidCommitSys1" in line_str:
            raise sqlite3.OperationalError("database is locked")
        return orig_process(line_str)

    with patch.object(parser, "process_journal_line", side_effect=fail_on_last_jump):
        with pytest.raises(sqlite3.OperationalError):
            parser.parse_file(str(jfile4))

    parser.parse_file(str(jfile4))
    assert conn.execute("SELECT visit_count FROM systems WHERE system_address = 98765432400").fetchone()["visit_count"] == 1
    assert conn.execute("SELECT visit_count FROM systems WHERE system_address = 98765432401").fetchone()["visit_count"] == 1
    assert conn.execute("SELECT COUNT(*) FROM surface_mining_sites WHERE system_address = 98765432400").fetchone()[0] == 1
    conn.close()


def test_codex_ggg_before_scan_preserves_body_name_h2():
    conn = get_db_connection()
    parser = JournalParser(db_conn=conn, is_live=False)
    sys_addr = 445566778899

    conn.execute("INSERT OR REPLACE INTO systems (system_address, star_system) VALUES (?, ?)", (sys_addr, "GGG Test Sys"))
    conn.execute(
        "INSERT OR REPLACE INTO bodies (system_address, body_id, body_name, star_system, star_type) VALUES (?, ?, ?, ?, ?)",
        (sys_addr, 0, "GGG Test Sys A", "GGG Test Sys", "G"),
    )
    conn.commit()

    codex_before_scan = json.dumps({
        "timestamp": "2026-01-02T00:00:00Z",
        "event": "CodexEntry",
        "SystemAddress": sys_addr,
        "NearestDestination": "GGG Test Sys 3",
        "Name": "$Codex_Ent_Green_ClassI_Name;",
        "Name_Localised": "Sudarsky Class I Gas Giant",
        "EntryID": 2100101,
    })
    parser.process_journal_line(codex_before_scan)

    c_row = conn.execute(
        "SELECT body_name, is_ggg FROM codex_entries WHERE system_address = ? AND name = ?",
        (sys_addr, "$Codex_Ent_Green_ClassI_Name;"),
    ).fetchone()
    assert c_row is not None
    assert c_row["is_ggg"] == 1
    assert c_row["body_name"] == "GGG Test Sys 3"

    sys_addr_2 = 445566779000
    codex_body0_unscanned = json.dumps({
        "timestamp": "2026-01-02T00:05:00Z",
        "event": "CodexEntry",
        "SystemAddress": sys_addr_2,
        "BodyID": 0,
        "Name": "$Codex_Ent_Green_ClassIII_Name;",
        "EntryID": 2100103,
    })
    parser.process_journal_line(codex_body0_unscanned)
    c_row2 = conn.execute(
        "SELECT body_id, body_name, is_ggg FROM codex_entries WHERE system_address = ? AND name = ?",
        (sys_addr_2, "$Codex_Ent_Green_ClassIII_Name;"),
    ).fetchone()
    assert c_row2 is not None
    assert c_row2["is_ggg"] == 1
    assert c_row2["body_id"] is None
    assert c_row2["body_name"] is None
    conn.close()


def test_tts_priority_eviction_and_settings_validation_m5b(client):
    svc = TTSService()
    for i in range(100):
        assert svc.enqueue_speak(f"normal message {i}", priority=False) is True

    # Normal queue full rejects non-priority item
    assert svc.enqueue_speak("normal overflow", priority=False) is False
    # Urgent priority item evicts normal item and succeeds
    assert svc.enqueue_speak("GGG urgent alert", priority=True) is True

    # /api/tts_settings rejects non-local voicevoxUrl, unknown keys, oversized strings, and nested dicts
    r_bad_url = client.post("/api/tts_settings", json={"voicevoxUrl": "http://169.254.169.254:50021"})
    assert r_bad_url.status_code == 400
    r_bad_key = client.post("/api/tts_settings", json={"arbitrary_key": "x"})
    assert r_bad_key.status_code == 400
    r_bad_len = client.post("/api/tts_settings", json={"customText": "A" * 5000})
    assert r_bad_len.status_code == 400
    r_bad_type = client.post("/api/tts_settings", json={"enabled": {"nested": True}})
    assert r_bad_type.status_code == 400

    # /api/tts/config ALSO rejects external voicevox_url (does not poison tts_settings.json)
    r_cfg_bad = client.post("/api/tts/config", json={"voicevox_url": "http://evil.example:50021"})
    assert r_cfg_bad.status_code == 400
    assert client.get("/api/tts_settings").json()["voicevoxUrl"] != "http://evil.example:50021"
