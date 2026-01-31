# Changelog

## 2025-12-30 - 📊 Image Provider Logging

### Feature
Log now shows EXACT image provider used for each generated image.

### Implementation
Added global variable `_last_image_provider` that each provider function sets upon success:
- `Pollinations NEW API (flux/turbo/zimage)` - Authenticated API
- `Pollinations OLD API (flux/turbo/zimage)` - Free tier
- `Prodia` - Paid API
- `Stable Horde` - Free community API
- `Dezgo` - Free fallback
- `Perchance` - Free fallback

### Log Format
```
✅ Image via: Pollinations NEW API (flux) | Size: 123456 bytes
```

**File:** `animator_v2.py` (Multiple locations)

---

## 2025-12-30 - 🚀 Pollinations Priority Fix (HUGE Speedup)

### Problem
Image generation stuck at 32% ("Generating consistent visuals") for long periods (>5 mins).

### Cause
**Configuration Error:** Default provider priority was hardcoded as **Stable Horde -> Pollinations**.
Stable Horde (Free) often has massive queues (waiting time 3-10 mins/image). The system waited for Stable Horde to timeout (180s) before trying Pollinations.

### Fix
**Reordered Providers:**
1. **Pollinations (Primary):** New API (Key) + Old API (Fallback) combined. Response time: ~5-10s.
2. **Prodia:** If user provides key.
3. **Stable Horde:** Fallback only.

### Result
Image generation is now instant (seconds) instead of minutes.

**File:** `animator_v2.py` Lines 1441-1460

---

## 2025-12-30 - 🐛 Bug Fixes: Animator Audio & Pollinations API

### 1. Animator "Failed to download audio" Fix
**Problem:** `yt-dlp` returned `audio.mp4` (m4a inside mp4 container) but `main.py` only checked for `m4a`, `mp3`, `webm`, `opus`.
**Fix:** Added `.mp4` to the list of checked extensions in `_download_audio`.
**File:** `main.py` Lines 2790-2797

### 2. Pollinations API Key Restoration
**Problem:** Resetting `animator_v2.py` accidentally removed the `set_pollinations_api_key` support.
**Fix:** Re-implemented Bearer auth logic for faster generation using `gen.pollinations.ai`.
**File:** `animator_v2.py` Lines 1103-1175

---

## 2025-12-29 - 🎨 Pollinations API Update (New Endpoint + Bearer Auth)

### Problem
Pollinations API inconsisten dengan server yang sering offline ("No active flux/turbo servers available").

### Fix
1. **New Endpoint:** `gen.pollinations.ai` (was `image.pollinations.ai`)
2. **Bearer Auth:** Menggunakan API key untuk prioritas queue (lebih cepat)
3. **Model Fallback:** flux → turbo → zimage (jika satu offline, coba yang lain)
4. **Backward Compatible:** Jika tidak ada API key, tetap bisa pakai API lama (gratis tapi antri)

**Files:** 
- `animator_v2.py` lines ~1106-1175
- `main.py` lines ~71, ~2248, ~2305, ~3850-3870, ~3922

**Before (animator_v2.py):**
```python
def generate_image_pollinations(prompt: str, width: int, height: int, seed: int, output_path: str) -> bool:
    """Try Pollinations.ai (primary provider)"""
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model=flux..."
    response = requests.get(url, timeout=120)  # No auth
```

**After (animator_v2.py):**
```python
_pollinations_api_key: Optional[str] = None

def set_pollinations_api_key(key: str):
    """Set Pollinations API key for faster generation"""
    global _pollinations_api_key
    _pollinations_api_key = key if key else None

def generate_image_pollinations(prompt: str, width: int, height: int, seed: int, output_path: str) -> bool:
    """Models fallback: flux → turbo → zimage"""
    models = ['flux', 'turbo', 'zimage']
    for model in models:
        if _pollinations_api_key:
            url = f"https://gen.pollinations.ai/image/{encoded_prompt}?model={model}..."
            headers = {'Authorization': f'Bearer {_pollinations_api_key}'}
            response = requests.get(url, headers=headers, timeout=120)
        else:
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model={model}..."
            response = requests.get(url, timeout=120)
        if response.status_code == 200: return True
    return False
```

**main.py Changes:**
- Added `set_pollinations_api_key` to import
- Added Pollinations API Key entry field in API Settings tab
- Added `pollinations_api_key` to config save/load
- Added `set_pollinations_api_key()` call when animation starts
- Added Pollinations URL to info section

---

## 2025-12-27 - 🖼️ Watermark Placed in Bottom Black Bar

### Problem
1. Watermark diletakkan di pojok kanan bawah video content
2. Filter chain broken - watermark [1:v] syntax joined with comma to vf filters

### Fix
Rebuild filter_complex to properly chain: [0:v]filters[v1];[1:v]scale[wm];[v1][wm]overlay

**File:** `character_edit.py` lines 1396-1442

**Before:**
```python
wm_filter = "[1:v]scale=108:-1[wm];[0:v][wm]overlay=W-w-20:H-h-20"
vf_filters.append(wm_filter)  # BROKEN - mixing stream syntax with vf filters
vf_string = ",".join(vf_filters)
cmd = [..., "-filter_complex" if watermark_path else "-vf", vf_string, ...]
```

**After:**
```python
# Proper filter_complex chain
base_filter = f"[0:v]{','.join(vf_filters)}[v1]"  # Main video + filters
wm_scale = "[1:v]scale=-1:200[wm]"  # Scale watermark
wm_overlay = "[v1][wm]overlay=(main_w-overlay_w)/2:1610"  # Overlay center bottom
filter_complex = f"{base_filter};{wm_scale};{wm_overlay}"
cmd = [..., "-filter_complex", filter_complex, ...]
```

---

## 2025-12-26 - 🎨 Flash Color Changed to Medium Gray

### Problem
White flash terlalu terang/menyilaukan. #CCCCCC masih terlalu terang (terlihat hampir putih).

### Fix
Ubah warna flash ke medium gray (#888888) yang lebih terlihat kontrasnya.

**File:** `character_edit.py` line 1229

**Before:**
```python
"-i", "color=c=0xCCCCCC:s=1080x1920:r=30:d=0.1",  # Light gray flash
```

**After:**
```python
"-i", "color=c=0x888888:s=1080x1920:r=30:d=0.1",  # Medium gray flash (visible)
```

---

## 2025-12-26 - 📝 Subtitle Overlap Fix

### Problem
Subtitle menampilkan 2 baris teks yang sama bersamaan (overlapping).

### Cause
ASS renderer menampilkan multiple dialogue events yang aktif pada waktu bersamaan karena timing end_time = next_start_time (tepat sama).

### Fix
Tambahkan 0.01s gap antara subtitle events.

**File:** `character_edit.py` lines 350-374, 401-420

**Before:**
```python
if word_idx + 1 < len(chunk):
    end_time = chunk[word_idx + 1]['abs_start']
```

**After:**
```python
if word_idx + 1 < len(chunk):
    end_time = chunk[word_idx + 1]['abs_start'] - 0.01
# Skip if duration too short
if end_time <= start_time:
    continue
```

---

## 2025-12-26 - 🎬 Gemini Climax Keyword Validation

### Problem
Gemini analysis memberikan timestamps yang bervariasi setiap run, menyebabkan fight/action scene hilang.

### Cause
Gemini tidak deterministik meski dengan temperature=0. Timestamp yang disarankan mungkin tidak berisi action content.

### Fix
Validasi Gemini climax dengan ACTION_KEYWORDS. Jika tidak ada action words dalam 10 detik dari timestamp, cari action scene menggunakan keyword matching.

**File:** `character_edit.py` lines 928-997

**Before:**
```python
gemini_climax = gemini_hints.get('climax_time')
if gemini_climax and isinstance(gemini_climax, (int, float)):
    # Use Gemini-suggested climax time directly
    climax_start = max(last_end_time, gemini_climax - climax_clip_duration / 2)
```

**After:**
```python
gemini_climax = gemini_hints.get('climax_time')
use_gemini_climax = False

def find_action_scene(search_start, search_end):
    # Find timestamp with most action keywords
    ...

if gemini_climax and isinstance(gemini_climax, (int, float)):
    # Check if Gemini timestamp contains action keywords
    has_action = any(kw in text_lower for kw in ACTION_KEYWORDS
                     for seg in segments if abs(seg_start - gemini_climax) <= 10)
    
    if not has_action:
        # Search for actual action scene
        keyword_climax = find_action_scene(mid_end, climax_end)
        if keyword_climax:
            gemini_climax = keyword_climax
```

---

## 2025-12-26 - ⚡ White Flash Effect (Separate Clip Approach)

### Problem
`fade=t=in` dan `fade=t=out` dengan `setpts` menyebabkan timing conflict (4KB corrupt clips).

### Cause
FFmpeg fade filter timing tidak sync dengan video yang sudah di-slow-mo dengan setpts.

### Fix
Generate 0.1s white frame clip menggunakan `lavfi color` dan interleave dengan face clips dalam concat list.

**File:** `character_edit.py` lines 1220-1270

**Before:**
```python
# No flash - only slowmo
slowmo_filter = f"{crop_filter},setpts=2.0*PTS"
# Direct concat face clips
for fc in face_clip_paths:
    f.write(f"file '{escaped}'\n")
```

**After:**
```python
# Generate white flash frame
flash_cmd = [ffmpeg_path, "-y", "-f", "lavfi",
             "-i", "color=c=white:s=1080x1920:r=30:d=0.1",
             "-c:v", "libx264", flash_path]

# Interleave flash before each face clip
for fc in face_clip_paths:
    if has_flash:
        f.write(f"file '{flash_path}'\n")  # Flash
    f.write(f"file '{escaped}'\n")  # Face
```

---

## 2025-12-21 - 🎭 NEW: Character Edit Feature

### Feature
New tab "🎭 Character Edit" that creates character-focused highlight reels from films and videos.

### Implementation
**Files:** `character_edit.py` (NEW ~400 lines), `main.py`, `requirements.txt`

1. **New Engine:** `character_edit.py`
   - `detect_faces_in_frames()` - Extract faces with timestamps
   - `cluster_faces()` - Group similar faces by identity
   - `identify_main_character()` - Find main character (auto or by name)
   - `select_best_moments()` - Pick best moments across video
   - `create_character_edit()` - FFmpeg cut + concat + effects
   - `create_rapid_face_ending()` - 5 second rapid face montage

2. **New Tab UI:** `main.py`
   - Video input (YouTube URL or local file)
   - Character name (optional, auto-detect if empty)
   - Duration: 30s / 45s / 60s
   - Moment count: 3-10 slider
   - Transition: Random / Cut / Shake / Zoom / Flash
   - Filter, Watermark options

3. **Dependencies:** `requirements.txt`
   - `face_recognition>=1.3.0`
   - `dlib>=19.24.0`
   - `numpy>=1.24.0`

### Notes
- Falls back to transcript-only mode if face_recognition not installed
- Output saved to Desktop/CharacterEdits folder

## 2025-12-21 - 🛠️ Character Edit Import Fix for PyInstaller

### Problem
EXE crashed at startup with error: "Unable to open C:\...\dist\KilatCodeClipper\_int"
Traceback showed error in `character_edit.py` line 22.

### Cause
- `face_recognition` import uses `pkg_resources` which fails in PyInstaller bundle
- Model file paths not accessible in bundled EXE

### Fix
Changed import handling from:
```python
try:
    import face_recognition
    import numpy as np
    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False
```

To broader exception handling:
```python
HAS_FACE_RECOGNITION = False
face_recognition = None
np = None

try:
    import numpy as np
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError as e:
    print(f"[CharacterEdit] face_recognition not installed: {e}")
except Exception as e:
    # Catch all errors including path issues in PyInstaller bundle
    print(f"[CharacterEdit] face_recognition failed to load: {e}")
```

**File:** `character_edit.py` lines 20-35

---

## 2025-12-21 - 🔧 Face Recognition Dependencies Installation

### Problem
dlib and face_recognition failed to install:
- `pip install cmake` created broken cmake module
- dlib build subprocess couldn't find cmake executable

### Solution
**Steps:**
1. Downloaded CMake 3.28.1 portable ZIP from cmake.org
2. Extracted to project folder: `cmake-3.28.1-windows-x86_64/`
3. Set PATH to include portable CMake bin folder
4. Compiled dlib 20.0.0 from source (~5 min compile time)
5. Installed face_recognition 1.3.0

**Commands Used:**
```powershell
# Download CMake portable
Invoke-WebRequest -Uri "https://github.com/Kitware/CMake/releases/download/v3.28.1/cmake-3.28.1-windows-x86_64.zip" -OutFile "cmake.zip"
Expand-Archive -Path cmake.zip -DestinationPath . -Force

# Build dlib with CMake in PATH
$env:PATH = "C:\path\to\cmake-3.28.1-windows-x86_64\bin;" + $env:PATH
pip install dlib  # Compiles from source
pip install face_recognition
```

### Result
```
Face Recognition: True ✅
```

---

## 2025-12-20 - 🎭 Genre-Aware Narration for ALL 10 Genres

### Problem
- Narration was robot-like: "Ayahnya terluka." (too short)
- Line 1592 forced "1-2 sentences (~10-20 words)" for ALL genres
- This overrode genre templates which had richer examples

### Solution
**File:** `animator_v2.py` (Lines 1593-1597)

**Before:**
```
Each scene narration = 1-2 sentences (~10-20 words, ~2-3 seconds speech)
```

**After:**
```
3. Narration style MUST match genre:
   - Horror/Sci-Fi: Dark, atmospheric, suspenseful (2-3 sentences per scene)
   - Documentary/Motivational: Clear, informative, inspiring (2-3 sentences)
   - Fairy Tale/Children's: Gentle, magical, warm (2-3 sentences)
   - Comedy/Viral: Punchy, conversational, witty (1-2 sentences)
   - Brainrot/Brainrot ID: Short, chaotic, meme-speak (1 sentence with slang)
```

**Also added line 1600:**
```
5. Sound like a HUMAN telling a story to a friend, NOT a robot reading news!
```

---

## 2025-12-20 - 🔊 SFX Volume Reduced to 50%

### Problem
- SFX drowning out TTS voice
- Volume was 0.7 (70%)

### Solution
**Files:** `animator_v2.py` (Line 932), `main.py` (Line 3252)
- Changed: `sfx_volume: float = 0.5`
- Both Animator and Clipper tabs consistent at 50%

---

## 2025-12-20 - 🏗️ 5-Part Multi-Scene Architecture (MAJOR REFACTOR v2)

### Problem
- Old architecture: 1 narration per part + multiple visuals (first visual speaks, others silent)
- Result: Non-speaking visuals skipped, only 5 images rendered instead of 13
- "Scene X" text appearing in subtitles from fallback logic

### Solution
**Files:** `animator_v2.py` (Lines 1571-1660, 1775-1835)

1. **New Schema: `parts[].scenes[]`**
   - Each PART contains multiple SCENES
   - Each SCENE has its own short narration (~2-3 sec) + image
   - NO more empty narrations / skipped visuals

2. **Flexible Distribution:**
   - HOOK: ~15%, DETAIL: ~30%, REALIZATION: ~20%, CLIMAX: ~25%, ENDING: ~10%
   - AI can adjust ±1-2 scenes based on story flow

3. **Fixes Applied:**
   - Line 1854-1857: Removed "Scene X" fallback
   - Line 1880-1884: Added scene_visual quote cleaning
   - Line 1775-1835: Backward compatible parsing (new + old schema)

**Before:**
```json
{"parts": [{"part_name": "[THE HOOK]", "narration": "long text...", "visuals": [...]}]}
```

**After:**
```json
{"parts": [{"part_name": "[THE HOOK]", "scenes": [{"narration": "short text", "scene_visual": "..."}]}]}
```

---

## 2025-12-20 - 🏗️ Fixed 5-Parts Narration Architecture (MAJOR REFACTOR)

### Problem
- User selected 14 scenes → AI generated 14 separate narrations
- Template only had 5 parts → AI improvised 9 extra narrations
- Result: Narration bertele-tele, tidak sesuai template

### Solution
**Files:** `animator_v2.py` (Lines 1571-1660, 1775-1835), `main.py` (Lines 1636-1658)

1. **Fixed 5 Narration Parts:**
   - [THE HOOK] → [THE DETAIL] → [THE REALIZATION] → [THE CLIMAX] → [THE ENDING]
   - Struktur tetap sama, durasi adjust based on video length

2. **Separate Image Count:**
   - UI slider renamed: "Scene Count" → "Image Count"
   - Range: 5-75 images (max 3 min)
   - Images distributed across 5 parts, change every 2-3 seconds

3. **New JSON Schema:**
   ```json
   {"parts": [{"part_name": "[THE HOOK]", "narration": "...", "visuals": [...]}]}
   ```

4. **Backward Compatible:**
   - Flattens parts[].visuals[] into scenes[]
   - First visual of each part gets narration (TTS)
   - Other visuals in same part are image-only

---

## 2024-12-20 - 🎭 Genre-Specific Narration Templates (MAJOR UPDATE)

1. **Pronoun Style per Genre:**
   | Genre | pronoun_style | Contoh |
   |-------|---------------|--------|
   | Horror, Documentary, Fairy Tale, Children's, Sci-Fi | `formal` | "Seseorang...", "Polisi menyadari..." |
   | Motivational | `semi-formal` | "Aku/Kamu" (bukan Gue/Lu) |
   | Comedy, Viral, Brainrot, Brainrot ID | `casual` | "Gue kaget, bro!" |

2. **Forbidden Words per Genre:**
   - Horror: `["gue", "lu", "bro", "banget", "anjir", "sumpah", "gokil", "wkwk"]`
   - Documentary: `["gue", "lu", "bro", "anjir", "banget", "sumpah", "gila"]`
   - Comedy/Viral/Brainrot: `[]` (semua diizinkan)

3. **5-Scene Narration Example per Genre (ID + EN):**
   - `narration_example_id` - Indonesian version
   - `narration_example_en` - English version
   - Format: `[THE HOOK]` → `[THE DETAIL]` → `[THE REALIZATION]` → `[THE CLIMAX]` → `[THE ENDING]`

4. **Updated language_rules:**
   - **REMOVED:** Global "USE: Gue/Lu" instruction
   - **ADDED:** Conditional pronoun instruction based on `pronoun_style`

5. **Fallback Mechanism Verified:**
   - Provider fallback: Gemini → Groq → Gemini retry
   - **NO content simplification** - prompt stays exactly the same
   - If all fail → return None (handle in UI)

---

## 2024-12-20 - 🎙️ Voice Options Sync Between Tabs

### Problem
- Animator hanya 3 voices (Indonesian Female, Indonesian Male, English Female)
- Clipper punya 5 voices dengan format nama berbeda (Indonesian (Male), dll)
- Root cause: Animator UI pakai `HAS_ANIMATOR_MODULE` yang selalu False karena import dari file deprecated

### Fix
**File:** `main.py` (Lines 107-133, 1538)

1. **Line 1538:** Ganti `VOICE_OPTIONS` + `HAS_ANIMATOR_MODULE` → `VOICES_V2` + `HAS_ANIMATOR_V2`
2. **DUBBING_OPTIONS:** Sync dengan `VOICE_OPTIONS` dari animator_v2 + "Original"
3. **EDGE_TTS_VOICES:** Tambah English UK Female dan Japanese Female
4. **TRANSLATE_LANGS:** Tambah mapping untuk UK English (en) dan Japanese (ja)

### Result
| Tab | Voices |
|-----|--------|
| Animator | Indonesian Female/Male, English Female/Male, English UK Female, Japanese Female |
| Clipper | **Original** + sama dengan Animator (6 voices) |

---

## 2024-12-20 - 📝 Cold Open Prompt Enhancement (User Edit)

### Enhancement
User menambahkan instruksi baru untuk meningkatkan engagement video.

### Changes
**File:** `animator_v2.py` (Lines 1404, 1454-1455)

1. **Narrator Role:** `narrator` → `professional narrator and storyteller`
2. **PAYOFF Instruction:** "Briefly hint at the value or the ending of the video to keep the audience watching until the end."
3. **TRANSITION Instruction:** "End the Cold Open with a smooth bridge to the main intro or title sequence."

---

## 2024-12-20 - ⚖️ SFX Keywords Rebalancing

### Problem
Keyword `whoosh` over-mapped (30+ keywords) sehingga SFX lain jarang dipakai (footsteps, door_knock, dll).

### Fix
**File:** `animator_v2.py` (Lines 631-780)

Redistribusi keywords ke semua 17 SFX files:

| SFX File | Keywords (ID + EN) |
|----------|-------------------|
| `beep` | computer, robot, ai, sistem, notification, click, klik |
| `crash` | tabrak, hancur, pecah, shatter, smash, hantam, gebrak |
| `cry` | menangis, sedih, galau, mewek, terisak, heartbroken |
| `door_knock` | pintu, ketuk, masuk, datang, tiba, tamu |
| `door_slam` | banting, marah, kesal, frustasi, pergi, keluar |
| `explosion` | ledak, boom, wow, gila, amazing, hebat, spektakuler |
| `footsteps` | jalan, langkah, kejar, ikuti, mengendap |
| `heartbeat` | jantung, deg-degan, takut, cemas, tegang |
| `laser` | sinar, tembak, future, space, alien, teknologi |
| `laugh` | tertawa, lucu, kocak, ngakak, wkwk, haha |
| `magic` | sihir, ajaib, mantra, muncul, hilang, berkilau, indah |
| `rain` | hujan, badai, basah, tetes, banjir |
| `scream` | teriak, kaget, horor, hantu, pocong, ngeri |
| `thunder` | petir, kilat, kekuatan, epik, dramatis |
| `vine_boom` | bruh, sus, sigma, ternyata, akhirnya, plot twist |
| `whoosh` | cepat, lari, terbang, tiba-tiba (reduced!) |
| `wind` | angin, hembus, dingin, sejuk, alam, hutan |

---

## 2024-12-20 - 🔊 SFX Support for Clipper Tab

### Feature
Clipper tab sekarang juga support SFX seperti Animator! Sound effects akan ditambahkan berdasarkan transcript clip.

### Implementation
**File:** `main.py` (Lines 71, 3204-3304, 3358-3360)

1. **Import:** Ditambahkan `detect_sfx_keywords`, `mix_audio_with_sfx`, `SFX_KEYWORDS` dari animator_v2
2. **Step 5.5 (NEW):** Deteksi SFX keywords dari `clip.text_segment`:
   - Extract audio dari video
   - Deteksi keywords (whoosh, explosion, magic, dll)
   - Mix SFX ke audio asli
   - Log hasil ke UI console (`🔊 SFX Detected`, `✅ SFX Mixed`)
3. **Step 6:** Ditambahkan branch untuk menggunakan SFX-mixed audio
4. **Cleanup:** SFX temp files (`temp_audio_X.mp3`, `temp_sfx_mixed_X.mp3`) ditambahkan ke list cleanup

### UI Log Messages
- `🔊 SFX Detected: ['whoosh', 'magic']`
- `✅ SFX Mixed: ['whoosh.mp3']`
- `🎵 Using SFX-mixed audio in final render`

---

## 2024-12-20 - 🎭 Genre-Specific Language Rules

### Problem
Narasi "cringe" dan repetitif untuk semua genre. Horror pakai kata "Gila", "Sumpah", "Woy" yang tidak cocok. Power Words hardcoded untuk semua genre tanpa mempertimbangkan tone masing-masing.

### Fix
**File:** `animator_v2.py` (Lines 291-460, 1301-1353)

1. **Genre-Specific Power Words:** Setiap genre sekarang punya `power_words_id` dan `power_words_en` sendiri:
   - Horror: "Tiba-tiba,", "Perlahan,", "Di balik kegelapan,"
   - Comedy: "Gila,", "Sumpah,", "Anjir,", "Woy,"
   - Documentary: "Menurut penelitian,", "Faktanya,", "Data menunjukkan,"
   - Fairy Tale: "Alkisah,", "Konon,", "Di negeri antah berantah,"
   - dll (10 genre total)

2. **Genre-Specific Tone Instruction:** Setiap genre punya `tone_instruction_id/en`:
   - Horror: "Kayak baca creepypasta. Bangun ketegangan."
   - Comedy: "Kayak curhat lucu ke temen. Santai dan menghibur."
   - Documentary: "Kayak narrator NatGeo. Objektif dan informatif."

3. **Anti-Repetition Rule:** Ditambahkan instruksi eksplisit:
   - "JANGAN mulai 2 scene berturut-turut dengan kata yang sama!"
   - Contoh BAD/GOOD untuk variasi pembuka scene

4. **Dynamic Injection:** `language_rules` sekarang pakai f-string untuk inject power words dan tone dari genre preset.

### Removed (Deprecated)
- Hardcoded: `POWER WORDS: "Sumpah,", "Gila,", "Jujur,", "Woy,".`
- Hardcoded: `TONE: Kayak curhat seru ke temen deket.`

---

## 2024-12-20 - 🔊 SFX Import Random Fix

### Problem
SFX mix selalu gagal dengan error `NameError: name 'random' is not defined`.

### Fix
**File:** `animator_v2.py` (Line 19)
- Added: `import random` yang hilang dari imports.

---

## 2024-12-19 - 🚀 Viral Audio & Language Overhaul

### Problem
User feedback:
1. Subtitle kaku/formal ("Anda", "Mari kita").
2. Tempo audio terlalu lambat (tidak viral material).
3. Audio terdengar robotic (datar).
4. Perlu "Anti-Duplication" signature agar tidak kena Low Content.

### Fix
### Fix
**File:** `animator_v2.py`
1. **TTS Speed:** Base rate dinaikkan ke **+15%** (sebelumnya 0%) untuk energi lebih tinggi.
2. **Dynamic Pacing:** Implementasi `atempo` random (0.95x - 1.15x) per file agar tidak monoton.
3. **Anti-Duplication:** Reverb/Gema diperkuat (`aecho` 0.8:0.9) untuk signature unik tiap video.
4. **Language Rules:** Prompt sekarang **dinamis**. Jika Bahasa Indonesia -> Mahal Gaul (No Anda). Jika Inggris -> Viral Slang (No Textbook).
5. **SFX Variety:** SFX sekarang di-randomize speed/pitch-nya (0.85x - 1.15x) agar suara "sama" terdengar beda tiap kali muncul.
6. **Syntax Fix:** Koreksi indentasi pada blok `if/else` bahasa dan deklarasi `prompt` yang menyebabkan `SyntaxError`.
7. **Natural Conversation (Anti-Cringe):** Prompt diperbaiki untuk menghindari campuran kata baku & gaul ("Wajah" -> "Muka", "Partikel" -> "Debu", "Telah" -> "Udah"). Fokus pada *Spoken Language*.
8. **Particle Control:** Membatasi penggunaan partikel ("nih", "sih") agar tidak muncul di setiap akhir kalimat (repetitif). Instruksi: *Use SPARINGLY*.
9. **True Shorts Style:** Implementasi "Struktur Kalimat Terbalik" (Inversion) dan penghapusan subjek ("Baru tau gue" > "Saya baru tahu") untuk kesan *authentic conversation*.
11. **Nuclear Speed Boost (The Real Fix):**
    *   *Problem:* Prompt "Max 5 words" diabaikan AI (hasil tetap 8 kata = 6 detik). User: "10 images = 1 menit" (terlalu lambat).
    *   *Fix:*
        1. **TTS Base Speed:** DINA-IKKAN ke **+45%** (sebelumnya +15%).
        2. **DSP Speedup:** Filter `atempo` diset **1.25x - 1.45x** (semua audio dipercepat secara mekanis).
    *   *Result:* Kalimat 8 kata sekarang hanya berdurasi 2.5 detik. Konsisten dengan "Viral Pacing".

12. **Viral SFX Recovery:**
    *   *Problem:* Akibat prompt "Max 5 words", kata-kata deskriptif (pintu, lari, hujan) hilang, jadi SFX tidak bunyi.
    *   *Fix:* Menambahkan **50+ Kata Kunci Viral** ke mapping SFX.
        *   "Muncul", "Hilang", "Cepat" -> `whoosh.mp3`
        *   "Sumpah", "Anjir", "Gila", "Wow" -> `explosion.mp3`
        *   "Ternyata", "Fakta", "Keren" -> `magic.mp3`
    *   *Result:* SFX akan muncul otomatis mengikuti gaya bahasa "Tongkrongan".

13. **Natural Flow & Strict Path Fix:**
    *   *Problem:* Narasi Robotik & SFX Path Error pada Distribusi.
    *   *Voice Fix:* Prompt diubah ke **"Natural Fast (8-12 words)"** (Anti-Robot).
    *   *SFX Fix:* Logika path dikunci ke `_internal\sfx` untuk standar distribusi (OneDir). Tidak ada scanning folder sembarangan.
    *   *Result:* Aplikasi siap distribusi (Zip friendly).

---

## 2024-12-19 - 🐇 Fast-Paced Storytelling Prompt Fix

### Problem
Narasi terlalu bertele-tele, repetitif, dan terkesan membaca skrip. Hal ini disebabkan oleh instruksi AI yang memaksa menyebar konten tipis ke banyak scene ("Spread all content evenly") dan kurangnya instruksi untuk menjaga momentum cerita.

### Fix
**File:** `animator_v2.py`
1. **Removed:** Instruksi "Spread all content evenly" yang memaksa padding/filler.
2. **Added:** Instruksi **"Forward Momentum"** (setiap kalimat harus info/emosi baru).
3. **Added:** Gaya bahasa **"Storyteller Mode"** (seperti YouTuber cerita ke teman, bukan baca berita).
4. **Refined:** Batasan narasi "Short & Punchy (max 1-2 sentences)" di format JSON.

---

## 2024-12-19 - 🎨 Clipper Filter & Bitrate Fix

### Problem
Filter overlay di **Clipper Tab** tidak berfungsi (video hasil tetap original). Video bitrate di Clipper juga masih rendah (12M).

### Cause
1. Logika filter lama (Sepia, B&W, Slow Zoom) di `main.py` tidak sesuai dengan `VIDEO_FILTER_OPTIONS` baru.
2. `CLIPPER_FILTER_EFFECTS` didefinisikan tapi tidak pernah digunakan.
3. Encoder bitrate settings di `main.py` masih hardcoded 12M.

### Fix
**File:** `main.py` lines ~2935-3150

**Changes:**
1. **Removed:** Old filter logic causing conflicts.
2. **Fixed:** Video filter applied correctly during crop/scale step using imported `FILTER_EFFECTS`.
3. **Updated:** Bitrate increased to **20M** (max 25M, buf 30M) for ALL encoders (nvenc, qsv, amf, libx264).
4. **Cleaned:** Removed unused `CLIPPER_FILTER_EFFECTS` dictionary.

---

## 2024-12-19 - 🎭 Complete Genre Tone Enforcement

### Problem
Narasi terdengar formal/robotik meskipun memilih genre Comedy. AI mengabaikan genre tone.

### Fix
**File:** `animator_v2.py` line ~1215-1250

Added MANDATORY genre enforcement for ALL 10 genres with specific instructions:
```python
⚠️ GENRE ENFORCEMENT (MANDATORY FOR ALL GENRES!):
- Comedy → ADD JOKES, humor, funny observations, witty sarcasm!
- Horror → ADD tension, dread, creepy atmosphere, suspenseful pauses!
- Motivational → ADD inspiration, energy, empowerment, triumph!
- Documentary → Informative but ENGAGING, add "wow factor"!
- Children's Story → Warm, friendly, magical wonder!
- Fairy Tale → Whimsical, enchanting, wonder and awe!
- Drama → Emotional depth, human connection, heartfelt moments!
- Viral Shorts → Punchy, fast-paced, hook-driven, clickbait energy!
- Brainrot → CHAOTIC, GEN-Z humor, unhinged, meme energy!
- Brainrot ID → Bahasa gaul, "literally gila", "sus banget"!

❌ DON'T:
- Use em-dash (—), en-dash (–), or double hyphen (--)
- Use broken sentences like "Tapi tunggu—bagaimana" (NO DASHES!)
```

---

## 2024-12-19 - 🎚️ Scene Count Accuracy Fix

### Problem
User set 10 scenes, got 11 images. AI returned more scenes than requested.

### Fix
**File:** `animator_v2.py` line ~1379, `main.py` line ~1670

**Changes:**
1. Slider max upgraded: 45 → 100 (support 10+ minute videos)
2. Added hard truncation after AI response:
```python
if len(scenes_list) > num_scenes:
    print(f"DEBUG: AI returned {len(scenes_list)} but user requested {num_scenes}. Truncating...")
    scenes_list = scenes_list[:num_scenes]
```

---

## 2024-12-19 - 📹 Video Bitrate Increase

### Problem
Video file size hanya 18MB, seharusnya 25-30MB+ untuk 30 detik video.

### Fix
**File:** `animator_v2.py` line ~1966, ~2100+

Increased bitrate for ALL encoders (libx264, nvenc, qsv, amf):
```python
# BEFORE
'-b:v', '12M', '-maxrate', '15M', '-bufsize', '20M'

# AFTER
'-b:v', '20M', '-maxrate', '25M', '-bufsize', '30M'
```

---

## 2024-12-19 - 🧹 Code Cleanup

### Changes
- Deleted: `animator_old.py`, `test_animator.py`, `test_progressbar.py` (1-5)
- Deleted: `test_audio/`, `test_output/` folders
- Marked `calculate_optimal_scenes` as DEPRECATED
- Updated old animator import comment in `main.py`

---

## 2024-12-18 - 🚨 CRITICAL: Animator Module Loading Fix

### Problem
"Animator module not loaded!" error when clicking "Generate Story" button. User reported Animator tab completely broken.

### Cause
Line 1902 in `_start_animation()` checked `HAS_ANIMATOR_MODULE` (old animator.py, always False) instead of `HAS_ANIMATOR_V2` (animator_v2.py, True).

### Fix
**File:** `main.py` line 1902

**Before:**
```python
if not HAS_ANIMATOR_MODULE:  # <-- WRONG! This is False
    messagebox.showerror("Error", "Animator module not loaded!")
```

**After:**
```python
if not HAS_ANIMATOR_V2:  # <-- CORRECT! This is True when animator_v2.py loads
    messagebox.showerror("Error", "Animator module not loaded!")
```

---

## 2024-12-18 - 🔧 Prodia Field + Animator Filter UI Fix

### Problem
1. Prodia API Key field cut off at bottom of API Settings tab
2. Animator filter dropdown had 6 hardcoded filters vs backend's 10 FILTER_EFFECTS

### Fix
**Files:** `main.py` line ~1599, ~3367

**Changes:**
1. API Settings container changed to `CTkScrollableFrame` for scroll support
2. Animator `filter_options` now uses `FILTER_EFFECTS.keys()` from animator_v2.py

**Before (Animator):**
```python
filter_options = ["None", "Sepia", "Noir B&W", "Vintage VHS", "Vivid", "Deep Fried"]
```

**After (Animator):**
```python
filter_options = list(FILTER_EFFECTS.keys()) if HAS_ANIMATOR_V2 else [...]
# Results in 10 genre-matched filters
```

---

## 2024-12-18 - 🖼️ Prodia API as Fallback Image Provider

### Problem
Image generation only used Pollinations/Dezgo/Perchance. User wanted Prodia API as additional reliable fallback with SD 1.5 models.

### Fix
**Files:** 
- `animator_v2.py` line ~855-950, ~937-948
- `main.py` line ~70, ~1935-1940, ~3427-3450

**Changes:**
1. Added Prodia API key field in API Settings tab  
2. Created `generate_image_prodia_api()` function using Prodia SD v1 API
3. Added `set_prodia_api_key()` helper to configure key from main.py
4. Integrated into hybrid fallback chain as second option

**Fallback Order:**
1. Pollinations.ai (free, Flux model)
2. **Prodia (new)** (SD 1.5, requires API key)
3. Dezgo (free)
4. Perchance (free)

---

## 2024-12-18 - 🎬 Cold Open Narrative Structure

### Problem
Narration prompt used sequential retelling - no impact, flat opening. User wanted Cold Open structure (start with most dramatic moment) while preserving transcript content.

### Fix
**File:** `animator_v2.py` line ~285-406, ~968-1043

**Changes:**
1. Added `cold_open_instruction` to all 10 GENRES
2. Rewrote prompt template for Cold Open structure
3. Added natural language guidelines (no robotic, no cringe)
4. Ensured visual-narration sync

**Before:**
```python
# GENRES - old structure
"narrative_structure": "hook_deliver",
# No cold_open_instruction

# Prompt - sequential retelling
=== YOUR TASK ===
RETELL the COMPLETE transcript into {num_scenes} scenes
```

**After:**
```python
# GENRES - new Cold Open
"narrative_structure": "cold_open",
"cold_open_instruction": "Start with the most SHOCKING fact from transcript...",

# Prompt - Cold Open structure
=== YOUR TASK: COLD OPEN STRUCTURE ===
⚡ SCENE 1: Start with MOST IMPACTFUL moment
📖 SCENE 2+: Provide context

=== ✍️ WRITING STYLE ===
✅ Write naturally, like human narrator
❌ Don't sound robotic or use cringe slang
```

---

## 2024-12-17 - 📹 Support Video 3 Menit

### Problem
App hanya support video 1-1.5 menit, scene slider max 15, transcript dipotong 3000 chars.

### Fix
**File:** `main.py` line 1549-1570, `animator_v2.py` line 773

**Before:**
```python
# main.py
self.scene_slider = ctk.CTkSlider(col4_inner, from_=5, to=15, ...)
ctk.CTkLabel(slider_labels, text="Long (15)", ...)

# animator_v2.py
{transcript[:8000]}
```

**After:**
```python
# main.py
self.scene_slider = ctk.CTkSlider(col4_inner, from_=5, to=45, ...)
ctk.CTkLabel(slider_labels, text="3min (45)", ...)

# animator_v2.py
{transcript[:15000]}
```

---

## 2024-12-17 - 📝 Content Preservation (Anti-Hallucination)

### Problem
Gemini meringkas/memotong informasi penting dari transcript asli.

### Fix
**File:** `animator_v2.py` line 768-793

**Before:**
```python
=== YOUR TASK ===
PARAPHRASE the transcript into {num_scenes} scenes
```

**After:**
```python
=== YOUR TASK ===
RETELL the COMPLETE transcript into exactly {num_scenes} scenes
⚠️ IMPORTANT: Cover ALL information - do NOT skip or summarize!

CRITICAL RULES:
1. PRESERVE ALL key information - every important fact must appear
2. DO NOT skip, summarize, or compress - include ALL details
3. If transcript is long, each scene can have longer narration (2-3 sentences OK)
```

---

## 2024-12-17 - 🖼️ Visual Prompt Accuracy

### Problem
scene_visual (`King on throne`) dicampur dengan fallback (`a person`, `simple background`).

### Fix
**File:** `animator_v2.py` line 967-994

**Before:**
```python
visual_prompt = build_image_prompt(
    character_desc=base_character,  # "a person" ← SALAH
    action=scene_visual,
    background=bg_desc,  # "simple background" ← SALAH
    mood=mood  # "neutral" ← SALAH
)
```

**After:**
```python
# scene_visual already contains subject, action, setting, lighting
# Use it DIRECTLY - don't add fallback fields!
visual_prompt = ", ".join([
    scene_visual,  # "King on throne, coffee cup, castle interior"
    style_suffix,  # "studio ghibli style..."
    quality_tags   # "masterpiece, best quality..."
])
```

---

## 2024-12-17 - 🎨 Filter Overlay Integration

### Problem
Filter options berbeda antara UI dan backend (MISMATCH).

### Fix
**File:** `animator_v2.py` line 317-336, `main.py` line 70, 127-132, 2883-2913

Synced filters: `[None, Sepia, Noir B&W, Vintage VHS, Vivid]`

---

## 2024-12-17 - 🎯 White Box Hook Styling

### Problem
Hook box tidak sesuai reference screenshot.

### Fix
**File:** `animator_v2.py` line 1402-1421, `main.py` line 2880-2901

**Before:** Green box with white text
**After:** WHITE box (95% opacity), BLACK text, font 64

---

## 2024-12-15 - 🎨 OpusClip-Style Redesign + Quality Upgrade

### Features Added
1. **FFmpeg Quality Upgrade** - CRF 18, medium preset, libx264, 192k audio
2. **ClipCard Redesign** - Large vertical cards (220x340), grid layout (4 cols)
3. **Auto Hook (UI)** - Hook text overlay on thumbnails
4. **Auto Hook (Video)** - Hook text burned into first 5 seconds of rendered video

### Before/After
**Video Quality:**
- CRF: 28 → 18 (much sharper)
- Audio: 128k → 192k
- File size: 2-10MB → 10-30MB+

**ClipCard UI:**
- Size: 130x78 → 220x340
- Layout: Vertical list → Grid (4 cols)
- Hook text overlay + time badges

---

## 2024-12-15 - 🎬 Clipper Tab UI Restoration

### Problem
Clipper tab missing: Performance Mode switch, Min/Max Clips sliders, Video Filter dropdown, Debug Log

### Cause
Components were in old sidebar (`_create_sidebar_original()`) but never moved to fullscreen layout during Dec 2024 redesign.

### Fix
**File:** `main.py` lines ~1179-1305

**Added:**
- `_create_clipper_settings_row()` - Settings row with all controls
- `_create_clipper_debug_log()` - Console textbox like Animator tab
- `_log_clipper()` - Helper to append log messages
- Updated `_update_progress()` to log to debug console

**Before (Layout):**
```
Row 0: URL Input
Row 1: Label
Row 2: Clips Grid
Row 3: Render Section  ← Missing settings!
```

**After (Layout):**
```
Row 0: URL Input
Row 1: Label
Row 2: Clips Grid
Row 3: Settings Row (Performance Mode, Min/Max Clips, Filter)  ← NEW
Row 4: Debug Log Console  ← NEW
Row 5: Render Section
```

---


## 2024-12-15 - 📹 Video Download Fallback Fix

### Problem
"Failed to download video" error at Step 4 of analysis pipeline

### Cause
Single format string not always compatible with all YouTube videos

### Fix
**File:** `main.py` lines ~2325-2365

Added 4 format fallback strategies with detailed Debug Console logging.

---

## 2024-12-14 - 🔧 Critical Language Fix

### Problem
- Indonesian voice selected → English subtitles/TTS
- Subtitles stuck/flat (not animated)

### Cause
`_run_animation_thread` was using OLD `animator.py` module
NOT calling `animator_v2.py` with proper language handling.
`generate_restory_script` called WITHOUT voice/language parameter.

### Fix
**File:** `main.py` line ~1680

**Before:**
```python
scenes_data = generate_restory_script(transcript, genre, gemini_key, num_scenes)
# Uses OLD animator.py - no language parameter!
```

**After:**
```python
from animator_v2 import generate_animation_v2

output_path = generate_animation_v2(
    transcript=transcript,
    genre=genre,
    style=style,
    voice=voice,  # THIS PASSES VOICE/LANGUAGE!
    num_scenes=num_scenes,
    ...
)
```

### Test Results (Verified)
```
DEBUG: Generated 8 scenes in Indonesian
DEBUG: Scene 0 - Added SFX: ['beep']
DEBUG: Scene 4 - Added SFX: ['heartbeat']
✅ Final video: 18.49 MB @ 1080x1920
```

---

## 2024-12-14 - 🎨 Animator Tab UI Redesign

### New Features
- Obsidian dark theme (#0F0F0F)
- 4-column settings grid
- Log console textbox
- Scene preview panel
- Download button with duration

---

## 2024-12-14 - 🎭 SSML Prosody for Natural TTS

### Fix
Added SSML prosody wrapper for more natural storytelling voice.

**File:** `animator_v2.py` line ~820

```python
def create_ssml_prosody(text: str) -> str:
    ssml = f'''<speak>
<prosody rate="0.95" pitch="+5%">
{text}
</prosody>
</speak>'''
    return ssml
```

---

## 2024-12-14 - 🔊 Indonesian SFX Keywords

### Fix
Added 80+ Indonesian keywords to SFX detection.

**File:** `animator_v2.py` line ~284

```python
SFX_KEYWORDS = {
    "pintu": "door_knock",
    "meledak": "explosion",
    "tertawa": "laugh",
    "menangis": "cry",
    "takut": "heartbeat",
    # ... 80+ more
}
```
