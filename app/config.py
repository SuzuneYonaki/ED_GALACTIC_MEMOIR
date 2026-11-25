import os
import sys
from pathlib import Path

APP_VERSION = "0.9.7"

# PyInstaller one-file extraction support
if getattr(sys, 'frozen', False):
    EXE_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', EXE_DIR))
    DATA_DIR = EXE_DIR / "data"
    EXPORTS_DIR = EXE_DIR / "exports"
    ADDONS_DIR = EXE_DIR / "addons"
else:
    RESOURCE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = RESOURCE_DIR / "data"
    EXPORTS_DIR = RESOURCE_DIR / "exports"
    ADDONS_DIR = RESOURCE_DIR / "addons"

BASE_DIR = RESOURCE_DIR
DATA_DIR.mkdir(exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
ADDONS_DIR.mkdir(exist_ok=True)

# Separate WebView2 cache completely from user DATA_DIR to prevent locks and bloat
local_app_data = os.environ.get("LOCALAPPDATA")
if local_app_data:
    WEBVIEW_CACHE_DIR = Path(local_app_data) / "ED_Journal_Analyzer" / "webview_cache"
else:
    import tempfile
    WEBVIEW_CACHE_DIR = Path(tempfile.gettempdir()) / "ED_Journal_Analyzer" / "webview_cache"
WEBVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "elite_journal.db"

# Default Elite Dangerous Journal Directory on Windows (detect normal or OneDrive redirected paths)
def _resolve_default_journal_dir() -> Path:
    candidates = [
        Path(os.path.expanduser("~/Saved Games/Frontier Developments/Elite Dangerous")),
        Path(os.path.expanduser("~/OneDrive/Saved Games/Frontier Developments/Elite Dangerous")),
    ]
    best_dir = candidates[0]
    best_mtime = -1.0
    for cand in candidates:
        if cand.exists() and cand.is_dir():
            try:
                logs = list(cand.glob("Journal.*.log"))
                if logs:
                    latest = max(logs, key=lambda p: p.stat().st_mtime)
                    mtime = latest.stat().st_mtime
                    if mtime > best_mtime:
                        best_mtime = mtime
                        best_dir = cand
                elif best_mtime < 0 and cand.exists():
                    best_dir = cand
            except Exception:
                pass
    return best_dir

DEFAULT_JOURNAL_DIR = _resolve_default_journal_dir()

# Server Config
HOST = "127.0.0.1"
PORT = 8686
