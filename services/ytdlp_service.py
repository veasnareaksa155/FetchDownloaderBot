import asyncio
import logging
import uuid
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

from config import (
    TEMP_DIR,
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    NODE_EXEC,
    USER_AGENT
)

logger = logging.getLogger(__name__)

class YtDlpService:
    GENERAL_URL_PATTERN = re.compile(
        r'(https?://[^\s]+)',
        re.IGNORECASE
    )

    def __init__(self):
        try:
            self.impersonate_target = ImpersonateTarget(client="chrome")
        except Exception as e:
            logger.warning(f"Could not initialize ImpersonateTarget: {e}")
            self.impersonate_target = None

    @staticmethod
    def detect_platform(url: str) -> str:
        url_lower = url.lower()
        if "tiktok.com" in url_lower or "douyin.com" in url_lower:
            return "TikTok"
        elif "instagram.com" in url_lower:
            return "Instagram"
        elif "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "YouTube"
        elif "twitter.com" in url_lower or "x.com" in url_lower:
            return "Twitter/X"
        elif "facebook.com" in url_lower or "fb.watch" in url_lower:
            return "Facebook"
        elif "pinterest.com" in url_lower or "pin.it" in url_lower:
            return "Pinterest"
        elif "reddit.com" in url_lower:
            return "Reddit"
        elif "threads.net" in url_lower:
            return "Threads"
        elif "twitch.tv" in url_lower:
            return "Twitch"
        elif "vimeo.com" in url_lower:
            return "Vimeo"
        return "Web Media"

    @classmethod
    def extract_url(cls, text: str) -> Optional[str]:
        match = cls.GENERAL_URL_PATTERN.search(text)
        return match.group(1) if match else None

    def _get_ydl_opts(
        self,
        out_template: str,
        url: str,
        is_audio_only: bool = False,
        progress_hook: Optional[Callable] = None
    ) -> dict:
        platform = self.detect_platform(url)

        opts = {
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "nocheckcertificate": True,
            "user_agent": USER_AGENT,
            "concurrent_fragment_downloads": 8,
            "buffersize": 64 * 1024,
            "js_runtimes": {"node": {}},
            "max_filesize": MAX_FILE_SIZE_BYTES,
            "retries": 3,
            "fragment_retries": 3,
        }

        if progress_hook:
            opts["progress_hooks"] = [progress_hook]

        if self.impersonate_target:
            opts["impersonate"] = self.impersonate_target

        if is_audio_only:
            opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                }],
            })
        else:
            if platform == "TikTok":
                opts.update({
                    "format": (
                        f"best[format_id!=download][ext=mp4][filesize<{MAX_FILE_SIZE_MB}M]/"
                        f"bestvideo[format_id!=download][filesize<{MAX_FILE_SIZE_MB}M]+bestaudio/"
                        f"best[format_id!=download][filesize<{MAX_FILE_SIZE_MB}M]/"
                        f"best[filesize<{MAX_FILE_SIZE_MB}M]/"
                        "best"
                    ),
                    "merge_output_format": "mp4",
                    "postprocessors": [{
                        "key": "FFmpegVideoConvertor",
                        "preferedformat": "mp4",
                    }],
                })
            else:
                opts.update({
                    "format": (
                        f"bestvideo[ext=mp4][filesize<{MAX_FILE_SIZE_MB}M]+bestaudio[ext=m4a]/"
                        f"bestvideo[filesize<{MAX_FILE_SIZE_MB}M]+bestaudio/"
                        f"best[ext=mp4][filesize<{MAX_FILE_SIZE_MB}M]/"
                        f"best[filesize<{MAX_FILE_SIZE_MB}M]/"
                        "best"
                    ),
                    "merge_output_format": "mp4",
                    "postprocessors": [{
                        "key": "FFmpegVideoConvertor",
                        "preferedformat": "mp4",
                    }],
                })

        return opts

    async def extract_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extracts media metadata without downloading."""
        def _extract():
            opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "js_runtimes": {"node": {}},
                "user_agent": USER_AGENT,
            }
            if self.impersonate_target:
                opts["impersonate"] = self.impersonate_target

            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, _extract)
        except Exception as e:
            logger.warning(f"Native extract_info error: {e}")
            return None

    async def download_video(
        self,
        url: str,
        progress_hook: Optional[Callable] = None
    ) -> Optional[Dict[str, Any]]:
        """Downloads the highest quality video with live progress updates."""
        unique_id = uuid.uuid4().hex[:8]
        out_template = str(TEMP_DIR / f"vid_{unique_id}.%(ext)s")
        opts = self._get_ydl_opts(out_template, url, is_audio_only=False, progress_hook=progress_hook)

        def _download():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None
                
                # Check if it's an image slideshow/carousel
                if info.get("_type") == "playlist" or (info.get("entries") and not info.get("url")):
                    entries = list(info.get("entries", []))
                    if entries:
                        return {
                            "type": "slides",
                            "entries": entries,
                            "title": info.get("title", ""),
                            "author": info.get("uploader") or info.get("creator"),
                            "platform": self.detect_platform(url),
                            "source_url": url
                        }

                downloaded_file = None
                if "requested_downloads" in info and info["requested_downloads"]:
                    downloaded_file = info["requested_downloads"][0].get("filepath")
                
                if not downloaded_file or not Path(downloaded_file).exists():
                    downloaded_file = ydl.prepare_filename(info)
                    mp4_path = Path(downloaded_file).with_suffix(".mp4")
                    if mp4_path.exists():
                        downloaded_file = str(mp4_path)

                return {
                    "type": "video",
                    "file_path": Path(downloaded_file),
                    "title": info.get("title", "Video"),
                    "author": info.get("uploader") or info.get("channel") or info.get("creator"),
                    "duration": int(info.get("duration") or 0),
                    "width": int(info.get("width") or 0),
                    "height": int(info.get("height") or 0),
                    "resolution": info.get("resolution") or (f"{info.get('width')}x{info.get('height')}" if info.get('width') else None),
                    "platform": self.detect_platform(url),
                    "source_url": url,
                    "thumbnail_url": info.get("thumbnail")
                }

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, _download)
            if not result:
                return None

            if result.get("type") == "slides":
                return result

            fpath: Path = result.get("file_path")
            if fpath and fpath.exists() and fpath.stat().st_size > 0:
                if fpath.stat().st_size > MAX_FILE_SIZE_BYTES:
                    logger.warning(f"File {fpath} exceeded Telegram limit ({fpath.stat().st_size} bytes)")
                    fpath.unlink(missing_ok=True)
                    return {"error": "file_too_large"}
                return result
        except yt_dlp.utils.MaxDownloadsReached:
            logger.error("Max downloads reached.")
        except Exception as e:
            logger.error(f"Native direct download failed for {url}: {e}")
            if "File is larger than max-filesize" in str(e):
                return {"error": "file_too_large"}

        return None

    async def download_audio(
        self,
        url: str,
        progress_hook: Optional[Callable] = None
    ) -> Optional[Dict[str, Any]]:
        """Extracts and downloads only audio as high quality 320kbps MP3."""
        unique_id = uuid.uuid4().hex[:8]
        out_template = str(TEMP_DIR / f"audio_{unique_id}.%(ext)s")
        opts = self._get_ydl_opts(out_template, url, is_audio_only=True, progress_hook=progress_hook)

        def _download_audio():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None
                
                expected_mp3 = TEMP_DIR / f"audio_{unique_id}.mp3"
                if not expected_mp3.exists():
                    downloaded_file = ydl.prepare_filename(info)
                    p = Path(downloaded_file).with_suffix(".mp3")
                    if p.exists():
                        expected_mp3 = p

                return {
                    "file_path": expected_mp3,
                    "title": info.get("title", "Audio Track"),
                    "author": info.get("uploader") or info.get("channel"),
                    "duration": int(info.get("duration") or 0),
                    "platform": self.detect_platform(url),
                    "source_url": url
                }

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, _download_audio)
            if result and result["file_path"].exists() and result["file_path"].stat().st_size > 0:
                return result
        except Exception as e:
            logger.error(f"Native audio download failed for {url}: {e}")
        return None

ytdlp_service = YtDlpService()
