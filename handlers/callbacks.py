import logging
import asyncio
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from services import cache_service, tiktok_service, ytdlp_service, media_helper
from handlers.commands import help_command, stats_command, start_command

logger = logging.getLogger(__name__)

# Temporary in-memory dictionary to map short hash to source_url and metadata
# (Prevents Telegram 64-byte callback_data overflow)
URL_MAP = {}

def register_url(url: str, metadata: dict = None) -> str:
    url_hash = cache_service.get_url_hash(url)[:12]
    URL_MAP[url_hash] = {
        "url": url,
        "metadata": metadata or {}
    }
    return url_hash

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routes inline keyboard callback queries."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""

    if data == "help_menu":
        await help_command(update, context)
        return
    elif data == "stats_menu":
        await stats_command(update, context)
        return
    elif data == "start_menu":
        # Edit back to start menu
        welcome_text = (
            f"👋 <b>Welcome!</b>\n\n"
            "⚡ <b>Fast Video & Audio Downloader Bot Pro</b>\n"
            "I can download high-speed, watermark-free videos, music, and photo slides from your favorite platforms!\n\n"
            "🌐 <b>Supported Platforms:</b>\n"
            "• <b>TikTok</b> (No watermark HD, Audio MP3, Photo Slides)\n"
            "• <b>Instagram</b> (Reels, Posts, Carousels)\n"
            "• <b>YouTube</b> (Shorts & Videos)\n"
            "• <b>Twitter / X</b> (Videos & GIFs)\n"
            "• <b>Facebook</b> (Reels & Watch)\n"
            "• <b>Pinterest</b>, <b>Reddit</b>, <b>Threads</b> & more!\n\n"
            "🚀 <b>How to Use:</b>\n"
            "Simply copy and paste any video link into this chat. That's it!"
        )
        keyboard = [
            [
                InlineKeyboardButton("📖 Help & Tips", callback_data="help_menu"),
                InlineKeyboardButton("📊 Bot Stats", callback_data="stats_menu")
            ]
        ]
        await query.message.edit_text(
            text=welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
        return

    # Handle Audio Extraction: "audio:<hash>"
    if data.startswith("audio:"):
        short_hash = data.split(":", 1)[1]
        item = URL_MAP.get(short_hash)
        if not item:
            await query.message.reply_text("⚠️ Link session expired. Please resend the video link.")
            return

        source_url = item["url"]
        meta = item["metadata"]

        # Check Cache first!
        cached_audio = await cache_service.get_cached_media(source_url, media_type="audio")
        if cached_audio:
            await context.bot.send_audio(
                chat_id=query.message.chat_id,
                audio=cached_audio["file_id"],
                title=cached_audio.get("title") or meta.get("title", "Audio Track"),
                caption="🎵 <b>Instant Audio Delivery (Cached)</b>",
                parse_mode=ParseMode.HTML
            )
            return

        status_msg = await query.message.reply_text("🎵 <i>Extracting audio track...</i>", parse_mode=ParseMode.HTML)
        audio_file: Optional[Path] = None
        created_temp = False

        try:
            # Check if TikTok direct music url exists
            if meta.get("platform") == "TikTok" and meta.get("music_url"):
                audio_file = await tiktok_service.download_file(meta["music_url"], suffix=".mp3")
                created_temp = True
            
            # Fallback to ytdlp audio extractor
            if not audio_file or not audio_file.exists():
                res = await ytdlp_service.download_audio(source_url)
                if res and res.get("file_path"):
                    audio_file = res["file_path"]
                    created_temp = True

            if audio_file and audio_file.exists():
                with open(audio_file, "rb") as af:
                    title = meta.get("music_title") or meta.get("title") or "Audio Track"
                    performer = meta.get("author") or "TikTok"
                    sent_audio = await context.bot.send_audio(
                        chat_id=query.message.chat_id,
                        audio=InputFile(af, filename=f"{title[:40]}.mp3"),
                        title=title[:64],
                        performer=performer[:64],
                        caption=f"🎵 <b>{title}</b>\n👤 <i>{performer}</i>",
                        parse_mode=ParseMode.HTML
                    )
                    # Cache audio file_id
                    if sent_audio.audio:
                        await cache_service.save_media(
                            url=source_url,
                            file_id=sent_audio.audio.file_id,
                            file_type="audio",
                            title=title
                        )
                await status_msg.delete()
            else:
                await status_msg.edit_text("❌ Failed to extract audio. The audio track might be private or unavailable.")
        except Exception as e:
            logger.error(f"Error sending audio: {e}")
            await status_msg.edit_text("❌ An error occurred while extracting audio.")
        finally:
            if created_temp and audio_file:
                media_helper.cleanup_files(audio_file)

