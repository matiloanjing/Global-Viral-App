"""
MindVideo AI Browser Automation Module
=======================================
Uses Playwright to automate MindVideo.ai web interface for Image-to-Video generation.
Free tier uses Sora 2 Free (Beta) model.

Author: Kilat Code Clipper
Date: Dec 2025
"""

import os
import time
import json
import tempfile
from typing import Optional, Callable, List
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# MindVideo URLs
MINDVIDEO_URL = "https://www.mindvideo.ai"
MINDVIDEO_IMG2VID_URL = "https://www.mindvideo.ai/image-to-video/"


def parse_netscape_cookies(filepath: str) -> List[dict]:
    """Parse Netscape format cookies file (TXT) to Playwright format."""
    cookies = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('\t')
            if len(parts) >= 7:
                domain, include_subdomains, path, secure, expires, name, value = parts[:7]
                
                cookie = {
                    'name': name,
                    'value': value,
                    'domain': domain,
                    'path': path,
                    'expires': int(expires) if expires.isdigit() else -1,
                    'httpOnly': False,
                    'secure': secure.upper() == 'TRUE',
                    'sameSite': 'Lax'
                }
                cookies.append(cookie)
    
    return cookies


class MindVideoBrowser:
    """
    MindVideo AI browser automation using Playwright.
    
    Usage:
        # With manual login:
        mvid = MindVideoBrowser(headless=False)
        mvid.login_manual()  # Opens browser for manual login
        mvid.save_cookies("mindvideo_cookies.json")
        
        # Later, use saved cookies:
        mvid = MindVideoBrowser(headless=True)
        mvid.load_cookies("mindvideo_cookies.json")
        video_path = mvid.image_to_video("image.png", "Camera slowly zooms in")
    """
    
    def __init__(self, headless: bool = True, timeout: int = 300000):
        """
        Initialize MindVideo browser automation.
        
        Args:
            headless: Run browser without GUI (faster, but can't see what's happening)
            timeout: Default timeout in milliseconds (5 minutes)
        """
        if not HAS_PLAYWRIGHT:
            raise ImportError("Playwright not installed. Run: pip install playwright && python -m playwright install chromium")
        
        self.headless = headless
        self.timeout = timeout
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._is_logged_in = False
    
    def start(self):
        """Start the browser."""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout)
    
    def close(self):
        """Close the browser and cleanup."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def login_manual(self, wait_timeout: int = 300000) -> bool:
        """
        Navigate to MindVideo and wait for manual login.
        
        Args:
            wait_timeout: Timeout in ms to wait for login (default 5 min)
            
        Returns:
            True if login successful
        """
        if not self.page:
            self.start()
        
        print("[MindVideo] Navigating to MindVideo.ai...")
        self.page.goto(MINDVIDEO_IMG2VID_URL)
        
        print("[MindVideo] Please log in manually (Google or Email)...")
        print("[MindVideo] Click 'Sign In' button and complete login...")
        print("[MindVideo] Waiting for login to complete...")
        
        try:
            # Wait for login to complete - look for user profile element
            # After login, the Sign In button usually disappears or changes
            self.page.wait_for_function(
                """() => {
                    // Check if user is logged in by looking for profile/avatar elements
                    const signInBtn = Array.from(document.querySelectorAll('button, span'))
                        .find(el => el.textContent.trim() === 'Sign In');
                    return !signInBtn || !signInBtn.offsetParent;  // Hidden or removed
                }""",
                timeout=wait_timeout
            )
            self._is_logged_in = True
            print("[MindVideo] Login detected!")
            return True
        except Exception as e:
            print(f"[MindVideo] Login timeout or error: {e}")
            return False
    
    def save_cookies(self, filepath: str):
        """Save browser cookies to file for future sessions."""
        if not self.context:
            raise RuntimeError("Browser not started")
        
        cookies = self.context.cookies()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2)
        print(f"[MindVideo] Cookies saved to {filepath}")
    
    def load_cookies(self, filepath: str) -> bool:
        """Load cookies from file. Supports both JSON and Netscape TXT format."""
        if not os.path.exists(filepath):
            print(f"[MindVideo] Cookies file not found: {filepath}")
            return False
        
        if not self.context:
            self.start()
        
        try:
            # Detect format
            with open(filepath, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
            
            if first_line.startswith('#') or '\t' in first_line:
                # Netscape format (TXT)
                print(f"[MindVideo] Detected Netscape cookies format")
                cookies = parse_netscape_cookies(filepath)
            else:
                # JSON format
                print(f"[MindVideo] Detected JSON cookies format")
                with open(filepath, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
            
            self.context.add_cookies(cookies)
            self._is_logged_in = True
            print(f"[MindVideo] Loaded {len(cookies)} cookies from {filepath}")
            return True
        except Exception as e:
            print(f"[MindVideo] Failed to load cookies: {e}")
            return False
    
    def is_logged_in(self) -> bool:
        """Check if user is currently logged in."""
        if not self.page:
            return False
        
        try:
            # Check for Sign In button (visible = not logged in)
            sign_in = self.page.query_selector('button:has-text("Sign In"), span:has-text("Sign In")')
            return sign_in is None or not sign_in.is_visible()
        except:
            return False
    
    def image_to_video(
        self,
        image_path: str,
        prompt: str,
        aspect_ratio: str = "9:16",  # "9:16" or "16:9"
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """
        Generate video from image using MindVideo AI.
        
        Args:
            image_path: Path to input image
            prompt: Motion/animation prompt (e.g., "Slow zoom in with cinematic lighting")
            aspect_ratio: Output aspect ratio ("9:16" for vertical, "16:9" for horizontal)
            output_path: Where to save the result (auto-generated if None)
            progress_callback: Callback for progress updates (progress, message)
            
        Returns:
            Path to generated video, or None if failed
        """
        if not self.page:
            self.start()
        
        if not os.path.exists(image_path):
            print(f"[MindVideo] Image not found: {image_path}")
            return None
        
        def log(msg, progress=0):
            print(f"[MindVideo] {msg}")
            if progress_callback:
                progress_callback(progress, msg)
        
        try:
            log("Navigating to Image-to-Video page...", 0.05)
            self.page.goto(MINDVIDEO_IMG2VID_URL, wait_until='networkidle')
            time.sleep(3)
            
            # Check if logged in
            if not self.is_logged_in():
                log("⚠️ Not logged in! Please login first.", 0)
                return None
            
            # Step 1: Upload image
            log(f"Uploading image: {os.path.basename(image_path)}", 0.1)
            
            # Find file input (usually hidden)
            file_input = self.page.query_selector('input[type="file"]')
            if not file_input:
                log("❌ Could not find file input", 0)
                return None
            
            file_input.set_input_files(image_path)
            time.sleep(2)
            log("✅ Image uploaded", 0.2)
            
            # Step 2: Enter prompt
            log("Entering motion prompt...", 0.25)
            prompt_input = self.page.query_selector('textarea')
            if prompt_input:
                prompt_input.fill(prompt)
                log("✅ Prompt entered", 0.3)
            else:
                log("⚠️ Could not find prompt input", 0.3)
            
            # Step 3: Select aspect ratio if different from default
            if aspect_ratio == "16:9":
                log("Setting aspect ratio to 16:9...", 0.35)
                try:
                    ratio_btn = self.page.query_selector('div:has-text("16:9"), span:has-text("16:9")')
                    if ratio_btn:
                        ratio_btn.click()
                        time.sleep(0.5)
                except:
                    pass
            
            # Step 4: Click Create button
            log("Clicking Create button...", 0.4)
            create_btn = self.page.query_selector('button:has-text("Create")')
            
            if not create_btn:
                log("❌ Could not find Create button", 0)
                return None
            
            if not create_btn.is_enabled():
                log("❌ Create button is disabled (check login or image upload)", 0)
                return None
            
            create_btn.click()
            log("✅ Generation started!", 0.45)
            
            # Step 5: Wait for generation
            log("Waiting for video generation (2-5 minutes)...", 0.5)
            
            max_wait = 600  # 10 minutes max
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                elapsed = time.time() - start_time
                progress = 0.5 + (elapsed / max_wait) * 0.4
                log(f"Generating... ({int(elapsed)}s elapsed)", min(progress, 0.9))
                
                # Check for video element or download button
                video = self.page.query_selector('video[src], [class*="video-player"], [class*="result"]')
                download_btn = self.page.query_selector('button:has-text("Download"), a[download], [class*="download"]')
                
                if video or download_btn:
                    log("✅ Generation complete!", 0.95)
                    break
                
                # Check for error
                error = self.page.query_selector('[class*="error"], [class*="fail"]')
                if error and error.is_visible():
                    error_text = error.inner_text()
                    log(f"❌ Generation failed: {error_text}", 0)
                    return None
                
                time.sleep(5)
            
            # Step 6: Download video
            log("Downloading video...", 0.97)
            
            if not output_path:
                output_path = os.path.join(tempfile.gettempdir(), f"mindvideo_{int(time.time())}.mp4")
            
            download_success = False
            
            # Try download button
            for selector in ['button:has-text("Download")', 'a[download]', '[class*="download"]']:
                try:
                    download_btn = self.page.query_selector(selector)
                    if download_btn and download_btn.is_visible():
                        with self.page.expect_download() as download_info:
                            download_btn.click()
                        download = download_info.value
                        download.save_as(output_path)
                        download_success = True
                        break
                except:
                    continue
            
            # Fallback: try to get video src
            if not download_success:
                video = self.page.query_selector('video[src]')
                if video:
                    video_url = video.get_attribute('src')
                    if video_url:
                        log(f"Video URL found, downloading...", 0.98)
                        # Use page.goto to download
                        try:
                            import requests
                            response = requests.get(video_url, stream=True)
                            with open(output_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            download_success = True
                        except:
                            pass
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                log(f"✅ Video saved: {output_path}", 1.0)
                return output_path
            else:
                log("❌ Failed to save video", 0)
                return None
            
        except Exception as e:
            log(f"❌ Error: {str(e)}", 0)
            return None


# ============================================================================
# HELPER FUNCTION FOR INTEGRATION
# ============================================================================

def generate_3d_video(
    image_path: str,
    prompt: str,
    cookies_path: str = None,
    output_path: str = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Optional[str]:
    """
    High-level function to generate 3D-animated video from image.
    
    Args:
        image_path: Path to source image
        prompt: Animation prompt
        cookies_path: Path to cookies file (optional, will prompt login if None)
        output_path: Where to save result
        progress_callback: Progress callback function
        
    Returns:
        Path to generated video, or None if failed
    """
    if not HAS_PLAYWRIGHT:
        print("[MindVideo] Playwright not installed!")
        return None
    
    # Default cookies path
    if not cookies_path:
        cookies_path = os.path.join(os.path.dirname(__file__), "mindvideo_cookies.json")
    
    with MindVideoBrowser(headless=False) as mvid:  # headless=False for debugging
        # Load cookies or do manual login
        if os.path.exists(cookies_path):
            mvid.load_cookies(cookies_path)
        else:
            print("[MindVideo] No cookies found. Please login manually...")
            if not mvid.login_manual():
                return None
            mvid.save_cookies(cookies_path)
        
        # Generate video
        return mvid.image_to_video(
            image_path=image_path,
            prompt=prompt,
            output_path=output_path,
            progress_callback=progress_callback
        )


# ============================================================================
# CLI / TESTING
# ============================================================================

def test_login():
    """Test manual login flow."""
    print("=" * 60)
    print("MINDVIDEO LOGIN TEST")
    print("=" * 60)
    
    with MindVideoBrowser(headless=False) as mvid:
        if mvid.login_manual():
            print("✅ Login successful!")
            mvid.save_cookies("mindvideo_cookies.json")
            print("✅ Cookies saved to mindvideo_cookies.json")
        else:
            print("❌ Login failed")


def test_navigation():
    """Test navigation with cookies."""
    print("=" * 60)
    print("MINDVIDEO NAVIGATION TEST")
    print("=" * 60)
    
    cookies_file = os.path.join(os.path.dirname(__file__), "mindvideo_cookies.txt")
    
    with MindVideoBrowser(headless=False) as mvid:
        if os.path.exists(cookies_file):
            mvid.load_cookies(cookies_file)
        
        mvid.page.goto(MINDVIDEO_IMG2VID_URL)
        mvid.page.wait_for_timeout(5000)
        
        logged_in = mvid.is_logged_in()
        print(f"Logged in: {'✅ Yes' if logged_in else '❌ No'}")
        
        # Keep browser open for inspection
        print("Browser open for 10s for inspection...")
        mvid.page.wait_for_timeout(10000)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "login":
            test_login()
        elif cmd == "nav":
            test_navigation()
        else:
            print(f"Unknown command: {cmd}")
    else:
        print("Usage:")
        print("  python mindvideo_browser.py login  - Login and save cookies")
        print("  python mindvideo_browser.py nav    - Test navigation with cookies")
