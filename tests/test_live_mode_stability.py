import shutil
import subprocess
from pathlib import Path
import pytest


def test_live_mode_jump_tracking_and_honk_guard():
    """Verify that Live Mode automatically switches to CMDR location,
    avoids blocking with honk placeholder if bodies already exist,
    and updates immediately on toggle.
    """
    node_exe = shutil.which("node")
    if not node_exe:
        pytest.skip("Node.js is not installed or not in PATH")

    js_path = (Path(__file__).resolve().parent.parent / "app" / "ui" / "js" / "system_map.js").as_posix()
    app_js_path = (Path(__file__).resolve().parent.parent / "app" / "ui" / "js" / "app.js").as_posix()
    utils_path = (Path(__file__).resolve().parent.parent / "app" / "ui" / "js" / "utils.js").as_posix()

    test_script = f"""
    const fs = require('fs');

    global.window = global;
    global.window.location = {{ protocol: 'http:', host: '127.0.0.1:8686' }};
    global.window.addEventListener = function() {{}};
    global.window.removeEventListener = function() {{}};
    global.localStorage = {{
        getItem: function() {{ return null; }},
        setItem: function() {{}}
    }};
    global.requestAnimationFrame = function(cb) {{ cb(); }};
    global.t = function(k) {{ return k; }};

    const elementsById = {{}};
    global.document = {{
        getElementById: function(id) {{ return elementsById[id] || null; }},
        addEventListener: function() {{}},
        removeEventListener: function() {{}},
        querySelector: function() {{ return null; }},
        querySelectorAll: function() {{ return []; }},
        createElement: function(tag) {{
            return {{
                tagName: tag,
                className: '',
                classList: {{ add: function() {{}}, remove: function() {{}}, toggle: function() {{}} }},
                style: {{}},
                dataset: {{}},
                children: [],
                parentElement: null,
                scrollLeft: 0,
                scrollTop: 0,
                appendChild: function(c) {{ this.children.push(c); return c; }},
                querySelector: function() {{ return null; }},
                querySelectorAll: function() {{ return []; }},
                closest: function() {{ return this; }},
                setAttribute: function() {{}},
                addEventListener: function() {{}}
            }};
        }}
    }};

    const mapContent = global.document.createElement('div');
    mapContent.id = 'map-content';
    elementsById['map-content'] = mapContent;

    const btnLive = global.document.createElement('button');
    btnLive.id = 'btn-live-toggle';
    elementsById['btn-live-toggle'] = btnLive;

    const liveText = global.document.createElement('span');
    liveText.id = 'live-status-text';
    elementsById['live-status-text'] = liveText;

    eval(fs.readFileSync('{utils_path}', 'utf8'));
    eval(fs.readFileSync('{app_js_path}', 'utf8'));
    eval(fs.readFileSync('{js_path}', 'utf8'));

    const state = global.state;

    let selectedSystemAddr = null;
    global.selectSystem = async function(addr) {{
        selectedSystemAddr = addr;
        state.selectedSystem = {{ system_address: addr, star_system: 'Sys ' + addr }};
    }};

    global.fetch = async function(url) {{
        if (url.includes('/api/stats')) {{
            return {{
                ok: true,
                json: async () => ({{
                    current_location: {{ system_address: 777888, star_system: 'Eol Prou Live-1' }}
                }})
            }};
        }}
        if (url.includes('/api/systems')) {{
            return {{
                ok: true,
                json: async () => ({{
                    systems: [{{ system_address: 777888, star_system: 'Eol Prou Live-1' }}],
                    total: 1,
                    current_location: {{ system_address: 777888, star_system: 'Eol Prou Live-1' }}
                }})
            }};
        }}
        return {{ ok: true, json: async () => ({{}}) }};
    }};

    async function runTests() {{
        // Test 1: toggleLiveSync immediately loads CMDR location from /api/stats
        state.liveSyncEnabled = false;
        await global.toggleLiveSync();

        if (!state.liveSyncEnabled) {{
            console.error('FAIL: liveSyncEnabled should be true after toggle');
            process.exit(1);
        }}
        if (state.currentCmdrSystemAddress !== 777888) {{
            console.error('FAIL: currentCmdrSystemAddress not updated from stats, got:', state.currentCmdrSystemAddress);
            process.exit(1);
        }}
        if (selectedSystemAddr !== 777888) {{
            console.error('FAIL: selectSystem was not called with CMDR location on toggle, got:', selectedSystemAddr);
            process.exit(1);
        }}

        // Test 2: Honk guard test: if system already has bodies, renderCurrentView does NOT block with placeholder
        state.jumpState = 'arrived_waiting_fss';
        state.currentSystemData = {{
            system: {{ system_address: 777888, star_system: 'Eol Prou Live-1' }},
            bodies: [{{ body_id: 0, body_name: 'Star A', is_star: 1 }}]
        }};
        global.renderCurrentView();

        // Container should NOT contain jump-status-placeholder because bodies are known
        if (mapContent.innerHTML && mapContent.innerHTML.includes('jump-status-placeholder')) {{
            console.error('FAIL: arrived_waiting_fss placeholder should not block view when bodies already exist');
            process.exit(1);
        }}

        // Test 3: If no bodies exist yet, placeholder IS shown
        state.currentSystemData = {{
            system: {{ system_address: 777888, star_system: 'Eol Prou Live-1' }},
            bodies: []
        }};
        global.renderCurrentView();
        if (!mapContent.innerHTML || !mapContent.innerHTML.includes('jump-status-placeholder')) {{
            console.error('FAIL: arrived_waiting_fss placeholder should be shown when 0 bodies exist');
            process.exit(1);
        }}

        console.log('ALL_LIVE_STABILITY_TESTS_PASSED');
        process.exit(0);
    }}

    runTests().catch(err => {{
        console.error('Test error:', err);
        process.exit(1);
    }});
    """

    res = subprocess.run([node_exe, "-e", test_script], capture_output=True, text=True, timeout=10)
    assert res.returncode == 0, f"Node test failed:\nStdout: {res.stdout}\nStderr: {res.stderr}"
    assert "ALL_LIVE_STABILITY_TESTS_PASSED" in res.stdout
