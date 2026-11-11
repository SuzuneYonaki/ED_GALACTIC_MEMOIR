import re
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


if __name__ == "__main__":
    unittest.main()
