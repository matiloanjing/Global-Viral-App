"""
GeminiGen.ai - Connect via CDP to existing Chrome
================================================
This connects to Chrome running with --remote-debugging-port=9222
where user is already logged in.
"""
import json
import os
import time
from typing import Optional, Callable
from playwright.sync_api import sync_playwright

class GeminiGenCDP:
    """Connect to Chrome via CDP for GeminiGen automation."""
    
    def __init__(self, cdp_url: str = "http://localhost:9222"):
        self.cdp_url = cdp_url
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
    
    def connect(self) -> bool:
        """Connect to Chrome via CDP."""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
            
            if not self.browser.contexts:
                print("[GeminiGen] No browser contexts found")
                return False
            
            self.context = self.browser.contexts[0]
            
            # Find or create geminigen page
            for page in self.context.pages:
                if 'geminigen' in page.url.lower():
                    self.page = page
                    break
            
            if not self.page:
                self.page = self.context.new_page()
            
            print(f"[GeminiGen] Connected via CDP. Page: {self.page.url}")
            return True
            
        except Exception as e:
            print(f"[GeminiGen] Connection failed: {e}")
            print("\nMake sure Chrome is running with:")
            print('  chrome.exe --remote-debugging-port=9222')
            return False
    
    def close(self):
        """Disconnect (doesn't close Chrome)."""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        print("[GeminiGen] Disconnected")
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, *args):
        self.close()
    
    def navigate_to_video_gen(self):
        """Navigate to video generation page."""
        self.page.goto("https://geminigen.ai/app/video-gen/", wait_until='networkidle', timeout=30000)
        time.sleep(2)
        return 'video-gen' in self.page.url
    
    def is_logged_in(self) -> bool:
        """Check if logged in by looking for UI elements."""
        try:
            page_text = self.page.evaluate("() => document.body.innerText")
            # Look for logged-in indicators
            if 'Credits' in page_text or 'Generate' in page_text:
                return True
            if 'Login' in page_text[:500] or 'Sign in' in page_text[:500]:
                return False
            return True  # Assume logged in if we can see the page
        except:
            return False
    
    def generate_video(
        self,
        prompt: str,
        model: str = "veo-3-fast",
        aspect_ratio: str = "16:9",
        duration: int = 8,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """
        Generate video using GeminiGen.ai interface.
        
        Args:
            prompt: Video prompt
            model: Model to use (veo-3-fast, veo-3, sora-2)
            aspect_ratio: 16:9 or 9:16
            duration: Video duration in seconds
            output_path: Where to save the video
            progress_callback: Callback for progress updates
        """
        def log(msg, progress=0):
            print(f"[GeminiGen] {msg}")
            if progress_callback:
                progress_callback(progress, msg)
        
        try:
            # Navigate to video gen page
            log("Navigating to video generator...", 0.05)
            if not self.navigate_to_video_gen():
                log("Failed to navigate", 0)
                return None
            
            if not self.is_logged_in():
                log("Not logged in!", 0)
                return None
            
            log("Logged in. Finding prompt input...", 0.1)
            
            # Wait for prompt textarea
            time.sleep(2)
            
            # Find and fill prompt
            prompt_selectors = [
                'textarea[placeholder*="prompt"]',
                'textarea[placeholder*="Prompt"]',
                'textarea[placeholder*="describe"]',
                'textarea[placeholder*="Describe"]',
                'textarea',
            ]
            
            prompt_filled = False
            for selector in prompt_selectors:
                try:
                    textarea = self.page.query_selector(selector)
                    if textarea:
                        textarea.click()
                        textarea.fill(prompt)
                        log(f"Filled prompt using: {selector}", 0.2)
                        prompt_filled = True
                        break
                except:
                    continue
            
            if not prompt_filled:
                log("Could not find prompt input!", 0)
                return None
            
            # Find and click generate button
            log("Looking for Generate button...", 0.25)
            time.sleep(1)
            
            generate_selectors = [
                'button:has-text("Generate")',
                'button:has-text("Create")',
                'button:has-text("Start")',
                '[class*="generate"]',
            ]
            
            for selector in generate_selectors:
                try:
                    button = self.page.query_selector(selector)
                    if button and button.is_visible():
                        button.click()
                        log("Clicked Generate button!", 0.3)
                        break
                except:
                    continue
            
            # Wait for video generation (this can take 2-5 minutes)
            log("Waiting for video generation...", 0.35)
            
            # Poll for completion (max 10 minutes)
            start_time = time.time()
            max_wait = 600  # 10 minutes
            
            while time.time() - start_time < max_wait:
                time.sleep(10)
                elapsed = time.time() - start_time
                progress = min(0.35 + (elapsed / max_wait) * 0.5, 0.85)
                log(f"Generating... ({int(elapsed)}s elapsed)", progress)
                
                # Check for video element or download link
                video_ready = self.page.evaluate("""
                    () => {
                        const video = document.querySelector('video[src*="blob:"], video[src*="http"]');
                        const download = document.querySelector('a[download], button:has-text("Download")');
                        return video !== null || download !== null;
                    }
                """)
                
                if video_ready:
                    log("Video ready!", 0.9)
                    break
                
                # Check for error
                page_text = self.page.evaluate("() => document.body.innerText")
                if 'error' in page_text.lower() and 'failed' in page_text.lower():
                    log("Generation failed!", 0)
                    return None
            
            # Try to download the video
            if output_path:
                log("Downloading video...", 0.95)
                # Look for download button
                download_clicked = self.page.evaluate("""
                    () => {
                        const btn = document.querySelector('a[download], button:has-text("Download")');
                        if (btn) { btn.click(); return true; }
                        return false;
                    }
                """)
                
                if download_clicked:
                    time.sleep(5)  # Wait for download
                    log("Download initiated", 0.98)
            
            log("Done!", 1.0)
            return output_path
            
        except Exception as e:
            log(f"Error: {e}", 0)
            return None


def test_cdp_connection():
    """Test CDP connection to Chrome."""
    print("=" * 60)
    print("Testing GeminiGen CDP Connection")
    print("=" * 60)
    print("\nMake sure Chrome is running with:")
    print('  chrome.exe --remote-debugging-port=9222')
    print("And you are logged into geminigen.ai")
    print()
    
    with GeminiGenCDP() as gen:
        if not gen.browser:
            return False
        
        gen.navigate_to_video_gen()
        
        if gen.is_logged_in():
            print("\n✅ SUCCESS! Connected and logged in.")
            print(f"   Current page: {gen.page.url}")
            return True
        else:
            print("\n❌ Not logged in")
            return False


if __name__ == "__main__":
    test_cdp_connection()
