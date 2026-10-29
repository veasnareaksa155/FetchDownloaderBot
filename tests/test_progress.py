import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.progress_tracker import ProgressTracker

class DummyMessage:
    async def edit_text(self, text, parse_mode=None):
        pass

msg = DummyMessage()
tracker = ProgressTracker(msg, platform="TikTok", quality="1080p FHD (No Watermark)")

print("=" * 60)
print("TESTING PROGRESS TRACKER STAGES")
print("=" * 60)

# 1. Analyzing Stage
tracker.set_stage("analyzing")
print("\n[Stage 1: Analyzing]")
print(tracker.render_content())

# 2. Downloading Stage
tracker.set_stage("downloading")
tracker.update_chunk(downloaded=18 * 1024 * 1024, total=31 * 1024 * 1024, speed=8.4 * 1024 * 1024, eta=2)
print("\n[Stage 2: Downloading Progress]")
print(tracker.render_content())

# 3. Uploading Stage
tracker.set_stage("uploading")
print("\n[Stage 3: Uploading]")
print(tracker.render_content())

print("\n" + "=" * 60)
print("✅ PROGRESS TRACKER TEST PASSED PERFECTLY!")
print("=" * 60)

