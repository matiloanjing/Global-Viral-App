"""
AI Video Maker Browser Automation Module
=========================================
Uses Playwright to automate aivideomaker.ai for Image-to-Video generation.
NO LOGIN REQUIRED - Free tier available (480p, 5s, with watermark).

Author: Kilat Code Clipper
Date: Dec 2025
"""

import os
import time
import tempfile
from typing import Optional, Callable
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# Try to import stealth for Cloudflare bypass
try:
    from playwright_stealth import stealth_sync
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

# AI Video Maker URLs
AIVIDEOMAKER_URL = "https://aivideomaker.ai"
AIVIDEOMAKER_IMG2VID_URL = "https://aivideomaker.ai/image-to-video"
AIVIDEOMAKER_TXT2VID_URL = "https://aivideomaker.ai/text-to-video"

# Persistent browser profile directory for session persistence
BROWSER_PROFILE_DIR = os.path.join(tempfile.gettempdir(), "aivideomaker_browser_profile")


class AIVideoMakerBrowser:
    """
    AI Video Maker browser automation using Playwright.
    NO LOGIN REQUIRED!
    
    Limitations (Free Tier):
        - 480p resolution
        - 5 second videos
        - Watermark included
        - Queue waiting time
    
    Usage:
        with AIVideoMakerBrowser(headless=False) as avm:
            video = avm.image_to_video("image.png", "Slow zoom in")
            print(f"Video saved: {video}")
    """
    
    def __init__(self, headless: bool = True, timeout: int = 600000, use_persistent: bool = True):
        """
        Initialize AI Video Maker browser automation.
        
        Args:
            headless: Run browser without GUI
            timeout: Default timeout in milliseconds (10 minutes for generation)
            use_persistent: Use persistent browser profile (helps with Cloudflare)
        """
        if not HAS_PLAYWRIGHT:
            raise ImportError("Playwright not installed. Run: pip install playwright && python -m playwright install chromium")
        
        self.headless = headless
        self.timeout = timeout
        self.use_persistent = use_persistent
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
    
    def start(self):
        """Start the browser with stealth mode for Cloudflare bypass."""
        self.playwright = sync_playwright().start()
        
        # Common browser args for stealth
        browser_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process'
        ]
        
        if self.use_persistent:
            # Use persistent context to maintain cookies/session
            os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=BROWSER_PROFILE_DIR,
                headless=self.headless,
                viewport={'width': 1280, 'height': 900},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                args=browser_args,
                ignore_https_errors=True
            )
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        else:
            # Regular context
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=browser_args
            )
            self.context = self.browser.new_context(
                viewport={'width': 1280, 'height': 900},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            self.page = self.context.new_page()
        
        # Apply stealth mode if available
        if HAS_STEALTH:
            stealth_sync(self.page)
            print("[AIVideoMaker] Stealth mode applied for Cloudflare bypass")
        
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
    
    def image_to_video(
        self,
        image_path: str,
        prompt: str,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """
        Generate video from image using AI Video Maker.
        NO LOGIN REQUIRED!
        
        Args:
            image_path: Path to input image (JPG, PNG, WEBP - max 10MB, min 300px)
            prompt: Motion/animation prompt in English
            output_path: Where to save the result (auto-generated if None)
            progress_callback: Callback for progress updates (progress, message)
            
        Returns:
            Path to generated video, or None if failed
            
        Note:
            Free tier produces 480p, 5s video with watermark.
        """
        if not self.page:
            self.start()
        
        if not os.path.exists(image_path):
            print(f"[AIVideoMaker] Image not found: {image_path}")
            return None
        
        def log(msg, progress=0):
            print(f"[AIVideoMaker] {msg}")
            if progress_callback:
                progress_callback(progress, msg)
        
        try:
            log("Navigating to Image-to-Video page...", 0.05)
            self.page.goto(AIVIDEOMAKER_IMG2VID_URL, wait_until='networkidle')
            time.sleep(3)
            
            # Step 1: Upload image
            log(f"Uploading image: {os.path.basename(image_path)}", 0.1)
            
            # Find hidden file input
            file_input = self.page.query_selector('input[type="file"]')
            if not file_input:
                log("❌ Could not find file input", 0)
                return None
            
            file_input.set_input_files(image_path)
            log("✅ Image uploaded, waiting for resolution picker...", 0.15)
            
            # Step 2: Handle Resolution Picker Modal
            # After upload, a modal appears to select aspect ratio (Original, 1:1, 16:9, 9:16, 4:3, 3:4)
            time.sleep(3)
            
            log("Selecting aspect ratio (9:16 for vertical)...", 0.18)
            
            # Try to find and click 9:16 option (best for short video)
            ratio_clicked = self.page.evaluate("""
                () => {
                    // Look for 9:16 button in the modal
                    const elements = Array.from(document.querySelectorAll('div, button, span'));
                    for (const el of elements) {
                        if (el.innerText && el.innerText.trim() === '9:16') {
                            el.click();
                            return '9:16';
                        }
                    }
                    // Fallback to Original if 9:16 not found
                    for (const el of elements) {
                        if (el.innerText && el.innerText.trim() === 'Original') {
                            el.click();
                            return 'Original';
                        }
                    }
                    return null;
                }
            """)
            
            if ratio_clicked:
                log(f"✅ Selected ratio: {ratio_clicked}", 0.2)
            else:
                log("⚠️ Could not select ratio, continuing...", 0.2)
            
            time.sleep(1)
            
            # Click Confirm button on modal
            log("Clicking Confirm button...", 0.22)
            confirm_clicked = self.page.evaluate("""
                () => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const confirmBtn = btns.find(b => b.innerText && b.innerText.trim() === 'Confirm');
                    if (confirmBtn) {
                        confirmBtn.click();
                        return true;
                    }
                    return false;
                }
            """)
            
            if confirm_clicked:
                log("✅ Image confirmed!", 0.25)
            else:
                log("⚠️ Confirm button not found, may already be confirmed", 0.25)
            
            time.sleep(2)
            
            # Step 3: Enter prompt
            log("Entering motion prompt...", 0.28)
            prompt_input = self.page.query_selector('textarea')
            if prompt_input:
                prompt_input.fill(prompt)
                log("✅ Prompt entered", 0.3)
            else:
                log("⚠️ Could not find prompt input, continuing anyway", 0.3)
            
            # Step 3: Wait for Create button to be enabled and click
            log("Waiting for Create button to be enabled...", 0.35)
            
            # Wait for button to be enabled (max 30 seconds)
            for i in range(30):
                try:
                    # Use JavaScript to check if button is enabled AND click it
                    clicked = self.page.evaluate("""
                        () => {
                            const btns = Array.from(document.querySelectorAll('button'));
                            const btn = btns.find(b => b.innerText && b.innerText.includes('Create Video Now'));
                            if (btn && !btn.disabled && btn.offsetParent !== null) {
                                btn.click();
                                return true;
                            }
                            return false;
                        }
                    """)
                    if clicked:
                        log("✅ Generation started!", 0.4)
                        break
                except:
                    pass
                time.sleep(1)
            else:
                log("❌ Create button never became enabled (image may not have uploaded correctly)", 0)
                return None
            
            # IMPORTANT: Track existing video sources BEFORE generation
            # This helps identify the NEW video after generation completes
            existing_video_sources = self.page.evaluate("""
                () => {
                    const videos = document.querySelectorAll('video');
                    return Array.from(videos).map(v => v.src || '').filter(s => s);
                }
            """)
            log(f"Tracked {len(existing_video_sources or [])} existing video sources", 0.41)
            
            # Step 4: Dismiss upsell modal if it appears
            log("Checking for upsell modal...", 0.42)
            time.sleep(2)
            
            # Dismiss any popup modal (upgrade, subscribe, etc)
            self.page.evaluate("""
                () => {
                    // Try to find and click Close button on any modal
                    const closeBtns = Array.from(document.querySelectorAll('button'));
                    const closeBtn = closeBtns.find(b => b.innerText && b.innerText.trim() === 'Close');
                    if (closeBtn) closeBtn.click();
                    
                    // Also try clicking outside modal
                    const overlay = document.querySelector('[class*="overlay"], [class*="modal-backdrop"]');
                    if (overlay) overlay.click();
                }
            """)
            time.sleep(1)
            
            # Step 5: Wait for actual video generation (5-10 minutes for free tier)
            log("Waiting for video generation (5-10 minutes for free tier)...", 0.45)
            log("ℹ️ Free tier: 480p, 5s, with watermark", 0.45)
            
            max_wait = 900  # 15 minutes max for safety
            start_time = time.time()
            last_status = ""
            was_in_queue = False  # Track if we ever entered queue
            
            while time.time() - start_time < max_wait:
                elapsed = time.time() - start_time
                progress = 0.45 + (elapsed / max_wait) * 0.45
                
                # Check queue status via JavaScript
                status = self.page.evaluate("""
                    () => {
                        const bodyText = document.body.innerText;
                        
                        // Check if still in queue or creating
                        const inQueue = bodyText.includes("You're in line") || bodyText.includes("jobs ahead");
                        const creating = bodyText.includes("Creating Task") || bodyText.includes("Queuing Task");
                        const generating = bodyText.includes("Generating");
                        
                        if (inQueue) {
                            const match = bodyText.match(/(\\d+)\\s*jobs?\\s*ahead/i);
                            return { status: 'queue', jobs: match ? match[1] : '?', inProgress: true };
                        }
                        
                        if (creating || generating) {
                            return { status: 'creating', inProgress: true };
                        }
                        
                        // Only check for completion if NOT in queue/creating
                        // Look for result panel with actual generated video
                        // The result appears when queue is done and shows new Download option
                        
                        // Check if there's a video that changed (result video replaces or adds)
                        const allVideos = document.querySelectorAll('video');
                        for (const video of allVideos) {
                            // Result video typically has blob: or CDN URL
                            if (video.src && (video.src.includes('blob:') || video.src.includes('r2.dev') || video.src.includes('cdn'))) {
                                // Found a potential result video
                                return { status: 'complete', src: video.src, inProgress: false };
                            }
                        }
                        
                        // Check for "Reprompt" button which only appears after generation complete
                        const repromptBtn = Array.from(document.querySelectorAll('button, span'))
                            .find(el => el.innerText && el.innerText.includes('Reprompt'));
                        if (repromptBtn) {
                            return { status: 'complete', hasReprompt: true, inProgress: false };
                        }
                        
                        // Check for "Upscale Video" button which only appears after generation
                        const upscaleBtn = Array.from(document.querySelectorAll('button, span'))
                            .find(el => el.innerText && el.innerText.includes('Upscale'));
                        if (upscaleBtn) {
                            return { status: 'complete', hasUpscale: true, inProgress: false };
                        }
                        
                        return { status: 'waiting', inProgress: false };
                    }
                """)
                
                if status and isinstance(status, dict):
                    in_progress = status.get('inProgress', False)
                    
                    if status.get('status') == 'queue':
                        was_in_queue = True
                        jobs = status.get('jobs', '?')
                        new_status = f"In queue ({jobs} jobs ahead)... ({int(elapsed)}s)"
                        if new_status != last_status:
                            log(new_status, min(progress, 0.85))
                            last_status = new_status
                    elif status.get('status') == 'creating':
                        was_in_queue = True
                        log(f"Creating video... ({int(elapsed)}s)", min(progress, 0.85))
                    elif status.get('status') == 'complete' and was_in_queue:
                        # Only accept complete if we were previously in queue
                        log("✅ Generation complete!", 0.95)
                        break
                    elif status.get('status') == 'complete' and elapsed > 60:
                        # After 60 seconds, accept complete even if we didn't see queue
                        log("✅ Generation complete!", 0.95)
                        break
                    else:
                        log(f"Waiting for queue... ({int(elapsed)}s)", min(progress, 0.8))
                else:
                    log(f"Checking status... ({int(elapsed)}s)", min(progress, 0.8))
                
                time.sleep(10)  # Check every 10 seconds
            
            # Step 6: Download video from result panel
            log("Looking for Download button in result panel...", 0.97)
            
            if not output_path:
                output_path = os.path.join(tempfile.gettempdir(), f"aivideomaker_{int(time.time())}.mp4")
            
            download_success = False
            
            # Find the Download button that's in the result panel (near Reprompt/Upscale buttons)
            # This is the key: we need the Download button that appears AFTER generation,
            # not the sample video's controls
            
            try:
                # Use JavaScript to find the correct Download button
                # The result panel contains: video player + Reprompt + Upscale + Download
                download_clicked = self.page.evaluate("""
                    () => {
                        // Find buttons/spans with "Download" text
                        const allElements = Array.from(document.querySelectorAll('button, span, a, div'));
                        
                        // Look for Download button that's near Reprompt or Upscale buttons
                        // This indicates it's the result panel, not sample video
                        const repromptEl = allElements.find(el => el.innerText && el.innerText.includes('Reprompt'));
                        const upscaleEl = allElements.find(el => el.innerText && el.innerText.includes('Upscale'));
                        
                        // If we found result panel indicators, find Download in same area
                        if (repromptEl || upscaleEl) {
                            const nearbyEl = repromptEl || upscaleEl;
                            const parent = nearbyEl.parentElement?.parentElement || nearbyEl.parentElement;
                            if (parent) {
                                const downloadBtn = Array.from(parent.querySelectorAll('button, span, a'))
                                    .find(el => el.innerText && el.innerText.trim() === 'Download');
                                if (downloadBtn) {
                                    downloadBtn.click();
                                    return { clicked: true, method: 'near-reprompt' };
                                }
                            }
                        }
                        
                        // Fallback: find any Download button that's in a section with video
                        const sections = document.querySelectorAll('[class*="result"], [class*="preview"], [class*="output"]');
                        for (const section of sections) {
                            const downloadBtn = section.querySelector('button:has(span), span');
                            if (downloadBtn && downloadBtn.innerText && downloadBtn.innerText.includes('Download')) {
                                downloadBtn.click();
                                return { clicked: true, method: 'section-search' };
                            }
                        }
                        
                        return { clicked: false };
                    }
                """)
                
                if download_clicked and download_clicked.get('clicked'):
                    log(f"Download button clicked ({download_clicked.get('method')})", 0.98)
                    time.sleep(3)  # Wait for download to start
                    
                    # Try to capture the download
                    try:
                        with self.page.expect_download(timeout=30000) as download_info:
                            # The click already happened, just wait
                            pass
                        download = download_info.value
                        download.save_as(output_path)
                        download_success = True
                        log("✅ Downloaded via result panel button", 0.99)
                    except:
                        pass
            except Exception as e:
                log(f"Download button method failed: {e}", 0.98)
            
            # Fallback: Try to get the video src from result video (not sample)
            if not download_success:
                try:
                    # Get ALL video sources and find the NEW one that wasn't there before generation
                    video_sources = self.page.evaluate("""
                        () => {
                            const videos = document.querySelectorAll('video');
                            const sources = [];
                            videos.forEach((v, i) => {
                                if (v.src) {
                                    sources.push({
                                        index: i,
                                        src: v.src,
                                        isCDN: v.src.includes('r2.dev') || v.src.includes('cdn'),
                                        isBlob: v.src.startsWith('blob:'),
                                        parentClass: v.parentElement?.className || ''
                                    });
                                }
                            });
                            return sources;
                        }
                    """)
                    
                    # CRITICAL: Filter out videos that existed BEFORE generation
                    # Only consider NEW videos that appeared after generation
                    new_videos = []
                    for vs in (video_sources or []):
                        src = vs.get('src', '')
                        if src and src not in (existing_video_sources or []):
                            new_videos.append(vs)
                    
                    log(f"Found {len(new_videos)} NEW video(s) after generation", 0.97)
                    
                    # Prefer the new video with CDN URL
                    result_video = None
                    for vs in new_videos:
                        if vs.get('isCDN'):
                            result_video = vs
                            break
                    
                    # If no CDN in new videos, try any new video
                    if not result_video and new_videos:
                        result_video = new_videos[0]
                    
                    if result_video and result_video.get('src'):
                        video_src = result_video['src']
                        log(f"Downloading NEW video source #{result_video.get('index')}...", 0.98)
                        
                        if video_src.startswith('blob:'):
                            log("⚠️ Blob URL detected - cannot download directly", 0.98)
                        else:
                            import requests
                            response = requests.get(video_src, stream=True, timeout=120)
                            with open(output_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            download_success = True
                            log("✅ Downloaded from NEW video source", 0.99)
                    else:
                        log("⚠️ No NEW video source found - generation may have failed", 0.98)
                except Exception as e:
                    log(f"⚠️ Video source download failed: {e}", 0.98)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                log(f"✅ Video saved: {output_path} ({size_mb:.2f} MB)", 1.0)
                return output_path
            else:
                log("❌ Failed to save video", 0)
                return None
            
        except Exception as e:
            log(f"❌ Error: {str(e)}", 0)
            return None
    
    def text_to_video(
        self,
        prompt: str,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """
        Generate video from text prompt using AI Video Maker.
        NO LOGIN REQUIRED!
        
        Args:
            prompt: Text description of desired video (English)
            output_path: Where to save the result
            progress_callback: Callback for progress updates
            
        Returns:
            Path to generated video, or None if failed
        """
        if not self.page:
            self.start()
        
        def log(msg, progress=0):
            print(f"[AIVideoMaker] {msg}")
            if progress_callback:
                progress_callback(progress, msg)
        
        try:
            log("Navigating to Text-to-Video page...", 0.05)
            self.page.goto(AIVIDEOMAKER_TXT2VID_URL, wait_until='networkidle')
            time.sleep(3)
            
            # Enter prompt
            log("Entering prompt...", 0.15)
            prompt_input = self.page.query_selector('textarea')
            if prompt_input:
                prompt_input.fill(prompt)
            else:
                log("❌ Could not find prompt input", 0)
                return None
            
            # Click create button
            log("Clicking Create button...", 0.25)
            self.page.evaluate("""
                () => {
                    const btns = Array.from(document.querySelectorAll('button, div'));
                    const btn = btns.find(b => b.innerText && b.innerText.includes('Create Free AI Video'));
                    if (btn) btn.click();
                }
            """)
            
            log("✅ Generation started!", 0.3)
            
            # Wait and download (similar to image_to_video)
            # ... (implementation similar to above)
            
            log("Text-to-video: waiting for completion...", 0.5)
            time.sleep(60)  # Simplified - wait 1 minute
            
            return None  # Full implementation needed
            
        except Exception as e:
            log(f"❌ Error: {str(e)}", 0)
            return None


# ============================================================================
# HIGH-LEVEL API FOR INTEGRATION
# ============================================================================

def generate_3d_video(
    image_path: str,
    prompt: str,
    output_path: str = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Optional[str]:
    """
    High-level function to generate 3D/animated video from image.
    Uses AI Video Maker (FREE, NO LOGIN).
    
    Args:
        image_path: Path to source image
        prompt: Animation prompt (English)
        output_path: Where to save result
        progress_callback: Progress callback
        
    Returns:
        Path to generated video, or None if failed
        
    Note:
        Free tier: 480p, 5s, with watermark
    """
    if not HAS_PLAYWRIGHT:
        print("[AIVideoMaker] Playwright not installed!")
        return None
    
    with AIVideoMakerBrowser(headless=False) as avm:  # headless=False for debugging
        return avm.image_to_video(
            image_path=image_path,
            prompt=prompt,
            output_path=output_path,
            progress_callback=progress_callback
        )


# ============================================================================
# CLI / TESTING
# ============================================================================

def test_navigation():
    """Test basic navigation to the site."""
    print("=" * 60)
    print("AI VIDEO MAKER NAVIGATION TEST")
    print("=" * 60)
    
    with AIVideoMakerBrowser(headless=False) as avm:
        avm.page.goto(AIVIDEOMAKER_IMG2VID_URL)
        print("✅ Page loaded")
        
        # Check elements
        file_input = avm.page.query_selector('input[type="file"]')
        print(f"File input: {'✅ Found' if file_input else '❌ Not found'}")
        
        textarea = avm.page.query_selector('textarea')
        print(f"Prompt textarea: {'✅ Found' if textarea else '❌ Not found'}")
        
        create_btn = avm.page.query_selector('button:has-text("Create Video Now")')
        print(f"Create button: {'✅ Found' if create_btn else '❌ Not found'}")
        
        print("\nBrowser open for 10s for inspection...")
        avm.page.wait_for_timeout(10000)


def test_generation():
    """Test video generation with a test image."""
    print("=" * 60)
    print("AI VIDEO MAKER GENERATION TEST")
    print("=" * 60)
    
    # Find or create test image
    project_dir = os.path.dirname(os.path.abspath(__file__))
    test_image = None
    
    for name in ['test_image.png', 'test_image.jpg', 'kling_test_screenshot.png']:
        path = os.path.join(project_dir, name)
        if os.path.exists(path):
            test_image = path
            break
    
    if not test_image:
        print("❌ No test image found. Creating one...")
        try:
            from PIL import Image
            img = Image.new('RGB', (512, 512), color=(50, 100, 150))
            test_image = os.path.join(project_dir, "test_image_avm.png")
            img.save(test_image)
            print(f"✅ Created: {test_image}")
        except ImportError:
            print("❌ PIL not installed, cannot create test image")
            return
    
    print(f"Using test image: {test_image}")
    
    def on_progress(progress, message):
        bar_len = 30
        filled = int(bar_len * progress)
        bar = '█' * filled + '░' * (bar_len - filled)
        print(f"\r[{bar}] {progress*100:5.1f}% - {message}", end='', flush=True)
        if progress >= 1.0:
            print()
    
    result = generate_3d_video(
        image_path=test_image,
        prompt="Slow cinematic zoom in with dramatic lighting",
        progress_callback=on_progress
    )
    
    if result:
        print(f"\n✅ SUCCESS! Video saved: {result}")
    else:
        print(f"\n❌ FAILED")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "nav":
            test_navigation()
        elif cmd == "gen":
            test_generation()
        else:
            print(f"Unknown command: {cmd}")
    else:
        print("Usage:")
        print("  python aivideomaker_browser.py nav  - Test navigation")
        print("  python aivideomaker_browser.py gen  - Test video generation")
        print("")
        # Default: run navigation test
        test_navigation()
