"""
YouTube Download Helper - Production-Grade Solution
Handles YouTube's anti-bot detection with multiple fallback strategies.
"""

import os
import sys
import subprocess
import time
from typing import Optional, Tuple

# Try to import yt-dlp
try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False
    print("[YouTubeHelper] yt-dlp not installed")


def update_ytdlp() -> bool:
    """Update yt-dlp to latest version to handle YouTube API changes."""
    try:
        print("[YouTubeHelper] Updating yt-dlp...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            print("[YouTubeHelper] yt-dlp updated successfully")
            return True
        else:
            print(f"[YouTubeHelper] yt-dlp update failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"[YouTubeHelper] yt-dlp update error: {e}")
        return False


def download_youtube_video(
    url: str,
    output_path: str,
    cookies_file: Optional[str] = None,
    max_height: int = 720,
    progress_callback: callable = None
) -> Tuple[bool, str]:
    """
    Download YouTube video with production-grade anti-bot handling.
    
    Strategy order:
    1. Try with cookies file (if provided)
    2. Try with mobile clients (no PO token needed)
    3. Try with ios client (different API)
    4. Try with tv client (legacy API)
    
    Args:
        url: YouTube URL
        output_path: Output file path
        cookies_file: Optional path to cookies.txt file
        max_height: Maximum video height (default 720p)
        progress_callback: Optional callback(percent, message)
    
    Returns:
        Tuple of (success: bool, result: str)
    """
    if not HAS_YTDLP:
        return False, "yt-dlp not installed"
    
    def log(msg):
        print(f"[YouTubeHelper] {msg}")
        if progress_callback:
            progress_callback(0, msg)
    
    # Verify cookies file if provided
    if cookies_file and not os.path.exists(cookies_file):
        log(f"Warning: Cookies file not found: {cookies_file}")
        cookies_file = None
    
    # Base options for all attempts
    base_opts = {
        'format': f'best[height<={max_height}]/best',
        'outtmpl': output_path,
        'no_playlist': True,
        'socket_timeout': 30,
        'retries': 3,
        # Rate limiting to avoid detection
        'sleep_interval': 3,
        'max_sleep_interval': 8,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }
    
    # Strategy list - order matters!
    strategies = []
    
    # Strategy 1: With cookies (if available)
    if cookies_file:
        strategies.append({
            'name': 'Cookies file',
            'opts': {
                'cookiefile': cookies_file,
                # Don't use extractor_args with cookies - can conflict
            }
        })
    
    # Strategy 2: Android client (no PO token, no cookies needed for public)
    strategies.append({
        'name': 'Android client',
        'opts': {
            'extractor_args': {'youtube': {'player_client': ['android']}}
        }
    })
    
    # Strategy 3: iOS client
    strategies.append({
        'name': 'iOS client', 
        'opts': {
            'extractor_args': {'youtube': {'player_client': ['ios']}}
        }
    })
    
    # Strategy 4: TV client (legacy, sometimes bypasses)
    strategies.append({
        'name': 'TV client',
        'opts': {
            'extractor_args': {'youtube': {'player_client': ['tv']}}
        }
    })
    
    # Strategy 5: Web with mweb fallback
    strategies.append({
        'name': 'Web + mweb fallback',
        'opts': {
            'extractor_args': {'youtube': {'player_client': ['web', 'mweb']}}
        }
    })
    
    last_error = "No strategies attempted"
    
    for strategy in strategies:
        log(f"Trying: {strategy['name']}...")
        
        # Merge options
        opts = {**base_opts, **strategy['opts']}
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            
            # Check if file was created
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                log(f"SUCCESS with {strategy['name']}!")
                return True, output_path
            
            # Check alternative extensions
            for ext in ['.webm', '.mkv', '.mp4']:
                alt_path = output_path.rsplit('.', 1)[0] + ext
                if os.path.exists(alt_path) and os.path.getsize(alt_path) > 10000:
                    log(f"SUCCESS with {strategy['name']}!")
                    return True, alt_path
            
            last_error = f"{strategy['name']}: File not created"
            
        except Exception as e:
            error_str = str(e)
            last_error = f"{strategy['name']}: {error_str[:100]}"
            log(f"Failed: {last_error}")
            
            # Don't continue if it's a video-specific error (not bot detection)
            if "Video unavailable" in error_str or "Private video" in error_str:
                return False, error_str
            
            # Add delay before next attempt
            time.sleep(2)
    
    return False, last_error


def get_cookies_instructions() -> str:
    """Return user-friendly instructions for exporting cookies."""
    return """
================================================================================
YouTube Bot Detection - Cookies Required
================================================================================

YouTube has detected automated access. To fix this:

OPTION 1: Export cookies from browser (MUST use INCOGNITO window!)
  1. Open a new INCOGNITO/PRIVATE browser window
  2. Login to YouTube
  3. Go to: https://www.youtube.com/robots.txt
  4. Install extension: "Get cookies.txt LOCALLY"
  5. Click extension, export cookies for youtube.com
  6. Save as: youtube_cookies.txt in the app folder
  7. IMMEDIATELY CLOSE the incognito window (important!)
  8. Try again

OPTION 2: Use local video file
  - Download video manually from YouTube (using browser)
  - Use the local file path instead of YouTube URL

OPTION 3: YouTube Premium account
  - Premium accounts have fewer restrictions
  - Export cookies from a Premium-logged-in browser

NOTE: If IP is flagged, try using a VPN to change your IP address.
================================================================================
"""


def check_local_or_url(path_or_url: str) -> Tuple[bool, str]:
    """
    Check if input is a local file or URL.
    Returns: (is_local: bool, path_or_url: str)
    """
    if os.path.exists(path_or_url):
        return True, path_or_url
    elif path_or_url.startswith(('http://', 'https://', 'www.')):
        return False, path_or_url
    else:
        return False, path_or_url


# Export for easy import
__all__ = [
    'download_youtube_video',
    'update_ytdlp', 
    'get_cookies_instructions',
    'check_local_or_url',
    'HAS_YTDLP'
]
