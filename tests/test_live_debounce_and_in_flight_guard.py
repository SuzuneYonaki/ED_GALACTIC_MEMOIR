import shutil
import subprocess
from pathlib import Path
import pytest


def test_live_journal_debounce_and_queue():
    """Verify that handleLiveJournalEvent debounces multiple burst Scan events,
    and selectSystem queues in-flight calls without concurrency corruption.
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
                querySelector: function(sel) {{
                    if (sel === '.ed-system-map-container') {{
                        return this.children.find(c => c.className === 'ed-system-map-container') || null;
                    }}
                    return null;
                }},
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

    eval(fs.readFileSync('{utils_path}', 'utf8'));
    eval(fs.readFileSync('{app_js_path}', 'utf8'));
    eval(fs.readFileSync('{js_path}', 'utf8'));

    const state = global.state;
    state.liveSyncEnabled = true;

    let fetchSystemCount = 0;
    let fetchSystemsListCount = 0;

    global.fetch = async function(url) {{
        if (url.includes('/api/system/')) {{
            fetchSystemCount++;
            // Simulate 20ms network latency
            await new Promise(r => setTimeout(r, 20));
            return {{
                ok: true,
                json: async () => ({{
                    system: {{ system_address: 12345, star_system: 'Test System' }},
                    bodies: [{{ body_id: 1, body_name: 'Body 1', is_star: 1 }}]
                }})
            }};
        }}
        if (url.includes('/api/systems')) {{
            fetchSystemsListCount++;
            return {{
                ok: true,
                json: async () => ({{ systems: [], total: 0 }})
            }};
        }}
        if (url.includes('/api/stats')) {{
            return {{ ok: true, json: async () => ({{}}) }};
        }}
        return {{ ok: true, json: async () => ({{}}) }};
    }};

    async function runTests() {{
        // Test 1: Fire burst of 15 Scan events in rapid succession (simulating FSS/DSS multi-body scan)
        for (let i = 0; i < 15; i++) {{
            global.handleLiveJournalEvent('Scan', {{ SystemAddress: 12345, StarSystem: 'Test System', BodyName: 'Body ' + i }});
        }}

        // Immediately after burst, fetch should NOT have fired 15 times
        if (fetchSystemCount > 1) {{
            console.error('FAIL: debounce failed, immediate calls fired:', fetchSystemCount);
            process.exit(1);
        }}

        // Wait 350ms for debounce timer (250ms) to trigger and settle
        await new Promise(r => setTimeout(r, 350));

        // After debounce, it should have batched into exactly 1 call!
        if (fetchSystemCount !== 1) {{
            console.error('FAIL: expected exactly 1 batched fetchSystem call after debounce, got:', fetchSystemCount);
            process.exit(1);
        }}

        // Test 2: In-flight queue guard for selectSystem
        fetchSystemCount = 0;
        const p1 = global.selectSystem(12345);
        const p2 = global.selectSystem(12345);
        const p3 = global.selectSystem(12345);
        await Promise.all([p1, p2, p3]);

        // First call started immediately, remaining 2 were coalesced into 1 queued execution -> total 2 calls
        if (fetchSystemCount > 2) {{
            console.error('FAIL: in-flight guard failed to coalesce concurrent selectSystem calls, got:', fetchSystemCount);
            process.exit(1);
        }}

        console.log('ALL_DEBOUNCE_TESTS_PASSED');
        process.exit(0);
    }}

    runTests().catch(err => {{
        console.error('Test error:', err);
        process.exit(1);
    }});
    """

    res = subprocess.run([node_exe, "-e", test_script], capture_output=True, text=True, timeout=10)
    assert res.returncode == 0, f"Node test failed:\nStdout: {res.stdout}\nStderr: {res.stderr}"
    assert "ALL_DEBOUNCE_TESTS_PASSED" in res.stdout
