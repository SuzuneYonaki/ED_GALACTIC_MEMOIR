import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.server.api import app
from app.db.database import init_db


@pytest.fixture
def search_client(tmp_path, monkeypatch):
    test_db = tmp_path / "test_search_api.db"

    def mock_get_db_connection():
        conn = sqlite3.connect(str(test_db), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr("app.server.api.get_db_connection", mock_get_db_connection)

    conn = mock_get_db_connection()
    init_db(conn, force=True)
    c = conn.cursor()

    # System 101: Alpha Mining
    c.execute(
        """
        INSERT INTO systems (system_address, star_system, main_star_type, visit_count, is_external, last_visited)
        VALUES (101, 'Alpha Frontier', 'K', 2, 0, '2026-11-01T10:00:00Z')
        """
    )
    c.execute(
        """
        INSERT INTO bodies (system_address, body_id, body_name, star_system, planet_class, materials)
        VALUES (101, 1, 'Alpha Frontier 1', 'Alpha Frontier', 'High metal content body', ?)
        """,
        (json.dumps([{"Name": "Polonium", "Percent": 1.8}]),),
    )
    c.execute(
        """
        INSERT INTO stations (system_address, station_name, station_type, body_name, body_id, economy, updated_at)
        VALUES (101, 'Horizon Orbital', 'Coriolis Starport', 'Alpha Frontier 1', 1, 'Refinery', '2026-11-01T10:00:00Z')
        """
    )

    # System 102: Beta Exobiology
    c.execute(
        """
        INSERT INTO systems (system_address, star_system, main_star_type, visit_count, is_external, last_visited)
        VALUES (102, 'Beta Oasis', 'G', 1, 0, '2026-11-02T10:00:00Z')
        """
    )
    c.execute(
        """
        INSERT INTO scanned_organics (
            system_address, body_id, body_name, timestamp, scan_type,
            genus, species, species_localised
        ) VALUES (102, 2, 'Beta Oasis A 2', '2026-11-02T10:15:00Z', 'Analyse', 'Fungoida', 'Fungoida Setisis', 'ファンゴイダ・セティシス')
        """
    )
    c.execute(
        """
        INSERT INTO system_physics_evaluations (
            system_address, star_system, rarity_score, star_count, planet_count,
            anomalies_json, narrative_report, raw_features_json, evaluated_at
        ) VALUES (102, 'Beta Oasis', 88.0, 1, 3, '[]', '三重連星による潮汐加熱が顕著です。', '{}', '2026-11-02T10:20:00Z')
        """
    )

    conn.commit()
    conn.close()

    return TestClient(app)


def test_api_search_cross_category_and_rebuild(search_client):
    # Rebuild index explicitly
    res_reb = search_client.post("/api/search/rebuild")
    assert res_reb.status_code == 200
    assert res_reb.json()["status"] == "ok"
    assert res_reb.json()["indexed_count"] >= 5

    # Search body material
    res_mat = search_client.get("/api/search?q=Polonium")
    assert res_mat.status_code == 200
    data_mat = res_mat.json()
    assert data_mat["total"] == 1
    assert data_mat["results"][0]["star_system"] == "Alpha Frontier"
    assert data_mat["results"][0]["category"] == "body"

    # Search station
    res_st = search_client.get("/api/search?q=Horizon%20Orbital")
    assert res_st.status_code == 200
    assert res_st.json()["results"][0]["category"] == "station"

    # Search Japanese physics narrative
    res_phys = search_client.get("/api/search?q=潮汐加熱")
    assert res_phys.status_code == 200
    assert res_phys.json()["total"] == 1
    assert res_phys.json()["results"][0]["category"] == "physics"

    # Filter by category
    res_cat = search_client.get("/api/search?q=Beta&category=bio")
    assert res_cat.status_code == 200
    assert res_cat.json()["total"] == 1
    assert res_cat.json()["results"][0]["category"] == "bio"


def test_api_systems_enhanced_with_fulltext_and_exclusions(search_client):
    # Search systems by station name (previously unsupported in /api/systems?q=)
    res_sys = search_client.get("/api/systems?q=Horizon%20Orbital")
    assert res_sys.status_code == 200
    systems = res_sys.json()["systems"]
    assert len(systems) == 1
    assert systems[0]["star_system"] == "Alpha Frontier"

    # Search systems by Japanese bio species name
    res_bio_sys = search_client.get("/api/systems?q=ファンゴイダ")
    assert res_bio_sys.status_code == 200
    systems_bio = res_bio_sys.json()["systems"]
    assert len(systems_bio) == 1
    assert systems_bio[0]["star_system"] == "Beta Oasis"

    # Exclusion operator test (-Polonium)
    res_excl = search_client.get("/api/systems?q=Frontier%20-Polonium")
    assert res_excl.status_code == 200
    assert len(res_excl.json()["systems"]) == 0


def test_incremental_sync_on_bookmark_and_mining_site(search_client):
    # Add bookmark with Japanese note + XSS attempt
    res_bm = search_client.post(
        "/api/bookmark",
        json={
            "system_address": 101,
            "body_id": 1,
            "body_name": "Alpha Frontier 1",
            "star_system": "Alpha Frontier",
            "alias_name": "秘密の隠れ家",
            "note_markdown": "ここに稀少なトリチウム鉱脈あり <script>alert(9)</script>",
        },
    )
    assert res_bm.status_code == 200

    res_find_bm = search_client.get("/api/search?q=トリチウム鉱脈")
    assert res_find_bm.status_code == 200
    data_bm = res_find_bm.json()
    assert data_bm["total"] == 1
    assert data_bm["results"][0]["category"] == "bookmark"
    assert "<script>" not in data_bm["results"][0]["highlighted_snippet"]
    assert "&lt;script&gt;" in data_bm["results"][0]["highlighted_snippet"]

    # Add manual mining site
    res_ms = search_client.post(
        "/api/mining_sites",
        json={
            "system_address": 102,
            "star_system": "Beta Oasis",
            "body_id": 2,
            "body_name": "Beta Oasis A 2",
            "latitude": 10.5,
            "longitude": -20.5,
            "minerals": "Yttrium, Ruthenium",
            "hotspot": "Crater Rim Base",
            "note": "最高効率のイットリウム群生地",
        },
    )
    assert res_ms.status_code == 200
    site_id = res_ms.json()["site_id"]

    res_find_ms = search_client.get("/api/search?q=イットリウム群生地")
    assert res_find_ms.status_code == 200
    assert res_find_ms.json()["total"] == 1
    assert res_find_ms.json()["results"][0]["category"] == "mining"

    # Update mining site and verify sync
    res_upd = search_client.put(
        f"/api/mining_sites/{site_id}",
        json={
            "latitude": 10.5,
            "longitude": -20.5,
            "minerals": "Yttrium",
            "hotspot": "Updated Rim Base",
            "note": "更新後の結晶サイト",
        },
    )
    assert res_upd.status_code == 200
    assert search_client.get("/api/search?q=イットリウム群生地").json()["total"] == 0
    assert search_client.get("/api/search?q=結晶サイト").json()["total"] == 1

    # Delete mining site and verify removal from index
    res_del = search_client.delete(f"/api/mining_sites/{site_id}")
    assert res_del.status_code == 200
    assert search_client.get("/api/search?q=結晶サイト").json()["total"] == 0


def test_search_empty_and_malformed_queries(search_client):
    res_empty = search_client.get("/api/search?q=")
    assert res_empty.status_code == 200
    assert res_empty.json()["total"] == 0

    res_sqli = search_client.get("/api/search?q=' OR 1=1; DROP TABLE search_documents; --")
    assert res_sqli.status_code == 200
