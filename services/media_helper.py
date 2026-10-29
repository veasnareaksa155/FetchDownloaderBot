import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

class MediaHelper:
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Formats bytes into human readable string (KB, MB, GB)."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    @staticmethod
    def format_duration(seconds: int) -> str:
        """Formats seconds into MM:SS or HH:MM:SS."""
        if not seconds or seconds < 0:
            return "00:00"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @staticmethod
    async def get_video_info(video_path: Path) -> Dict[str, Any]:
        """Uses ffprobe to extract width, height, and duration of a video file."""
        info = {"width": 0, "height": 0, "duration": 0}
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path)
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                data = json.loads(stdout.decode("utf-8", errors="ignore"))
                # Duration from format
                fmt_dur = data.get("format", {}).get("duration")
                if fmt_dur:
                    try:
                        info["duration"] = int(float(fmt_dur))
                    except (ValueError, TypeError):
                        pass

                # Dimensions from video stream
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        info["width"] = int(stream.get("width", 0))
                        info["height"] = int(stream.get("height", 0))
                        if not info["duration"]:
                            try:
                                info["duration"] = int(float(stream.get("duration", 0)))
                            except (ValueError, TypeError):
                                pass
                        break
        except Exception as e:
            logger.warning(f"ffprobe extraction failed for {video_path}: {e}")
        return info

    @staticmethod
    async def generate_thumbnail(video_path: Path, output_thumb: Optional[Path] = None) -> Optional[Path]:
        """Extracts a high quality frame from the video at 1s to use as Telegram preview thumbnail."""
        if output_thumb is None:
            output_thumb = video_path.with_suffix(".thumb.jpg")

        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", "00:00:01",
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", "scale='min(640,iw)':-1",
                "-q:v", "2",
                str(output_thumb)
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if output_thumb.exists() and output_thumb.stat().st_size > 0:
                return output_thumb
            
            # Fallback to 00:00:00 if 1s failed (e.g. very short video)
            cmd[3] = "00:00:00"
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if output_thumb.exists() and output_thumb.stat().st_size > 0:
                return output_thumb
        except Exception as e:
            logger.warning(f"Thumbnail generation failed: {e}")
        return None

    @staticmethod
    async def convert_video_to_mp3(video_path: Path, output_mp3: Optional[Path] = None) -> Optional[Path]:
        """Extracts audio track from video as high quality 192k MP3."""
        if output_mp3 is None:
            output_mp3 = video_path.with_suffix(".mp3")

        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-vn",
                "-acodec", "libmp3lame",
                "-q:a", "2",
                str(output_mp3)
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if output_mp3.exists() and output_mp3.stat().st_size > 0:
                return output_mp3
        except Exception as e:
            logger.error(f"MP3 conversion error: {e}")
        return None

    @staticmethod
    def cleanup_files(*paths):
        """Safely removes temporary files."""
        for p in paths:
            if not p:
                continue
            try:
                path_obj = Path(p)
                if path_obj.is_file():
                    path_obj.unlink(missing_ok=True)
                elif path_obj.is_dir():
                    import shutil
                    shutil.rmtree(path_obj, ignore_errors=True)
            except Exception as e:
                logger.debug(f"Failed to delete {p}: {e}")

    @staticmethod
    def build_caption(
        title: str,
        author: Optional[str] = None,
        duration: int = 0,
        platform: str = "TikTok",
        source_url: str = ""
    ) -> str:
        """Formats a clean, eye-catching caption for Telegram media."""
        caption_lines = []
        
        # Clean title
        if title:
            clean_title = title.strip()
            if len(clean_title) > 300:
                clean_title = clean_title[:297] + "..."
            caption_lines.append(f"🎬 <b>{clean_title}</b>\n")
        
        # Details
        details = []
        if author:
            details.append(f"👤 <b>Author:</b> {author}")
        if duration > 0:
            details.append(f"⏱ <b>Duration:</b> {MediaHelper.format_duration(duration)}")
        if platform:
            details.append(f"🌐 <b>Platform:</b> {platform}")
        
        if details:
            caption_lines.append("\n".join(details))
        
        caption_lines.append("\n⚡ <i>Downloaded via Pro Video Downloader Bot</i>")
        return "\n".join(caption_lines)

media_helper = MediaHelper()

