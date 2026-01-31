"""
GeminiGen.ai Browser Automation Module
======================================
Uses Playwright with stealth mode for Cloudflare bypass.
Cookie-based authentication - login manually once, then reuse cookies.

Features:
- Veo 3.1 (Google's video model) - FREE
- Sora 2 (OpenAI's video model) - FREE
- Text-to-Video, Image-to-Video

Usage:
1. First time: Run with headless=False to login manually
2. Cookies will be saved automatically
3. Next runs: Cookies are loaded, no login needed
"""

import os
import json
import time
import tempfile
from typing import Optional, Callable
from playwright.sync_api import sync_playwright, Browser, Page

# URLs
GEMINIGEN_BASE_URL = "https://geminigen.ai"
GEMINIGEN_LOGIN_URL = f"{GEMINIGEN_BASE_URL}/auth/login"
GEMINIGEN_VIDEO_URL = f"{GEMINIGEN_BASE_URL}/video"  # Adjust based on actual URL

# Cookie storage
COOKIE_FILE = os.path.join(tempfile.gettempdir(), "geminigen_cookies.json")
BROWSER_PROFILE_DIR = os.path.join(tempfile.gettempdir(), "geminigen_browser_profile")


class GeminiGenBrowser:
    """
    GeminiGen.ai browser automation using Playwright.
    Cookie-based authentication for persistent sessions.
    """
    
    def __init__(self, headless: bool = True, timeout: int = 600000):
        """
        Initialize GeminiGen browser automation.
        
        Args:
            headless: Run browser without GUI (set False for first login)
            timeout: Default timeout in milliseconds
        """
        self.headless = headless
        self.timeout = timeout
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.is_logged_in = False
    
    def start(self):
        """Start the browser with persistent profile for Cloudflare bypass."""
        self.playwright = sync_playwright().start()
        
        # Ensure profile directory exists
        os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
        
        # Stealth browser args - more comprehensive for Cloudflare bypass
        browser_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-site-isolation-trials',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--no-first-run',
            '--no-zygote',
            '--disable-infobars',
            '--window-size=1920,1080',
            '--start-maximized',
            # Critical: Remove automation indicators
            '--disable-automation',
            '--disable-blink-features=AutomationControlled',
            # Additional stealth flags
            '--disable-extensions',
            '--disable-default-apps',
            '--disable-component-extensions-with-background-pages',
            '--disable-background-networking',
            '--metrics-recording-only',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--excludeSwitches=enable-automation',
            '--useAutomationExtension=false',
        ]
        
        # Use persistent context (like real browser with user profile)
        # This preserves all browser data including localStorage, IndexedDB, etc.
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=BROWSER_PROFILE_DIR,
            headless=self.headless,
            args=browser_args,
            # CRITICAL: Ignore default args that reveal automation
            ignore_default_args=['--enable-automation'],
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='Asia/Jakarta',
            permissions=['geolocation'],
            java_script_enabled=True,
            ignore_https_errors=True,
            bypass_csp=True,
            # Channel uses real Chrome instead of bundled Chromium
            channel='chrome' if not self.headless else None,
        )
        
        # Add stealth scripts to evade detection
        self.context.add_init_script("""
            // Remove webdriver property
            delete Object.getPrototypeOf(navigator).webdriver;
            
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
            
            // Mock plugins array
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                    ];
                    plugins.length = 3;
                    return plugins;
                },
                configurable: true
            });
            
            // Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'id'],
                configurable: true
            });
            
            // Mock chrome runtime
            window.chrome = window.chrome || {};
            window.chrome.runtime = window.chrome.runtime || {};
            
            // Mock permissions
            if (navigator.permissions) {
                const originalQuery = navigator.permissions.query.bind(navigator.permissions);
                navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            }
            
            // Mock WebGL vendor/renderer
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.call(this, parameter);
            };
            
            // Remove automation indicators
            if (window.outerWidth === 0) window.outerWidth = window.innerWidth;
            if (window.outerHeight === 0) window.outerHeight = window.innerHeight;
        """)
        
        # Get existing page or create new one
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()
        
        self.page.set_default_timeout(self.timeout)
        self.browser = None  # Persistent context doesn't use separate browser
        
        # Load cookies into context
        self._load_cookies()
        
        print("[GeminiGen] Browser started with persistent profile")
    
    def close(self):
        """Close the browser and cleanup."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        print("[GeminiGen] Browser closed")
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def _save_cookies(self):
        """Save cookies to file for reuse."""
        try:
            cookies = self.context.cookies()
            with open(COOKIE_FILE, 'w') as f:
                json.dump(cookies, f)
            print(f"[GeminiGen] Cookies saved to {COOKIE_FILE}")
        except Exception as e:
            print(f"[GeminiGen] Failed to save cookies: {e}")
    
    def _parse_netscape_cookies(self, filepath: str) -> list:
        """Parse Netscape format cookies file to Playwright format."""
        cookies = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        domain = parts[0]
                        # Remove leading dot for Playwright
                        if domain.startswith('.'):
                            domain = domain[1:]
                        
                        # Only include geminigen.ai cookies
                        if 'geminigen' not in domain.lower():
                            continue
                        
                        cookie = {
                            'name': parts[5],
                            'value': parts[6],
                            'domain': domain,
                            'path': parts[2],
                            'secure': parts[3].lower() == 'true',
                            'httpOnly': False,  # Netscape format doesn't have this
                        }
                        
                        # Handle expiry
                        try:
                            expiry = int(parts[4])
                            if expiry > 0:
                                cookie['expires'] = expiry
                        except:
                            pass
                        
                        cookies.append(cookie)
            
            print(f"[GeminiGen] Parsed {len(cookies)} cookies from Netscape file")
        except Exception as e:
            print(f"[GeminiGen] Error parsing Netscape cookies: {e}")
        
        return cookies
    
    def _load_cookies(self):
        """Load cookies from file if exists. Supports JSON and Netscape format."""
        # First check for Netscape format (geminigen_cookies.txt)
        netscape_file = os.path.join(os.path.dirname(COOKIE_FILE), "geminigen_cookies.txt")
        project_netscape = os.path.join(os.path.dirname(__file__), "geminigen_cookies.txt")
        
        # Try project folder first, then temp
        for cookie_path in [project_netscape, netscape_file]:
            if os.path.exists(cookie_path):
                cookies = self._parse_netscape_cookies(cookie_path)
                if cookies:
                    try:
                        self.context.add_cookies(cookies)
                        print(f"[GeminiGen] Loaded {len(cookies)} Netscape cookies from {cookie_path}")
                        return True
                    except Exception as e:
                        print(f"[GeminiGen] Failed to add Netscape cookies: {e}")
        
        # Fallback to JSON format
        try:
            if os.path.exists(COOKIE_FILE):
                with open(COOKIE_FILE, 'r') as f:
                    cookies = json.load(f)
                self.context.add_cookies(cookies)
                print(f"[GeminiGen] Loaded {len(cookies)} JSON cookies from file")
                return True
        except Exception as e:
            print(f"[GeminiGen] Failed to load cookies: {e}")
        return False
    
    def check_login_status(self) -> bool:
        """Check if currently logged in."""
        try:
            # Navigate to main page
            self.page.goto(GEMINIGEN_BASE_URL, wait_until='networkidle', timeout=30000)
            time.sleep(3)  # Wait for any redirects
            
            # Check if redirected to login or if logged in
            current_url = self.page.url
            if '/auth/login' in current_url or '/login' in current_url:
                self.is_logged_in = False
                print("[GeminiGen] Not logged in - at login page")
                return False
            
            # Check for user elements (avatar, profile, etc)
            logged_in_indicators = self.page.evaluate("""
                () => {
                    const body = document.body.innerText;
                    const hasAvatar = document.querySelector('[class*="avatar"]') !== null;
                    const hasProfile = document.querySelector('[class*="profile"]') !== null;
                    const hasLogout = body.includes('Logout') || body.includes('Sign out');
                    const hasDashboard = body.includes('Dashboard') || body.includes('Generate');
                    return { hasAvatar, hasProfile, hasLogout, hasDashboard };
                }
            """)
            
            if logged_in_indicators.get('hasLogout') or logged_in_indicators.get('hasDashboard'):
                self.is_logged_in = True
                print("[GeminiGen] ✅ Logged in!")
                return True
            
            self.is_logged_in = False
            return False
            
        except Exception as e:
            print(f"[GeminiGen] Error checking login: {e}")
            return False
    
    def wait_for_manual_login(self, timeout: int = 300):
        """
        Navigate to login page and wait for user to login manually.
        Used for first-time setup.
        
        Args:
            timeout: Max seconds to wait for login
        """
        print("[GeminiGen] Opening login page for manual authentication...")
        print("[GeminiGen] Please login manually in the browser window.")
        print(f"[GeminiGen] Waiting up to {timeout} seconds...")
        
        self.page.goto(GEMINIGEN_LOGIN_URL, wait_until='networkidle')
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                current_url = self.page.url
                
                # Check if navigated away from login page
                if '/auth/login' not in current_url and '/login' not in current_url:
                    # Verify actually logged in
                    time.sleep(2)
                    if self.check_login_status():
                        self._save_cookies()
                        print("[GeminiGen] ✅ Login successful! Cookies saved.")
                        return True
                
                time.sleep(2)
            except:
                time.sleep(2)
        
        print("[GeminiGen] ❌ Login timeout")
        return False
    
    def navigate_to_video_generator(self) -> bool:
        """Navigate to video generation page."""
        try:
            # Try common video generation URLs
            video_urls = [
                f"{GEMINIGEN_BASE_URL}/video",
                f"{GEMINIGEN_BASE_URL}/generate/video",
                f"{GEMINIGEN_BASE_URL}/text-to-video",
                f"{GEMINIGEN_BASE_URL}/image-to-video",
            ]
            
            for url in video_urls:
                self.page.goto(url, wait_until='networkidle', timeout=30000)
                time.sleep(2)
                
                # Check if page has video generation form
                has_generator = self.page.evaluate("""
                    () => {
                        const body = document.body.innerText.toLowerCase();
                        return body.includes('generate') || body.includes('create video') || 
                               body.includes('text to video') || body.includes('prompt');
                    }
                """)
                
                if has_generator:
                    print(f"[GeminiGen] Found video generator at: {url}")
                    return True
            
            # Try clicking menu items to find video generator
            self.page.goto(GEMINIGEN_BASE_URL, wait_until='networkidle')
            time.sleep(2)
            
            # Look for video/generate buttons
            video_link = self.page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a, button'));
                    for (const link of links) {
                        const text = link.innerText.toLowerCase();
                        if (text.includes('video') || text.includes('generate') || text.includes('veo') || text.includes('sora')) {
                            return link.href || 'click';
                        }
                    }
                    return null;
                }
            """)
            
            if video_link:
                if video_link == 'click':
                    # Click the button
                    self.page.click('a:has-text("Video"), button:has-text("Video"), a:has-text("Generate"), button:has-text("Generate")')
                else:
                    self.page.goto(video_link, wait_until='networkidle')
                time.sleep(2)
                print("[GeminiGen] Navigated to video generator")
                return True
            
            print("[GeminiGen] Could not find video generator page")
            return False
            
        except Exception as e:
            print(f"[GeminiGen] Error navigating to video: {e}")
            return False
    
    def generate_video(
        self,
        prompt: str,
        model: str = "veo",  # "veo" or "sora"
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """
        Generate video from text prompt.
        
        Args:
            prompt: Text description of desired video
            model: "veo" for Veo 3.1 or "sora" for Sora 2
            output_path: Where to save the result
            progress_callback: Function to call with (progress, message)
            
        Returns:
            Path to saved video or None if failed
        """
        def log(msg, progress=0):
            print(f"[GeminiGen] {msg}")
            if progress_callback:
                progress_callback(progress, msg)
        
        try:
            if not self.is_logged_in:
                if not self.check_login_status():
                    log("Not logged in. Please run with headless=False to login first.", 0)
                    return None
            
            log("Navigating to video generator...", 0.1)
            if not self.navigate_to_video_generator():
                log("Could not find video generator", 0)
                return None
            
            # TODO: Implement actual generation flow
            # This requires understanding the specific UI of GeminiGen.ai
            # which may vary based on their current implementation
            
            log("Video generation interface found", 0.2)
            log("⚠️ Full automation not yet implemented - need to map UI elements", 0.2)
            
            return None
            
        except Exception as e:
            log(f"Error: {e}", 0)
            return None


# ============================================================================
# HIGH-LEVEL API
# ============================================================================

def setup_geminigen_login():
    """
    Interactive setup - opens browser for manual login.
    Run this once to save cookies.
    """
    print("=" * 60)
    print("GeminiGen.ai Login Setup")
    print("=" * 60)
    print("A browser window will open. Please:")
    print("1. Complete the Cloudflare challenge if shown")
    print("2. Login with your account (Google, email, etc)")
    print("3. Wait for redirect to dashboard")
    print("=" * 60)
    
    with GeminiGenBrowser(headless=False) as browser:
        if browser.wait_for_manual_login(timeout=300):
            print("\n✅ Setup complete! Cookies saved.")
            print("You can now run automation in headless mode.")
            return True
        else:
            print("\n❌ Setup failed. Please try again.")
            return False


def test_geminigen():
    """Test if cookies work and we're logged in."""
    print("Testing GeminiGen.ai connection...")
    
    with GeminiGenBrowser(headless=True) as browser:
        if browser.check_login_status():
            print("✅ Logged in! Ready to generate videos.")
            browser.navigate_to_video_generator()
            return True
        else:
            print("❌ Not logged in. Run setup_geminigen_login() first.")
            return False


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "setup":
            setup_geminigen_login()
        elif cmd == "test":
            test_geminigen()
        else:
            print(f"Unknown command: {cmd}")
            print("Usage:")
            print("  python geminigen_browser.py setup  - Login and save cookies")
            print("  python geminigen_browser.py test   - Test if logged in")
    else:
        print("GeminiGen.ai Browser Automation")
        print("")
        print("Usage:")
        print("  python geminigen_browser.py setup  - Login and save cookies")
        print("  python geminigen_browser.py test   - Test if logged in")
