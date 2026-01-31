## 0. 🎬 AIVideoMaker Download Fix V2 (Dec 30, 2025)
**Problem:** Downloaded sample videos (landscape) instead of generated videos (vertical 9:16)
**Root Cause:** Network interception captured sample video URLs on page, not generated video
**Fix:** 
- Removed unreliable Method 0 (network interception priority)
- Added `_validate_video_is_vertical()` - uses ffprobe to check aspect ratio
- Validation: landscape = sample → reject, vertical = generated → accept
**Files:** `aivideomaker_browser.py` - lines 167-218 (validation), 484-494 (disabled method 0), 796-812 (check before return)

## 1. 📊 Image Provider Logging (Dec 30, 2025)
**New:** Log now shows EXACT provider used: `Pollinations NEW API (flux)`, `Pollinations OLD API (turbo)`, `Prodia`, `Stable Horde`, etc.
**Files:** `animator_v2.py` Lines 1109-1116, 1155, 1205, 1287, 1320, 1398, 1489

## 2. 🚀 Pollinations Priority Fix (Dec 30, 2025)
**Problem:** Image generation stuck/slow due to Stable Horde (slow) being default primary
**Fix:** Reordered providers: Pollinations (Primary) -> Prodia -> Stable Horde
**Result:** Instant generation using Pollinations New/Old API, huge speedup.
**File:** `animator_v2.py` Lines 1441-1460

## 2. 🔊 Animator Audio Download Fix (Dec 30, 2025)
**Problem:** "Failed to download audio" error in Animator tab
**Fix:** Added support for `.mp4` audio files in `_download_audio`
**File:** `main.py` Lines 2790-2797

## 3. 🎨 Pollinations API Restoration (Dec 30, 2025)
**Problem:** Pollinations API key support lost after reset
**Fix:** Restored `set_pollinations_api_key` and Bearer auth logic
**File:** `animator_v2.py` Lines 1103-1175

## 4. 🎮 GeminiGen Browser Automation (Dec 30, 2025)
**New:** Created `geminigen_browser.py` for https://geminigen.ai
**File:** `geminigen_browser.py` (NEW - 350 lines)

## 5. 🔊 TTS Voice Bug Fix (Dec 29, 2025)
**Fix:** Pass voice name ("Indonesian Female") not voice_id
**File:** `test_full_3d.py` Lines 220-246
