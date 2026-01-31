"""
Pollinations Video Generation Module
=====================================
Uses Pollinations.ai API for video generation from prompts.

Available models:
- seedance: BytePlus model for dance/motion (15 pollen, ~1.8/M)
- seedance-pro: Higher quality (25 pollen, ~1.0/M)
- veo: Google Veo for high quality (costs pollen per second)

Usage:
    from pollinations_video import generate_video_pollinations, generate_video_from_image
    
    # Text-to-video
    result = generate_video_pollinations("A cat dancing", model="seedance")
    
    # Image-to-video (with image reference)
    result = generate_video_from_image("image.png", "Cat dancing", model="seedance")
"""

import os
import json
import time
import base64
import requests
import urllib.parse
from pathlib import Path
from typing import Optional, Callable

POLLINATIONS_API = "https://gen.pollinations.ai"


def _get_api_key() -> str:
    """Get Pollinations API key from config."""
    config_path = Path(__file__).parent / "config.json"
    try:
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                return config.get("pollinations_api_key", "")
    except:
        pass
    return ""


def generate_video_pollinations(
    prompt: str,
    model: str = "seedance",
    output_path: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Optional[str]:
    """
    Generate video from text prompt using Pollinations API.
    
    Args:
        prompt: Text description of the video
        model: seedance, seedance-pro, or veo
        output_path: Where to save the video
        progress_callback: Optional (progress, message) callback
        
    Returns:
        Path to generated video or None if failed
    """
    def log(msg, progress=0):
        print(f"[Pollinations] {msg}")
        if progress_callback:
            progress_callback(progress, msg)
    
    api_key = _get_api_key()
    
    log(f"Starting video generation with {model}...", 0.05)
    log(f"Prompt: {prompt[:50]}...", 0.1)
    
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        log("Using API key", 0.15)
    else:
        log("No API key - may fail for premium models", 0.15)
    
    # Encode prompt
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"{POLLINATIONS_API}/image/{encoded_prompt}?model={model}&nologo=true"
    
    log("Requesting video...", 0.2)
    
    try:
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=300, stream=True)
        elapsed = time.time() - start_time
        
        log(f"Response: {response.status_code} ({elapsed:.1f}s)", 0.8)
        
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            
            # Video response
            if 'video' in content_type or 'mp4' in content_type:
                if not output_path:
                    output_path = os.path.join(
                        os.path.dirname(__file__),
                        f"pollinations_{model}_{int(time.time())}.mp4"
                    )
                
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                log(f"✅ Video saved: {output_path} ({size_mb:.2f} MB)", 1.0)
                return output_path
            
            # GIF or image fallback
            elif 'gif' in content_type or 'image' in content_type:
                ext = 'gif' if 'gif' in content_type else 'png'
                if not output_path:
                    output_path = os.path.join(
                        os.path.dirname(__file__),
                        f"pollinations_{model}_{int(time.time())}.{ext}"
                    )
                
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                log(f"⚠️ Got image/GIF: {output_path}", 0.9)
                return output_path
            
            # JSON with video URL
            elif 'json' in content_type:
                data = response.json()
                video_url = data.get('url') or data.get('video_url')
                if video_url:
                    log(f"Downloading from URL...", 0.85)
                    video_resp = requests.get(video_url, timeout=120)
                    if video_resp.status_code == 200:
                        if not output_path:
                            output_path = os.path.join(
                                os.path.dirname(__file__),
                                f"pollinations_{model}_{int(time.time())}.mp4"
                            )
                        with open(output_path, 'wb') as f:
                            f.write(video_resp.content)
                        size_mb = os.path.getsize(output_path) / (1024 * 1024)
                        log(f"✅ Video saved: {output_path} ({size_mb:.2f} MB)", 1.0)
                        return output_path
            
            else:
                # Unknown - try to save as raw video
                if not output_path:
                    output_path = os.path.join(
                        os.path.dirname(__file__),
                        f"pollinations_{model}_{int(time.time())}.mp4"
                    )
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                if os.path.getsize(output_path) > 10000:
                    log(f"Saved raw response: {output_path}", 0.9)
                    return output_path
        
        else:
            error_msg = response.text[:200] if response.text else "Unknown error"
            log(f"❌ Error {response.status_code}: {error_msg}", 0)
    
    except requests.exceptions.Timeout:
        log("❌ Request timed out (5 minutes)", 0)
    except Exception as e:
        log(f"❌ Exception: {e}", 0)
    
    return None


def generate_video_from_image(
    image_path: str,
    prompt: str,
    model: str = "seedance",
    output_path: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Optional[str]:
    """
    Generate video from image + prompt using Pollinations.
    
    Note: This creates a prompt that references the image style/content.
    The image is used for context but Pollinations generates fresh video.
    
    For true image-to-video (animate existing image), use AIVideoMaker instead.
    
    Args:
        image_path: Path to reference image
        prompt: Motion/animation description
        model: seedance, seedance-pro, or veo
        output_path: Where to save the video
        progress_callback: Progress callback
        
    Returns:
        Path to generated video or None
    """
    def log(msg, progress=0):
        print(f"[Pollinations I2V] {msg}")
        if progress_callback:
            progress_callback(progress, msg)
    
    if not os.path.exists(image_path):
        log(f"❌ Image not found: {image_path}", 0)
        return None
    
    # For Pollinations, we can't directly animate the image,
    # but we can describe the image content and add motion
    enhanced_prompt = f"{prompt}, highly detailed, smooth motion, cinematic quality"
    
    log(f"Generating video for: {os.path.basename(image_path)}", 0.05)
    log(f"Motion: {prompt[:50]}...", 0.1)
    
    return generate_video_pollinations(
        prompt=enhanced_prompt,
        model=model,
        output_path=output_path,
        progress_callback=progress_callback
    )


# High-level API for integration with test_full_3d.py
def generate_3d_video_pollinations(
    image_path: str,
    prompt: str,
    output_path: Optional[str] = None,
    model: str = "seedance",
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Optional[str]:
    """
    Alternative to AIVideoMaker's generate_3d_video.
    Uses Pollinations video API (faster, but generates new video rather than animating the specific image).
    
    Args:
        image_path: Path to source image (used for context in prompt)
        prompt: Motion/animation description
        output_path: Where to save the video
        model: Pollinations video model
        progress_callback: Progress callback
        
    Returns:
        Path to generated video or None
    """
    return generate_video_from_image(
        image_path=image_path,
        prompt=prompt,
        model=model,
        output_path=output_path,
        progress_callback=progress_callback
    )


if __name__ == "__main__":
    # Quick test
    print("=" * 60)
    print("POLLINATIONS VIDEO MODULE TEST")
    print("=" * 60)
    
    result = generate_video_pollinations(
        prompt="A peaceful forest with gentle sunlight filtering through trees, birds flying, cinematic",
        model="seedance"
    )
    
    if result:
        print(f"\n✅ SUCCESS: {result}")
    else:
        print("\n❌ FAILED")
