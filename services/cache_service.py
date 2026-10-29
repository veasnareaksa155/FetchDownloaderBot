import hashlib
import re
import aiosqlite
import logging
from typing import Optional, Dict, Any
from config import DB_PATH

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    async def init_db(self):
        """Initializes tables for media caching, statistics, and users with high-performance WAL mode."""
        async with aiosqlite.connect(self.db_path) as db:
            # High-performance SQLite pragmas
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA cache_size=-64000;")  # 64MB RAM cache
            await db.execute("PRAGMA temp_store=MEMORY;")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS media_cache (
                    url_hash TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    title TEXT,
                    duration INTEGER DEFAULT 0,
                    width INTEGER DEFAULT 0,
                    height INTEGER DEFAULT 0,
                    caption TEXT,
                    hits INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    total_requests INTEGER DEFAULT 1,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS global_stats (
                    key TEXT PRIMARY KEY,
                    value INTEGER DEFAULT 0
                )
            """)
            for key in ("total_downloads", "cache_hits", "failed_requests"):
                await db.execute(
                    "INSERT OR IGNORE INTO global_stats (key, value) VALUES (?, 0)",
                    (key,)
                )
            await db.commit()

    @staticmethod
    def normalize_url(url: str) -> str:
        """Strips query trackers (utm, igsh, si, etc.) to maximize cache hit rate."""
        cleaned = re.sub(r'[\?&](utm_[^&]+|igsh=[^&]+|si=[^&]+|feature=[^&]+|t=[^&]+|share=[^&]+)', '', url)
        cleaned = cleaned.rstrip('?').rstrip('/')
        return cleaned.strip()

    @classmethod
    def get_url_hash(cls, url: str, media_type: str = "video") -> str:
        norm = cls.normalize_url(url)
        return hashlib.sha256(f"{norm}::{media_type}".encode("utf-8")).hexdigest()

    async def get_cached_media(self, url: str, media_type: str = "video") -> Optional[Dict[str, Any]]:
        """Checks if media has already been sent to Telegram and returns its file_id in < 1ms."""
        url_hash = self.get_url_hash(url, media_type)
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM media_cache WHERE url_hash = ?", (url_hash,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        await db.execute(
                            "UPDATE media_cache SET hits = hits + 1 WHERE url_hash = ?",
                            (url_hash,)
                        )
                        await db.execute(
                            "UPDATE global_stats SET value = value + 1 WHERE key = 'cache_hits'"
                        )
                        await db.commit()
                        return dict(row)
        except Exception as e:
            logger.error(f"Error fetching cached media: {e}")
        return None

    async def save_media(
        self,
        url: str,
        file_id: str,
        file_type: str = "video",
        title: str = "",
        duration: int = 0,
        width: int = 0,
        height: int = 0,
        caption: str = ""
    ):
        """Saves telegram file_id to the cache for instant future reuse."""
        url_hash = self.get_url_hash(url, file_type)
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO media_cache (url_hash, file_id, file_type, title, duration, width, height, caption)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url_hash) DO UPDATE SET
                        file_id = excluded.file_id,
                        hits = hits + 1
                """, (url_hash, file_id, file_type, title, duration, width, height, caption))
                await db.execute(
                    "UPDATE global_stats SET value = value + 1 WHERE key = 'total_downloads'"
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error saving media to cache: {e}")

    async def record_user_activity(self, user_id: int, username: Optional[str], first_name: Optional[str]):
        """Records user request activity in background."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO users (user_id, username, first_name, total_requests, last_seen)
                    VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name,
                        total_requests = total_requests + 1,
                        last_seen = CURRENT_TIMESTAMP
                """, (user_id, username or "", first_name or ""))
                await db.commit()
        except Exception as e:
            logger.error(f"Error recording user activity: {e}")

    async def get_stats(self) -> Dict[str, Any]:
        """Returns statistics for admin /stats command."""
        stats = {
            "total_downloads": 0,
            "cache_hits": 0,
            "cached_items": 0,
            "total_users": 0
        }
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT key, value FROM global_stats") as cur:
                    rows = await cur.fetchall()
                    for k, v in rows:
                        stats[k] = v

                async with db.execute("SELECT COUNT(*) FROM media_cache") as cur:
                    row = await cur.fetchone()
                    stats["cached_items"] = row[0] if row else 0

                async with db.execute("SELECT COUNT(*) FROM users") as cur:
                    row = await cur.fetchone()
                    stats["total_users"] = row[0] if row else 0
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
        return stats

cache_service = CacheService()
