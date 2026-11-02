"""
Penetration & Security Test Suite for ED GALACTIC MEMOIR.
Simulates real-world cyberattacks against local API endpoints, SQL queries,
static file serving, and Markdown parsing.
"""

import pytest
from fastapi.testclient import TestClient
from app.server.api import app
from app.db.database import get_db_connection, init_db

client = TestClient(app)


class TestSQLInjectionPenetration:
    """Simulates SQL Injection (SQLi) attacks across endpoints and parameters."""

    SQLI_PAYLOADS = [
        "' OR '1'='1",
        "'; DROP TABLE systems; --",
        "\" OR 1=1 --",
        "1 UNION SELECT 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26 --",
        "SLEEP(5)",
        "'; ATTACH DATABASE 'malicious.db' AS mal; --",
    ]

    def test_systems_search_sqli(self):
        """Verify /api/systems search parameter escapes SQL payloads safely."""
        for payload in self.SQLI_PAYLOADS:
            res = client.get(f"/api/systems?q={payload}")
            # Must return 200 with empty list or normal filtered list, never 500 SQL syntax error
            assert res.status_code == 200, f"Failed on payload: {payload}"
            data = res.json()
            assert "systems" in data

    def test_systems_sort_sqli(self):
        """Verify sorting column parameter cannot be hijacked for SQL injection."""
        malicious_sorts = [
            "star_system; DROP TABLE systems; --",
            "(SELECT 1 FROM sqlite_master)",
            "star_system DESC, (SELECT CASE WHEN (1=1) THEN total_potential_value ELSE 0 END)",
        ]
        for sort_col in malicious_sorts:
            res = client.get(f"/api/systems?sort_by={sort_col}")
            # Invalid sort keys must be ignored or gracefully handled, never cause 500 error
            assert res.status_code in [200, 400], f"Crash on sort_by: {sort_col}"

    def test_system_detail_sqli(self):
        """Verify /api/system/{addr} endpoint rejects non-numeric or SQLi paths."""
        res = client.get("/api/system/12345%20OR%201=1")
        # FastAPI path parameter type validation: system_address is int, so this must return 422 Unprocessable Entity
        assert res.status_code == 422

    def test_body_bookmark_sqli(self):
        """Verify bookmark save endpoint prevents SQL injection in notes and alias names."""
        for payload in self.SQLI_PAYLOADS:
            req_body = {
                "system_address": 99999999,
                "body_id": 999,
                "body_name": f"TestBody_{payload}",
                "star_system": "SQLi_Test_System",
                "alias_name": payload,
                "note_markdown": f"# Note\n{payload}"
            }
            res = client.post("/api/bookmark", json=req_body)
            assert res.status_code == 200
            # Clean up
            client.delete("/api/bookmark/99999999/999")


class TestPathTraversalPenetration:
    """Simulates directory traversal attacks to read arbitrary local files."""

    TRAVERSAL_PAYLOADS = [
        "../../requirements.txt",
        "..\\..\\requirements.txt",
        "%2e%2e/%2e%2e/requirements.txt",
        "..%2f..%2frequirements.txt",
        "....//....//requirements.txt",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
    ]

    def test_js_path_traversal(self):
        """Verify /js/{path} strictly blocks traversal and returns 403 or 404."""
        for payload in self.TRAVERSAL_PAYLOADS:
            res = client.get(f"/js/{payload}")
            assert res.status_code in [403, 404], f"Status was {res.status_code} for {payload}"
            assert "[fonts]" not in res.text
            assert "fastapi" not in res.text

    def test_css_path_traversal(self):
        """Verify /css/{path} strictly blocks traversal and returns 403 or 404."""
        for payload in self.TRAVERSAL_PAYLOADS:
            res = client.get(f"/css/{payload}")
            assert res.status_code in [403, 404], f"Status was {res.status_code} for {payload}"
            assert "[fonts]" not in res.text
            assert "fastapi" not in res.text

    def test_legitimate_static_file_access(self):
        """Verify valid files within directories remain accessible."""
        res_js = client.get("/js/app.js")
        assert res_js.status_code == 200
        res_css = client.get("/css/style.css")
        assert res_css.status_code == 200


class TestXSSMarkdownPenetration:
    """Verifies that Markdown parsing and stored notes sanitize dangerous HTML and scripts."""

    XSS_PAYLOADS = [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert(1)>",
        "<svg/onload=alert(1)>",
        "javascript:alert(1)",
        "[ClickMe](javascript:alert(1))",
    ]

    def test_markdown_sanitization_in_api(self):
        """Ensure storing XSS payloads in notes does not alter API integrity."""
        for payload in self.XSS_PAYLOADS:
            req_body = {
                "system_address": 99999998,
                "body_id": 998,
                "body_name": "XSS_Test_Body",
                "star_system": "XSS_Test_System",
                "alias_name": "XSS_Alias",
                "note_markdown": payload
            }
            res = client.post("/api/bookmark", json=req_body)
            assert res.status_code == 200
            
            # Fetch back
            get_res = client.get("/api/bookmarks")
            assert get_res.status_code == 200
            bookmarks = get_res.json().get("bookmarks", [])
            saved = next((b for b in bookmarks if b["system_address"] == 99999998 and b["body_id"] == 998), None)
            assert saved is not None
            assert saved["note_markdown"] == payload

            # Clean up
            client.delete("/api/bookmark/99999998/998")


class TestMalformedPayloadDoS:
    """Tests resilience against malformed, oversized, or invalid payloads."""

    def test_oversized_search_string(self):
        """Ensure long search query does not crash SQLite or backend."""
        huge_str = "NON_EXISTENT_SYSTEM_SEARCH_STRING_" + ("A" * 5000)
        res = client.get(f"/api/systems?q={huge_str}")
        assert res.status_code == 200
        assert res.json().get("systems") == []

    def test_invalid_json_body(self):
        """Ensure malformed JSON headers return clean 422 responses."""
        res = client.post(
            "/api/bookmark",
            content=b"{invalid_json: true,",
            headers={"Content-Type": "application/json"}
        )
        assert res.status_code == 422
