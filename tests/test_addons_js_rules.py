from pathlib import Path


def test_addons_js_toast_pointer_events_and_rules():
    js_path = Path("app/ui/js/addons.js")
    assert js_path.exists(), "addons.js must exist"
    content = js_path.read_text(encoding="utf-8")

    # 1. Verify /api/tts_settings is NOT monitored for disabled toasts
    assert "p === '/api/tts_settings'" not in content, "Internal tts_settings endpoint should not trigger disabled toasts"
    assert "p.startsWith('/api/tts/')" in content, "Direct /api/tts/ actions should trigger disabled toasts"

    # 2. Verify pointer-events: none is set on the toast
    assert "pointerEvents = 'none'" in content, "Toast must have pointerEvents = 'none' to avoid blocking card clicks"

    # 3. Verify display: none is set after fade out
    assert "display = 'none'" in content, "Toast must be hidden (display: none) after fade timeout"
