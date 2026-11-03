from pathlib import Path


def test_header_period_i18n_support():
    root = Path(__file__).resolve().parent.parent
    i18n_js = (root / "app" / "ui" / "js" / "i18n.js").read_text(encoding="utf-8")
    app_js = (root / "app" / "ui" / "js" / "app.js").read_text(encoding="utf-8")

    # 1. Verify i18n dictionaries contain period keys
    assert 'stat_period_all: "全期間"' in i18n_js
    assert 'stat_period_all: "All Time"' in i18n_js
    assert 'stat_period_from_today: "{from} 〜 今日"' in i18n_js
    assert 'stat_period_from_today: "{from} ~ Today"' in i18n_js

    # 2. Verify app.js uses translation key instead of hardcoded '全期間'
    assert "t('stat_period_all')" in app_js
    assert "updateHeaderPeriodLabel" in app_js

    # 3. Ensure language change triggers period update
    assert "updateHeaderPeriodLabel();" in app_js


def test_header_jump_dist_tooltip_i18n():
    root = Path(__file__).resolve().parent.parent
    i18n_js = (root / "app" / "ui" / "js" / "i18n.js").read_text(encoding="utf-8")
    app_js = (root / "app" / "ui" / "js" / "app.js").read_text(encoding="utf-8")

    # 1. Verify i18n dictionaries contain jump distance tooltip keys
    assert 'tip_total_jump_dist: "🚀 累計ジャンプ距離:' in i18n_js
    assert 'tip_total_jump_dist: "🚀 Total Jump Distance:' in i18n_js
    assert 'tip_straight_jump_dist: "📏 直線距離:' in i18n_js
    assert 'tip_straight_jump_dist: "📏 Straight-Line Distance:' in i18n_js
    assert 'sys_initial_fallback: "初期星系"' in i18n_js
    assert 'sys_initial_fallback: "Initial System"' in i18n_js
    assert 'sys_current_fallback: "現在星系"' in i18n_js
    assert 'sys_current_fallback: "Current System"' in i18n_js

    # 2. Verify app.js uses translation keys for jump distance tooltips
    assert "t('tip_total_jump_dist'" in app_js
    assert "t('tip_straight_jump_dist'" in app_js
    assert "t('sys_initial_fallback')" in app_js
    assert "t('sys_current_fallback')" in app_js
