import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.database import init_db
from app.server.api import app
from app.services.region_service import get_region_sectors, get_regions_overview
from app.utils.galactic_regions import GALACTIC_REGIONS, coords_to_grid_cell, get_region_map_grid
from app.utils.voxel import extract_sector_name


def test_extract_sector_name_and_grid_metadata():
    assert extract_sector_name("Dryooe Flyou AA-A h55") == "Dryooe Flyou"
    assert extract_sector_name("Col 285 Sector EX-T d3-112") == "Col 285 Sector"
    assert extract_sector_name("Gludgaa BP-U b30-3") == "Gludgaa"
    assert extract_sector_name("Sol") is None
    assert extract_sector_name("HIP 12099") is None
    assert extract_sector_name("") is None
    assert extract_sector_name(None) is None

    grid = get_region_map_grid(8)
    assert grid["width"] == 256
    assert grid["height"] == 256
    rids = {rid for row in grid["rle_rows"] for _, rid in row if rid > 0}
    assert rids == set(GALACTIC_REGIONS.keys())

    sol_cell = coords_to_grid_cell(0.0, 0.0)
    assert sol_cell is not None
    assert 0 <= sol_cell[0] < 256 and 0 <= sol_cell[1] < 256


@pytest.fixture
def region_client(tmp_path, monkeypatch):
    test_db = tmp_path / "test_regions.db"

    def mock_get_db_connection():
        conn = sqlite3.connect(str(test_db), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr("app.server.api.get_db_connection", mock_get_db_connection)

    conn = mock_get_db_connection()
    init_db(conn, force=True)
    c = conn.cursor()

    # Region 18: Inner Orion Spur (near Sol: 0, 0, 0)
    rows = [
        (101, "Sol", 0.0, 0.0, 0.0, 5, 9, 9, 1, 0, 0, "2026-11-10T10:00:00Z"),
        (102, "Col 285 Sector EX-T d3-112", 120.0, 10.0, -80.0, 2, 12, 12, 0, 1, 0, "2026-11-11T10:00:00Z"),
        (103, "Col 285 Sector AB-C b1-0", 130.0, -5.0, -70.0, 1, 8, 4, 0, 0, 0, "2026-11-11T12:00:00Z"),
        (104, "Synuefe XR-H d11-102", 450.0, -20.0, -350.0, 3, 6, 6, 0, 0, 0, "2026-11-09T10:00:00Z"),
        # External (unvisited) EDSM record in Inner Orion Spur - must not inflate visited counts
        (105, "Col 285 Sector ZZ-Z a0-1", 125.0, 0.0, -75.0, 0, 0, 0, 0, 0, 1, "2026-11-01T10:00:00Z"),
        # Region 1: Galactic Centre (near Sag A*: 25.2, -20.9, 25900)
        (201, "Dryooe Flyou AA-A h55", 25.2, -20.9, 25900.0, 4, 15, 15, 1, 1, 0, "2026-11-12T08:00:00Z"),
    ]
    c.executemany(
        """
        INSERT INTO systems (
            system_address, star_system, star_pos_x, star_pos_y, star_pos_z,
            visit_count, total_bodies, scanned_bodies, has_elw, has_water_world,
            is_external, last_visited
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    return TestClient(app), mock_get_db_connection


def test_region_service_overview_and_sectors(region_client):
    _, get_conn = region_client
    conn = get_conn()
    try:
        ov = get_regions_overview(conn, current_coords=(120.0, 10.0, -80.0))
        assert ov["summary"]["total_regions"] == 42
        assert ov["summary"]["explored_regions"] == 2
        assert ov["summary"]["total_visited_systems"] == 5
        assert ov["summary"]["total_sectors"] == 3  # Col 285 Sector, Synuefe, Dryooe Flyou
        assert ov["current_location"]["region_id"] == 18

        by_id = {r["region_id"]: r for r in ov["regions"]}
        assert by_id[18]["visited_systems"] == 4
        assert by_id[18]["external_systems"] == 1
        assert by_id[18]["sector_count"] == 2
        assert by_id[1]["visited_systems"] == 1
        assert by_id[1]["sector_count"] == 1

        sec18 = get_region_sectors(conn, 18)
        assert sec18 is not None
        assert sec18["region"]["visited_systems"] == 4
        sectors = {s["sector_name"] if not s["is_named_catalog"] else "__NAMED__": s for s in sec18["sectors"]}
        assert sectors["Col 285 Sector"]["visited_systems"] == 2
        assert sectors["Col 285 Sector"]["external_systems"] == 1
        assert sectors["Col 285 Sector"]["fss_complete_systems"] == 1
        assert sectors["Col 285 Sector"]["scanned_bodies"] == 16
        assert sectors["Synuefe"]["visited_systems"] == 1
        assert sectors["__NAMED__"]["visited_systems"] == 1
        assert sectors["__NAMED__"]["sample_systems"][0]["star_system"] == "Sol"

        assert get_region_sectors(conn, 9999) is None
    finally:
        conn.close()


def test_region_endpoints_and_systems_enrichment(region_client):
    client, _ = region_client

    r_map = client.get("/api/regions/map")
    assert r_map.status_code == 200
    map_data = r_map.json()
    assert map_data["summary"]["explored_regions"] == 2
    assert len(map_data["regions"]) == 42
    assert len(map_data["visited_cells"]) >= 2

    r_sec = client.get("/api/regions/1/sectors")
    assert r_sec.status_code == 200
    sec_data = r_sec.json()
    assert sec_data["region"]["name_en"] == "Galactic Centre"
    assert sec_data["sectors"][0]["sector_name"] == "Dryooe Flyou"

    assert client.get("/api/regions/999/sectors").status_code == 404

    # /api/systems enrichment + region/sector filtering
    r_sys = client.get("/api/systems")
    assert r_sys.status_code == 200
    by_name = {s["star_system"]: s for s in r_sys.json()["systems"]}
    assert by_name["Sol"]["galactic_region_id"] == 18
    assert by_name["Sol"]["galactic_region_en"] == "Inner Orion Spur"
    assert by_name["Dryooe Flyou AA-A h55"]["galactic_region_id"] == 1

    r_reg1 = client.get("/api/systems", params={"region_id": 1})
    assert r_reg1.status_code == 200
    assert [s["star_system"] for s in r_reg1.json()["systems"]] == ["Dryooe Flyou AA-A h55"]

    r_col = client.get("/api/systems", params={"region_id": 18, "sector": "Col 285 Sector"})
    assert r_col.status_code == 200
    assert {s["system_address"] for s in r_col.json()["systems"]} == {102, 103, 105}

    r_named = client.get("/api/systems", params={"region_id": 18, "sector_named_only": "true"})
    assert r_named.status_code == 200
    assert [s["star_system"] for s in r_named.json()["systems"]] == ["Sol"]


def test_region_map_ui_assets_and_js_syntax():
    root = Path(__file__).resolve().parent.parent
    client = TestClient(app)

    res_js = client.get("/js/region_map.js")
    assert res_js.status_code == 200

    res_home = client.get("/")
    assert res_home.status_code == 200
    for marker in (
        "btn-open-region-map",
        "current-system-region-badge",
        "modal-region-map",
        "region-map-canvas",
        "region-map-selected-banner",
        "region-sectors-list",
        "active-region-sector-bar",
        "/static/js/region_map.js",
    ):
        assert marker in res_home.text

    node = shutil.which("node")
    if node:
        for rel in (
            "app/ui/js/region_map.js",
            "app/ui/js/system_list.js",
            "app/ui/js/app.js",
            "app/ui/js/i18n.js",
        ):
            proc = subprocess.run([node, "--check", str(root / rel)], capture_output=True, text=True)
            assert proc.returncode == 0, proc.stderr
