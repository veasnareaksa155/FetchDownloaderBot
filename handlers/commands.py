import time
import asyncio
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ADMIN_USER_IDS, TEMP_DIR
from services import cache_service

BOT_START_TIME = time.time()

# Pre-cached welcome & help keyboards for instant dispatch
START_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📖 Help & Tips", callback_data="help_menu"),
        InlineKeyboardButton("📊 Bot Stats", callback_data="stats_menu")
    ]
])

BACK_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Back to Menu", callback_data="start_menu")]
])

WELCOME_TEXT_TEMPLATE = (
    "👋 <b>Welcome, {name}!</b>\n\n"
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
    "Simply paste any video link into this chat. That's it!"
)

HELP_TEXT = (
    "💡 <b>Downloader Bot Help & Tips</b>\n\n"
    "<b>1. Downloading Videos:</b>\n"
    "Just send any link directly. The bot automatically detects the platform and downloads the highest quality available.\n\n"
    "<b>2. Audio / MP3 Extraction:</b>\n"
    "After downloading a video, click the <b>🎵 Audio (MP3)</b> button below it to receive just the audio track!\n\n"
    "<b>3. TikTok Slides / Photos:</b>\n"
    "TikTok photo carousel posts are automatically sent as a photo album with the original background song attached!\n\n"
    "<b>4. Telegram Size Limit:</b>\n"
    "Standard Telegram bots support files up to <b>50 MB</b>. If a video is larger, the bot selects an optimized format within 50MB.\n\n"
    "<b>Available Commands:</b>\n"
    "• /start - Welcome menu\n"
    "• /help - Instructions & guide\n"
    "• /ping - Check bot response speed\n"
    "• /stats - View statistics"
)

def get_uptime() -> str:
    uptime_seconds = int(time.time() - BOT_START_TIME)
    days, rem = divmod(uptime_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    return f"{minutes}m {seconds}s"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command with zero-delay reply."""
    user = update.effective_user
    if user:
        # Fire-and-forget: do not wait for DB write before answering the user!
        asyncio.create_task(cache_service.record_user_activity(user.id, user.username, user.first_name))

    first_name = user.first_name if user else "there"
    welcome_text = WELCOME_TEXT_TEMPLATE.format(name=first_name)

    await update.message.reply_text(
        text=welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=START_KEYBOARD,
        disable_web_page_preview=True
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command instantly."""
    if update.callback_query:
        await update.callback_query.message.edit_text(
            text=HELP_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=BACK_KEYBOARD
        )
    else:
        await update.message.reply_text(
            text=HELP_TEXT,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /ping command to measure latency in real-time."""
    t0 = time.perf_counter()
    msg = await update.message.reply_text("🏓 <i>Pinging...</i>", parse_mode=ParseMode.HTML)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    await msg.edit_text(
        f"⚡ <b>Pong!</b> Response latency: <code>{latency_ms} ms</code>\n🚀 <i>Ultra-fast concurrent pipeline active.</i>",
        parse_mode=ParseMode.HTML
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /stats command."""
    stats = await cache_service.get_stats()
    uptime = get_uptime()
    
    # Calculate temp disk space usage
    temp_size_bytes = sum(f.stat().st_size for f in TEMP_DIR.glob("*") if f.is_file())
    from services.media_helper import media_helper
    temp_size_str = media_helper.format_size(temp_size_bytes)

    stats_text = (
        "📊 <b>Bot Performance & Statistics</b>\n\n"
        f"⏱ <b>Uptime:</b> {uptime}\n"
        f"👥 <b>Total Users:</b> {stats.get('total_users', 0)}\n"
        f"📥 <b>Total Downloads:</b> {stats.get('total_downloads', 0)}\n"
        f"⚡ <b>Instant Cache Hits:</b> {stats.get('cache_hits', 0)}\n"
        f"💾 <b>Cached Items:</b> {stats.get('cached_items', 0)}\n"
        f"📁 <b>Temp Storage:</b> {temp_size_str}\n\n"
        "<i>Instant caching ensures identical links are served in &lt; 0.2s!</i>"
    )

    if update.callback_query:
        await update.callback_query.message.edit_text(
            text=stats_text,
            parse_mode=ParseMode.HTML,
            reply_markup=BACK_KEYBOARD
        )
    else:
        await update.message.reply_text(
            text=stats_text,
            parse_mode=ParseMode.HTML
        )
