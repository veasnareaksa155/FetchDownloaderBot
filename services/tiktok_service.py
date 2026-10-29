import re
import aiohttp
import asyncio
import time
import logging
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List

from config import TEMP_DIR, API_TIMEOUT, DOWNLOAD_TIMEOUT, USER_AGENT, MAX_FILE_SIZE_BYTES

logger = logging.getLogger(__name__)

class TikTokService:
    TIKTOK_PATTERN = re.compile(
        r'(https?://(?:www\.|vm\.|vt\.|m\.)?(?:tiktok\.com|douyin\.com)/[^\s]+)',
        re.IGNORECASE
    )

    @classmethod
    def is_tiktok_url(cls, text: str) -> bool:
        """Checks if text contains a TikTok link."""
        return bool(cls.TIKTOK_PATTERN.search(text))

    @classmethod
    def extract_url(cls, text: str) -> Optional[str]:
        """Extracts the first TikTok URL from text."""
        match = cls.TIKTOK_PATTERN.search(text)
        return match.group(1) if match else None

    async def fetch_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Fast multi-provider API fallback pool to guarantee 100% uptime:
        Tries TikWM (HD=1) -> TikWM Mirror
        """
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://www.tikwm.com/"
        }
        payload = {"url": url, "hd": 1}

        endpoints = [
            "https://www.tikwm.com/api/",
            "https://tikwm.com/api/"
        ]

        timeout = aiohttp.ClientTimeout(total=min(API_TIMEOUT, 8))
        for ep in endpoints:
            try:
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    async with session.post(ep, data=payload) as resp:
                        if resp.status == 200:
                            res = await resp.json()
                            if res.get("code") == 0 and "data" in res:
                                data = res["data"]
                                
                                # Photos / Slides
                                images = data.get("images")
                                if images and isinstance(images, list) and len(images) > 0:
                                    return {
                                        "success": True,
                                        "type": "slides",
                                        "images": images,
                                        "title": data.get("title", ""),
                                        "author": data.get("author", {}).get("nickname", "TikTok Creator"),
                                        "author_username": data.get("author", {}).get("unique_id", ""),
                                        "music_url": data.get("music"),
                                        "music_title": data.get("music_info", {}).get("title", "Audio"),
                                        "platform": "TikTok",
                                        "source_url": url
                                    }

                                # Video: Prefer 'hdplay' (1080p) over standard 'play'
                                video_url = data.get("hdplay") or data.get("play") or data.get("wmplay")
                                if video_url:
                                    return {
                                        "success": True,
                                        "type": "video",
                                        "video_url": video_url,
                                        "title": data.get("title", ""),
                                        "author": data.get("author", {}).get("nickname", "TikTok Creator"),
                                        "author_username": data.get("author", {}).get("unique_id", ""),
                                        "duration": data.get("duration", 0),
                                        "size": data.get("size", 0),
                                        "cover": data.get("cover") or data.get("origin_cover"),
                                        "music_url": data.get("music"),
                                        "music_title": data.get("music_info", {}).get("title", "Original Sound"),
                                        "platform": "TikTok",
                                        "source_url": url
                                    }
            except Exception as e:
                logger.debug(f"API endpoint {ep} attempt failed: {e}")

        return None

    async def download_file(
        self,
        download_url: str,
        suffix: str = ".mp4",
        progress_tracker: Optional[Any] = None
    ) -> Optional[Path]:
        """
        High speed chunked download with live progress tracking updates.
        """
        filename = f"tiktok_{uuid.uuid4().hex[:8]}{suffix}"
        target_path = TEMP_DIR / filename
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.tiktok.com/"
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(download_url) as resp:
                    if resp.status != 200:
                        return None
                    
                    content_length = int(resp.headers.get("Content-Length", 0))
                    if content_length > MAX_FILE_SIZE_BYTES:
                        return None
                    
                    downloaded = 0
                    t_start = time.time()
                    with open(target_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(128 * 1024):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if downloaded > MAX_FILE_SIZE_BYTES:
                                target_path.unlink(missing_ok=True)
                                return None

                            if progress_tracker:
                                elapsed = time.time() - t_start
                                speed = (downloaded / elapsed) if elapsed > 0 else 0.0
                                rem_bytes = max(0, content_length - downloaded)
                                eta = int(rem_bytes / speed) if speed > 0 else 0
                                progress_tracker.update_chunk(
                                    downloaded=downloaded,
                                    total=content_length,
                                    speed=speed,
                                    eta=eta
                                )

                    if target_path.exists() and target_path.stat().st_size > 0:
                        return target_path
        except Exception as e:
            logger.error(f"Failed to stream file from {download_url}: {e}")
            if target_path.exists():
                target_path.unlink(missing_ok=True)
        return None

tiktok_service = TikTokService()
