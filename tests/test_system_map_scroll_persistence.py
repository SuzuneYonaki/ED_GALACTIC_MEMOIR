import json
import shutil
import subprocess
from pathlib import Path
import pytest


def test_system_map_scroll_persistence_logic():
    """Verify that System Map scroll position and zoom level are preserved during same-system updates,
    and reset when switching to a different star system.
    """
    node_exe = shutil.which("node")
    if not node_exe:
        pytest.skip("Node.js is not installed or not in PATH")

    js_path = (Path(__file__).resolve().parent.parent / "app" / "ui" / "js" / "system_map.js").as_posix()
    app_js_path = (Path(__file__).resolve().parent.parent / "app" / "ui" / "js" / "app.js").as_posix()
    utils_path = (Path(__file__).resolve().parent.parent / "app" / "ui" / "js" / "utils.js").as_posix()

    test_script = f"""
    const fs = require('fs');

    // Mock minimal browser DOM environment
    global.window = global;
    global.window.addEventListener = function() {{}};
    global.window.removeEventListener = function() {{}};
    global.localStorage = {{
        getItem: function() {{ return null; }},
        setItem: function() {{}}
    }};
    global.requestAnimationFrame = function(cb) {{
        cb();
    }};
    global.t = function(k) {{ return k; }};

    const elementsById = {{}};
    global.document = {{
        getElementById: function(id) {{
            return elementsById[id] || null;
        }},
        addEventListener: function() {{}},
        removeEventListener: function() {{}},
        querySelector: function() {{ return null; }},
        querySelectorAll: function() {{ return []; }},
        createElement: function(tag) {{
            const listeners = {{}};
            return {{
                tagName: tag,
                className: '',
                classList: {{
                    add: function(cls) {{}},
                    remove: function(cls) {{}},
                    toggle: function(cls, val) {{}}
                }},
                style: {{}},
                dataset: {{}},
                children: [],
                parentElement: null,
                scrollLeft: 0,
                scrollTop: 0,
                clientWidth: 800,
                clientHeight: 600,
                getBoundingClientRect: function() {{
                    return {{ left: 0, top: 0, width: 800, height: 600 }};
                }},
                appendChild: function(c) {{
                    c.parentElement = this;
                    this.children.push(c);
                    return c;
                }},
                querySelector: function(sel) {{
                    if (sel === '.ed-system-map-container') {{
                        return this.children.find(c => c.className === 'ed-system-map-container') || null;
                    }}
                    return null;
                }},
                querySelectorAll: function() {{ return []; }},
                closest: function(sel) {{ return this; }},
                setAttribute: function(k, v) {{ this[k] = v; }},
                addEventListener: function(evt, handler) {{
                    listeners[evt] = listeners[evt] || [];
                    listeners[evt].push(handler);
                }},
                _fire: function(evt, data) {{
                    if (listeners[evt]) {{
                        listeners[evt].forEach(h => h(data || {{}}));
                    }}
                }}
            }};
        }}
    }};

    // Setup map-content container
    const mapContent = global.document.createElement('div');
    mapContent.id = 'map-content';
    elementsById['map-content'] = mapContent;

    // Load scripts via eval to simulate global browser scope
    eval(fs.readFileSync('{utils_path}', 'utf8'));
    eval(fs.readFileSync('{app_js_path}', 'utf8'));
    eval(fs.readFileSync('{js_path}', 'utf8'));

    const state = global.state;

    // 1. Initial State Check
    if (state.sysmapZoom !== 1.0) {{
        console.error('FAIL: sysmapZoom should initialize to 1.0, got', state.sysmapZoom);
        process.exit(1);
    }}

    // Simulate system 123456
    state.selectedSystem = {{
        system_address: 123456,
        star_system: 'Col 285 Sector Test'
    }};
    state.sysmapZoom = 1.35;

    // Render system map into container
    const bodies = [
        {{ body_id: 0, body_name: 'Col 285 Sector Test A', body_type: 'Star', star_type: 'G', distance_ls: 0 }}
    ];
    renderSystemMapView(mapContent, [], bodies);

    const mapWrapper = mapContent.querySelector('.ed-system-map-container');
    if (!mapWrapper) {{
        console.error('FAIL: mapWrapper not created');
        process.exit(1);
    }}

    // Simulate user scroll/pan
    mapWrapper.scrollLeft = 450;
    mapWrapper.scrollTop = 220;
    mapWrapper._fire('scroll');

    if (!state.sysmapScroll || state.sysmapScroll.scrollLeft !== 450 || state.sysmapScroll.scrollTop !== 220) {{
        console.error('FAIL: state.sysmapScroll not updated on scroll event:', state.sysmapScroll);
        process.exit(1);
    }}

    // Test saveCurrentSysmapScroll helper
    mapWrapper.scrollLeft = 500;
    mapWrapper.scrollTop = 300;
    saveCurrentSysmapScroll();
    if (state.sysmapScroll.scrollLeft !== 500 || state.sysmapScroll.scrollTop !== 300) {{
        console.error('FAIL: saveCurrentSysmapScroll failed:', state.sysmapScroll);
        process.exit(1);
    }}

    // 2. Simulate re-render of the SAME system (e.g. DSS scan event, memoir update)
    renderSystemMapView(mapContent, [], bodies);
    const newMapWrapper = mapContent.querySelector('.ed-system-map-container');
    if (newMapWrapper.scrollLeft !== 500 || newMapWrapper.scrollTop !== 300) {{
        console.error('FAIL: scroll position was not restored on same system re-render! got:', newMapWrapper.scrollLeft, newMapWrapper.scrollTop);
        process.exit(1);
    }}
    if (state.sysmapZoom !== 1.35) {{
        console.error('FAIL: zoom level was not preserved! got:', state.sysmapZoom);
        process.exit(1);
    }}

    // 3. Test selectSystem behavior with mock fetch
    global.fetch = async function(url) {{
        if (url.includes('123456')) {{
            return {{
                json: async () => ({{
                    system: {{ system_address: 123456, star_system: 'Col 285 Sector Test' }},
                    bodies: bodies
                }})
            }};
        }} else if (url.includes('999999')) {{
            return {{
                json: async () => ({{
                    system: {{ system_address: 999999, star_system: 'Another Star System' }},
                    bodies: bodies
                }})
            }};
        }}
        throw new Error('Unknown URL: ' + url);
    }};

    async function runAsyncTests() {{
        // Same system update: selectSystem(123456)
        await selectSystem(123456);
        if (state.sysmapZoom !== 1.35) {{
            console.error('FAIL: selectSystem reset sysmapZoom on same system update! got:', state.sysmapZoom);
            process.exit(1);
        }}
        if (!state.sysmapScroll || state.sysmapScroll.scrollLeft !== 500) {{
            console.error('FAIL: selectSystem reset sysmapScroll on same system update! got:', state.sysmapScroll);
            process.exit(1);
        }}

        // Switching to different system: selectSystem(999999)
        await selectSystem(999999);
        if (state.sysmapZoom !== 1.0) {{
            console.error('FAIL: selectSystem should reset sysmapZoom to 1.0 when changing system! got:', state.sysmapZoom);
            process.exit(1);
        }}
        if (state.sysmapScroll !== null) {{
            console.error('FAIL: selectSystem should reset sysmapScroll to null when changing system! got:', state.sysmapScroll);
            process.exit(1);
        }}

        console.log('ALL_PERSISTENCE_TESTS_PASSED');
    }}

    runAsyncTests().catch(err => {{
        console.error('Test error:', err);
        process.exit(1);
    }});
    """

    res = subprocess.run([node_exe, "-e", test_script], capture_output=True, text=True)
    assert res.returncode == 0, f"Node test failed:\nStdout: {res.stdout}\nStderr: {res.stderr}"
    assert "ALL_PERSISTENCE_TESTS_PASSED" in res.stdout
