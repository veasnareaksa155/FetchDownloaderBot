import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Workspace Base Directory
BASE_DIR = Path(__file__).resolve().parent

# Bot Credentials
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Admin user IDs (comma-separated list of integers in .env)
_admin_raw = os.getenv("ADMIN_USER_IDS", "").strip()
ADMIN_USER_IDS = [int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()]

# Directories
TEMP_DIR = BASE_DIR / "temp_media"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Database
DB_PATH = BASE_DIR / "bot_database.db"

# Limits & Concurrency
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
CONCURRENT_DOWNLOADS = int(os.getenv("CONCURRENT_DOWNLOADS", "5"))

# Request Timeouts (in seconds)
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "25"))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "120"))

# Auto-detect Node.js for yt-dlp JavaScript extraction (required for YouTube)
NODE_EXEC = shutil.which("node") or "node"

# User-Agent for downloads
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

