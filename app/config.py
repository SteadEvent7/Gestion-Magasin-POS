import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _default_app_data_dir() -> Path:
    # In packaged installs (Program Files), write data in ProgramData by default.
    if getattr(sys, "frozen", False):
        program_data = Path(os.getenv("PROGRAMDATA", r"C:\ProgramData"))
        return program_data / "GestionMagasinPOS"
    return Path.cwd()


APP_DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(_default_app_data_dir())))
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").strip().lower() or "sqlite"
_sqlite_db_env = (os.getenv("SQLITE_DB_PATH") or "").strip()
SQLITE_DB_PATH = Path(_sqlite_db_env) if _sqlite_db_env else (APP_DATA_DIR / "gestion_magasin.db")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "gestion_magasin"),
}

APP_TITLE = os.getenv("APP_TITLE", "Gestion Magasin POS")
APP_VERSION = os.getenv("APP_VERSION", "1.0.2")
APP_PATCH = _int_env("APP_PATCH", 8)
APP_UPDATE_URL = os.getenv("APP_UPDATE_URL", "https://raw.githubusercontent.com/SteadEvent7/Gestion-Magasin-POS/main/update.json")
BACKUPS_DIR = APP_DATA_DIR / "backups"
EXPORTS_DIR = APP_DATA_DIR / "exports"
LOGS_DIR = APP_DATA_DIR / "logs"
