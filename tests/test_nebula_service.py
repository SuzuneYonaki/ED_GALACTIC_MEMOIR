import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.database import init_db
from app.server.api import app
from app.services.nebula_service import NEBULA_CATALOG_FILE, find_nebula_for_system


def test_edastro_nebulae_ssot_catalog_integrity():
    assert NEBULA_CATALOG_FILE.exists(), "Static EDAstro nebula JSON catalog must exist"
    size_bytes = NEBULA_CATALOG_FILE.stat().st_size
    assert size_bytes < 600_000, f"Catalog too large for lightweight goal: {size_bytes} bytes"

    data = json.loads(NEBULA_CATALOG_FILE.read_text(encoding="utf-8"))
    assert "edastro.com" in (data.get("source") or "")
    types = data.get("types") or {}
    assert {"planetary", "procgen", "real"}.issubset(types.keys())
    entries = data.get("entries") or []
    assert len(entries) > 5000
    assert data.get("columns") == ["name", "system", "x", "y", "z", "type", "region_id"]


def test_find_nebula_for_system_offline_resolution():
    # 1. Outside all nebulae -> None
    assert find_nebula_for_system("Sol", 0.0, 0.0, 0.0) is None
    assert find_nebula_for_system(None, None, None, None) is None

    # 2. Named sector diffuse nebula match
    cal = find_nebula_for_system("California Sector ZE-A d2", -340.0, -210.0, -930.0)
    assert cal is not None
    assert cal["inside"] is True
    assert cal["name"] == "California Nebula"
    assert cal["type"] == "real"
    assert cal["type_label_ja"] == "実在・散光星雲"
    assert cal["match_method"] == "sector"

    # 3. Planetary nebula exact reference system match
    laz = find_nebula_for_system("Aemonz WZ-Y e6771", 3886.78, -660.69, 33718.8)
    assert laz is not None
    assert laz["inside"] is True
    assert "Lazurite" in laz["name"]
    assert laz["type"] == "planetary"
    assert laz["type_label_en"] == "Planetary Nebula"
    assert laz["type_label_ja"] == "惑星状星雲"
    assert laz["match_method"] == "system"

    # 4. Procedural nebula exact system & spatial radius check
    proc = find_nebula_for_system("Agnairt TA-U d4-360", -10010.4, -33.7, 22444.2)
    assert proc is not None
    assert proc["type"] == "procgen"
    assert proc["type_label_ja"] == "手続生成星雲"

    proc_nearby = find_nebula_for_system("Agnairt XX-Y z1-0", -10020.0, -30.0, 22450.0)
    assert proc_nearby is not None
    assert proc_nearby["type"] == "procgen"
    assert proc_nearby["match_method"] == "coords"

    # 5. Coordinate-space match inside diffuse nebula (Barnard's Loop)
    barnard = find_nebula_for_system("Random Test Star", 610.0, -425.0, -1220.0)
    assert barnard is not None
    assert barnard["name"] == "Barnard's Loop"
    assert barnard["match_method"] == "coords"


@pytest.fixture
def nebula_client(tmp_path, monkeypatch):
    test_db = tmp_path / "test_nebula.db"

    def mock_get_db_connection():
        conn = sqlite3.connect(str(test_db), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr("app.server.api.get_db_connection", mock_get_db_connection)

    conn = mock_get_db_connection()
    init_db(conn, force=True)
    c = conn.cursor()
    c.executemany(
        """
        INSERT INTO systems (
            system_address, star_system, star_pos_x, star_pos_y, star_pos_z,
            visit_count, last_visited
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (101, "Sol", 0.0, 0.0, 0.0, 3, "2026-11-10T10:00:00Z"),
            (102, "California Sector LX-T b3-0", -337.9, -211.9, -927.0, 1, "2026-11-11T10:00:00Z"),
            (103, "Aemonz WZ-Y e6771", 3886.78, -660.69, 33718.8, 2, "2026-11-12T10:00:00Z"),
        ],
    )
    conn.commit()
    conn.close()
    return TestClient(app)


def test_nebula_fields_in_systems_and_detail_endpoints(nebula_client):
    r_list = nebula_client.get("/api/systems")
    assert r_list.status_code == 200
    by_addr = {s["system_address"]: s for s in r_list.json()["systems"]}

    assert "nebula" not in by_addr[101]
    assert by_addr[102]["nebula"]["name"] == "California Nebula"
    assert by_addr[102]["nebula"]["type"] == "real"
    assert by_addr[103]["nebula"]["type"] == "planetary"

    r_sol = nebula_client.get("/api/system/101")
    assert r_sol.status_code == 200
    assert "nebula" not in r_sol.json()["system"]

    r_cal = nebula_client.get("/api/system/102")
    assert r_cal.status_code == 200
    assert r_cal.json()["system"]["nebula"]["name"] == "California Nebula"


def test_ui_nebula_hidden_in_live_mode_and_safe_rendering():
    root = Path(__file__).resolve().parent.parent
    client = TestClient(app)
    res_home = client.get("/")
    assert res_home.status_code == 200
    assert "current-system-nebula-badge" in res_home.text

    sl_js = (root / "app" / "ui" / "js" / "system_list.js").read_text(encoding="utf-8")
    # Regular system card and header both guard nebula display strictly behind !state.liveSyncEnabled
    assert sl_js.count("!state.liveSyncEnabled") >= 2
    assert "escapeHtml(neb.name)" in sl_js

    node = shutil.which("node")
    if node:
        for rel in ("app/ui/js/system_list.js", "app/ui/js/app.js", "app/ui/js/i18n.js"):
            proc = subprocess.run([node, "--check", str(root / rel)], capture_output=True, text=True)
            assert proc.returncode == 0, proc.stderr
