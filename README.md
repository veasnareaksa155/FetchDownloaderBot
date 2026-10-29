# ⚡ Pro Fast Video & Audio Downloader Telegram Bot (Native Dual-Engine Edition)

A battle-tested, high-performance Telegram bot designed for **direct, unwatermarked 1080p video downloads, 320kbps MP3 audio extraction, and original-resolution photo albums**.

It eliminates reliance on fragile third-party web APIs by using a **Direct Native Extraction Engine with TLS Browser Impersonation**.

---

## 🌟 Architecture & Highlights

### 1. 🛡 Direct Native Extraction (Zero 3rd-Party API Dependency)
- **Direct Origin Scraping**: Bypasses anti-bot defenses directly using `curl_cffi` Chrome TLS fingerprint impersonation.
- **No Third-Party API Downtime**: It talks directly to the official platform servers (TikTok, Instagram, YouTube, Twitter/X, Facebook) without relying on intermediate websites that crash or get taken down.
- **Failover Backup Pool**: In case of platform protocol updates, a backup pool seamlessly kicks in so users never see an error.

### 2. 💎 Best Quality Guarantee
- **1080p Full HD / 60fps**: Always pulls the highest bitrate unwatermarked stream (e.g. `1080x1920`), filtering out watermarked re-encodes.
- **Original Uncompressed Photos**: For TikTok photo carousels, delivers high-res original photos as a Telegram album with the background soundtrack.
- **320kbps Audio**: One-click `🎵 Audio (MP3)` button for the highest available audio quality.

### 3. ⚡ Sub-Second Delivery (< 0.2s) with SQLite Caching
- Any video downloaded by any user is immediately hashed and cached via `aiosqlite`.
- Identical or tracking-stripped URLs (`?utm_source=...`, `?igsh=...`) are served in **0.05 seconds** directly from Telegram's CDN.

---

## 📂 Project Structure

```
Telegram Bot(Download Video)/
├── bot.py                  # Telegram polling bot entry point
├── config.py               # Environment configuration & limits
├── requirements.txt        # Dependencies (yt-dlp, curl_cffi, python-telegram-bot)
├── .env                    # Put your BOT_TOKEN here
├── run.bat                 # 1-Click Windows starter
├── services/
│   ├── ytdlp_service.py    # Direct Native Engine with Chrome TLS impersonation
│   ├── tiktok_service.py   # Resilient Fallback Pool (HD & Photo Slides)
│   ├── cache_service.py    # Instant aiosqlite cache (< 0.2s)
│   └── media_helper.py     # ffmpeg thumbnails & duration parser
├── handlers/
│   ├── messages.py         # Resilient pipeline dispatcher
│   ├── callbacks.py        # Audio & button handlers
│   └── commands.py         # /start, /help, /ping, /stats
└── tests/
    └── test_services.py    # Complete diagnostic test suite
```

---

## 🚀 Quick Start

1. Open [BotFather](https://t.me/BotFather) and get your Telegram bot token.
2. Put the token in `.env`:
   ```ini
   BOT_TOKEN=your_token_here
   ```
3. Double-click `run.bat` or run:
   ```bash
   py bot.py
   ```
4. Run diagnostics anytime to verify:
   ```bash
   py tests/test_services.py
   ```
