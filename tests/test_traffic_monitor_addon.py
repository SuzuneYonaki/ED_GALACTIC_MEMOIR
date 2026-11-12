import importlib.util
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.addons.manager import AddonManager
from app.db.database import init_db
from app.server.api import app

ROOT = Path(__file__).resolve().parent.parent
ADDON_DIR = ROOT / "addons" / "traffic_monitor"


def _load_traffic_addon_module():
    spec = importlib.util.spec_from_file_location("traffic_monitor_addon_test", ADDON_DIR / "addon.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_traffic_monitor_manifest_defaults_and_discovery(tmp_path):
    manifest = json.loads((ADDON_DIR / "addon.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "traffic_monitor"
    assert manifest["enabled_by_default"] is False
    assert manifest["requires_network"] is True

    mgr = AddonManager(addons_dir=ROOT / "addons", settings_path=tmp_path / "addons_settings.json")
    mgr.discover()
    assert mgr.is_enabled("traffic_monitor") is False

    res = TestClient(app).get("/api/addons")
    assert res.status_code == 200
    items = {a["id"]: a for a in res.json()["data"]}
    assert "traffic_monitor" in items
    assert items["traffic_monitor"]["requires_network"] is True


def test_traffic_cache_sync_and_api_routes(tmp_path, monkeypatch):
    mod = _load_traffic_addon_module()
    test_db = tmp_path / "test_traffic.db"

    def mock_conn():
        conn = sqlite3.connect(str(test_db), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    conn = mock_conn()
    init_db(conn, force=True)
    conn.execute(
        "INSERT INTO systems (system_address, star_system, visit_count) VALUES (?, ?, ?)",
        (10477373803, "Sol", 5),
    )
    conn.commit()

    # Before any sync, cache is empty and zero HTTP requests occur
    calls = []
    monkeypatch.setattr(mod.requests, "get", lambda *a, **kw: calls.append((a, kw)))
    assert mod.get_cached_traffic(conn, 10477373803) == {"cached": False, "system_address": 10477373803}
    assert calls == []
    conn.close()

    # Register addon router onto an isolated FastAPI test instance
    monkeypatch.setattr(mod, "get_db_connection", mock_conn)
    monkeypatch.setattr(mod, "REQUEST_DELAY_SEC", 0.0)

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "name": "Sol",
                "traffic": {"total": 123456, "week": 1234, "day": 123},
                "breakdown": {"Anaconda": 50, "Asp Explorer": 80, "IgnoredZero": 0},
            },
        )

    monkeypatch.setattr(mod.requests, "get", fake_get)

    iso_app = FastAPI()

    class _Ctx:
        def add_api_router(self, router, prefix=""):
            iso_app.include_router(router, prefix=prefix)

    mod.register(_Ctx())
    client = TestClient(iso_app)

    # Cache GET stays strictly offline
    r_pre = client.get("/api/systems/10477373803/traffic")
    assert r_pre.status_code == 200
    assert r_pre.json()["cached"] is False
    assert calls == []

    # Manual POST sync queries EDSM and caches result
    r_sync = client.post("/api/systems/10477373803/traffic_sync")
    assert r_sync.status_code == 200
    body = r_sync.json()
    assert body["status"] == "ok"
    assert body["total"] == 123456
    assert body["week"] == 1234
    assert body["day"] == 123
    assert body["breakdown"] == [
        {"ship": "Asp Explorer", "count": 80},
        {"ship": "Anaconda", "count": 50},
    ]
    assert len(calls) == 1
    assert calls[0][1] == {"systemName": "Sol"}

    # Subsequent GET serves SQLite cache without network call
    r_cached = client.get("/api/systems/10477373803/traffic")
    assert r_cached.status_code == 200
    assert r_cached.json()["cached"] is True
    assert r_cached.json()["total"] == 123456
    assert len(calls) == 1

    # Unknown system_address returns 404
    assert client.post("/api/systems/999999/traffic_sync").status_code == 404

    # Upstream failure returns 502 cleanly
    def failing_get(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(mod.requests, "get", failing_get)
    r_err = client.post("/api/systems/10477373803/traffic_sync")
    assert r_err.status_code == 502
    assert r_err.json()["status"] == "error"


def test_traffic_monitor_ui_gating_and_xss_safety():
    client = TestClient(app)
    assert client.get("/js/traffic_monitor.js").status_code == 200

    home = client.get("/").text
    assert "btn-sync-traffic" in home
    assert "current-system-traffic-badge" in home
    assert 'data-requires-addon="traffic_monitor"' in home
    assert "/static/js/traffic_monitor.js" in home

    css = (ROOT / "app" / "ui" / "css" / "style.css").read_text(encoding="utf-8")
    assert 'body.addon-off-traffic_monitor [data-requires-addon="traffic_monitor"]' in css

    node = shutil.which("node")
    assert node is not None
    for rel in (
        "app/ui/js/traffic_monitor.js",
        "app/ui/js/addons.js",
        "app/ui/js/system_list.js",
        "app/ui/js/i18n.js",
    ):
        chk = subprocess.run([node, "--check", str(ROOT / rel)], capture_output=True, text=True)
        assert chk.returncode == 0, chk.stderr

    js_src = (ROOT / "app" / "ui" / "js" / "traffic_monitor.js").read_text(encoding="utf-8")
    harness = rf"""
let fetches = [];
const badge = {{
  id: 'current-system-traffic-badge',
  style: {{ display: 'none' }},
  textContent: '',
  title: ''
}};
const document = {{
  addEventListener: () => {{}},
  getElementById: (id) => (id === 'current-system-traffic-badge' ? badge : null)
}};
const window = {{
  __addonsInitialized: true,
  __disabledAddons: {{ traffic_monitor: 'Traffic Monitor' }},
  state: {{ selectedSystem: {{ system_address: 10477373803, star_system: 'Sol' }} }}
}};
async function fetch(url) {{
  fetches.push(url);
  return {{
    ok: true,
    json: async () => ({{
      cached: true,
      total: 42,
      week: 7,
      day: 1,
      breakdown: [{{ ship: '<img src=x onerror=alert(1)>', count: 3 }}],
      fetched_at: '2026-11-12T00:00:00Z'
    }})
  }};
}}
eval({json.dumps(js_src)});

(async () => {{
  // 1. Disabled addon => zero fetch calls, badge stays hidden
  await window.refreshTrafficMonitorBadge();
  const disabledFetches = fetches.length;
  const disabledDisplay = badge.style.display;

  // 2. Enabled addon => fetches cache and assigns textContent/title safely
  window.__disabledAddons = {{}};
  await window.refreshTrafficMonitorBadge();
  console.log(JSON.stringify({{
    disabledFetches,
    disabledDisplay,
    enabledFetches: fetches,
    enabledDisplay: badge.style.display,
    badgeText: badge.textContent,
    badgeTitle: badge.title
  }}));
}})();
"""
    proc = subprocess.run([node, "-e", harness], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip())
    assert out["disabledFetches"] == 0
    assert out["disabledDisplay"] == "none"
    assert out["enabledFetches"] == ["/api/systems/10477373803/traffic"]
    assert out["enabledDisplay"] == "inline-flex"
    assert "42" in out["badgeText"]
    assert "<img src=x onerror=alert(1)>" in out["badgeTitle"]
