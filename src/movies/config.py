"""Application configuration and dynamic runtime settings helper."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(ENV_PATH)


class Config:
    """Base Flask configuration."""

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "cinevault-alist-media-center-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{(DATA_DIR / 'cinevault.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_AS_ASCII = False


DEFAULT_SETTINGS = {
    "ALIST_URL": os.getenv("ALIST_URL", "http://localhost:5244"),
    "ALIST_USERNAME": os.getenv("ALIST_USERNAME", "admin"),
    "ALIST_PASSWORD": os.getenv("ALIST_PASSWORD", ""),
    "ALIST_SCAN_PATH": os.getenv("ALIST_SCAN_PATH", "/Quark/来自：分享"),
    "TMDB_TOKEN": os.getenv("TMDB_TOKEN", ""),
    "MDBLIST_APIKEY": os.getenv("MDBLIST_APIKEY", ""),
    "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
    "LLM_API_KEY": os.getenv("LLM_API_KEY", ""),
    "LLM_MODEL": os.getenv("LLM_MODEL", "deepseek-flash"),
    "LLM_API": os.getenv("LLM_API", "responses"),
    "MPC_HC_PATH": os.getenv("MPC_HC_PATH", r"C:\Program Files\MPC-HC\mpc-hc64.exe"),
}
