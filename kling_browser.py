"""
Kling AI Browser Automation Module
===================================
Uses Playwright to automate Kling AI web interface for 3D video generation.
Free accounts don't have API access, so we use browser automation.

Author: Kilat Code Clipper
Date: Dec 2025
"""

import os
import time
import json
import tempfile
from typing import Optional, Callable
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# Kling AI URLs (global version)
KLING_URL = "https://app.klingai.com/global/"
KLING_CREATE_URL = "https://app.klingai.com/global/text-to-video"
KLING_IMG2VID_URL = "https://app.klingai.com/global/image-to-video"


class KlingBrowser:
    """
    Kling AI browser automation using Playwright.
    
    Usage:
        kling = KlingBrowser(headless=False)
        kling.login()  # Opens browser for manual login
        kling.save_cookies("kling_cookies.json")
        
        # Later, use saved cookies:
        kling = KlingBrowser(headless=True)
        kling.load_cookies("kling_cookies.json")
        video_path = kling.image_to_video("image.png", "Make this move", duration=5)
    """
    
    def __init__(self, headless: bool = True, timeout: int = 300000):
        """
        Initialize Kling browser automation.
        
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
    
    def login(self, wait_for_manual: bool = True) -> bool:
        """
        Navigate to Kling AI login page.
        
        Args:
            wait_for_manual: If True, wait for user to complete login manually
            
        Returns:
            True if login successful
        """
        if not self.page:
            self.start()
        
        print("[KlingBrowser] Navigating to Kling AI...")
        self.page.goto(KLING_URL)
        
        if wait_for_manual:
            print("[KlingBrowser] Please log in manually in the browser window...")
            print("[KlingBrowser] Waiting for login to complete...")
            
            # Wait for user to be logged in (look for profile/avatar element)
            try:
                # Wait for either profile picture or create button to appear
                self.page.wait_for_selector('[class*="avatar"], [class*="profile"], [class*="user"]', timeout=300000)
                self._is_logged_in = True
                print("[KlingBrowser] Login detected!")
                return True
            except Exception as e:
                print(f"[KlingBrowser] Login timeout or error: {e}")
                return False
        
        return True
    
    def save_cookies(self, filepath: str):
        """Save browser cookies to file for future sessions."""
        if not self.context:
            raise RuntimeError("Browser not started")
        
        cookies = self.context.cookies()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2)
        print(f"[KlingBrowser] Cookies saved to {filepath}")
    
    def _parse_netscape_cookies(self, filepath: str) -> list:
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
    
    def load_cookies(self, filepath: str) -> bool:
        """Load cookies from file to restore session. Supports both JSON and Netscape TXT format."""
        if not os.path.exists(filepath):
            print(f"[KlingBrowser] Cookies file not found: {filepath}")
            return False
        
        if not self.context:
            self.start()
        
        try:
            # Detect format based on file content
            with open(filepath, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
            
            if first_line.startswith('#') or '\t' in first_line:
                # Netscape format (TXT)
                print(f"[KlingBrowser] Detected Netscape cookies format")
                cookies = self._parse_netscape_cookies(filepath)
            else:
                # JSON format
                print(f"[KlingBrowser] Detected JSON cookies format")
                with open(filepath, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
            
            self.context.add_cookies(cookies)
            self._is_logged_in = True
            print(f"[KlingBrowser] Loaded {len(cookies)} cookies from {filepath}")
            return True
        except Exception as e:
            print(f"[KlingBrowser] Failed to load cookies: {e}")
            return False
    
    def is_logged_in(self) -> bool:
        """Check if user is logged in."""
        if not self.page:
            return False
        
        try:
            self.page.goto(KLING_URL, wait_until='domcontentloaded')
            # Check for logged-in indicators
            avatar = self.page.query_selector('[class*="avatar"], [class*="profile"]')
            return avatar is not None
        except:
            return False
    
    def image_to_video(
        self,
        image_path: str,
        prompt: str,
        duration: int = 5,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """
        Generate video from image using Kling AI.
        
        Args:
            image_path: Path to input image
            prompt: Motion/animation prompt
            duration: Video duration in seconds (5 or 10)
            output_path: Where to save the result (auto-generated if None)
            progress_callback: Callback for progress updates (progress, message)
            
        Returns:
            Path to generated video, or None if failed
        """
        if not self.page:
            self.start()
        
        if not os.path.exists(image_path):
            print(f"[KlingBrowser] Image not found: {image_path}")
            return None
        
        def log(msg, progress=0):
            print(f"[KlingBrowser] {msg}")
            if progress_callback:
                progress_callback(progress, msg)
        
        try:
            log("Navigating to Image-to-Video...", 0.1)
            self.page.goto(KLING_IMG2VID_URL, wait_until='networkidle')
            time.sleep(2)
            
            # Find and click upload button
            log("Looking for upload button...", 0.15)
            
            # Try multiple selectors for upload
            upload_selectors = [
                'input[type="file"]',
                '[class*="upload"] input',
                '[data-testid*="upload"]',
                'button:has-text("Upload")',
            ]
            
            file_input = None
            for selector in upload_selectors:
                try:
                    file_input = self.page.query_selector(selector)
                    if file_input:
                        break
                except:
                    continue
            
            if not file_input:
                log("Could not find upload button. Page may have changed.", 0)
                return None
            
            # Upload image
            log(f"Uploading image: {os.path.basename(image_path)}", 0.2)
            file_input.set_input_files(image_path)
            time.sleep(2)
            
            # Enter prompt
            log("Entering motion prompt...", 0.3)
            prompt_selectors = [
                'textarea[placeholder*="prompt"]',
                'textarea[class*="prompt"]',
                'input[placeholder*="describe"]',
                'textarea',
            ]
            
            prompt_input = None
            for selector in prompt_selectors:
                try:
                    prompt_input = self.page.query_selector(selector)
                    if prompt_input:
                        break
                except:
                    continue
            
            if prompt_input:
                prompt_input.fill(prompt)
            else:
                log("Could not find prompt input", 0)
            
            # Set duration if option exists
            log(f"Setting duration to {duration}s...", 0.35)
            try:
                duration_btn = self.page.query_selector(f'button:has-text("{duration}s"), [data-value="{duration}"]')
                if duration_btn:
                    duration_btn.click()
            except:
                pass
            
            # Click generate button
            log("Clicking Generate button...", 0.4)
            generate_selectors = [
                'button:has-text("Generate")',
                'button:has-text("Create")',
                'button[class*="generate"]',
                'button[class*="submit"]',
            ]
            
            for selector in generate_selectors:
                try:
                    btn = self.page.query_selector(selector)
                    if btn and btn.is_visible():
                        btn.click()
                        break
                except:
                    continue
            
            # Wait for generation to complete
            log("Waiting for video generation (this may take 2-5 minutes)...", 0.5)
            
            # Poll for completion
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
                    log("Generation complete!", 0.95)
                    break
                
                # Check for error
                error = self.page.query_selector('[class*="error"], [class*="fail"]')
                if error:
                    error_text = error.inner_text()
                    log(f"Generation failed: {error_text}", 0)
                    return None
                
                time.sleep(5)
            
            # Download the result
            log("Downloading generated video...", 0.97)
            
            if not output_path:
                output_path = os.path.join(tempfile.gettempdir(), f"kling_video_{int(time.time())}.mp4")
            
            # Try to find and click download button
            download_success = False
            for selector in ['button:has-text("Download")', 'a[download]', '[class*="download"]']:
                try:
                    download_btn = self.page.query_selector(selector)
                    if download_btn:
                        with self.page.expect_download() as download_info:
                            download_btn.click()
                        download = download_info.value
                        download.save_as(output_path)
                        download_success = True
                        break
                except:
                    continue
            
            if not download_success:
                # Try to get video src directly
                video = self.page.query_selector('video[src]')
                if video:
                    video_url = video.get_attribute('src')
                    if video_url:
                        # Download via requests or page.goto
                        log(f"Video URL found: {video_url[:50]}...", 0.98)
                        # TODO: Download video from URL
                        pass
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                log(f"Video saved to: {output_path}", 1.0)
                return output_path
            else:
                log("Failed to save video", 0)
                return None
            
        except Exception as e:
            log(f"Error during generation: {str(e)}", 0)
            return None
    
    def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """
        Generate video from text prompt using Kling AI.
        
        Args:
            prompt: Text description of desired video
            duration: Video duration in seconds
            output_path: Where to save the result
            progress_callback: Callback for progress updates
            
        Returns:
            Path to generated video, or None if failed
        """
        if not self.page:
            self.start()
        
        def log(msg, progress=0):
            print(f"[KlingBrowser] {msg}")
            if progress_callback:
                progress_callback(progress, msg)
        
        try:
            log("Navigating to Text-to-Video...", 0.1)
            self.page.goto(KLING_CREATE_URL, wait_until='networkidle')
            time.sleep(2)
            
            # Enter prompt
            log("Entering prompt...", 0.2)
            prompt_input = self.page.query_selector('textarea, input[type="text"]')
            if prompt_input:
                prompt_input.fill(prompt)
            
            # Click generate and wait (similar to image_to_video)
            # ... (similar flow)
            
            log("Text-to-video not fully implemented yet", 0)
            return None
            
        except Exception as e:
            log(f"Error: {str(e)}", 0)
            return None


# ============================================================================
# TESTING
# ============================================================================

def test_kling_login():
    """Test manual login flow."""
    print("Testing Kling AI login...")
    
    with KlingBrowser(headless=False) as kling:
        if kling.login(wait_for_manual=True):
            print("Login successful!")
            kling.save_cookies("kling_cookies.json")
        else:
            print("Login failed or timed out")


def test_kling_generation():
    """Test video generation with saved cookies."""
    print("Testing Kling AI video generation...")
    
    with KlingBrowser(headless=False) as kling:
        if not kling.load_cookies("kling_cookies.json"):
            print("Please run test_kling_login() first")
            return
        
        result = kling.image_to_video(
            image_path="test_image.png",
            prompt="Make the character wave their hand and smile",
            duration=5
        )
        
        if result:
            print(f"Video generated: {result}")
        else:
            print("Generation failed")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "login":
            test_kling_login()
        elif sys.argv[1] == "test":
            test_kling_generation()
    else:
        print("Usage:")
        print("  python kling_browser.py login  - Manual login and save cookies")
        print("  python kling_browser.py test   - Test video generation")
