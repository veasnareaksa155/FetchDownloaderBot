import logging
import asyncio
from pathlib import Path
from typing import Optional, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto
)
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ContextTypes

from config import CONCURRENT_DOWNLOADS
from services import (
    cache_service,
    tiktok_service,
    ytdlp_service,
    media_helper
)
from handlers.callbacks import register_url

logger = logging.getLogger(__name__)

# Concurrency semaphore
download_semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOADS)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming messages using ultra-fast cloud-direct delivery."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Record user in background (0ms delay)
    if user:
        asyncio.create_task(cache_service.record_user_activity(user.id, user.username, user.first_name))

    # Extract URL
    url = tiktok_service.extract_url(text) or ytdlp_service.extract_url(text)
    if not url:
        if update.message.chat.type == "private":
            greetings = {"hi", "hello", "hey", "hola", "start", "menu", "help", "halo", "yo", "greeting"}
            if text.lower().strip() in greetings:
                from handlers.commands import start_command
                await start_command(update, context)
                return

            first_name = user.first_name if user else "there"
            keyboard = [
                [
                    InlineKeyboardButton("📖 How to Use", callback_data="help_menu"),
                    InlineKeyboardButton("📊 Bot Stats", callback_data="stats_menu")
                ]
            ]
            await update.message.reply_text(
                f"👋 <b>Hi {first_name}!</b> Ready to download?\n\n"
                "Just send or paste any video link directly into this chat:\n"
                "• <b>TikTok</b> (HD Videos & Photo Slides)\n"
                "• <b>Instagram</b> (Reels, Posts & Stories)\n"
                "• <b>YouTube</b> (Shorts & Videos)\n"
                "• <b>Twitter/X & Facebook</b>\n\n"
                "⚡ <i>I will download and deliver it in seconds!</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

    # 1. Level 1: Sub-Second Cache Check (< 0.1s instant hit)
    cached = await cache_service.get_cached_media(url, media_type="video")
    if cached and cached.get("file_id"):
        short_hash = register_url(url, {
            "title": cached.get("title", ""),
            "author": "Creator",
            "duration": cached.get("duration", 0),
            "platform": ytdlp_service.detect_platform(url),
            "source_url": url
        })
        keyboard = [
            [
                InlineKeyboardButton("🎵 Audio (MP3)", callback_data=f"audio:{short_hash}"),
                InlineKeyboardButton("🔗 Source", url=url)
            ]
        ]
        try:
            await context.bot.send_video(
                chat_id=chat_id,
                video=cached["file_id"],
                caption=cached.get("caption") or "⚡ <b>Instant Delivery (Cached)</b>",
                parse_mode=ParseMode.HTML,
                duration=cached.get("duration", 0),
                width=cached.get("width", 0),
                height=cached.get("height", 0),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        except Exception as e:
            logger.warning(f"Cached file_id failed, will re-download: {e}")

    # 2. Native Telegram indicator (zero message spam, looks clean & instant)
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)

    # 3. Fast Cloud Delivery Pipeline
    async with download_semaphore:
        try:
            is_tiktok = tiktok_service.is_tiktok_url(url)
            platform = ytdlp_service.detect_platform(url)

            # --- TIKTOK ULTRA-FAST CLOUD PIPELINE ---
            if is_tiktok:
                handled = await process_tiktok_ultra(update, context, url)
                if handled:
                    return

            # --- UNIVERSAL ENGINE (Instagram, YouTube, Twitter/X, Facebook, etc.) ---
            await process_universal_ultra(update, context, url, platform)

        except Exception as e:
            logger.error(f"Error handling link {url}: {e}", exc_info=True)
            try:
                await update.message.reply_text(
                    "❌ <b>Download Error:</b> Unable to process this link. Please check if the video is private or deleted.",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass

async def process_tiktok_ultra(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str
) -> bool:
    """Direct cloud-pass TikTok downloader: 0-disk-overhead, sub-5-second delivery."""
    chat_id = update.effective_chat.id
    info = await tiktok_service.fetch_info(url)
    if not info:
        return False

    # Case A: TikTok Photo Carousel / Slideshow Post (Images ONLY, NO sound)
    if info.get("type") == "slides":
        images: List[str] = info.get("images", [])
        if not images:
            return False

        caption = media_helper.build_caption(
            title=info.get("title", "TikTok Photos"),
            author=info.get("author", "TikTok Creator"),
            platform="TikTok",
            source_url=url
        )

        # Single Photo
        if len(images) == 1:
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=images[0],
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
                return True
            except Exception as e:
                logger.warning(f"Direct photo URL failed: {e}")
                # Fallback to download single image
                img_path = await tiktok_service.download_file(images[0], suffix=".jpg")
                if img_path:
                    with open(img_path, "rb") as pf:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=InputFile(pf, filename="photo.jpg"),
                            caption=caption,
                            parse_mode=ParseMode.HTML
                        )
                    media_helper.cleanup_files(img_path)
                    return True

        # Multiple Photos (Media Group)
        try:
            # First attempt: Let Telegram fetch images directly from URLs (Fastest: < 3s!)
            media_group = [
                InputMediaPhoto(
                    media=img_url,
                    caption=caption if idx == 0 else None,
                    parse_mode=ParseMode.HTML if idx == 0 else None
                )
                for idx, img_url in enumerate(images[:10])
            ]
            await context.bot.send_media_group(chat_id=chat_id, media=media_group)
            return True
        except Exception as e:
            logger.warning(f"Direct image URLs failed, downloading locally: {e}")
            # Fallback to local image download
            temp_paths = []
            for img_url in images[:10]:
                p = await tiktok_service.download_file(img_url, suffix=".jpg")
                if p:
                    temp_paths.append(p)

            if temp_paths:
                file_handles = [open(p, "rb") for p in temp_paths]
                try:
                    local_group = [
                        InputMediaPhoto(
                            media=fh,
                            caption=caption if idx == 0 else None,
                            parse_mode=ParseMode.HTML if idx == 0 else None
                        )
                        for idx, fh in enumerate(file_handles)
                    ]
                    await context.bot.send_media_group(chat_id=chat_id, media=local_group)
                    return True
                finally:
                    for fh in file_handles:
                        fh.close()
                    media_helper.cleanup_files(*temp_paths)
        return False

    # Case B: Video Post
    video_url = info.get("video_url")
    if not video_url:
        return False

    caption = media_helper.build_caption(
        title=info.get("title", ""),
        author=info.get("author", "TikTok Creator"),
        duration=info.get("duration", 0),
        platform="TikTok",
        source_url=url
    )

    short_hash = register_url(url, {
        "title": info.get("title", ""),
        "author": info.get("author", "TikTok Creator"),
        "duration": info.get("duration", 0),
        "platform": "TikTok",
        "source_url": url,
        "music_url": info.get("music_url")
    })

    keyboard = [
        [
            InlineKeyboardButton("🎵 Audio (MP3)", callback_data=f"audio:{short_hash}"),
            InlineKeyboardButton("🔗 Source", url=url)
        ]
    ]

    # Speed Strategy 1: Direct Cloud Pass to Telegram (Telegram data center downloads CDN in 3s!)
    try:
        sent = await context.bot.send_video(
            chat_id=chat_id,
            video=video_url,
            caption=caption,
            parse_mode=ParseMode.HTML,
            duration=info.get("duration", 0),
            supports_streaming=True,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        if sent and sent.video:
            await cache_service.save_media(
                url=url,
                file_id=sent.video.file_id,
                file_type="video",
                title=info.get("title", ""),
                duration=info.get("duration", 0),
                caption=caption
            )
        return True
    except Exception as e:
        logger.info(f"Direct cloud pass failed ({e}), streaming locally...")

    # Speed Strategy 2: Stream Download with high concurrency & upload
    video_path = await tiktok_service.download_file(video_url, suffix=".mp4")
    if video_path and video_path.exists():
        try:
            with open(video_path, "rb") as vf:
                sent = await context.bot.send_video(
                    chat_id=chat_id,
                    video=InputFile(vf, filename="tiktok.mp4"),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    duration=info.get("duration", 0),
                    supports_streaming=True,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            if sent and sent.video:
                await cache_service.save_media(
                    url=url,
                    file_id=sent.video.file_id,
                    file_type="video",
                    title=info.get("title", ""),
                    duration=info.get("duration", 0),
                    caption=caption
                )
            return True
        finally:
            media_helper.cleanup_files(video_path)

    return False

async def process_universal_ultra(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    platform: str
):
    """Ultra-fast downloader for Instagram, YouTube, Twitter/X, Facebook, etc."""
    chat_id = update.effective_chat.id

    # 1. First check if it's an image post or direct video stream via fast metadata
    info = await ytdlp_service.extract_info(url)
    if info:
        # Check if photo post / carousel
        if info.get("_type") == "playlist" or (info.get("entries") and not info.get("url")):
            entries = list(info.get("entries", []))
            image_urls = [e.get("url") or e.get("thumbnail") for e in entries if e.get("url") or e.get("thumbnail")]
            if image_urls:
                caption = media_helper.build_caption(
                    title=info.get("title", "Photos"),
                    author=info.get("uploader") or info.get("creator"),
                    platform=platform,
                    source_url=url
                )
                try:
                    if len(image_urls) == 1:
                        await context.bot.send_photo(chat_id=chat_id, photo=image_urls[0], caption=caption, parse_mode=ParseMode.HTML)
                        return
                    else:
                        media_group = [
                            InputMediaPhoto(media=img, caption=caption if idx == 0 else None, parse_mode=ParseMode.HTML if idx == 0 else None)
                            for idx, img in enumerate(image_urls[:10])
                        ]
                        await context.bot.send_media_group(chat_id=chat_id, media=media_group)
                        return
                except Exception as e:
                    logger.warning(f"Direct universal image URLs failed: {e}")

    # 2. Video Download
    result = await ytdlp_service.download_video(url)
    if not result:
        await update.message.reply_text(
            f"❌ <b>Download Failed:</b> Could not retrieve video from {platform}.",
            parse_mode=ParseMode.HTML
        )
        return

    if result.get("error") == "file_too_large":
        await update.message.reply_text(
            "⚠️ <b>Video Exceeds Limit:</b> Larger than Telegram's 50MB limit.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Open in Browser", url=url)]])
        )
        return

    # Check if result is slides
    if result.get("type") == "slides":
        entries = result.get("entries", [])
        image_urls = [e.get("url") or e.get("thumbnail") for e in entries if e.get("url") or e.get("thumbnail")]
        if image_urls:
            caption = media_helper.build_caption(
                title=result.get("title", "Photos"),
                author=result.get("author", "Creator"),
                platform=platform,
                source_url=url
            )
            media_group = [
                InputMediaPhoto(media=img, caption=caption if idx == 0 else None, parse_mode=ParseMode.HTML if idx == 0 else None)
                for idx, img in enumerate(image_urls[:10])
            ]
            await context.bot.send_media_group(chat_id=chat_id, media=media_group)
            return

    # Deliver Video
    video_path: Path = result["file_path"]
    try:
        duration = result.get("duration", 0)
        width = result.get("width", 0)
        height = result.get("height", 0)

        caption = media_helper.build_caption(
            title=result.get("title", ""),
            author=result.get("author"),
            duration=duration,
            platform=platform,
            source_url=url
        )

        short_hash = register_url(url, {
            "title": result.get("title", ""),
            "author": result.get("author", platform),
            "duration": duration,
            "platform": platform,
            "source_url": url
        })

        keyboard = [
            [
                InlineKeyboardButton("🎵 Audio (MP3)", callback_data=f"audio:{short_hash}"),
                InlineKeyboardButton("🔗 Source", url=url)
            ]
        ]

        with open(video_path, "rb") as vf:
            sent = await context.bot.send_video(
                chat_id=chat_id,
                video=InputFile(vf, filename=f"{platform.lower()}_video.mp4"),
                caption=caption,
                parse_mode=ParseMode.HTML,
                duration=duration,
                width=width,
                height=height,
                supports_streaming=True,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        if sent and sent.video:
            await cache_service.save_media(
                url=url,
                file_id=sent.video.file_id,
                file_type="video",
                title=result.get("title", ""),
                duration=duration,
                width=width,
                height=height,
                caption=caption
            )
    finally:
        media_helper.cleanup_files(video_path)
