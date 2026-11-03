import json
import shutil
import subprocess
from pathlib import Path
import pytest


def run_js_eval(expression, setup_code=""):
    node_exe = shutil.which("node")
    if not node_exe:
        pytest.skip("Node.js is not installed or not in PATH")

    utils_path = (Path(__file__).resolve().parent.parent / "app" / "ui" / "js" / "utils.js").as_posix()
    i18n_path = (Path(__file__).resolve().parent.parent / "app" / "ui" / "js" / "i18n.js").as_posix()

    runner_script = f"""
    global.window = global;
    const utilsMod = require('{utils_path}');
    const i18nMod = require('{i18n_path}');
    Object.assign(global, utilsMod);
    Object.assign(global, i18nMod);
    {setup_code}
    const result = ({expression});
    console.log(JSON.stringify(result));
    """
    proc = subprocess.run([node_exe, "-e", runner_script], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(proc.stdout)


def test_format_credits_unit_modes():
    val = 17359342937  # ~17.36 Billion / 173.59億

    # 1. Raw mode (full digits)
    raw_str = run_js_eval(f'formatCreditsUnit({val}, "raw")')
    assert "17,359,342,937 Cr" in raw_str

    # 2. MCr mode (Millions)
    mcr_str = run_js_eval(f'formatCreditsUnit({val}, "mcr")')
    assert "17,359.3 MCr" in mcr_str

    # 3. BCr mode (Billions)
    bcr_str = run_js_eval(f'formatCreditsUnit({val}, "bcr")')
    assert "17.36 BCr" in bcr_str

    # 4. Japanese mode (万・億)
    jp_str = run_js_eval(f'formatCreditsUnit({val}, "japanese")')
    assert "173.59億 Cr" in jp_str

    # Lower amount for Japanese mode (万)
    low_val = 5420000  # 542万
    jp_low = run_js_eval(f'formatCreditsUnit({low_val}, "japanese")')
    assert "542.0万 Cr" in jp_low

    # Even lower (< 1万)
    under_ten_k = 8500
    jp_under = run_js_eval(f'formatCreditsUnit({under_ten_k}, "japanese")')
    assert "8,500 Cr" in jp_under


def test_value_unit_settings_and_templates_integration():
    root = Path(__file__).resolve().parent.parent
    modals_html = (root / "app" / "ui" / "components" / "modals.html").read_text(encoding="utf-8")
    header_html = (root / "app" / "ui" / "components" / "header.html").read_text(encoding="utf-8")
    app_js = (root / "app" / "ui" / "js" / "app.js").read_text(encoding="utf-8")
    i18n_js = (root / "app" / "ui" / "js" / "i18n.js").read_text(encoding="utf-8")

    # 1. Header has stat-payout-container with click pointer
    assert 'id="stat-payout-container"' in header_html
    assert 'cursor: pointer;' in header_html

    # 2. Modals has setting-value-unit select with 4 options
    assert 'id="setting-value-unit"' in modals_html
    assert 'value="raw"' in modals_html
    assert 'value="mcr"' in modals_html
    assert 'value="bcr"' in modals_html
    assert 'value="japanese"' in modals_html

    # 3. app.js contains cycleValueUnitMode, getValueUnitMode, setValueUnitMode, updateHeaderValueDisplay
    assert 'function cycleValueUnitMode()' in app_js
    assert 'function getValueUnitMode()' in app_js
    assert 'function setValueUnitMode(' in app_js
    assert 'function updateHeaderValueDisplay(' in app_js

    # 4. i18n contains translation keys in both ja and en
    assert 'settings_value_unit_label:' in i18n_js
    assert 'tip_cycle_value_unit:' in i18n_js
    assert 'value_unit_japanese:' in i18n_js
