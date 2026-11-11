import json
import sqlite3
import unittest
from app.db.database import init_db
from app.services.search_service import (
    build_highlighted_html,
    build_highlighted_snippet,
    parse_search_query,
    rebuild_search_index,
    search_fulltext,
    search_matching_system_addresses,
    sync_system_search_index,
)


class TestSearchService(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn, force=True)
        self._seed_sample_data()

    def tearDown(self):
        self.conn.close()

    def _seed_sample_data(self):
        cur = self.conn.cursor()
        # System 1: Gludgaa BP-U b30-3
        cur.execute(
            """
            INSERT INTO systems (
                system_address, star_system, main_star_type, system_economy,
                controlling_faction, shared_notes, last_visited
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1001,
                "Gludgaa BP-U b30-3",
                "M",
                "Extraction",
                "Pilots Federation",
                "深宇宙の素晴らしい採掘拠点",
                "2026-11-01T12:00:00Z",
            ),
        )
        # Bodies for System 1
        cur.execute(
            """
            INSERT INTO bodies (
                system_address, body_id, body_name, star_system,
                planet_class, atmosphere, volcanism, rings, materials, anomalies_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1001,
                1,
                "Gludgaa BP-U b30-3 A 1",
                "Gludgaa BP-U b30-3",
                "High metal content body",
                "Thin Carbon dioxide atmosphere",
                "Silicate magma volcanism",
                json.dumps([{"Name": "Gludgaa BP-U b30-3 A 1 A Ring", "RingClass": "eRingClass_Metallic"}]),
                json.dumps([{"Name": "iron", "Percent": 22.5}, {"Name": "nickel", "Percent": 15.0}]),
                json.dumps([{"tag": "Exotic Ring Host", "desc": "珍しいリング惑星"}]),
            ),
        )
        # Bookmark for System 1
        cur.execute(
            """
            INSERT INTO body_bookmarks (
                system_address, body_id, body_name, star_system,
                alias_name, note_markdown, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1001,
                1,
                "Gludgaa BP-U b30-3 A 1",
                "Gludgaa BP-U b30-3",
                "第一鉄鉱石基地",
                "高重力なので着陸注意！鉄とニッケルが大量に掘れる。",
                "2026-11-01T12:00:00Z",
                "2026-11-01T12:05:00Z",
            ),
        )
        # Scanned organic for System 1
        cur.execute(
            """
            INSERT INTO scanned_organics (
                system_address, body_id, body_name, timestamp, scan_type,
                genus, genus_localised, species, species_localised, variant_localised
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1001,
                1,
                "Gludgaa BP-U b30-3 A 1",
                "2026-11-01T12:10:00Z",
                "Analyse",
                "Stratum",
                "ストラタム",
                "Stratum Tectonicas",
                "ストラタム・テクトニカス",
                "ストラタム・テクトニカス - エメラルド",
            ),
        )
        # Codex for System 1
        cur.execute(
            """
            INSERT INTO codex_entries (
                system_address, body_id, body_name, entry_id, name, name_localised,
                category, sub_category, region_name, is_ggg, ggg_variant, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1001,
                2,
                "Gludgaa BP-U b30-3 A 2",
                12345,
                "Green Gas Giant",
                "緑色の巨大ガス惑星",
                "Biological and Geological",
                "Gas Giants",
                "Inner Orion Spur",
                1,
                "Class III Gas Giant",
                "2026-11-01T12:15:00Z",
                "2026-11-01T12:15:00Z",
            ),
        )
        # Mining site for System 1
        cur.execute(
            """
            INSERT INTO surface_mining_sites (
                system_address, star_system, body_id, body_name,
                latitude, longitude, hotspot, minerals, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1001,
                "Gludgaa BP-U b30-3",
                1,
                "Gludgaa BP-U b30-3 A 1",
                12.34,
                -56.78,
                "PML Alpha",
                "Polonium, Tellurium",
                "クレーター底に高品質素材集中",
                "2026-11-01T12:20:00Z",
                "2026-11-01T12:20:00Z",
            ),
        )
        # Station for System 1
        cur.execute(
            """
            INSERT INTO stations (
                system_address, station_name, station_type, body_name, body_id,
                economy, controlling_faction, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1001,
                "Jameson Research Outpost",
                "Outpost",
                "Gludgaa BP-U b30-3 A 1",
                1,
                "High Tech",
                "Independent Explorers",
                "2026-11-01T12:25:00Z",
            ),
        )
        # Physics report for System 1
        cur.execute(
            """
            INSERT INTO system_physics_evaluations (
                system_address, star_system, rarity_score, star_count, planet_count,
                anomalies_json, narrative_report, raw_features_json, evaluated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1001,
                "Gludgaa BP-U b30-3",
                92.5,
                1,
                2,
                json.dumps(["Confirmed GGG"]),
                "この星系は極めて稀少な蛍光グリーンガスジャイアントを有します。",
                "{}",
                "2026-11-01T12:30:00Z",
            ),
        )

        # System 2: Sol (XSS / special chars test case)
        cur.execute(
            """
            INSERT INTO systems (system_address, star_system, last_visited)
            VALUES (?, ?, ?)
            """,
            (2002, "Sol", "2026-11-02T10:00:00Z"),
        )
        cur.execute(
            """
            INSERT INTO body_bookmarks (
                system_address, body_id, body_name, star_system,
                alias_name, note_markdown, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                2002,
                3,
                "Earth",
                "Sol",
                "Home <script>alert(1)</script>",
                "人類の故郷 <b>Test</b> & <img src=x onerror=alert(1)>",
                "2026-11-02T10:00:00Z",
                "2026-11-02T10:00:00Z",
            ),
        )
        self.conn.commit()

    def test_rebuild_index_covers_all_eight_categories(self):
        count = rebuild_search_index(self.conn)
        self.assertGreaterEqual(count, 10)
        cats = {
            r[0]
            for r in self.conn.execute("SELECT DISTINCT category FROM search_documents").fetchall()
        }
        expected = {"system", "body", "bookmark", "bio", "codex", "mining", "station", "physics"}
        self.assertEqual(cats, expected)

    def test_japanese_and_english_fulltext_search(self):
        rebuild_search_index(self.conn)
        # Japanese note search
        res_jp = search_fulltext(self.conn, "採掘拠点")
        self.assertGreaterEqual(res_jp["total"], 1)
        self.assertEqual(res_jp["results"][0]["star_system"], "Gludgaa BP-U b30-3")
        self.assertIn('<mark class="search-hl">採掘拠点</mark>', res_jp["results"][0]["highlighted_snippet"])

        # English bio species search
        res_bio = search_fulltext(self.conn, "Tectonicas")
        self.assertEqual(res_bio["total"], 1)
        self.assertEqual(res_bio["results"][0]["category"], "bio")

        # Station search
        res_st = search_fulltext(self.conn, "Jameson Research")
        self.assertEqual(res_st["total"], 1)
        self.assertEqual(res_st["results"][0]["category"], "station")

        # Physics report search
        res_phys = search_fulltext(self.conn, "蛍光グリーン")
        self.assertEqual(res_phys["total"], 1)
        self.assertEqual(res_phys["results"][0]["category"], "physics")

    def test_short_term_fallback_and_and_not_operators(self):
        rebuild_search_index(self.conn)
        # 1-char Japanese search
        res_short = search_fulltext(self.conn, "鉄")
        self.assertGreaterEqual(res_short["total"], 1)

        # Mixed AND + NOT search
        res_and_not = search_fulltext(self.conn, "ニッケル -クレーター")
        # Should match bookmark (contains ニッケル, no クレーター) and exclude mining if it had both
        self.assertGreaterEqual(res_and_not["total"], 1)
        for item in res_and_not["results"]:
            self.assertNotIn("クレーター", item["highlighted_snippet"])

        # Quoted phrase search
        pos, neg = parse_search_query('"High metal" -Water')
        self.assertEqual(pos, ["High metal"])
        self.assertEqual(neg, ["Water"])
        res_phrase = search_fulltext(self.conn, '"High metal"')
        self.assertEqual(res_phrase["total"], 1)
        self.assertEqual(res_phrase["results"][0]["category"], "body")

    def test_category_filter_and_system_address_lookup(self):
        rebuild_search_index(self.conn)
        res_filtered = search_fulltext(self.conn, "Gludgaa", categories=["mining"])
        self.assertEqual(res_filtered["total"], 1)
        self.assertEqual(res_filtered["results"][0]["category"], "mining")
        self.assertGreater(res_filtered["total_unfiltered"], 1)

        addrs = search_matching_system_addresses(self.conn, "Tellurium")
        self.assertEqual(addrs, {1001})

    def test_incremental_system_sync(self):
        rebuild_search_index(self.conn)
        self.conn.execute(
            "UPDATE body_bookmarks SET note_markdown = ? WHERE system_address = 1001 AND body_id = 1",
            ("新しく発見した超高価値なプラチナ鉱脈",),
        )
        self.conn.commit()
        sync_system_search_index(self.conn, 1001)

        res_new = search_fulltext(self.conn, "プラチナ鉱脈")
        self.assertEqual(res_new["total"], 1)
        self.assertEqual(res_new["results"][0]["category"], "bookmark")

    def test_xss_escaping_and_malicious_fts_syntax_safety(self):
        rebuild_search_index(self.conn)
        res_xss = search_fulltext(self.conn, "alert")
        self.assertEqual(res_xss["total"], 1)
        item = res_xss["results"][0]
        self.assertNotIn("<script>", item["highlighted_title"])
        self.assertNotIn("<img", item["highlighted_snippet"])
        self.assertIn("&lt;script&gt;", item["highlighted_title"])
        self.assertIn('<mark class="search-hl">alert</mark>', item["highlighted_title"])

        # Direct helper verification
        safe_html = build_highlighted_html('<script>alert("xss")</script>', ["alert"])
        self.assertEqual(
            safe_html,
            '&lt;script&gt;<mark class="search-hl">alert</mark>(&quot;xss&quot;)&lt;/script&gt;',
        )
        safe_snip = build_highlighted_snippet("prefix " + "<svg onload=alert(1)>", ["alert"])
        self.assertIn("&lt;svg", safe_snip)

        # Malicious FTS5 / SQLi inputs must not raise errors
        for evil in [
            '" OR ""="',
            "'; DROP TABLE search_documents; --",
            'NEAR("a" "b", 10) * : ^',
            "a" * 2000,
        ]:
            res = search_fulltext(self.conn, evil)
            self.assertIsInstance(res["results"], list)


if __name__ == "__main__":
    unittest.main()
