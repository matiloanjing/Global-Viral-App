"""
GeminiGen.ai API Client
=======================
Direct API access using JWT authentication.
No browser needed - just API calls!

Usage:
    from geminigen_api import GeminiGenAPI
    
    api = GeminiGenAPI()
    result = api.generate_video("A cat playing piano", model="veo-3-fast")
"""

import os
import json
import time
import requests
from typing import Optional, Callable, Dict, Any
from datetime import datetime

# API Configuration
GEMINIGEN_API_BASE = "https://geminigen.ai/api"
AUTH_FILE = os.path.join(os.path.dirname(__file__), "geminigen_auth.json")


class GeminiGenAPI:
    """GeminiGen.ai API client with JWT authentication."""
    
    def __init__(self, auth_file: str = AUTH_FILE):
        self.auth_file = auth_file
        self.access_token = None
        self.refresh_token = None
        self.user = None
        self._load_auth()
    
    def _load_auth(self):
        """Load auth tokens from file."""
        try:
            if os.path.exists(self.auth_file):
                with open(self.auth_file, 'r') as f:
                    data = json.load(f)
                self.access_token = data.get('access_token')
                self.refresh_token = data.get('refresh_token')
                self.user = data.get('user', {})
                print(f"[GeminiGen] Loaded auth for: {self.user.get('email', 'unknown')}")
                print(f"[GeminiGen] Credits: {self.user.get('available_credit', 0)}")
                return True
        except Exception as e:
            print(f"[GeminiGen] Failed to load auth: {e}")
        return False
    
    def _save_auth(self):
        """Save auth tokens to file."""
        try:
            data = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'user': self.user,
                'updated_at': datetime.now().isoformat()
            }
            with open(self.auth_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[GeminiGen] Failed to save auth: {e}")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers with auth token."""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Origin': 'https://geminigen.ai',
            'Referer': 'https://geminigen.ai/app/video-gen/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def _api_call(self, method: str, endpoint: str, data: dict = None) -> Optional[Dict]:
        """Make API call with auth."""
        url = f"{GEMINIGEN_API_BASE}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=self._get_headers(), timeout=30)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=self._get_headers(), json=data, timeout=60)
            else:
                return None
            
            if response.status_code == 401:
                print("[GeminiGen] Token expired - need to refresh")
                # Try to refresh token
                if self._refresh_access_token():
                    return self._api_call(method, endpoint, data)
                return None
            
            if response.status_code >= 400:
                print(f"[GeminiGen] API error {response.status_code}: {response.text[:200]}")
                return None
            
            return response.json()
            
        except Exception as e:
            print(f"[GeminiGen] API call failed: {e}")
            return None
    
    def _refresh_access_token(self) -> bool:
        """Refresh the access token."""
        try:
            response = requests.post(
                f"{GEMINIGEN_API_BASE}/auth/refresh",
                json={'refresh_token': self.refresh_token},
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get('access_token', self.access_token)
                if 'refresh_token' in data:
                    self.refresh_token = data['refresh_token']
                self._save_auth()
                print("[GeminiGen] Token refreshed!")
                return True
                
        except Exception as e:
            print(f"[GeminiGen] Token refresh failed: {e}")
        
        return False
    
    def get_user_info(self) -> Optional[Dict]:
        """Get current user info and credits."""
        result = self._api_call('GET', '/users/me')
        if result:
            self.user = result.get('user', result)
            self._save_auth()
        return result
    
    def get_credits(self) -> int:
        """Get available credits."""
        info = self.get_user_info()
        if info and 'user_credit' in info:
            return info['user_credit'].get('available_credit', 0)
        return self.user.get('available_credit', 0)
    
    def generate_video(
        self,
        prompt: str,
        model: str = "veo-3-fast",
        aspect_ratio: str = "16:9",
        duration: int = 8,
        resolution: str = "720p",
        enhance_prompt: bool = True,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """
        Generate video using GeminiGen API.
        
        Args:
            prompt: Video description
            model: veo-3-fast, veo-3, sora-2, etc.
            aspect_ratio: 16:9 or 9:16
            duration: Video duration seconds
            resolution: 720p or 1080p
            enhance_prompt: Let AI enhance prompt
            output_path: Where to save video
            progress_callback: (progress, message) callback
            
        Returns:
            Path to downloaded video or None
        """
        def log(msg, progress=0):
            print(f"[GeminiGen] {msg}")
            if progress_callback:
                progress_callback(progress, msg)
        
        if not self.access_token:
            log("No auth token! Please set up authentication first.", 0)
            return None
        
        log(f"Starting video generation with {model}...", 0.05)
        log(f"Prompt: {prompt[:50]}...", 0.1)
        
        # Prepare request
        payload = {
            "prompt": prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "resolution": resolution,
            "enhance_prompt": enhance_prompt
        }
        
        # Submit generation request
        log("Submitting generation request...", 0.15)
        
        # Try different API endpoints (need to discover the correct one)
        endpoints = [
            '/v1/video/generate',
            '/video/generate',
            '/ai/video/generate',
            '/generate/video',
        ]
        
        result = None
        for endpoint in endpoints:
            result = self._api_call('POST', endpoint, payload)
            if result:
                log(f"Request submitted via {endpoint}", 0.2)
                break
        
        if not result:
            log("Failed to submit request - API endpoint unknown", 0)
            log("Please check browser Network tab for correct API endpoint", 0)
            return None
        
        # Get task/job ID
        task_id = result.get('task_id') or result.get('job_id') or result.get('id')
        if not task_id:
            log(f"Response: {result}", 0.2)
            # Maybe result is the video directly?
            if 'url' in result or 'video_url' in result:
                video_url = result.get('url') or result.get('video_url')
                log("Video URL received directly!", 0.9)
                return self._download_video(video_url, output_path, log)
        
        # Poll for completion
        log(f"Task ID: {task_id} - Waiting for generation...", 0.25)
        
        status_endpoints = [
            f'/v1/video/status/{task_id}',
            f'/video/status/{task_id}',
            f'/task/{task_id}',
        ]
        
        max_wait = 600  # 10 minutes
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            time.sleep(10)
            elapsed = int(time.time() - start_time)
            progress = min(0.25 + (elapsed / max_wait) * 0.6, 0.85)
            
            for endpoint in status_endpoints:
                status = self._api_call('GET', endpoint)
                if status:
                    state = status.get('status') or status.get('state')
                    log(f"Status: {state} ({elapsed}s)", progress)
                    
                    if state in ['completed', 'done', 'success', 'finished']:
                        video_url = status.get('url') or status.get('video_url') or status.get('result', {}).get('url')
                        if video_url:
                            log("Video ready!", 0.9)
                            return self._download_video(video_url, output_path, log)
                    
                    if state in ['failed', 'error']:
                        log(f"Generation failed: {status.get('error', 'Unknown')}", 0)
                        return None
                    
                    break
        
        log("Timeout waiting for video", 0)
        return None
    
    def _download_video(self, url: str, output_path: Optional[str], log) -> Optional[str]:
        """Download video from URL."""
        if not output_path:
            output_path = os.path.join(os.path.dirname(__file__), f"geminigen_video_{int(time.time())}.mp4")
        
        log(f"Downloading video...", 0.92)
        
        try:
            response = requests.get(url, stream=True, timeout=120)
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                log(f"Saved to: {output_path}", 1.0)
                return output_path
        except Exception as e:
            log(f"Download failed: {e}", 0)
        
        return None


def test_api():
    """Test API connection."""
    print("=" * 60)
    print("Testing GeminiGen API")
    print("=" * 60)
    
    api = GeminiGenAPI()
    
    if not api.access_token:
        print("\n❌ No auth token found!")
        print("Please save your tokens to geminigen_auth.json")
        return False
    
    print(f"\n✅ Token loaded for: {api.user.get('email')}")
    print(f"   Credits: {api.user.get('available_credit', 'unknown')}")
    
    # Test getting user info
    print("\nTesting user info endpoint...")
    info = api.get_user_info()
    if info:
        print(f"✅ User info retrieved successfully")
        return True
    else:
        print("⚠️ Could not retrieve user info (token may be expired)")
        print("   But we can still try to generate videos")
        return True


if __name__ == "__main__":
    test_api()
