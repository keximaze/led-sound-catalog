#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def get_bundled_ffmpeg():
    """Get path to bundled FFmpeg or system FFmpeg."""
    import os
    import sys
    from pathlib import Path
    import platform
    # Check if running as bundled app
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        bundle_dir = Path(sys._MEIPASS if hasattr(sys, "_MEIPASS") else sys.executable).parent
        # Check for ffmpeg / ffmpeg.exe inside bundled bin
        for name in ("ffmpeg", "ffmpeg.exe"):
            ffmpeg_path = bundle_dir / "bin" / name
            if ffmpeg_path.exists():
                return str(ffmpeg_path)
    # Check Resources folder (for .app bundle)
    if hasattr(sys, "frozen"):
        app_path = Path(sys.executable).parent.parent
        for name in ("ffmpeg", "ffmpeg.exe"):
            ffmpeg_path = app_path / "Resources" / "bin" / name
            if ffmpeg_path.exists():
                return str(ffmpeg_path)
    # Fall back to system FFmpeg depending on platform
    system = platform.system().lower()
    if system == "darwin":
        return "/opt/homebrew/bin/ffmpeg"
    # On Windows / Linux, rely on ffmpeg in PATH
    return "ffmpeg"


"""
kexi's Downloader Pro v2.0 - macOS Native Design

A beautiful, full-featured video/audio downloader with native macOS design.
Supports: YouTube, Facebook, TikTok, Instagram, SoundCloud & more!
All original features preserved + enhanced UX. 
"""

__title__ = "kexi's Downloader Pro"
__version__ = "2.0.0"
__author__ = "mark keximaze"
__license__ = "MIT"

import os
import sys
import re
import shutil
import queue
import threading
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import webbrowser

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext

# Try to import yt_dlp, show error if not installed
try:
    import yt_dlp
except ImportError:
    import sys
    from tkinter import messagebox
    messagebox.showerror(
        "yt-dlp Not Installed",
        "The required module 'yt-dlp' is not installed. Please install it with:\n\npip install yt-dlp\n\nThen restart the application."
    )
    sys.exit(1)

# Try to import darkdetect for system theme detection

try:
    import darkdetect

    HAS_DARKDETECT = True
except ImportError:
    HAS_DARKDETECT = False

# ----------------------------------------------------------------------
# Global settings
# ----------------------------------------------------------------------
os.environ["TK_SILENCE_DEPRECATION"] = "1"

 # Set appearance / theme, but be defensive if running with a
 # stripped-down or older customtkinter where these helpers are missing
if hasattr(ctk, "set_appearance_mode"):
    ctk.set_appearance_mode("system")  # 'system', 'light', or 'dark'
if hasattr(ctk, "set_default_color_theme"):
    ctk.set_default_color_theme("blue")
# ----------------------------------------------------------------------
# Thread-safe log queue
# ----------------------------------------------------------------------
log_queue: queue.Queue[tuple[str, Any]] = queue.Queue()


def ui_append(tag: str, msg: str | float) -> None:
    """Push a log line / progress value onto the queue."""
    log_queue.put((tag, msg))


# ----------------------------------------------------------------------
# Video / audio format dictionaries
# ----------------------------------------------------------------------
# Universal format selectors that work across all platforms (YouTube, Facebook, TikTok, Instagram, etc.)
VIDEO_IDS: Dict[str, str] = {
    "Best Quality (Auto)": "bestvideo+bestaudio/best",
    "4K 2160p (MP4)": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best[height<=2160]",
    "1440p (MP4)": "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[height<=1440]",
    "1080p (MP4)": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p (MP4)": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p (MP4)": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p (MP4)": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]",
    # YouTube-specific format IDs (720p to 8K)
    "YouTube 8K – AV01 – 403": "403+251/403+140",
    "YouTube 8K – AV1 – 702": "702+251/702+140",
    "YouTube 8K – AV1 – 571": "571+251/571+140",
    "YouTube 8K – VP9 – 272": "272+251/272+140",
    "YouTube 4K – AV01 – 401": "401+251/401+140",
    "YouTube 4K – VP9 – 315": "315+251/315+140",
    "YouTube 4K – VP9 – 337": "337+251/337+140",
    "YouTube 4K – AVC1 – 266": "266+251/266+140",
    "YouTube 1440p – VP9 – 308": "308+251/308+140",
    "YouTube 1440p – VP9 – 271": "271+251/271+140",
    "YouTube 1440p – AV1 – 400": "400+251/400+140",
    "YouTube 1440p – AVC1 – 264": "264+251/264+140",
    "YouTube 1080p – VP9 – 303": "303+251/303+140",
    "YouTube 1080p – VP9 – 248": "248+251/248+140",
    "YouTube 1080p – AV1 – 399": "399+251/399+140",
    "YouTube 1080p – AVC1 – 137": "137+251/137+140",
    "YouTube 1080p – AVC1 – 299": "299+251/299+140",
    "YouTube 720p – VP9 – 302": "302+251/302+140",
    "YouTube 720p – VP9 – 247": "247+251/247+140",
    "YouTube 720p – AV1 – 398": "398+251/398+140",
    "YouTube 720p – AVC1 – 136": "136+251/136+140",
    "YouTube 720p – AVC1 – 298": "298+251/298+140",
}

# Universal audio format selectors
AUDIO_IDS_LEFT: Dict[str, str] = {
    "Best Quality (Auto)": "bestaudio/best",
    "High Quality (256k)": "bestaudio[abr<=256]/bestaudio/best",
    "Medium Quality (128k)": "bestaudio[abr<=128]/bestaudio/best",
    "Low Quality (96k)": "bestaudio[abr<=96]/bestaudio/best",
    # YouTube-specific formats for advanced users
    "YouTube 251 Opus – Best": "251",
    "YouTube 140 AAC – 256k": "140",
    "YouTube 139 AAC – Low": "139",
}

AUDIO_CODECS_RIGHT = ["mp3", "flac", "alac", "wav", "m4a", "opus", "ogg"]


# ----------------------------------------------------------------------
# Find yt-dlp binary
# ----------------------------------------------------------------------
def find_yt_dlp() -> str:
    """Return the absolute path to the yt-dlp executable."""
    if getattr(sys, "frozen", False):
        bundle_dir = Path(
            sys._MEIPASS if hasattr(sys, "_MEIPASS") else sys.executable
        ).parent
        candidate = bundle_dir.parent / "Resources" / "bin" / "yt-dlp"
        if candidate.exists():
            return str(candidate)
        candidate = bundle_dir / "bin" / "yt-dlp"
        if candidate.exists():
            return str(candidate)

    # Check system PATH first (most common)
    exe = shutil.which("yt-dlp") or shutil.which("yt_dlp.exe")
    if exe:
        return exe
    
    # Check venv as fallback
    venv_path = Path(__file__).parent / "venv" / "bin" / "yt-dlp"
    if venv_path.exists():
        return str(venv_path)

    raise FileNotFoundError(
        "yt-dlp not found. Install it with `pip install yt-dlp`."
    )
    return exe


YTDLP_EXE = find_yt_dlp()


# ----------------------------------------------------------------------
# Format fetching and parsing (All Platforms)
# ----------------------------------------------------------------------
def fetch_video_formats(url: str, max_retries: int = 3, timeout: int = 30) -> Dict[str, List[Dict[str, str]]]:
    """Fetch and parse real video formats for any platform (YouTube, TikTok, Facebook, Instagram).

    Args:
        url: Video URL to fetch formats for
        max_retries: Maximum number of retry attempts (default: 3)
        timeout: Timeout in seconds for each attempt (default: 30)

    Returns:
        Dictionary of formats grouped by resolution
    """
    # Try different browser cookies for YouTube (works best when user
    # clicks "Always Allow" on the macOS Keychain prompt).
    browsers_to_try = ["chrome", "safari", "firefox", "edge"] if ("youtube.com" in url.lower() or "youtu.be" in url.lower()) else [None]
    
    for browser in browsers_to_try:
        for attempt in range(max_retries):
            try:
                if browser:
                    print(f"🔄 Fetching video info (attempt {attempt + 1}/{max_retries}) with {browser.title()} cookies...")
                else:
                    print(f"🔄 Fetching video info (attempt {attempt + 1}/{max_retries})...")
                
                # Build command
                cmd = [YTDLP_EXE, "--remote-components", "ejs:github"]
                
                # Add cookies for YouTube
                if browser:
                    cmd.extend(["--cookies-from-browser", browser])
                
                cmd.extend(["-F", url])
            
                creation_flags = 0
                if os.name == "nt":
                    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                
                # Set up environment for bundled app
                env = os.environ.copy()
                if getattr(sys, "frozen", False):
                    # Running in bundled app - ensure Python paths are set
                    bundle_dir = Path(sys.executable).parent
                    resources_dir = bundle_dir.parent / "Resources"
                    env["PYTHONHOME"] = str(resources_dir)
                    env["PYTHONPATH"] = str(resources_dir / "lib" / "python3.13")
                
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creation_flags,
                    env=env,
                )
                
                output_lines = []
                try:
                    # Read output with timeout
                    if proc.stdout:
                        for line in proc.stdout:
                            output_lines.append(line.rstrip())
                    
                    # Wait for process with timeout
                    proc.wait(timeout=timeout)
                    
                    # Success!
                    result = parse_video_formats("\n".join(output_lines))
                    if result:  # Only return if we got valid formats
                        cookie_msg = f" using {browser.title()} cookies" if browser else ""
                        print(f"✅ Successfully fetched video info on attempt {attempt + 1}{cookie_msg}")
                        return result
                    else:
                        print(f"⚠️ No formats found on attempt {attempt + 1}")
                        
                except subprocess.TimeoutExpired:
                    print(f"⏱️ Timeout on attempt {attempt + 1} with {browser or 'no cookies'}")
                    proc.kill()
                    proc.wait()
                    # If cookie reading times out, try next browser
                    break
            
            except Exception as exc:
                print(f"❌ Error on attempt {attempt + 1}: {exc}")
                # If this browser fails, try next one
                if "cookie" in str(exc).lower():
                    print(f"🔄 Cookie issue with {browser}, trying next browser...")
                    break
            
            # Wait before retrying (exponential backoff) only if not last attempt
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 4)  # 1s, 2s, 4s max
                print(f"⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
    
    # All retries failed
    print(f"❌ Failed to fetch video info after {max_retries} attempts")
    return {}


def detect_platform(url: str) -> str:
    """Detect platform from URL."""
    low = url.lower()
    if "youtube.com" in low or "youtu.be" in low:
        return "YouTube"
    elif "tiktok.com" in low:
        return "TikTok"
    elif "facebook.com" in low or "fb.watch" in low or "fb.com" in low:
        return "Facebook"
    elif "instagram.com" in low:
        return "Instagram"
    elif "soundcloud.com" in low:
        return "SoundCloud"
    else:
        return "Video"


def parse_video_formats(output: str) -> Dict[str, List[Dict[str, str]]]:
    """Parse yt-dlp -F output into grouped format dictionary (all platforms)."""
    lines = output.split("\n")
    
    # Debug: print output
    print(f"DEBUG: Parsing {len(lines)} lines")
    
    # Find header line
    start = -1
    for i, line in enumerate(lines):
        if "ID" in line and ("EXT" in line or "RESOLUTION" in line):
            start = i
            print(f"DEBUG: Found header at line {i}: {line}")
            break
    
    if start == -1:
        print("DEBUG: No header found in output")
        return {}
    
    # Group formats by resolution
    formats_by_res = {
        "8K (4320p)": [],
        "4K (2160p)": [],
        "1440p": [],
        "1080p": [],
        "720p": []
    }
    
    video_formats = {}  # format_id -> format_info
    audio_formats = {}  # format_id -> format_info
    
    # Parse all formats
    for line in lines[start + 2:]:
        if not line.strip():
            continue
        
        parts = line.split()
        if len(parts) < 2:
            continue
        
        format_id = parts[0]
        low = line.lower()
        
        # Extract codec (look for common patterns)
        codec = ""
        if "av01" in low:
            codec = "AV01"
        elif "bytevc1" in low:
            codec = "ByteVC1"
        elif "avc" in low or "h264" in low:
            codec = "H264"
        elif "vp9" in low or "vp09" in low:
            codec = "VP9"
        elif "opus" in low:
            codec = "Opus"
        elif "m4a" in low or "mp4a" in low:
            codec = "AAC"
        
        # Check if audio
        if "audio only" in low:
            bitrate = 0
            m = re.search(r"(\d+)k", low)
            if m:
                bitrate = int(m.group(1))
            
            audio_formats[format_id] = {
                "id": format_id,
                "codec": codec if codec else "Audio",
                "bitrate": bitrate,
                "line": line
            }
            print(f"DEBUG: Found audio format {format_id} - {codec} {bitrate}kbps")
            continue
        
        # Check if video (look for resolution patterns)
        # Pattern 1: YouTube style "1920x1080"
        res_match = re.search(r"(\d{3,4})x(\d{3,4})", line)
        # Pattern 2: TikTok/Instagram style "720p", "1080p" in format name
        res_name_match = re.search(r"(\d{3,4})p", line.lower())
        
        height = None
        if res_match:
            height = int(res_match.group(2))
        elif res_name_match:
            height = int(res_name_match.group(1))
        
        if height:
            # Map to resolution group
            res_group = None
            if height >= 4320:
                res_group = "8K (4320p)"
            elif height >= 2160:
                res_group = "4K (2160p)"
            elif height >= 1440:
                res_group = "1440p"
            elif height >= 1080:
                res_group = "1080p"
            elif height >= 720:
                res_group = "720p"
            
            if res_group:
                video_formats[format_id] = {
                    "id": format_id,
                    "codec": codec if codec else "Video",
                    "height": height,
                    "res_group": res_group,
                    "line": line
                }
                print(f"DEBUG: Found video format {format_id} - {res_group} {codec}")
    
    print(f"DEBUG: Found {len(video_formats)} video formats, {len(audio_formats)} audio formats")
    
    # Build format combinations (video + audio)
    # For YouTube: Combine video with audio (251, 140, etc.)
    # For TikTok/Instagram: Often video-only formats work (they include audio)
    audio_priority = ["251", "140", "250", "249", "139"]
    
    for vid_id, vid_info in video_formats.items():
        res_group = vid_info["res_group"]
        
        # Try to add with audio first
        audio_added = False
        for aud_id in audio_priority:
            if aud_id in audio_formats:
                aud_info = audio_formats[aud_id]
                formats_by_res[res_group].append({
                    "video_id": vid_id,
                    "video_codec": vid_info["codec"],
                    "audio_id": aud_id,
                    "audio_codec": aud_info["codec"],
                    "audio_bitrate": aud_info.get("bitrate", 0),
                    "format_string": f"{vid_id}+{aud_id}",
                    "display": f"{vid_info['codec']} • {vid_id}+{aud_id} ({aud_info['codec']} {aud_info.get('bitrate', 0)}k)"
                })
                print(f"DEBUG: Added combination {res_group}: {vid_id}+{aud_id}")
                audio_added = True
                break  # Only add one audio option per video format
        
        # If no audio formats available (TikTok, Instagram), add video-only
        if not audio_added:
            formats_by_res[res_group].append({
                "video_id": vid_id,
                "video_codec": vid_info["codec"],
                "audio_id": "",
                "audio_codec": "Included",
                "audio_bitrate": 0,
                "format_string": vid_id,
                "display": f"{vid_info['codec']} • {vid_id} (Audio Included)"
            })
            print(f"DEBUG: Added video-only format {res_group}: {vid_id}")
    
    # Remove empty resolution groups
    result = {k: v for k, v in formats_by_res.items() if v}
    print(f"DEBUG: Returning {len(result)} resolution groups with {sum(len(v) for v in result.values())} total formats")
    return result


# ----------------------------------------------------------------------
# URL validation
# ----------------------------------------------------------------------
URL_RE = re.compile(
    r"^(https?://)?(www\.)?"
    r"(youtube\.com|youtu\.be|"
    r"facebook\.com|fb\.watch|fb\.com|"
    r"tiktok\.com|"
    r"instagram\.com|"
    r"soundcloud\.com)"
    r"/.+$"
)


def clean_list(text: str) -> list[str]:
    """Extract video/audio URLs from multi-line string."""
    raw = [x.strip() for x in text.splitlines() if x.strip()]
    urls: list[str] = []
    ignored: list[str] = []

    for line in raw:
        if (
            line.startswith("=")
            or line.startswith("-")
            or "DOWNLOAD" in line.upper()
            or "RUNNING" in line.upper()
            or "COMMAND:" in line.upper()
            or line.startswith("Paste")
            or line.startswith("[")
            or "✅" in line
            or "❌" in line
        ):
            continue

        if URL_RE.match(line):
            urls.append(line)
        else:
            ignored.append(line)

    if ignored:
        messagebox.showwarning(
            "Invalid URLs",
            "These lines were ignored:\n"
            + "\n".join(ignored[:5])
            + (f"\n… and {len(ignored)-5} more" if len(ignored) > 5 else ""),
        )
    return urls


# ----------------------------------------------------------------------
# Core download routine
# ----------------------------------------------------------------------
def run_download(
    url: str,
    out: Path,
    *,
    audio: bool = False,
    audio_id: str | None = None,
    video_id: str | None = None,
    right_codec: str | None = None,
    cookies_path: str | None = None,
    tag: str = "Job",
    proc_ref: Optional["DownloadWorker"] = None,
) -> bool:
    """Build the yt-dlp command and run it."""
    out_tpl = str(out / "%(title)s.%(ext)s")

    # Allow browser cookies (Chrome) so YouTube behaves like in Safari/
    # Chrome itself. On macOS this will trigger a one-time Keychain
    # prompt; user can safely click "Always Allow".
    use_browser_cookies = True
    try:
        import shutil

        has_js_runtime = bool(shutil.which("node") or shutil.which("deno"))
    except Exception:
        has_js_runtime = False

    if audio:
        cmd = [YTDLP_EXE]
        if has_js_runtime:
            cmd.extend(["--remote-components", "ejs:github"])
        cmd.extend([
            "--extract-audio",
            "--audio-format", right_codec or "mp3",
            "--audio-quality", "0",
            "--newline",
            "-o", out_tpl,
        ])
        
        # Add cookies for YouTube audio downloads
        if cookies_path:
            cp = Path(cookies_path).expanduser()
            if cp.is_file():
                cmd.extend(["--cookies", str(cp)])
            elif use_browser_cookies:
                cmd.extend(["--cookies-from-browser", "chrome"])
        elif ("youtube.com" in url.lower() or "youtu.be" in url.lower()) and use_browser_cookies:
            cmd.extend(["--cookies-from-browser", "chrome"])
        
        cmd.append(url)
    else:
        if video_id and video_id != "best":
            if audio_id:
                fmt = f"{video_id}+{audio_id}/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            else:
                fmt = f"{video_id}+bestaudio/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
        else:
            fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

        cmd = [YTDLP_EXE]
        if has_js_runtime:
            cmd.extend(["--remote-components", "ejs:github"])
        cmd.extend(["-f", fmt, "--merge-output-format", "mp4", "--newline", "-o", out_tpl, url])

    # Add cookies for authentication
    if cookies_path:
        cp = Path(cookies_path).expanduser()
        if cp.is_file():
            cmd.extend(["--cookies", str(cp)])
        elif use_browser_cookies:
            cmd.extend(["--cookies-from-browser", "chrome"])
    elif ("youtube.com" in url.lower() or "youtu.be" in url.lower()) and use_browser_cookies:
        # Prefer cookies for YouTube in dev, but skip browser cookies in
        # frozen apps to avoid Keychain prompts.
        cmd.extend(["--cookies-from-browser", "chrome"])

    ui_append(tag, f"Running command:\n{' '.join(cmd)}\n")

    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creation_flags,
        )
        if proc_ref:
            proc_ref.current_proc = proc

        def stream_and_collect(p: subprocess.Popen) -> int:
            """Stream subprocess output to UI and return exit code."""
            if p.stdout:
                for line in p.stdout:
                    line = line.rstrip()
                    if "[download]" in line and "%" in line:
                        try:
                            percent = float(line.split("%")[0].split()[-1])
                            ui_append("progress", percent)
                        except Exception:
                            pass
                    ui_append(tag, line)

                    if proc_ref and proc_ref.stop_flag:
                        try:
                            p.terminate()
                        except Exception:
                            pass
                        break

            p.wait()
            return p.returncode

        code = stream_and_collect(proc)

        # If first attempt failed, try safe fallbacks (do not remove user's choices)
        if code != 0:
            ui_append(tag, "⚠️ Primary download failed, attempting fallbacks...")

            # Prepare fallback command variants
            fallbacks: list[list[str]] = []

            # 1) Remove remote-components (EJS) to avoid JS challenge issues
            fb1 = [c for c in cmd if c != "--remote-components" and c != "ejs:github"]
            fallbacks.append(fb1)

            # 2) Try forcing native HLS handling
            fb2 = fb1.copy()
            if "--hls-prefer-native" not in fb2:
                fb2.insert(1, "--hls-prefer-native")
            fallbacks.append(fb2)

            # 3) Force a strict MP4 format fallback to avoid fragmented m3u8
            fb3 = [c for c in fb1]
            # replace or add -f with a robust mp4 selector
            if "-f" in fb3:
                idx = fb3.index("-f")
                # keep url at the end; replace following format
                if idx + 1 < len(fb3):
                    fb3[idx + 1] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
            else:
                # insert format before output/template or url
                fb3.insert(1, "-f")
                fb3.insert(2, "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best")
            fallbacks.append(fb3)

            # 4) Try HLS using mpegts container and increase fragment retries
            # This can help when segmented HLS fragments produce 403s for
            # certain fragment request patterns; using mpegts + more
            # fragment retries sometimes recovers the stream.
            fb4 = [c for c in fb3]
            if "--hls-use-mpegts" not in fb4:
                fb4.insert(1, "--hls-use-mpegts")
            if "--fragment-retries" not in fb4:
                fb4.insert(1, "--fragment-retries")
                fb4.insert(2, "20")
            fallbacks.append(fb4)

            for attempt_cmd in fallbacks:
                try:
                    ui_append(tag, f"Running fallback: {' '.join(attempt_cmd)}")
                    p2 = subprocess.Popen(
                        attempt_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        creationflags=creation_flags,
                    )
                    if proc_ref:
                        proc_ref.current_proc = p2

                    code2 = stream_and_collect(p2)
                    if code2 == 0:
                        ui_append(tag, "✅ Fallback succeeded")
                        return True
                except Exception as exc2:
                    ui_append(tag, f"[FALLBACK EXCEPTION] {exc2}")
                finally:
                    if proc_ref:
                        proc_ref.current_proc = None

            ui_append(tag, "❌ All fallbacks failed")
            return False

        return True

    except Exception as exc:
        ui_append(tag, f"[EXCEPTION] {exc}")
        return False
    finally:
        if proc_ref:
            proc_ref.current_proc = None
        if proc and proc.stdout:
            try:
                proc.stdout.close()
            except Exception:
                pass


# ----------------------------------------------------------------------
# Worker thread
# ----------------------------------------------------------------------
class DownloadWorker(threading.Thread):
    """Thread that processes download jobs."""

    def __init__(self, jobs: List[Tuple[str, dict]], *, tag: str) -> None:
        super().__init__(daemon=True)
        self.jobs = jobs
        self.tag = tag
        self.stop_flag = False
        self.current_proc: Optional[subprocess.Popen] = None

    def stop(self) -> None:
        """Stop the worker."""
        self.stop_flag = True
        if self.current_proc:
            try:
                self.current_proc.terminate()
            except Exception:
                try:
                    self.current_proc.kill()
                except Exception:
                    pass

    def run(self) -> None:
        for url, opts in self.jobs:
            if self.stop_flag:
                ui_append(self.tag, "\n=== CANCELLED ===\n")
                return
            ok = run_download(url, **opts, tag=self.tag, proc_ref=self)
            ui_append(self.tag, f"\n{'✅' if ok else '❌'} Finished: {url}\n")
        ui_append(self.tag, "\n=== ALL DONE ===\n")


# ----------------------------------------------------------------------
# Main Application
# ----------------------------------------------------------------------
class kexisdownloader(ctk.CTk):
    """Main application with beautiful macOS design."""

    def __init__(self):
        super().__init__()

        # Window setup
        self.title("⚡ kexi's Downloader Pro")
        self.geometry("1100x800")
        self.minsize(900, 700)
        
        # Set vintage beige background color (matches logo)
        # Dark mode: default dark, Light mode: vintage beige
        self._set_appearance_colors()
        
        # Set icon - check multiple locations
        icon_locations = [
            Path(__file__).parent / "app.icon.png",  # Development folder
            Path(sys.executable).parent.parent / "Resources" / "app.icon.png",  # Bundled app Resources
            Path.cwd() / "app.icon.png",  # Current working directory
        ]
        
        for icon_path in icon_locations:
            if icon_path.exists():
                try:
                    self.iconphoto(True, tk.PhotoImage(file=str(icon_path)))
                    print(f"✅ Icon loaded from: {icon_path}")
                    break
                except Exception as e:
                    print(f"Could not load icon from {icon_path}: {e}")

        # Colors
        self.accent_color = "#5A524A"
        self.last_download_folder = None

        # Worker references
        self.video_workers = []
        self.audio_workers = []

        # Log widgets
        self._log_widgets: Dict[str, tk.Text] = {}

        # Smart format selection
        self.selected_format: Optional[Dict[str, str]] = None

        # Setup UI
        self._setup_menu()
        self._setup_ui()

        # Check for Node/Deno runtime required by yt-dlp JS solvers
        try:
            self._check_js_runtime()
        except Exception:
            # Non-fatal: if runtime check fails, proceed without blocking the UI
            pass

        # Start log polling
        self._poll_log()

        # Bind keyboard shortcuts
        self.bind("<Command-d>", lambda e: self._start_current_download())
        self.bind("<Command-k>", lambda e: self._show_format_checker())
        self.bind("<Command-comma>", lambda e: self._show_preferences())
        self.bind("<Command-q>", lambda e: self.quit())

        print("✅ kexi's Downloader Pro v2.0 initialized")

    # ------------------------------------------------------------------
    def _setup_menu(self):
        """Setup macOS-style menu bar."""
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Downloads Folder", command=self._open_downloads_folder, accelerator="⌘O")
        file_menu.add_separator()
        file_menu.add_command(label="Preferences...", command=self._show_preferences, accelerator="⌘,")
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.quit, accelerator="⌘Q")

        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Clear Logs", command=self._clear_logs)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Toggle Dark Mode", command=self._toggle_dark_mode)

        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Check Formats", command=self._show_format_checker, accelerator="⌘K")

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About kexi's Downloader", command=self._show_about)

        # Bind menu shortcuts
        self.bind("<Command-o>", lambda e: self._open_downloads_folder())

    # ------------------------------------------------------------------
    def _setup_ui(self):
        """Setup the main UI."""
        # Header with title
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        title_label = ctk. CTkLabel(
            header,
            text="⚡ kexi's Downloader Pro",
            font=ctk.CTkFont(size=28, weight="bold")
        )
        title_label.pack(side="left")

        # Dark mode toggle
        self.dark_mode_switch = ctk.CTkSwitch(
            header,
            text="🌓 Dark Mode",
            command=self._toggle_dark_mode,
            font=ctk.CTkFont(size=12)
        )
        self.dark_mode_switch.pack(side="right", padx=10)
        if ctk.get_appearance_mode() == "Dark":
            self. dark_mode_switch.select()

        # Tabview
        self.tabview = ctk.CTkTabview(self, corner_radius=15)
        self.tabview. pack(fill="both", expand=True, padx=20, pady=10)

        # Add tabs
        self.tabview.add("📹 Video")
        self.tabview.add("🎵 Audio")

        # Build tabs
        self._build_video_tab()
        self._build_audio_tab()

        # Progress bar at bottom
        progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        progress_frame. pack(fill="x", padx=20, pady=(0, 20))

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ctk.CTkProgressBar(
            progress_frame,
            variable=self.progress_var,
            mode="determinate",
            height=20,
            corner_radius=10
        )
        self.progress_bar.pack(fill="x", pady=5)
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            progress_frame,
            text="Ready to download",
            font=ctk.CTkFont(size=11)
        )
        self.progress_label.pack()

    # ------------------------------------------------------------------
    
    def _check_js_runtime(self) -> None:
        """Non-blocking check for Node.js or Deno. If missing, show a friendly prompt
        with a one-line Homebrew install command the user can copy.

        This preserves the app's ability to use yt-dlp's JS solvers for highest
        quality formats while avoiding automatic installs.
        """
        import shutil

        # Quick check for common JS runtimes used by yt-dlp remote components
        js_runtime = shutil.which("node") or shutil.which("deno")
        if js_runtime:
            print(f"✅ JS runtime found: {js_runtime}")
            return

        # If not found, show a non-modal recommendation window
        try:
            top = tk.Toplevel(self)
            top.title("JavaScript runtime recommended")
            top.resizable(False, False)
            top.geometry("480x140")

            msg = tk.Label(
                top,
                text=(
                    "For some high-quality YouTube formats the downloader uses a JavaScript "
                    "solver (Node.js or Deno). Installing Node via Homebrew enables these "
                    "formats.\n\nNo action is required if you prefer the simpler MP4 fallback."
                ),
                justify="left",
                wraplength=440,
            )
            msg.pack(padx=12, pady=(12, 6))

            btn_frame = tk.Frame(top)
            btn_frame.pack(pady=(0, 12))

            def _copy_cmd():
                cmd = "brew install node"
                try:
                    self.clipboard_clear()
                    self.clipboard_append(cmd)
                    ui_append("Info", "Copied: brew install node")
                except Exception:
                    ui_append("Info", "Could not copy install command to clipboard")

            def _open_brew():
                webbrowser.open("https://brew.sh")

            tk.Button(btn_frame, text="Copy install command", command=_copy_cmd).pack(side="left", padx=8)
            tk.Button(btn_frame, text="Open Homebrew site", command=_open_brew).pack(side="left", padx=8)
            tk.Button(btn_frame, text="Dismiss", command=top.destroy).pack(side="left", padx=8)

            # Make sure the prompt doesn't steal modal focus
            top.transient(self)
            top.lift()
        except Exception as e:
            print(f"Could not show JS runtime prompt: {e}")

    # ------------------------------------------------------------------
    def _build_video_tab(self):
        """Build the video download tab."""
        tab = self.tabview.tab("📹 Video")

        # URL section
        url_frame = ctk.CTkFrame(tab, corner_radius=15)
        url_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            url_frame,
            text="📝 Paste Video URLs (YouTube, Facebook, TikTok, Instagram):",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))

        # Log text box with terminal style
        self.video_log_text = tk.Text(
            url_frame,
            wrap="word",
            height=10,
            font=("SF Mono", 11),
            bg="#1E1E1E" if ctk.get_appearance_mode() == "Dark" else "#F5F0E8",
            fg="#A8FF60" if ctk.get_appearance_mode() == "Dark" else "#5A524A",
            relief="flat",
            borderwidth=0,
            insertbackground="#A8FF60",
            selectbackground="#3A3A3A",
            padx=10,
            pady=10
        )
        self.video_log_text.pack(fill="both", expand=True, padx=15, pady=(5, 10))
        self.video_log_text.insert("1.0", "Paste video URLs here (YouTube, Facebook, TikTok, Instagram), one per line.\n\n")
        self._log_widgets["VIDEO"] = self.video_log_text

        # Right-click menu for log
        self._add_log_context_menu(self.video_log_text)

        # Controls fram
        # e
        controls_frame = ctk.CTkFrame(tab, corner_radius=15)
        controls_frame.pack(fill="x", padx=10, pady=(0, 10))

        # Output folder
        ctk.CTkLabel(
            controls_frame,
            text="📁 Output Folder:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))

        folder_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        folder_frame.pack(fill="x", padx=15, pady=(0, 10))

        self.video_folder_entry = ctk. CTkEntry(
            folder_frame,
            placeholder_text=str(Path.home() / "Downloads"),
            height=35,
            corner_radius=8
        )
        self.video_folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.video_folder_entry.insert(0, str(Path.home() / "Downloads"))

        ctk.CTkButton(
            folder_frame,
            text="Browse",
            width=100,
            height=35,
            corner_radius=8,
            command=lambda: self._browse_folder(self.video_folder_entry)
        ).pack(side="left")

        # Buttons
        button_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkButton(
            button_frame,
            text="🎯 Smart Selector",
            height=40,
            corner_radius=10,
            fg_color="#9B59B6",
            hover_color="#8E44AD",
            command=self._show_smart_selector
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkButton(
            button_frame,
            text="🔍 Check Formats",
            height=40,
            corner_radius=10,
            fg_color="#4A90E2",
            hover_color="#357ABD",
            command=self._show_format_checker
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkButton(
            button_frame,
            text="❌ Cancel",
            height=40,
            corner_radius=10,
            fg_color="#E74C3C",
            hover_color="#C0392B",
            command=self._cancel_video
        ).pack(side="left", fill="x", expand=True, padx=5)

        ctk.CTkButton(
            button_frame,
            text="⚡ Download Video",
            height=40,
            corner_radius=10,
            fg_color="#27AE60",
            hover_color="#229954",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_video
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    # ------------------------------------------------------------------
    def _build_audio_tab(self):
        """Build the audio download tab."""
        tab = self.tabview. tab("🎵 Audio")

        # URL section
        url_frame = ctk.CTkFrame(tab, corner_radius=15)
        url_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            url_frame,
            text="📝 Paste Audio URLs (YouTube, SoundCloud, etc.):",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))

        # Log text box
        self.audio_log_text = tk.Text(
            url_frame,
            wrap="word",
            height=10,
            font=("SF Mono", 11),
            bg="#1E1E1E" if ctk.get_appearance_mode() == "Dark" else "#F5F0E8",
            fg="#A8FF60" if ctk.get_appearance_mode() == "Dark" else "#5A524A",
            relief="flat",
            borderwidth=0,
            insertbackground="#A8FF60",
            selectbackground="#3A3A3A",
            padx=10,
            pady=10
        )
        self.audio_log_text.pack(fill="both", expand=True, padx=15, pady=(5, 10))
        self.audio_log_text.insert("1.0", "Paste audio URLs here (YouTube, SoundCloud, etc.), one per line.\n\n")
        self._log_widgets["AUDIO"] = self.audio_log_text

        # Right-click menu
        self._add_log_context_menu(self.audio_log_text)

        # Controls
        controls_frame = ctk. CTkFrame(tab, corner_radius=15)
        controls_frame.pack(fill="x", padx=10, pady=(0, 10))

        # Output folder
        ctk.CTkLabel(
            controls_frame,
            text="📁 Output Folder:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))

        folder_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        folder_frame. pack(fill="x", padx=15, pady=(0, 10))

        self.audio_folder_entry = ctk.CTkEntry(
            folder_frame,
            placeholder_text=str(Path.home() / "Downloads"),
            height=35,
            corner_radius=8
        )
        self.audio_folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.audio_folder_entry.insert(0, str(Path.home() / "Downloads"))

        ctk.CTkButton(
            folder_frame,
            text="Browse",
            width=100,
            height=35,
            corner_radius=8,
            command=lambda:  self._browse_folder(self. audio_folder_entry)
        ).pack(side="left")

        # Audio codec
        ctk.CTkLabel(
            controls_frame,
            text="🎧 Audio Format:",
            font=ctk. CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.audio_codec_var = ctk.StringVar(value=AUDIO_CODECS_RIGHT[0])
        codec_menu = ctk.CTkOptionMenu(
            controls_frame,
            variable=self.audio_codec_var,
            values=AUDIO_CODECS_RIGHT,
            width=250,
            height=35,
            corner_radius=8
        )
        codec_menu.pack(anchor="w", padx=15, pady=(0, 15))

        # Buttons
        button_frame = ctk.CTkFrame(controls_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkButton(
            button_frame,
            text="❌ Cancel",
            height=40,
            corner_radius=10,
            fg_color="#E74C3C",
            hover_color="#C0392B",
            command=self._cancel_audio
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkButton(
            button_frame,
            text="⚡ Download Audio",
            height=40,
            corner_radius=10,
            fg_color="#27AE60",
            hover_color="#229954",
            font=ctk. CTkFont(size=14, weight="bold"),
            command=self._start_audio
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    # ------------------------------------------------------------------
    def _add_log_context_menu(self, text_widget):
        """Add right-click context menu to log widget."""
        menu = tk.Menu(text_widget, tearoff=0)
        menu.add_command(label="Copy All", command=lambda: self._copy_log(text_widget))
        menu.add_command(label="Clear Log", command=lambda: self._clear_single_log(text_widget))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: text_widget.tag_add("sel", "1.0", "end"))

        def show_menu(event):
            menu.tk_popup(event.x_root, event.y_root)

        text_widget.bind("<Button-2>", show_menu)  # Right-click on Mac
        text_widget.bind("<Control-Button-1>", show_menu)  # Ctrl+click

    # ------------------------------------------------------------------
    def _copy_log(self, widget):
        """Copy log contents to clipboard."""
        content = widget.get("1.0", "end-1c")
        self. clipboard_clear()
        self.clipboard_append(content)
        self.progress_label.configure(text="✅ Log copied to clipboard!")
        self.after(2000, lambda: self.progress_label.configure(text="Ready to download"))

    # ------------------------------------------------------------------
    def _clear_single_log(self, widget):
        """Clear a single log widget."""
        widget.delete("1.0", "end")
        widget.insert("1.0", "Paste YouTube URLs here, one per line.\n\n")

    # ------------------------------------------------------------------
    def _clear_logs(self):
        """Clear all logs."""
        for widget in self._log_widgets.values():
            widget.delete("1.0", "end")
            widget.insert("1.0", "Paste YouTube URLs here, one per line.\n\n")

    # ------------------------------------------------------------------
    def _set_appearance_colors(self):
        """Set custom appearance colors for light mode (vintage beige)."""
        # Get current mode
        mode = ctk.get_appearance_mode()
        
        # Set window background color
        if mode == "Light":
            # Vintage beige color from logo
            self.configure(fg_color="#E8DCC8")
        else:
            # Default dark mode
            self.configure(fg_color=("#2B2B2B", "#1A1A1A"))

    # ------------------------------------------------------------------
    def _browse_folder(self, entry_widget):
        """Browse for output folder."""
        folder = filedialog.askdirectory()
        if folder:
            entry_widget.delete(0, "end")
            entry_widget. insert(0, folder)

    # ------------------------------------------------------------------
    def _toggle_dark_mode(self):
        """Toggle between light and dark mode."""
        current = ctk.get_appearance_mode()
        new_mode = "Light" if current == "Dark" else "Dark"
        ctk. set_appearance_mode(new_mode)
        
        # Update window background color
        if new_mode == "Light":
            self.configure(fg_color="#E8DCC8")  # Vintage beige
        else:
            self.configure(fg_color=("#2B2B2B", "#1A1A1A"))  # Dark

        # Update log colors
        bg = "#1E1E1E" if new_mode == "Dark" else "#F5F0E8"
        fg = "#A8FF60" if new_mode == "Dark" else "#5A524A"

        for widget in self._log_widgets. values():
            widget.configure(bg=bg, fg=fg)

    # ------------------------------------------------------------------
    def _poll_log(self):
        """Poll the log queue and update UI."""
        try:
            while True:
                tag, line = log_queue.get_nowait()
                widget = self._log_widgets. get(tag)

                if tag == "progress":
                    self.progress_var.set(line / 100)
                    self.progress_label.configure(text=f"Downloading...  {int(line)}%")
                    continue

                if widget: 
                    widget.insert("end", line + "\n")
                    widget. see("end")
        except queue.Empty:
            pass
        self.after(100, self._poll_log)

    # ------------------------------------------------------------------
    def _find_cookies_file(self) -> Optional[str]:
        """Search for cookies. txt file."""
        for p in (
            Path.home() / "Downloads" / "cookies.txt",
            Path.cwd() / "cookies.txt",
            Path.home() / "cookies.txt",
        ):
            if p.is_file():
                return str(p)
        return None

    # ------------------------------------------------------------------
    def _ensure_folder(self, path_str: str) -> Path:
        """Ensure output folder exists."""
        if not path_str: 
            path_str = str(Path.home() / "Downloads")
        p = Path(path_str).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        self.last_download_folder = p
        return p

    # ------------------------------------------------------------------
    def _start_video(self):
        """Start video download."""
        content = self.video_log_text.get("1.0", "end-1c")
        urls = clean_list(content)
        if not urls:
            messagebox.showerror("Error", "No video URLs entered.")
            return

        out_folder = self._ensure_folder(self.video_folder_entry.get())
        cookies_path = self._find_cookies_file()

        self.video_log_text.insert("end", "\n" + "=" * 60 + "\n")
        self.video_log_text.insert("end", "DOWNLOAD STARTED\n")
        self.video_log_text.insert("end", "=" * 60 + "\n")
        self.video_log_text.see("end")

        jobs:  List[Tuple[str, dict]] = []
        for u in urls:
            # Use smart-selected format if available, otherwise use best quality
            if self.selected_format:
                self.video_log_text.insert("end", "\n" + "=" * 60 + "\n")
                self.video_log_text.insert("end", "🎯 USING SMART-SELECTED FORMAT\n")
                self.video_log_text.insert("end", f"Resolution: {self.selected_format['resolution']}\n")
                self.video_log_text.insert("end", f"Video: {self.selected_format['video_codec']} ({self.selected_format['video_id']})\n")
                self.video_log_text.insert("end", f"Audio: {self.selected_format['audio_codec']} ({self.selected_format['audio_id']})\n")
                self.video_log_text.insert("end", f"Format String: {self.selected_format['format_string']}\n")
                self.video_log_text.insert("end", "=" * 60 + "\n")
                self.video_log_text.see("end")
                
                jobs.append(
                    (
                        u,
                        dict(
                            out=out_folder,
                            audio=False,
                            video_id=self.selected_format['format_string'],
                            audio_id=None,  # Already included in format_string
                            cookies_path=cookies_path,
                        ),
                    )
                )
            else:
                # No smart format selected - use best quality (auto)
                jobs.append(
                    (
                        u,
                        dict(
                            out=out_folder,
                            audio=False,
                            video_id="bestvideo+bestaudio/best",
                            audio_id=None,
                            cookies_path=cookies_path,
                        ),
                    )
                )

        w = DownloadWorker(jobs, tag="VIDEO")
        self.video_workers = [w]
        w.start()

        # Show open folder button after completion
        self.after(2000, self._check_download_complete)

    # ------------------------------------------------------------------
    def _start_audio(self):
        """Start audio download."""
        content = self.audio_log_text. get("1.0", "end-1c")
        urls = clean_list(content)
        if not urls:
            messagebox.showerror("Error", "No audio URLs entered.")
            return

        out_folder = self._ensure_folder(self.audio_folder_entry.get())
        cookies_path = self._find_cookies_file()

        self.audio_log_text.insert("end", "\n" + "=" * 60 + "\n")
        self.audio_log_text.insert("end", "DOWNLOAD STARTED\n")
        self.audio_log_text. insert("end", "=" * 60 + "\n")
        self.audio_log_text. see("end")

        jobs: List[Tuple[str, dict]] = []
        for u in urls:
            jobs.append(
                (
                    u,
                    dict(
                        out=out_folder,
                        audio=True,
                        right_codec=self.audio_codec_var.get(),
                        cookies_path=cookies_path,
                    ),
                )
            )

        w = DownloadWorker(jobs, tag="AUDIO")
        self.audio_workers = [w]
        w. start()

        self.after(2000, self._check_download_complete)

    # ------------------------------------------------------------------
    def _check_download_complete(self):
        """Check if downloads are complete and show open folder button."""
        active_workers = [w for w in (self.video_workers + self. audio_workers) if w.is_alive()]
        if not active_workers and self.last_download_folder:
            result = messagebox.askyesno(
                "Download Complete! ",
                "Downloads finished!  Open the folder?"
            )
            if result: 
                self._open_specific_folder(self.last_download_folder)

    # ------------------------------------------------------------------
    def _cancel_video(self):
        """Cancel video download."""
        if self.video_workers:
            self.video_workers[-1].stop()
            messagebox.showinfo("Cancelled", "Video download cancelled.")
        else:
            messagebox.showinfo("Info", "No active video download.")

    # ------------------------------------------------------------------
    def _cancel_audio(self):
        """Cancel audio download."""
        if self.audio_workers:
            self.audio_workers[-1].stop()
            messagebox.showinfo("Cancelled", "Audio download cancelled.")
        else:
            messagebox.showinfo("Info", "No active audio download.")

    # ------------------------------------------------------------------
    def _start_current_download(self):
        """Start download for current tab (keyboard shortcut)."""
        current_tab = self.tabview. get()
        if "Video" in current_tab:
            self._start_video()
        else:
            self._start_audio()

    # ------------------------------------------------------------------
    def _show_smart_selector(self):
        """Show the smart format selector window."""
        content = self.video_log_text.get("1.0", "end-1c")
        urls = [line.strip() for line in content.splitlines() if line.strip() and URL_RE.match(line.strip())]
        
        if not urls:
            messagebox.showerror("No URL", "Please paste a video URL first (YouTube, TikTok, Facebook, Instagram).")
            return
        
        url = urls[0]
        try:
            platform = detect_platform(url)
            window = SmartFormatSelectorWindow(self, url)
            window.focus_force()
            window.lift()
            print(f"✅ Smart Selector opened for {platform}: {url}")
        except Exception as e:
            print(f"❌ Error opening Smart Selector: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Could not open Smart Selector:\n{e}")

    # ------------------------------------------------------------------
    def _show_format_checker(self):
        """Show the format checker window."""
        # Get URL from current tab
        current_tab = self.tabview. get()
        if "Video" in current_tab: 
            content = self.video_log_text.get("1.0", "end-1c")
        else:
            content = self. audio_log_text.get("1.0", "end-1c")

        urls = [line.strip() for line in content. splitlines() if line.strip() and URL_RE.match(line. strip())]
        url = urls[0] if urls else ""

        FormatCheckerWindow(self, url)

    # ------------------------------------------------------------------
    def _open_downloads_folder(self):
        """Open the default downloads folder."""
        folder = Path.home() / "Downloads"
        self._open_specific_folder(folder)

    # ------------------------------------------------------------------
    def _open_specific_folder(self, folder: Path):
        """Open a specific folder in Finder/Explorer."""
        if sys.platform == "darwin": 
            subprocess.run(["open", str(folder)])
        elif sys.platform == "win32":
            os.startfile(str(folder))
        else:
            subprocess.run(["xdg-open", str(folder)])

    # ------------------------------------------------------------------
    def _show_preferences(self):
        """Show preferences window."""
        PreferencesWindow(self)

    # ------------------------------------------------------------------
    def _show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About kexi's Downloader Pro",
            f"{__title__} v{__version__}\n\n"
            f"Download videos and audio from:\n"
            f"• YouTube\n"
            f"• Facebook\n"
            f"• TikTok\n"
            f"• Instagram\n"
            f"• SoundCloud\n"
            f"• and many more!\n\n"
            f"Created by {__author__}\n"
            f"License: {__license__}"
        )


# ----------------------------------------------------------------------
# Smart Format Selector Window
# ----------------------------------------------------------------------
class SmartFormatSelectorWindow(ctk.CTkToplevel):
    """Smart format selector with real-time YouTube format detection."""

    def __init__(self, parent: "kexisdownloader", url: str):
        super().__init__(parent)

        self.parent_app = parent
        self.url = url
        self.platform = detect_platform(url)
        self.formats_data: Dict[str, List[Dict[str, str]]] = {}
        self.selected_format: Optional[Dict[str, str]] = None

        self.title(f"🎯 Smart Format Selector - {self.platform}")
        self.geometry("900x700")
        self.minsize(800, 600)

        # Set icon
        icon_path = Path(__file__).parent / "app.icon.png"
        if icon_path.exists():
            try:
                self.iconphoto(True, tk.PhotoImage(file=str(icon_path)))
            except Exception:
                pass

        # Header
        header = ctk.CTkFrame(self, corner_radius=15)
        header.pack(fill="x", padx=20, pady=20)

        # Platform emoji map
        platform_emoji = {
            "YouTube": "📺",
            "TikTok": "🎵",
            "Facebook": "👥",
            "Instagram": "📷",
            "SoundCloud": "🎧",
            "Video": "🎬"
        }
        
        ctk.CTkLabel(
            header,
            text=f"🎯 Smart Format Selector - {platform_emoji.get(self.platform, '🎬')} {self.platform}",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))

        ctk.CTkLabel(
            header,
            text=f"Select exact video quality and codec from real {self.platform} formats",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        ).pack(anchor="w", padx=15, pady=(0, 15))

        # URL display
        url_frame = ctk.CTkFrame(header, fg_color="transparent")
        url_frame.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkLabel(
            url_frame,
            text="📺 Video:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 10))

        url_display = ctk.CTkLabel(
            url_frame,
            text=url[:80] + "..." if len(url) > 80 else url,
            font=ctk.CTkFont(size=11),
            text_color="#4A90E2"
        )
        url_display.pack(side="left")

        # Status label with loading animation
        self.status_label = ctk.CTkLabel(
            header,
            text=f"⏳ Fetching available formats from {self.platform}...",
            font=ctk.CTkFont(size=12),
            text_color="#F39C12"
        )
        self.status_label.pack(anchor="w", padx=15, pady=(0, 10))
        
        # Start loading animation
        self.loading_dots = 0
        self.is_loading = True
        self._update_loading_animation()

        # Scrollable format list
        self.formats_frame = ctk.CTkScrollableFrame(
            self,
            corner_radius=15,
            label_text="📋 Available Formats (8K → 720p)"
        )
        self.formats_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Bottom buttons
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkButton(
            button_frame,
            text="❌ Cancel",
            height=40,
            corner_radius=10,
            fg_color="#E74C3C",
            hover_color="#C0392B",
            command=self.destroy
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.confirm_button = ctk.CTkButton(
            button_frame,
            text="✅ Use Selected Format",
            height=40,
            corner_radius=10,
            fg_color="#27AE60",
            hover_color="#229954",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._confirm_selection,
            state="disabled"
        )
        self.confirm_button.pack(side="left", fill="x", expand=True)

        # Start fetching formats
        threading.Thread(target=self._fetch_formats, daemon=True).start()

    # ------------------------------------------------------------------
    def _update_loading_animation(self):
        """Animate loading dots."""
        if not self.is_loading:
            return
        
        dots = "." * (self.loading_dots % 4)
        self.status_label.configure(
            text=f"⏳ Fetching available formats from {self.platform}{dots}   "
        )
        self.loading_dots += 1
        self.after(400, self._update_loading_animation)

    # ------------------------------------------------------------------
    def _fetch_formats(self):
        """Fetch formats in background thread."""
        self.formats_data = fetch_video_formats(self.url)
        self.is_loading = False
        self.after(0, self._display_formats)

    # ------------------------------------------------------------------
    def _display_formats(self):
        """Display fetched formats grouped by resolution."""
        if not self.formats_data:
            self.status_label.configure(
                text="❌ Could not fetch video info. Please check:\n• Internet connection\n• Video URL is valid\n• Video is not private/geo-blocked",
                text_color="#E74C3C"
            )
            
            # Add retry button
            retry_button = ctk.CTkButton(
                self.formats_frame,
                text="🔄 Retry",
                height=40,
                corner_radius=10,
                fg_color="#F39C12",
                hover_color="#D68910",
                font=ctk.CTkFont(size=14, weight="bold"),
                command=self._retry_fetch
            )
            retry_button.pack(pady=20)
            return

        self.status_label.configure(
            text=f"✅ Found formats for {len(self.formats_data)} resolution(s) • Fast fetch complete!",
            text_color="#27AE60"
        )

        # Display formats grouped by resolution
        for resolution in ["8K (4320p)", "4K (2160p)", "1440p", "1080p", "720p"]:
            if resolution not in self.formats_data:
                continue

            formats = self.formats_data[resolution]
            if not formats:
                continue

            # Resolution header
            res_header = ctk.CTkFrame(self.formats_frame, corner_radius=10)
            res_header.pack(fill="x", pady=(10, 5), padx=5)

            ctk.CTkLabel(
                res_header,
                text=f"🎬 {resolution}",
                font=ctk.CTkFont(size=16, weight="bold")
            ).pack(anchor="w", padx=15, pady=10)

            # Format items (grouped by video codec)
            codecs_seen = set()
            for fmt in formats:
                video_codec = fmt["video_codec"]
                
                # Only show first audio option per video codec to reduce clutter
                if video_codec in codecs_seen:
                    continue
                codecs_seen.add(video_codec)

                format_frame = ctk.CTkFrame(self.formats_frame, corner_radius=8)
                format_frame.pack(fill="x", pady=2, padx=10)

                # Make frame clickable
                format_button = ctk.CTkButton(
                    format_frame,
                    text=f"{fmt['video_codec']} • {fmt['format_string']} ({fmt['audio_codec']} {fmt['audio_bitrate']}kbps)",
                    font=ctk.CTkFont(size=13),
                    anchor="w",
                    fg_color="transparent",
                    hover_color="#9B59B6",
                    command=lambda f=fmt, r=resolution: self._select_format(f, r)
                )
                format_button.pack(fill="x", padx=5, pady=5)

                # Store reference for highlighting
                format_button._format_data = fmt
                format_button._resolution = resolution

        if not any(self.formats_data.values()):
            self.status_label.configure(
                text="⚠️ No video formats found (720p–8K)",
                text_color="#F39C12"
            )

    # ------------------------------------------------------------------
    def _retry_fetch(self):
        """Retry fetching formats."""
        # Clear formats frame
        for widget in self.formats_frame.winfo_children():
            widget.destroy()
        
        # Reset loading state
        self.is_loading = True
        self.loading_dots = 0
        self.status_label.configure(
            text=f"⏳ Retrying... Fetching formats from {self.platform}",
            text_color="#F39C12"
        )
        self._update_loading_animation()
        
        # Start fetch
        threading.Thread(target=self._fetch_formats, daemon=True).start()

    # ------------------------------------------------------------------
    def _select_format(self, fmt: Dict[str, str], resolution: str):
        """Handle format selection."""
        self.selected_format = {
            "resolution": resolution,
            "video_id": fmt["video_id"],
            "video_codec": fmt["video_codec"],
            "audio_id": fmt["audio_id"],
            "audio_codec": fmt["audio_codec"],
            "format_string": fmt["format_string"]
        }

        # Update status
        self.status_label.configure(
            text=f"✅ Selected: {resolution} {fmt['video_codec']} + {fmt['audio_codec']}",
            text_color="#27AE60"
        )

        # Enable confirm button
        self.confirm_button.configure(state="normal")

    # ------------------------------------------------------------------
    def _confirm_selection(self):
        """Confirm and apply selected format."""
        if not self.selected_format:
            return

        # Store in parent app
        self.parent_app.selected_format = self.selected_format

        # Update parent UI to show selection
        self.parent_app.video_log_text.insert(
            "end",
            f"\n🎯 Smart Format Selected:\n"
            f"Resolution: {self.selected_format['resolution']}\n"
            f"Video: {self.selected_format['video_codec']} (ID: {self.selected_format['video_id']})\n"
            f"Audio: {self.selected_format['audio_codec']} (ID: {self.selected_format['audio_id']})\n"
            f"Format: {self.selected_format['format_string']}\n\n"
        )
        self.parent_app.video_log_text.see("end")

        messagebox.showinfo(
            "Format Selected",
            f"Smart format selected:\n\n"
            f"{self.selected_format['resolution']}\n"
            f"{self.selected_format['video_codec']} + {self.selected_format['audio_codec']}\n\n"
            f"Click 'Download Video' to start."
        )

        self.destroy()


# ----------------------------------------------------------------------
# Format Checker Window
# ----------------------------------------------------------------------
class FormatCheckerWindow(ctk.CTkToplevel):
    """Format checker window with all your original features + enhancements."""

    def __init__(self, parent, default_url=""):
        super().__init__(parent)

        self.title("🔍 Format Checker - kexi's Downloader Pro")
        self.geometry("1100x750")
        self.minsize(900, 600)
        
        # Set icon
        icon_path = Path(__file__).parent / "app.icon.png"
        if icon_path.exists():
            try:
                self.iconphoto(True, tk.PhotoImage(file=str(icon_path)))
            except Exception as e:
                print(f"Could not load icon: {e}")

        # URL input
        url_frame = ctk.CTkFrame(self, corner_radius=15)
        url_frame.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(
            url_frame,
            text="📺 YouTube URL:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))

        url_input_frame = ctk.CTkFrame(url_frame, fg_color="transparent")
        url_input_frame.pack(fill="x", padx=15, pady=(0, 15))

        self.url_entry = ctk.CTkEntry(
            url_input_frame,
            placeholder_text="Paste YouTube URL here...",
            height=40,
            corner_radius=10
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        if default_url:
            self. url_entry.insert(0, default_url)

        ctk.CTkButton(
            url_input_frame,
            text="🔍 Check Formats",
            width=150,
            height=40,
            corner_radius=10,
            fg_color="#4A90E2",
            hover_color="#357ABD",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._fetch_formats
        ).pack(side="left")

        # Filter controls
        filter_frame = ctk.CTkFrame(self, corner_radius=15)
        filter_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            filter_frame,
            text="🔽 Filter:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left", padx=(15, 10))

        self.filter_var = ctk.StringVar(value="all")

        filters = [
            ("All Formats", "all"),
            ("Audio Only", "audio"),
            ("High Audio ≥256kbps", "high_audio"),
            ("Best Audio ≥480kbps", "highest_audio"),
            ("Video Only", "video"),
        ]

        for text, value in filters:
            ctk. CTkRadioButton(
                filter_frame,
                text=text,
                variable=self.filter_var,
                value=value,
                command=self._apply_filter
            ).pack(side="left", padx=5)

        # Info label
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(fill="x", padx=20)

        ctk.CTkLabel(
            info_frame,
            text="💡 Tip: YouTube max audio bitrates - Stereo:  384kbps, 5.1: 512kbps",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        ).pack(anchor="w")

        # Results text box
        results_frame = ctk.CTkFrame(self, corner_radius=15)
        results_frame.pack(fill="both", expand=True, padx=20, pady=(10, 20))

        self.results_text = tk.Text(
            results_frame,
            wrap="none",
            font=("SF Mono", 10),
            bg="#1E1E1E" if ctk.get_appearance_mode() == "Dark" else "#F5F0E8",
            fg="#A8FF60" if ctk.get_appearance_mode() == "Dark" else "#5A524A",
            relief="flat",
            borderwidth=0,
            padx=15,
            pady=15
        )
        self.results_text.pack(fill="both", expand=True, padx=2, pady=2)

        # Add context menu
        self._add_context_menu()

        self.raw_output = ""

    # ------------------------------------------------------------------
    def _add_context_menu(self):
        """Add right-click context menu."""
        menu = tk.Menu(self. results_text, tearoff=0)
        menu.add_command(label="Copy All", command=self._copy_all)
        menu.add_command(label="Copy Selected", command=self._copy_selected)
        menu.add_separator()
        menu.add_command(label="Clear", command=lambda: self. results_text.delete("1.0", "end"))

        def show_menu(event):
            menu.tk_popup(event.x_root, event. y_root)

        self.results_text.bind("<Button-2>", show_menu)
        self.results_text.bind("<Control-Button-1>", show_menu)

    # ------------------------------------------------------------------
    def _copy_all(self):
        """Copy all text to clipboard."""
        content = self.results_text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(content)

    # ------------------------------------------------------------------
    def _copy_selected(self):
        """Copy selected text to clipboard."""
        try:
            content = self.results_text.get("sel.first", "sel.last")
            self.clipboard_clear()
            self.clipboard_append(content)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    def _fetch_formats(self):
        """Fetch formats using yt-dlp."""
        url = self.url_entry.get().strip()
        if not url or not URL_RE.match(url):
            messagebox.showerror("Invalid URL", "Please enter a valid YouTube URL.")
            return

        self.results_text.delete("1.0", "end")
        self.results_text.insert("1.0", "⏳ Fetching formats from YouTube...\n\n")

        def worker():
            cmd = [YTDLP_EXE, "--remote-components", "ejs:github", "--cookies-from-browser", "chrome", "-F", url]
            print("🍪 Using Chrome cookies for YouTube")

            try:
                creation_flags = 0
                if os.name == "nt": 
                    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

                # Set up environment for bundled app
                env = os.environ.copy()
                if getattr(sys, "frozen", False):
                    bundle_dir = Path(sys.executable).parent
                    resources_dir = bundle_dir.parent / "Resources"
                    env["PYTHONHOME"] = str(resources_dir)
                    env["PYTHONPATH"] = str(resources_dir / "lib" / "python3.13")

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creation_flags,
                    env=env,
                )

                raw_lines = []
                if proc.stdout:
                    for ln in proc.stdout:
                        raw_lines.append(ln. rstrip())

                self.raw_output = "\n".join(raw_lines)
                self.after(0, self._apply_filter)
                proc.wait()
            except Exception as exc:
                error_msg = str(exc)
                self.after(0, lambda msg=error_msg: self.results_text.insert("end", f"\n❌ Error: {msg}\n"))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    def _apply_filter(self):
        """Apply the selected filter to the results."""
        if not self.raw_output:
            return

        filtered = self._parse_and_filter(self.raw_output, self.filter_var.get())
        self.results_text. delete("1.0", "end")
        self.results_text.insert("1.0", filtered)

    # ------------------------------------------------------------------
    def _parse_and_filter(self, output: str, filter_type: str) -> str:
        """Parse and filter format output with quality indicators."""
        lines = output.split("\n")
        result = []
        audio_formats = []

        # Find header
        start = -1
        for i, line in enumerate(lines):
            if "ID" in line and "EXT" in line and "RESOLUTION" in line:
                start = i
                break
        if start == -1:
            return output

        result.extend(lines[: start + 2])

        # Process formats
        for line in lines[start + 2:]:
            if not line.strip():
                continue
            low = line.lower()
            bitrate = 0
            m = re.search(r"(\d+)k", low)
            if m:
                bitrate = int(m.group(1))

            is_audio = "audio only" in low
            is_video = ("video only" in low) or ("x" in low and not is_audio)

            # Add quality indicator
            indicator = ""
            if is_audio: 
                if bitrate >= 480:
                    indicator = " 🟢 EXCELLENT"
                elif bitrate >= 256:
                    indicator = " 🟡 VERY GOOD"
                elif bitrate >= 160:
                    indicator = " 🟠 GOOD"
                else:
                    indicator = " 🔴 MEDIUM"

            modified_line = line + indicator if indicator else line

            if filter_type == "all":
                result.append(modified_line)
            elif filter_type == "audio" and is_audio:
                result.append(modified_line)
                audio_formats.append((bitrate, line))
            elif filter_type == "high_audio" and is_audio and bitrate >= 256:
                result.append(modified_line)
                audio_formats.append((bitrate, line))
            elif filter_type == "highest_audio" and is_audio and bitrate >= 480:
                result. append(modified_line)
                audio_formats.append((bitrate, line))
            elif filter_type == "video" and is_video:
                result.append(modified_line)

        # Audio summary
        if filter_type in {"audio", "high_audio", "highest_audio"} and audio_formats:
            audio_formats.sort(reverse=True)
            result.append("\n" + "=" * 80)
            result.append("📊 AUDIO QUALITY SUMMARY:")
            result.append("=" * 80)

            max_br = audio_formats[0][0]
            result.append(f"🎵 Highest available bitrate: {max_br} kbps")
            if max_br >= 480:
                result.append("✅ EXCELLENT – near YouTube's max (512 kbps 5.1)")
            elif max_br >= 256:
                result.append("✅ VERY GOOD – high-quality stereo (max 384 kbps)")
            elif max_br >= 160:
                result.append("✓ GOOD – standard quality")
            else:
                result. append("⚠ MEDIUM – lower-quality audio")

            result.append(f"\n📋 Found {len(audio_formats)} audio format(s)")
            result.append("\n💡 Recommended:  Use format ID {audio_formats[0][1]. split()[0]} for best quality")

        return "\n".join(result)


# ----------------------------------------------------------------------
# Preferences Window
# ----------------------------------------------------------------------
class PreferencesWindow(ctk.CTkToplevel):
    """Preferences window."""

    def __init__(self, parent):
        super().__init__(parent)

        self.title("⚙️ Preferences")
        self.geometry("600x400")
        self.minsize(500, 300)
        
        # Set icon
        icon_path = Path(__file__).parent / "app.icon.png"
        if icon_path.exists():
            try:
                self.iconphoto(True, tk.PhotoImage(file=str(icon_path)))
            except Exception as e:
                print(f"Could not load icon: {e}")

        # Title
        ctk.CTkLabel(
            self,
            text="⚙️ Preferences",
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(pady=20)

        # Settings frame
        settings_frame = ctk.CTkFrame(self, corner_radius=15)
        settings_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        ctk.CTkLabel(
            settings_frame,
            text="🎨 Appearance",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            settings_frame,
            text="Theme:",
            font=ctk. CTkFont(size=13)
        ).pack(anchor="w", padx=20, pady=(10, 5))

        theme_var = ctk.StringVar(value=ctk.get_appearance_mode())
        theme_menu = ctk.CTkOptionMenu(
            settings_frame,
            variable=theme_var,
            values=["System", "Light", "Dark"],
            command=lambda choice: ctk.set_appearance_mode(choice),
            width=200,
            height=35,
            corner_radius=8
        )
        theme_menu.pack(anchor="w", padx=20, pady=(0, 20))

        # Info
        ctk.CTkLabel(
            settings_frame,
            text="More preferences coming soon!  🚀",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        ).pack(pady=20)


# ----------------------------------------------------------------------
# Run the app
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    def _diagnostic_log(msg):
        print(f"[DIAG] {msg}", file=sys.stderr)

    _diagnostic_log("Script start")
    try:
        _diagnostic_log("Imports and global setup complete")
        _diagnostic_log("__main__ entry point reached")
        try:
            app = kexisdownloader()
            app.mainloop()
        except Exception as e:
            import traceback
            _diagnostic_log(f"Exception in main app: {e}\n" + traceback.format_exc())
            raise
    except Exception as e:
        import traceback
        _diagnostic_log(f"Top-level exception: {e}\n" + traceback.format_exc())
        raise