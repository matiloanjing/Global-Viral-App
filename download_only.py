"""
Download YouTube video ONLY (no processing)
Use this with VPN ON, then run test_local_video.py with VPN OFF
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from youtube_helper import download_youtube_video, get_cookies_instructions

# Configuration
TEST_URL = "https://www.youtube.com/watch?v=Q16g_jjCzYk"
OUTPUT_VIDEO = os.path.join(os.path.dirname(__file__), "downloaded_video.mp4")
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "youtube_cookies.txt")

print("=" * 60)
print("YouTube Download ONLY (VPN should be ON)")
print("=" * 60)
print(f"URL: {TEST_URL}")
print(f"Output: {OUTPUT_VIDEO}")
print(f"Cookies: {'FOUND' if os.path.exists(COOKIES_FILE) else 'NOT FOUND'}")
print()

# Download
success, result = download_youtube_video(
    url=TEST_URL,
    output_path=OUTPUT_VIDEO,
    cookies_file=COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
    max_height=720
)

if success:
    print()
    print("=" * 60)
    print("SUCCESS! Video downloaded.")
    print("=" * 60)
    print(f"File: {result}")
    print(f"Size: {os.path.getsize(result) / (1024*1024):.1f} MB")
    print()
    print("NEXT STEPS:")
    print("1. TURN OFF VPN")
    print("2. Run: python test_local_video.py")
    print(f"   (Edit LOCAL_VIDEO path to: {result})")
else:
    print()
    print("FAILED!")
    print(f"Error: {result}")
    print(get_cookies_instructions())
