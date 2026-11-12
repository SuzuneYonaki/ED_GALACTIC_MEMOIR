import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app.server.api import app


class TestUIGlobalSearch(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent

    def test_html_components_and_script_inclusion(self):
        lp = (self.root / "app" / "ui" / "components" / "left_pane.html").read_text(encoding="utf-8")
        self.assertIn('id="btn-open-fulltext-search"', lp)

        modals = (self.root / "app" / "ui" / "components" / "modals.html").read_text(encoding="utf-8")
        for el_id in [
            'id="modal-global-search"',
            'id="global-search-input"',
            'id="global-search-categories"',
            'id="global-search-results"',
            'id="btn-global-search-rebuild"',
            'id="btn-global-search-more"',
        ]:
            self.assertIn(el_id, modals)

        idx = (self.root / "app" / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('/static/js/global_search.js', idx)

    def test_global_search_js_no_shortcuts_and_xss_safe_dom(self):
        js_path = self.root / "app" / "ui" / "js" / "global_search.js"
        self.assertTrue(js_path.exists())
        js = js_path.read_text(encoding="utf-8")

        # Must not register global shortcut keys (per user request)
        self.assertNotIn("ctrlKey", js)
        self.assertNotIn("metaKey", js)

        # Must use switchCenterPaneView('sysmap') / selectSystem / renderBodyInspector
        self.assertIn("switchCenterPaneView", js)
        self.assertIn("'sysmap'", js)
        self.assertIn("selectSystem", js)
        self.assertIn("renderBodyInspector", js)

        # Must construct highlighted DOM safely via createTextNode
        self.assertIn("document.createTextNode", js)

    def test_css_and_i18n_keys_symmetry(self):
        css = (self.root / "app" / "ui" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("mark.search-hl", css)
        self.assertIn(".global-search-item", css)

        i18n_txt = (self.root / "app" / "ui" / "js" / "i18n.js").read_text(encoding="utf-8")
        required_keys = [
            "btn_open_fulltext_search",
            "btn_open_fulltext_search_tip",
            "global_search_title",
            "global_search_placeholder",
            "global_search_syntax_hint",
            "global_search_rebuild_btn",
            "global_search_rebuild_tip",
            "global_search_cat_all",
            "global_search_cat_bookmark",
            "global_search_cat_system",
            "global_search_cat_body",
            "global_search_cat_bio",
            "global_search_cat_mining",
            "global_search_cat_codex",
            "global_search_cat_station",
            "global_search_cat_physics",
            "global_search_empty_prompt",
            "global_search_no_results",
            "global_search_count_fmt",
            "global_search_load_more",
        ]
        for key in required_keys:
            matches = re.findall(rf"^\s*{key}:", i18n_txt, flags=re.MULTILINE)
            self.assertEqual(len(matches), 2, f"Expected key '{key}' in both ja and en, found {len(matches)}")

    def test_static_serving_of_global_search_assets(self):
        client = TestClient(app)
        res_js = client.get("/js/global_search.js")
        self.assertEqual(res_js.status_code, 200)
        res_home = client.get("/")
        self.assertEqual(res_home.status_code, 200)
        self.assertIn("modal-global-search", res_home.text)

    def test_global_search_js_syntax_and_dom_xss_execution(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node binary not available")

        for rel in ("app/ui/js/global_search.js", "app/ui/js/i18n.js"):
            proc = subprocess.run([node, "--check", str(self.root / rel)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)

        js_src = (self.root / "app" / "ui" / "js" / "global_search.js").read_text(encoding="utf-8")
        # Extract appendSafeHighlightedNodes and execute in Node with a mock DOM recording all nodes
        harness = rf"""
const created = [];
const document = {{
  addEventListener: () => {{}},
  getElementById: () => null,
  createTextNode: (t) => {{
    const n = {{ nodeType: 3, text: String(t) }};
    created.push(n);
    return n;
  }},
  createElement: (tag) => {{
    const el = {{
      nodeType: 1,
      tagName: String(tag).toUpperCase(),
      className: '',
      _text: '',
      children: [],
      appendChild(c) {{ this.children.push(c); return c; }},
      set textContent(v) {{ this._text = String(v); }},
      get textContent() {{ return this._text; }}
    }};
    created.push(el);
    return el;
  }}
}};
const window = {{}};
const src = {json.dumps(js_src)};
const match = src.match(/function appendSafeHighlightedNodes\([\s\S]*?\n  \}}/);
if (!match) throw new Error('appendSafeHighlightedNodes not found');
const fn = new Function('document', match[0] + '; return appendSafeHighlightedNodes;')(document);
const parent = document.createElement('div');
const payload = '&lt;script&gt;<mark class="search-hl">alert</mark>(&quot;xss&quot;)&lt;/script&gt;&lt;img src=x onerror=alert(1)&gt;';
fn(parent, payload, '');
const tags = parent.children.filter(c => c.nodeType === 1).map(c => c.tagName);
const texts = parent.children.map(c => c.nodeType === 3 ? c.text : `[MARK:${{c.textContent}}]`);
console.log(JSON.stringify({{ tags, texts }}));
"""
        proc = subprocess.run([node, "-e", harness], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout.strip())
        # Only MARK elements should ever be created inside parent; all script/img tags stay inert text nodes
        self.assertEqual(data["tags"], ["MARK"])
        self.assertIn("[MARK:alert]", data["texts"])
        self.assertTrue(any("<script>" in t for t in data["texts"]))
        self.assertTrue(any("<img src=x onerror=alert(1)>" in t for t in data["texts"]))


if __name__ == "__main__":
    unittest.main()
