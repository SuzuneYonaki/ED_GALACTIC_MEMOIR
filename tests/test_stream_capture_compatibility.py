import os
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.server.api import app
import run


@pytest.fixture(autouse=True)
def clean_env():
    orig_env = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS")
    yield
    if orig_env is None:
        os.environ.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    else:
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = orig_env


def test_setup_webview_capture_flags_default():
    """Verify default capture flags always include occlusion disabling flags."""
    os.environ.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    run.setup_webview_capture_flags(stream_mode=False)

    flags = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    assert "--disable-features=CalculateNativeWinOcclusion" in flags
    assert "--disable-backgrounding-occluded-windows" in flags
    assert "--disable-gpu" not in flags
    assert "--disable-gpu-compositing" not in flags


def test_setup_webview_capture_flags_stream_mode():
    """Verify stream mode flags append GPU disabling flags for OBS compatibility."""
    os.environ.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    run.setup_webview_capture_flags(stream_mode=True)

    flags = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    assert "--disable-features=CalculateNativeWinOcclusion" in flags
    assert "--disable-backgrounding-occluded-windows" in flags
    assert "--disable-gpu" in flags
    assert "--disable-gpu-compositing" in flags


def test_setup_webview_capture_flags_merge_existing():
    """Verify flags merge cleanly without duplicates when pre-existing args exist."""
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--remote-debugging-port=9222"
    run.setup_webview_capture_flags(stream_mode=True)

    flags = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    assert "--remote-debugging-port=9222" in flags
    assert "--disable-features=CalculateNativeWinOcclusion" in flags
    assert "--disable-gpu" in flags


def test_module_settings_stream_capture_endpoint(tmp_path, monkeypatch):
    """Verify backend API properly returns and saves stream_capture_mode."""
    from app.server import api
    test_settings_file = tmp_path / "module_settings.json"
    monkeypatch.setattr(api, "MODULE_SETTINGS_FILE", test_settings_file)

    client = TestClient(app)
    # 1. Default settings
    resp = client.get("/api/module_settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "stream_capture_mode" in data
    assert data["stream_capture_mode"] is False

    # 2. Save stream_capture_mode = True
    resp_save = client.post("/api/module_settings", json={"stream_capture_mode": True, "exobiology": True})
    assert resp_save.status_code == 200
    assert resp_save.json()["settings"]["stream_capture_mode"] is True

    # 3. Read back
    resp2 = client.get("/api/module_settings")
    assert resp2.status_code == 200
    assert resp2.json()["stream_capture_mode"] is True


def test_ui_components_and_i18n_keys():
    """Verify UI modal contains cb-stream-capture-mode and i18n keys exist."""
    modals_html_path = Path(__file__).resolve().parent.parent / "app" / "ui" / "components" / "modals.html"
    i18n_js_path = Path(__file__).resolve().parent.parent / "app" / "ui" / "js" / "i18n.js"

    modals_html = modals_html_path.read_text(encoding="utf-8")
    assert 'id="cb-stream-capture-mode"' in modals_html
    assert 'data-module="stream_capture_mode"' in modals_html

    i18n_js = i18n_js_path.read_text(encoding="utf-8")
    assert "settings_stream_label" in i18n_js
    assert "mod_stream_capture" in i18n_js
    assert "stream_occlusion_notice" in i18n_js
