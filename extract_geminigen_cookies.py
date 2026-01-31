"""
Connect to Chrome via Remote Debugging and save cookies
"""
import json
import os
from playwright.sync_api import sync_playwright

COOKIE_FILE = os.path.join(os.path.dirname(__file__), "geminigen_cookies.json")

def connect_and_save_cookies():
    print("=" * 60)
    print("Connecting to Chrome via Remote Debugging")
    print("=" * 60)
    print("\nMake sure Chrome is running with --remote-debugging-port=9222")
    print("And you are logged into geminigen.ai\n")
    
    try:
        playwright = sync_playwright().start()
        
        # Connect to existing Chrome via CDP
        browser = playwright.chromium.connect_over_cdp("http://localhost:9222")
        print("[✓] Connected to Chrome")
        
        # Get all contexts
        contexts = browser.contexts
        if not contexts:
            print("[✗] No browser contexts found")
            return False
        
        context = contexts[0]
        print(f"[✓] Found {len(context.pages)} pages")
        
        # Find geminigen page or use first page
        target_page = None
        for page in context.pages:
            if 'geminigen' in page.url.lower():
                target_page = page
                print(f"[✓] Found GeminiGen page: {page.url}")
                break
        
        if not target_page and context.pages:
            target_page = context.pages[0]
            print(f"[!] Using first page: {target_page.url}")
        
        # Get all cookies
        cookies = context.cookies()
        print(f"[✓] Retrieved {len(cookies)} cookies")
        
        # Filter for geminigen cookies
        geminigen_cookies = [c for c in cookies if 'geminigen' in c.get('domain', '').lower()]
        print(f"[✓] Found {len(geminigen_cookies)} GeminiGen cookies")
        
        # Check for auth cookies
        auth_cookies = [c for c in geminigen_cookies if any(
            k in c['name'].lower() for k in ['session', 'auth', 'token', 'user', 'sb-']
        )]
        if auth_cookies:
            print(f"[✓] Found {len(auth_cookies)} auth-related cookies!")
            for c in auth_cookies:
                print(f"    - {c['name']}")
        
        # Save to JSON file (Playwright format)
        with open(COOKIE_FILE, 'w') as f:
            json.dump(geminigen_cookies, f, indent=2)
        print(f"\n[✓] Saved {len(geminigen_cookies)} cookies to {COOKIE_FILE}")
        
        # Also show if we're logged in
        if target_page:
            page_content = target_page.evaluate("() => document.body.innerText.substring(0, 1000)")
            if 'Generate' in page_content or 'Credits' in page_content:
                print("\n✅ SUCCESS! You appear to be logged in.")
                print("   Cookies saved. You can now use geminigen_browser.py")
            else:
                print("\n⚠️ Unable to confirm login status")
                print(f"   Page content preview: {page_content[:200]}...")
        
        # Cleanup
        browser.close()
        playwright.stop()
        
        return True
        
    except Exception as e:
        print(f"\n[✗] Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure Chrome is running with --remote-debugging-port=9222")
        print("2. Make sure no other Chrome instances were running before")
        print("3. Try closing all Chrome windows and restart with the debug flag")
        return False

if __name__ == "__main__":
    connect_and_save_cookies()
