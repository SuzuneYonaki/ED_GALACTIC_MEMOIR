"""Session-wide test setup.

Every addon ships with enabled_by_default=false (addons/*/addon.json),
so a clean checkout has none of them loaded -- correct for a real release,
but several existing tests exercise addon-provided code paths and expect them
loaded. This conftest isolates ALL test artifacts (DB_PATH, DATA_DIR,
EXPORTS_DIR, addon settings, and DEFAULT_JOURNAL_DIR) into disposable
temporary directories BEFORE importing app.db.database or app.server.api,
guaranteeing pytest never touches or locks the developer's real data/ files.
"""
import json
import os
import tempfile
from pathlib import Path

_scratch_dir = Path(tempfile.mkdtemp(prefix="ed_analyzer_test_env_"))
_test_data_dir = _scratch_dir / "data"
_test_exports_dir = _scratch_dir / "exports"
_test_journal_dir = _scratch_dir / "journals"
_test_data_dir.mkdir(parents=True, exist_ok=True)
_test_exports_dir.mkdir(parents=True, exist_ok=True)
_test_journal_dir.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("ED_DATA_DIR", str(_test_data_dir))
os.environ.setdefault("ED_EXPORTS_DIR", str(_test_exports_dir))
os.environ.setdefault("ED_JOURNAL_DIR", str(_test_journal_dir))

import app.config as _app_config  # noqa: E402

_app_config.DATA_DIR = _test_data_dir
_app_config.EXPORTS_DIR = _test_exports_dir
_app_config.DB_PATH = _test_data_dir / "elite_journal.db"
_app_config.DEFAULT_JOURNAL_DIR = _test_journal_dir

import app.db.database as _app_db  # noqa: E402

_app_db.DB_PATH = _app_config.DB_PATH
_app_db.init_db()

from app.addons import addon_manager  # noqa: E402

addon_manager.settings_path = _scratch_dir / "addons_settings.json"

_ALL_ADDON_IDS = [
    "edsm_sync",
    "spansh_sync",
    "tts",
    "export_share",
    "rarity_scorer",
    "exobiology_prediction",
]
addon_manager.settings_path.write_text(
    json.dumps({addon_id: True for addon_id in _ALL_ADDON_IDS}),
    encoding="utf-8",
)
addon_manager.discover()
addon_manager.load_enabled(_scratch_dir / "addons")
