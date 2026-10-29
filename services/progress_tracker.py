import asyncio
import time
import logging
from typing import Optional
from telegram import Message
from telegram.constants import ParseMode
from telegram.error import TelegramError

from services.media_helper import media_helper

logger = logging.getLogger(__name__)

class ProgressTracker:
    def __init__(self, message: Message, platform: str = "Web", quality: str = "1080p FHD"):
        self.message = message
        self.platform = platform
        self.quality = quality
        
        self.stage = "analyzing"  # "analyzing", "downloading", "uploading", "done"
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.speed = 0.0
        self.eta = 0
        self.percent = 0.0
        
        self.is_active = True
        self.last_rendered_text = ""
        self.last_update_time = 0.0
        self.ticker_task: Optional[asyncio.Task] = None

    @staticmethod
    def render_bar(percent: float, length: int = 10) -> str:
        """Renders an attractive, modern block progress bar."""
        p = max(0.0, min(100.0, percent))
        filled = int(length * (p / 100.0))
        bar = "▰" * filled + "▱" * (length - filled)
        return f"[{bar}] {p:.1f}%"

    def render_content(self) -> str:
        """Constructs an eye-catching, professional status dashboard."""
        if self.stage == "analyzing":
            return (
                f"⚡ <b>Analyzing Media Stream</b>\n"
                f"🌐 <b>Platform:</b> <code>{self.platform}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<code>[▱▱▱▱▱▱▱▱▱▱] 0.0%</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔍 <i>Selecting best resolution & audio bitrate...</i>"
            )
        elif self.stage == "downloading":
            bar = self.render_bar(self.percent)
            speed_str = (media_helper.format_size(int(self.speed)) + "/s") if self.speed > 0 else "Calculating..."
            
            if self.total_bytes > 0:
                size_str = f"{media_helper.format_size(self.downloaded_bytes)} / {media_helper.format_size(self.total_bytes)}"
            elif self.downloaded_bytes > 0:
                size_str = media_helper.format_size(self.downloaded_bytes)
            else:
                size_str = "Connecting..."

            eta_str = media_helper.format_duration(self.eta) if self.eta > 0 else "00:00"

            return (
                f"📥 <b>Downloading {self.quality}</b>\n"
                f"🌐 <b>Platform:</b> <code>{self.platform}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<code>{bar}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⚡ <b>Speed:</b> <code>{speed_str}</code>\n"
                f"💾 <b>Size:</b> <code>{size_str}</code>\n"
                f"⏳ <b>ETA:</b> <code>{eta_str}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ <i>Streaming directly from origin CDN...</i>"
            )
        elif self.stage == "uploading":
            return (
                f"🚀 <b>Uploading to Telegram</b>\n"
                f"🌐 <b>Platform:</b> <code>{self.platform}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<code>[▰▰▰▰▰▰▰▰▰▰] 100.0%</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ <i>Generating preview thumbnail & sending...</i>"
            )
        return ""

    async def _ticker_loop(self):
        """Asynchronous background loop throttled to avoid Telegram flood limits."""
        while self.is_active:
            try:
                now = time.time()
                # Throttle updates to at least 1.2s to be gentle on Telegram Bot API
                if now - self.last_update_time >= 1.2:
                    current_text = self.render_content()
                    if current_text and current_text != self.last_rendered_text:
                        self.last_rendered_text = current_text
                        self.last_update_time = now
                        await self.message.edit_text(
                            text=current_text,
                            parse_mode=ParseMode.HTML
                        )
            except TelegramError as te:
                err_msg = str(te).lower()
                if "flood" in err_msg:
                    await asyncio.sleep(3.0)
                elif "message is not modified" in err_msg:
                    pass
                else:
                    logger.debug(f"Progress update notice: {te}")
            except Exception as e:
                logger.debug(f"Ticker error: {e}")

            await asyncio.sleep(0.6)

    def start(self):
        """Starts the background updater loop."""
        self.is_active = True
        self.ticker_task = asyncio.create_task(self._ticker_loop())

    async def stop(self):
        """Stops the background updater loop."""
        self.is_active = False
        if self.ticker_task:
            self.ticker_task.cancel()
            try:
                await self.ticker_task
            except asyncio.CancelledError:
                pass
            self.ticker_task = None

    def set_stage(self, stage: str, quality: Optional[str] = None):
        """Switches the current stage."""
        self.stage = stage
        if quality:
            self.quality = quality

    def yt_hook(self, d: dict):
        """Progress hook callback invoked by yt-dlp."""
        status = d.get("status")
        if status == "downloading":
            self.stage = "downloading"
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            
            # If fragment download (e.g. HLS / DASH)
            frag_index = d.get("fragment_index")
            frag_count = d.get("fragment_count")

            if total and total > 0:
                self.percent = (downloaded / total) * 100.0
                self.downloaded_bytes = downloaded
                self.total_bytes = total
            elif frag_index and frag_count:
                self.percent = (frag_index / frag_count) * 100.0
                self.downloaded_bytes = downloaded
                self.total_bytes = int(downloaded / (frag_index / frag_count)) if frag_index > 0 else 0
            elif downloaded > 0:
                self.downloaded_bytes = downloaded

            speed = d.get("speed")
            if speed:
                self.speed = float(speed)

            eta = d.get("eta")
            if eta:
                self.eta = int(eta)

        elif status == "finished":
            self.percent = 100.0
            self.stage = "uploading"

    def update_chunk(self, downloaded: int, total: int, speed: float = 0.0, eta: int = 0):
        """Manual chunk update for fallback streaming downloads."""
        self.stage = "downloading"
        self.downloaded_bytes = downloaded
        self.total_bytes = total
        if total > 0:
            self.percent = (downloaded / total) * 100.0
        self.speed = speed
        self.eta = eta

