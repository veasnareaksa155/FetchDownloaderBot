import logging
import asyncio
import sys
import os
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from telegram.request import HTTPXRequest

# Reconfigure Windows console for UTF-8 emoji support
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import BOT_TOKEN
from services import cache_service
from handlers import (
    start_command,
    help_command,
    ping_command,
    stats_command,
    handle_callback,
    handle_message
)

# Prevent duplicate bot instances (fixes Telegram Conflict error)
_lock_file = None
def ensure_single_instance():
    global _lock_file
    lock_path = Path(__file__).resolve().parent / "bot.lock"
    try:
        _lock_file = open(lock_path, "w")
        import msvcrt
        msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except (IOError, OSError):
        print("\n" + "=" * 60)
        print(" [!] CONFLICT PREVENTED: Bot is ALREADY running in another window!")
        print(" Telegram only allows 1 bot instance at a time.")
        print(" Please close your other open terminal/cmd window first.")
        print("=" * 60 + "\n")
        sys.exit(1)

# Configure structured logging
logging.basicConfig(
    format="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
    level=logging.INFO
)
# Reduce verbose httpx logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("DownloaderBot")

async def post_init(application):
    """Initializes the database and caches on bot startup."""
    await cache_service.init_db()
    bot_info = await application.bot.get_me()
    logger.info(f"Bot successfully started as @{bot_info.username} (ID: {bot_info.id})")
    print(f"\n=======================================================")
    print(f"  ⚡ Pro Video Downloader Bot is RUNNING!")
    print(f"  🤖 Bot Username: @{bot_info.username}")
    print(f"  🚀 Ultra-fast concurrent updates enabled!")
    print(f"=======================================================\n")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Logs unexpected errors."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

def main():
    ensure_single_instance()

    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("\n" + "!" * 60)
        print(" [!] ERROR: Telegram BOT_TOKEN is missing or not configured!")
        print(" Please open the '.env' file and set:")
        print(" BOT_TOKEN=your_token_from_botfather")
        print("!" * 60 + "\n")
        sys.exit(1)

    # In Python 3.14+, get_event_loop() requires an active loop set for MainThread
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # High-Performance HTTP Request Configuration:
    # 64 persistent keep-alive connections eliminate TLS handshake delays
    request_client = HTTPXRequest(
        connection_pool_size=64,
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=60.0,
        media_write_timeout=180.0,
        pool_timeout=5.0
    )

    # Build Application with Concurrent Updates Enabled
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request_client)
        .concurrent_updates(True)  # Process all commands and messages concurrently!
        .post_init(post_init)
        .build()
    )

    # Command Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("stats", stats_command))

    # Callback Query Handler (for inline buttons)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Message Handler (for incoming links)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    # Error Handler
    app.add_error_handler(error_handler)

    # Start Polling
    logger.info("Starting bot polling with concurrent update pipeline...")
    app.run_polling(
        poll_interval=0.0,  # Zero delay between poll cycles for maximum responsiveness
        timeout=10,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()
