"""
Google Flow Browser Automation v3
=================================
Fixed download logic - intercept network requests for video URL.

UI Elements (Indonesian):
- Project page: https://labs.google/fx/id/tools/flow
- Tab: "Video" / "Gambar"
- Input: "Buat video dengan teks..." placeholder
- Model: "Veo 3.1 - Fast" dropdown
- Submit: Arrow button (→)
- New project: "+ Project baru" button

Usage:
    python flow_browser.py --setup     # Setup dan login
    python flow_browser.py --generate "prompt" --output video.mp4
    python flow_browser.py --credits   # Cek credits (via API)
"""

import asyncio
import json
import os
import sys
import time
import requests
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("❌ Install: pip install playwright && playwright install chromium")

# ============================================================================
# CONFIGURATION
# ============================================================================

FLOW_URL = "https://labs.google/fx/id/tools/flow"
FLOW_API_BASE = "https://aisandbox-pa.googleapis.com"
CHROME_USER_DATA = os.path.expanduser("~/.flow_chrome_profile")
DOWNLOADS_DIR = "./flow_downloads"
TOKEN_FILE = "flow_bearer_token.txt"

os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# ============================================================================
# UI SELECTORS (Indonesian UI)
# ============================================================================

SELECTORS = {
    "new_project_btn": [
        'text=Project baru',
        'text=+ Project',
        'button:has-text("Project baru")',
    ],
    "video_tab": [
        'text=Video',
        'button:has-text("Video")',
        '[role="tab"]:has-text("Video")',
    ],
    "video_input": [
        'textarea[placeholder*="Buat video dengan teks"]',
        'textarea[placeholder*="video dengan teks"]',
        'textarea',
    ],
    "submit_btn": [
        'button[aria-label*="submit"]',
        'button[aria-label*="Send"]',
        'button[aria-label*="Kirim"]',
        'button:has(svg)',
        'button >> nth=-1',
    ],
    "download_btn": [
        # More specific selectors for download
        'button:has-text("Download")',
        'button:has-text("Unduh")',
        '[aria-label*="download"]',
        '[aria-label*="Download"]',
        '[data-testid="download"]',
        'a[download]',
        # Menu items
        'text=Download',
        'text=Unduh',
        '[role="menuitem"]:has-text("Download")',
        '[role="menuitem"]:has-text("Unduh")',
    ],
    "video_card": [
        # Video card/container that might have menu
        '[data-testid="video-card"]',
        '.video-card',
        'div:has(video)',
    ],
    "aspect_ratio_trigger": [
        # Settings icon button (≡) that opens the aspect ratio popup
        'button:has-text("Veo")',
        '[aria-label*="settings"]',
        '[aria-label*="setelan"]',
        'button:has(svg[class*="tune"])',
        'button:has(svg[class*="settings"])',
        # The ≡ icon button next to prompt
        'button >> svg >> path[d*="M3"]',
        '.settings-button',
    ],
    "rasio_aspek_dropdown": [
        # "Rasio Aspek" dropdown label/button
        'text=Rasio Aspek',
        'text=Lanskap (16:9)',
        'button:has-text("Lanskap")',
        'button:has-text("16:9")',
        '[aria-label*="Rasio"]',
        'div:has-text("Rasio Aspek")',
    ],
    "aspect_9_16": [
        # Portrait mode option (9:16)
        'text=Potret (9:16)',
        'text=Potret',
        'text=9:16',
        '[role="option"]:has-text("9:16")',
        '[role="option"]:has-text("Potret")',
        '[role="menuitem"]:has-text("9:16")',
        '[role="menuitem"]:has-text("Potret")',
        'button:has-text("9:16")',
        'li:has-text("Potret")',
        'li:has-text("9:16")',
    ],
    "output_count_dropdown": [
        # "Output per perintah" dropdown
        'text=Output per perintah',
        'div:has-text("Output per perintah")',
        'button:has-text("2")',  # Default is 2
        'button:has-text("3")',
        'button:has-text("4")',
    ],
    "output_count_1": [
        # Select 1 output
        'text=1 >> visible=true',
        '[role="option"]:has-text("1")',
        '[role="menuitem"]:has-text("1")',
        'li:has-text("1"):first-child',
        'div:text-is("1")',
    ],
    "menu_btn": [
        # Three dots menu button
        'button[aria-label*="menu"]',
        'button[aria-label*="More"]',
        'button[aria-label*="option"]',
        'button:has-text("⋮")',
        'button:has-text("...")',
    ],
    # ===== FRAMES TO VIDEO (Image-to-Video) =====
    "frames_to_video_tab": [
        # Tab for Frames to Video mode
        'text=Frames to Video',
        'text=Frame ke Video',
        'button:has-text("Frames")',
        '[role="tab"]:has-text("Frames")',
        'div:has-text("Frames to Video")',
    ],
    "add_frame_btn": [
        # Add button to add start/end frame
        'text=Add',
        'text=Tambah',
        'button:has-text("Add")',
        'button:has-text("Tambah")',
        '[aria-label*="Add"]',
        'button:has-text("+")',
    ],
    "upload_image_option": [
        # Option to upload an image
        'text=Upload an image',
        'text=Unggah gambar',
        'text=Upload image',
        'button:has-text("Upload")',
        '[role="menuitem"]:has-text("Upload")',
        'div:has-text("Upload an image")',
    ],
    "file_input": [
        # File input for image upload
        'input[type="file"]',
        'input[accept*="image"]',
        'input[accept*=".jpg"]',
        'input[accept*=".png"]',
    ],
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def find_and_click(page, selector_list, timeout=5000):
    """Try multiple selectors and click the first found"""
    for selector in selector_list:
        try:
            element = await page.wait_for_selector(selector, timeout=timeout)
            if element:
                await element.click()
                print(f"   ✅ Clicked: {selector}")
                return True
        except:
            continue
    return False


async def find_and_fill(page, selector_list, text, timeout=5000):
    """Try multiple selectors and fill the first found"""
    for selector in selector_list:
        try:
            element = await page.wait_for_selector(selector, timeout=timeout)
            if element:
                await element.fill(text)
                print(f"   ✅ Filled: {selector}")
                return True
        except:
            continue
    return False


# ============================================================================
# NETWORK INTERCEPTOR FOR VIDEO URL
# ============================================================================

class VideoUrlInterceptor:
    """Intercept network requests to capture video URLs"""
    
    def __init__(self):
        self.video_urls = []
        self.video_patterns = [
            r'\.mp4',
            r'video',
            r'media',
            r'blob',
            r'storage\.googleapis',
            r'aisandbox.*video',
        ]
    
    def handle_response(self, response):
        """Handle response to capture video URLs"""
        url = response.url
        content_type = response.headers.get('content-type', '')
        
        # Check if it's a video response
        is_video = (
            'video' in content_type or
            any(re.search(p, url) for p in self.video_patterns)
        )
        
        if is_video and url not in self.video_urls:
            self.video_urls.append(url)
            print(f"   📹 Captured video URL: {url[:80]}...")
    
    def get_best_url(self):
        """Get the most likely video URL"""
        # Prefer mp4 URLs
        for url in self.video_urls:
            if '.mp4' in url:
                return url
        # Otherwise return the last one (most recent)
        return self.video_urls[-1] if self.video_urls else None


# ============================================================================
# BROWSER FUNCTIONS
# ============================================================================

async def get_browser(headless: bool = False):
    """Get browser with saved profile"""
    p = await async_playwright().start()
    
    browser = await p.chromium.launch_persistent_context(
        user_data_dir=CHROME_USER_DATA,
        headless=headless,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-first-run',
            '--no-default-browser-check',
        ],
        viewport={'width': 1400, 'height': 900},
        accept_downloads=True,
    )
    
    return p, browser


async def setup_and_login():
    """Setup: Login to Flow manually"""
    print("🔧 Setup: Opening Flow for manual login...")
    
    p, browser = await get_browser(headless=False)
    page = browser.pages[0] if browser.pages else await browser.new_page()
    
    try:
        await page.goto(FLOW_URL, wait_until="networkidle", timeout=60000)
        
        print("✅ Browser terbuka!")
        print()
        print("=" * 50)
        print("INSTRUKSI:")
        print("1. Login dengan akun Google AI Pro")
        print("2. Pastikan kamu lihat Flow dashboard")
        print("3. Tekan Enter di terminal setelah selesai")
        print("=" * 50)
        
        await asyncio.get_event_loop().run_in_executor(None, input, "\nTekan Enter setelah login selesai...")
        
        print(f"\n✅ Setup complete! Profile: {CHROME_USER_DATA}")
        
    finally:
        await browser.close()
        await p.stop()


async def generate_video(prompt: str, output_path: str = None, image_path: str = None):
    """Generate video via Flow UI automation with improved download
    
    Args:
        prompt: Text prompt for video generation (motion description if image provided)
        output_path: Path to save the video
        image_path: Optional image to use as start frame (Frames to Video mode)
    """
    
    use_frames_mode = image_path and os.path.exists(image_path)
    mode_str = "Frames to Video" if use_frames_mode else "Text to Video"
    
    print(f"🎬 Generate Video ({mode_str})")
    print(f"   Prompt: {prompt[:60]}...")
    if use_frames_mode:
        print(f"   Image: {os.path.basename(image_path)}")
    print()
    
    if not output_path:
        timestamp = int(time.time())
        output_path = os.path.join(DOWNLOADS_DIR, f"flow_{timestamp}.mp4")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else DOWNLOADS_DIR, exist_ok=True)
    
    p, browser = await get_browser(headless=False)
    page = browser.pages[0] if browser.pages else await browser.new_page()
    
    # Setup network interceptor
    interceptor = VideoUrlInterceptor()
    page.on("response", interceptor.handle_response)
    
    try:
        # 1. Navigate to Flow
        print("📍 Step 1: Opening Flow...")
        await page.goto(FLOW_URL, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        # 2. Check if need to create project
        print("📍 Step 2: Checking for project...")
        
        video_input_found = False
        for selector in SELECTORS["video_input"]:
            try:
                element = await page.wait_for_selector(selector, timeout=3000)
                if element:
                    video_input_found = True
                    break
            except:
                continue
        
        if not video_input_found:
            print("   No project open, looking for 'Project baru'...")
            created = await find_and_click(page, SELECTORS["new_project_btn"], timeout=5000)
            if created:
                await asyncio.sleep(3)
            else:
                print("   ⚠️ Could not find 'Project baru' - please create manually")
                await asyncio.get_event_loop().run_in_executor(None, input, "Press Enter when ready...")
        
        # 3. Select Video tab
        print("📍 Step 3: Selecting Video tab...")
        await find_and_click(page, SELECTORS["video_tab"], timeout=3000)
        await asyncio.sleep(1)
        
        # 3.1 If image provided, use Frames to Video mode
        if use_frames_mode:
            print("📍 Step 3.1: Switching to Frames to Video mode...")
            try:
                # Click "Frames to Video" tab
                frames_clicked = await find_and_click(page, SELECTORS["frames_to_video_tab"], timeout=5000)
                if frames_clicked:
                    print("   ✅ Switched to Frames to Video")
                    await asyncio.sleep(1)
                    
                    # Click "Add" button to add start frame
                    print("📍 Step 3.2: Adding start frame...")
                    add_clicked = await find_and_click(page, SELECTORS["add_frame_btn"], timeout=3000)
                    if add_clicked:
                        await asyncio.sleep(0.5)
                        
                        # Click "Upload an image" option
                        upload_clicked = await find_and_click(page, SELECTORS["upload_image_option"], timeout=3000)
                        if upload_clicked:
                            await asyncio.sleep(0.5)
                        
                        # Find file input and upload image
                        file_input = await page.query_selector('input[type="file"]')
                        if not file_input:
                            # Try to find hidden file input
                            file_inputs = await page.query_selector_all('input[type="file"]')
                            if file_inputs:
                                file_input = file_inputs[0]
                        
                        if file_input:
                            await file_input.set_input_files(image_path)
                            print(f"   ✅ Uploaded: {os.path.basename(image_path)}")
                            await asyncio.sleep(3)  # Wait for image to process
                        else:
                            print("   ⚠️ File input not found, trying drag-drop...")
                            # Fallback: evaluate script to trigger file upload
                            await page.evaluate('''
                                () => {
                                    const input = document.querySelector('input[type="file"]');
                                    if (input) input.click();
                                }
                            ''')
                            await asyncio.sleep(1)
                    else:
                        print("   ⚠️ Add button not found")
                else:
                    print("   ⚠️ Frames to Video tab not found, using Text to Video")
                    use_frames_mode = False
            except Exception as e:
                print(f"   ⚠️ Frames to Video error: {e}")
                use_frames_mode = False
        
        # 3.5 Select 9:16 portrait aspect ratio (for Shorts/TikTok)
        print("📍 Step 3.5: Setting 9:16 portrait aspect ratio...")
        try:
            # Step A: Click settings icon (≡) to open popup
            settings_clicked = await find_and_click(page, SELECTORS["aspect_ratio_trigger"], timeout=3000)
            if settings_clicked:
                print("   ✅ Clicked settings icon")
                await asyncio.sleep(0.5)
                
                # Step B: Click "Rasio Aspek" dropdown 
                rasio_clicked = await find_and_click(page, SELECTORS["rasio_aspek_dropdown"], timeout=3000)
                if rasio_clicked:
                    print("   ✅ Clicked Rasio Aspek dropdown")
                    await asyncio.sleep(0.5)
                    
                    # Step C: Select "Potret (9:16)" option
                    portrait_selected = await find_and_click(page, SELECTORS["aspect_9_16"], timeout=3000)
                    if portrait_selected:
                        print("   ✅ Selected Potret (9:16)")
                        await asyncio.sleep(0.5)
                        
                        # Step D: Set "Output per perintah" to 1 (save credits)
                        output_clicked = await find_and_click(page, SELECTORS["output_count_dropdown"], timeout=3000)
                        if output_clicked:
                            print("   ✅ Clicked Output per perintah dropdown")
                            await asyncio.sleep(0.3)
                            count_1_selected = await find_and_click(page, SELECTORS["output_count_1"], timeout=3000)
                            if count_1_selected:
                                print("   ✅ Set Output per perintah = 1")
                            await asyncio.sleep(0.3)
                        
                        # Close popup by clicking elsewhere
                        await page.keyboard.press("Escape")
                        await asyncio.sleep(0.3)
                    else:
                        print("   ⚠️ Could not find Potret option")
                else:
                    print("   ⚠️ Could not find Rasio Aspek dropdown")
            else:
                print("   ⚠️ Settings icon not found, using default aspect ratio")
        except Exception as e:
            print(f"   ⚠️ Aspect ratio error: {e}")
        
        # 4. Enter prompt
        print("📍 Step 4: Entering prompt...")
        filled = await find_and_fill(page, SELECTORS["video_input"], prompt, timeout=5000)
        
        if not filled:
            print(f"   ⚠️ Please enter prompt manually: \"{prompt[:50]}...\"")
            await asyncio.get_event_loop().run_in_executor(None, input, "Press Enter after entering prompt...")
        
        await asyncio.sleep(1)
        
        # 5. Click submit/generate
        print("📍 Step 5: Clicking generate...")
        submitted = await find_and_click(page, SELECTORS["submit_btn"], timeout=5000)
        
        if not submitted:
            print("   Trying Enter key...")
            await page.keyboard.press('Enter')
        
        # 6. Wait for video generation
        print("\n⏳ Step 6: Waiting for video generation...")
        print("   This may take 30-120 seconds...")
        print("   (Network interceptor active - capturing video URL)")
        
        max_wait = 180
        start_time = time.time()
        video_ready = False
        
        while (time.time() - start_time) < max_wait:
            elapsed = int(time.time() - start_time)
            
            # Check for video element
            try:
                video = await page.query_selector('video')
                if video:
                    video_ready = True
                    print(f"\n✅ Video element detected! ({elapsed}s)")
                    await asyncio.sleep(3)  # Wait a bit for video to load
                    break
            except:
                pass
            
            # Check for download button
            for sel in SELECTORS["download_btn"]:
                try:
                    dl = await page.query_selector(sel)
                    if dl:
                        video_ready = True
                        print(f"\n✅ Download button found! ({elapsed}s)")
                        break
                except:
                    pass
            
            if video_ready:
                break
            
            print(f"\r   Waiting... ({elapsed}s / {max_wait}s) | URLs captured: {len(interceptor.video_urls)}", end="", flush=True)
            await asyncio.sleep(3)
        
        # 7. Download video
        if video_ready:
            print("\n\n📥 Step 7: Downloading video...")
            download_success = False
            
            # Method 1: Get video src directly from video element
            print("   Trying Method 1: Get video src attribute...")
            try:
                video = await page.query_selector('video')
                if video:
                    video_src = await video.get_attribute('src')
                    if video_src and video_src.startswith('http'):
                        print(f"   Found video src: {video_src[:80]}...")
                        
                        # Download with requests
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
                            "Referer": "https://labs.google/",
                        }
                        response = requests.get(video_src, headers=headers, timeout=120, stream=True)
                        
                        if response.status_code == 200:
                            with open(output_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            
                            file_size = os.path.getsize(output_path)
                            print(f"   ✅ Video saved: {output_path} ({file_size / 1024 / 1024:.2f} MB)")
                            download_success = True
                        else:
                            print(f"   ❌ Download failed: HTTP {response.status_code}")
            except Exception as e:
                print(f"   Method 1 error: {e}")
            
            # Method 2: Get video source from <source> element
            if not download_success:
                print("   Trying Method 2: Get source element...")
                try:
                    source = await page.query_selector('video source')
                    if source:
                        src = await source.get_attribute('src')
                        if src and src.startswith('http'):
                            print(f"   Found source: {src[:80]}...")
                            response = requests.get(src, timeout=120, stream=True)
                            if response.status_code == 200:
                                with open(output_path, 'wb') as f:
                                    for chunk in response.iter_content(chunk_size=8192):
                                        f.write(chunk)
                                file_size = os.path.getsize(output_path)
                                print(f"   ✅ Video saved: {output_path} ({file_size / 1024 / 1024:.2f} MB)")
                                download_success = True
                except Exception as e:
                    print(f"   Method 2 error: {e}")
            
            # Method 3: Use intercepted URL
            if not download_success and interceptor.video_urls:
                print("   Trying Method 3: Use intercepted URL...")
                try:
                    video_url = interceptor.get_best_url()
                    if video_url:
                        print(f"   Using: {video_url[:80]}...")
                        response = requests.get(video_url, timeout=120, stream=True)
                        if response.status_code == 200:
                            with open(output_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            file_size = os.path.getsize(output_path)
                            print(f"   ✅ Video saved: {output_path} ({file_size / 1024 / 1024:.2f} MB)")
                            download_success = True
                except Exception as e:
                    print(f"   Method 3 error: {e}")
            
            # Method 4: Right-click video and get blob URL via JavaScript
            if not download_success:
                print("   Trying Method 4: Get blob URL via JavaScript...")
                try:
                    video_url = await page.evaluate('''() => {
                        const video = document.querySelector('video');
                        if (video) {
                            // Try src attribute
                            if (video.src) return video.src;
                            // Try source element
                            const source = video.querySelector('source');
                            if (source && source.src) return source.src;
                            // Try currentSrc
                            if (video.currentSrc) return video.currentSrc;
                        }
                        return null;
                    }''')
                    
                    if video_url and video_url.startswith('http'):
                        print(f"   JS found URL: {video_url[:80]}...")
                        response = requests.get(video_url, timeout=120, stream=True)
                        if response.status_code == 200:
                            with open(output_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            file_size = os.path.getsize(output_path)
                            print(f"   ✅ Video saved: {output_path} ({file_size / 1024 / 1024:.2f} MB)")
                            download_success = True
                    elif video_url and video_url.startswith('blob:'):
                        print(f"   Found blob URL: {video_url}")
                        print("   Blob URLs cannot be downloaded directly, trying download button...")
                except Exception as e:
                    print(f"   Method 4 error: {e}")
            
            # Method 5: Click on video to open menu, then download
            if not download_success:
                print("   Trying Method 5: Click video card for menu...")
                try:
                    # Click on video area
                    video = await page.query_selector('video')
                    if video:
                        await video.click()
                        await asyncio.sleep(1)
                    
                    # Look for menu/download button
                    for sel in SELECTORS["menu_btn"]:
                        try:
                            menu = await page.query_selector(sel)
                            if menu:
                                await menu.click()
                                await asyncio.sleep(1)
                                break
                        except:
                            continue
                    
                    # Now try download button
                    async with page.expect_download(timeout=30000) as download_info:
                        clicked = await find_and_click(page, SELECTORS["download_btn"], timeout=5000)
                        if not clicked:
                            # Try clicking any download-like element
                            await page.click('text=Download', timeout=5000)
                    
                    download = await download_info.value
                    await download.save_as(output_path)
                    file_size = os.path.getsize(output_path)
                    print(f"   ✅ Video saved: {output_path} ({file_size / 1024 / 1024:.2f} MB)")
                    download_success = True
                except Exception as e:
                    print(f"   Method 5 error: {e}")
            
            # Method 6: Hover on video for download overlay
            if not download_success:
                print("   Trying Method 6: Hover on video...")
                try:
                    video = await page.query_selector('video')
                    if video:
                        await video.hover()
                        await asyncio.sleep(2)
                        
                        # Take screenshot to see what buttons appear
                        screenshot_path = os.path.join(DOWNLOADS_DIR, "debug_hover.png")
                        await page.screenshot(path=screenshot_path)
                        print(f"   Screenshot saved: {screenshot_path}")
                        
                        # Try download buttons again
                        async with page.expect_download(timeout=15000) as download_info:
                            await find_and_click(page, SELECTORS["download_btn"], timeout=5000)
                        
                        download = await download_info.value
                        await download.save_as(output_path)
                        download_success = True
                except Exception as e:
                    print(f"   Method 6 error: {e}")
            
            if not download_success:
                # Save all captured URLs for debugging
                print("\n   ❌ All automatic download methods failed")
                print(f"\n   📋 Captured URLs ({len(interceptor.video_urls)}):")
                for i, url in enumerate(interceptor.video_urls[-5:], 1):
                    print(f"      {i}. {url[:100]}...")
                
                # Take debug screenshot
                screenshot_path = os.path.join(DOWNLOADS_DIR, "debug_download.png")
                await page.screenshot(path=screenshot_path)
                print(f"\n   📸 Debug screenshot: {screenshot_path}")
                
                print(f"\n   ⚠️ Please download video manually to: {output_path}")
                await asyncio.get_event_loop().run_in_executor(None, input, "Press Enter when done...")
                
                if os.path.exists(output_path):
                    download_success = True
            
            return download_success
        
        else:
            print("\n⚠️ Video not ready. Taking debug screenshot...")
            screenshot_path = os.path.join(DOWNLOADS_DIR, "debug_timeout.png")
            await page.screenshot(path=screenshot_path)
            print(f"   Screenshot: {screenshot_path}")
            return False
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        print("\n   Closing browser in 3 seconds...")
        await asyncio.sleep(3)
        try:
            await browser.close()
            await p.stop()
        except:
            pass


async def check_credits_api():
    """Check credits via API"""
    print("💰 Checking credits via API...")
    
    if not os.path.exists(TOKEN_FILE):
        print(f"   ❌ No token file: {TOKEN_FILE}")
        return None
    
    with open(TOKEN_FILE, 'r') as f:
        token = f.read().strip()
    
    try:
        response = requests.get(
            f"{FLOW_API_BASE}/v1/credits",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Credits: {data.get('credits', 'N/A')}")
            print(f"   Tier: {data.get('userPaygateTier', 'N/A')}")
            return data
        else:
            print(f"   ❌ API error: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


# ============================================================================
# MAIN
# ============================================================================

async def main():
    print("=" * 60)
    print("Google Flow Browser Automation v3")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    if not PLAYWRIGHT_AVAILABLE:
        print("❌ Playwright not installed!")
        return
    
    args = sys.argv[1:]
    
    if "--setup" in args:
        await setup_and_login()
        
    elif "--credits" in args:
        await check_credits_api()
        
    elif "--generate" in args:
        try:
            idx = args.index("--generate") + 1
            prompt = args[idx]
        except:
            prompt = input("Enter prompt: ").strip()
        
        output_path = None
        if "--output" in args:
            try:
                idx = args.index("--output") + 1
                output_path = args[idx]
            except:
                pass
        
        success = await generate_video(prompt, output_path)
        if success:
            print("\n🎉 Video generation and download complete!")
        else:
            print("\n⚠️ Video generation may have failed")
        
    else:
        print("Usage:")
        print("  --setup              Setup and login")
        print("  --credits            Check credits via API")
        print("  --generate 'prompt'  Generate video")
        print("  --output path.mp4    Output path")
        print()
        print("Example:")
        print('  python flow_browser.py --generate "A cat playing piano"')
        
        if not os.path.exists(CHROME_USER_DATA):
            print("\n⚠️ No profile found. Running setup...")
            await setup_and_login()
    
    print()
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
