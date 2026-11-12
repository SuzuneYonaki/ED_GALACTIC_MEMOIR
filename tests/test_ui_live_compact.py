import json
import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.server.api import app


def test_live_compact_assets_and_markup():
    root = Path(__file__).resolve().parent.parent
    client = TestClient(app)

    res_js = client.get("/js/live_compact.js")
    assert res_js.status_code == 200

    res_home = client.get("/")
    assert res_home.status_code == 200
    for marker in (
        "btn-live-compact",
        "btn-live-compact-left",
        "live-compact-hud-strip",
        "cb-live-compact-mode",
        "cb-live-compact-auto-panes",
        "/static/js/live_compact.js",
    ):
        assert marker in res_home.text

    css = (root / "app" / "ui" / "css" / "style.css").read_text(encoding="utf-8")
    assert "body.live-compact-active" in css
    assert ".live-compact-hud-strip" in css


def test_live_compact_js_execution_pane_restore_and_xss_safety():
    node = shutil.which("node")
    assert node is not None, "node is required to execute UI logic tests"

    root = Path(__file__).resolve().parent.parent
    for rel in (
        "app/ui/js/live_compact.js",
        "app/ui/js/app.js",
        "app/ui/js/system_list.js",
        "app/ui/js/i18n.js",
    ):
        chk = subprocess.run([node, "--check", str(root / rel)], capture_output=True, text=True)
        assert chk.returncode == 0, chk.stderr

    js_src = (root / "app" / "ui" / "js" / "live_compact.js").read_text(encoding="utf-8")

    harness = rf"""
const bodyClasses = new Set();
const strip = {{
  id: 'live-compact-hud-strip',
  style: {{ display: 'none' }},
  _html: '',
  children: [],
  set innerHTML(v) {{ this._html = String(v); if (!v) this.children = []; }},
  get innerHTML() {{ return this._html; }},
  appendChild(c) {{ this.children.push(c); return c; }}
}};
const ls = {{}};
const localStorage = {{
  getItem: k => (k in ls ? ls[k] : null),
  setItem: (k, v) => {{ ls[k] = String(v); }}
}};
const document = {{
  body: {{
    classList: {{
      toggle: (cls, force) => force ? bodyClasses.add(cls) : bodyClasses.delete(cls),
      contains: cls => bodyClasses.has(cls)
    }}
  }},
  addEventListener: () => {{}},
  getElementById: (id) => (id === 'live-compact-hud-strip' ? strip : null),
  createElement: (tag) => ({{
    tagName: String(tag).toUpperCase(),
    className: '',
    style: {{}},
    children: [],
    _text: '',
    appendChild(c) {{ this.children.push(c); return c; }},
    set textContent(v) {{ this._text = String(v); }},
    get textContent() {{ return this._text; }},
    addEventListener: () => {{}}
  }})
}};
let paneState = {{ left: false, right: false }};
const window = {{
  state: {{
    liveSyncEnabled: false,
    liveCompactEnabled: true,
    liveCompactAutoCollapse: true,
    jumpState: 'hyperspace',
    targetJumpSystem: '<img src=x onerror=alert(1)>',
    selectedSystem: {{ star_system: 'Sol', scanned_bodies: 2, total_bodies: 5 }},
    currentSystemData: {{
      system: {{ star_system: 'Sol', scanned_bodies: 2, total_bodies: 5 }},
      bodies: [
        {{ planet_class: 'Earthlike body', terraform_state: '', bio_signals: 0, landable: false }},
        {{ planet_class: 'High metal content body', terraform_state: 'Terraformable', bio_signals: 3, landable: true, surface_gravity_ms2: 39.24 }}
      ]
    }}
  }},
  getSidePanesCollapsed: () => ({{ ...paneState }}),
  setSidePanesCollapsed: (l, r) => {{ paneState = {{ left: Boolean(l), right: Boolean(r) }}; }},
  toggleLiveSync: () => {{ window.state.liveSyncEnabled = !window.state.liveSyncEnabled; window.syncLiveCompactModeUI(); }}
}};
const state = window.state;
eval({json.dumps(js_src)});

// 1. Live OFF + Compact Armed => not active, panes stay open
window.syncLiveCompactModeUI();
const step1Active = bodyClasses.has('live-compact-active');
const step1Panes = {{ ...paneState }};

// 2. Live ON => Compact activates, collapses panes, renders HUD summary pills cleanly
window.state.liveSyncEnabled = true;
window.syncLiveCompactModeUI();
const step2Active = bodyClasses.has('live-compact-active');
const step2Panes = {{ ...paneState }};
const step2Pills = strip.children.filter(c => c.tagName === 'SPAN').map(c => c.textContent);
const step2Tags = strip.children.map(c => c.tagName);

// 3. Pause Live => Compact deactivates and restores prior open panes
window.state.liveSyncEnabled = false;
window.syncLiveCompactModeUI();
const step3Active = bodyClasses.has('live-compact-active');
const step3Panes = {{ ...paneState }};

console.log(JSON.stringify({{
  step1Active, step1Panes,
  step2Active, step2Panes, step2Pills, step2Tags,
  step3Active, step3Panes
}}));
"""
    proc = subprocess.run([node, "-e", harness], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip())

    assert out["step1Active"] is False
    assert out["step1Panes"] == {"left": False, "right": False}

    assert out["step2Active"] is True
    assert out["step2Panes"] == {"left": True, "right": True}
    pills_joined = " | ".join(out["step2Pills"])
    assert "🔭 2/5" in pills_joined
    assert "🌍 ELW:1" in pills_joined
    assert "🌱 TF:1" in pills_joined
    assert "🦠 Bio:3 (1)" in pills_joined
    assert "⚠ High-G:1" in pills_joined
    assert "<img src=x onerror=alert(1)>" in pills_joined  # kept as safe plain text inside textContent
    assert out["step2Tags"] == ["SPAN"] * len(out["step2Pills"]) + ["DIV"]

    assert out["step3Active"] is False
    assert out["step3Panes"] == {"left": False, "right": False}
