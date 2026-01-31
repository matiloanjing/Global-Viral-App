# GlobalViral Clipper - Project Memory

## 📋 Project Overview

**Name:** GlobalViral Clipper (OplusClip)  
**Type:** Desktop Application (Windows EXE)  
**Framework:** Python + CustomTkinter  
**Purpose:** Repurpose long YouTube videos into viral short-form clips for TikTok/Reels/Shorts

## 🏗️ Architecture

### Philosophy
- **Heavy Logic in Cloud:** Groq + Gemini API (transcription & AI analysis)
- **Light Logic Locally:** UI + FFmpeg (rendering)
- **Optimized for 4GB RAM**

### Core Technologies
| Component | Technology |
|-----------|------------|
| GUI | CustomTkinter (dark theme) |
| Video Download | yt-dlp |
| Transcription | Groq Whisper (whisper-large-v3-turbo) |
| AI Analysis | Google Gemini 2.5 Flash |
| Translation | deep-translator (GoogleTranslator) |
| TTS Dubbing | edge-tts |
| Rendering | FFmpeg |
| Build | PyInstaller |

## 🎯 Key Features

### 1. YouTube Analysis Pipeline
1. Download video + audio via yt-dlp
2. Transcribe with Groq (returns segments with timestamps)
3. Analyze transcript with Gemini to find 3-5 viral moments
4. Display clips with score, category, and reason

### 2. Subtitle System (Netflix/CapCut Style)
- **Segment-based timing:** Uses real Groq timestamps for accurate sync
- **3 words at a time:** CapCut-style word-by-word animation
- **Word highlight:** Current word in yellow, others white
- **Translation:** Per-segment translation maintains timing
- **Position:** Top-center (Alignment 8, MarginV 300)

### 3. Dubbing System
- **Edge-TTS voices:** Indonesian/English (Male/Female)
- **Speed:** +30% rate for faster speech
- **Volume:** 5x boost for TTS, 0.05 for original audio
- **Independent:** Subtitle and dubbing languages can differ

### 4. Video Processing
- **9:16 crop:** Auto center-crop for vertical
- **Filters:** None, Sepia, Black & White, Slow Zoom (Ken Burns)
- **Watermark:** Centered overlay
- **Preset:** ultrafast, CRF 28

## 📁 File Structure

```
OplusClip/
├── main.py              # Main app (~1500 lines)
├── build_installer.py   # Auto-build script
├── requirements.txt     # Dependencies
├── README.md           # Documentation
├── config.json         # Saved API keys
├── .agent/             # Agent memory
│   ├── PROJECT.md      # This file
│   └── workflows/      # Slash commands
├── bin/                # FFmpeg binaries
└── dist/               # Built EXE output
```

## 🔧 Key Code Components

### main.py Structure
1. **Imports & Optional Dependencies** (lines 1-60)
2. **Constants & Configuration** (lines 65-115)
3. **Utility Functions** (lines 130-300)
4. **ASS Subtitle Generator** (lines 300-470)
   - `create_ass_subtitle()` - basic version
   - `create_ass_subtitle_from_segments()` - segment-based timing
5. **ClipCard Widget** (lines 475-550)
6. **GlobalViralClipperApp Class** (lines 560-1580)
   - `__init__` - state variables
   - `_create_layout()` - UI construction
   - `_start_analysis()` - download/transcribe/analyze
   - `_render_worker()` - render selected clips
   - `_render_single_clip()` - FFmpeg pipeline

### State Variables
- `self.transcript_segments: List[Dict]` - Raw Groq segments with timestamps
- `self.clips: List[ClipData]` - AI-detected viral clips
- `self.video_path` - Downloaded video path

## 🐛 Known Issues & Fixes Applied

| Issue | Cause | Fix |
|-------|-------|-----|
| Ken Burns 3+ hours | zoompan filter too slow | Replaced with scale+crop expression |
| Subtitle full paragraph | All words shown at once | Chunk into 3 words at a time |
| Subtitle out of sync | Even division by words | Use Groq segment timestamps |
| Watermark corner | overlay=W-w-20:H-h-20 | Changed to center (W-w)/2:(H-h)/2 |
| TTS too quiet | volume=1.2 | Increased to volume=5.0 |

## 🔑 API Keys Required

| API | Purpose | Link |
|-----|---------|------|
| Groq | Transcription | https://console.groq.com/ |
| Gemini | AI Analysis | https://aistudio.google.com/ |

## 📦 Build Command

```bash
python build_installer.py
```

Output: `dist/GlobalViralClipper/GlobalViralClipper.exe` (~20.7 MB)

## 🎨 UI Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ [Sidebar 280px]        │  [Main Content]                        │
│ ────────────────       │  ┌───────────────────────────────────┐ │
│ 🌍 GlobalViral         │  │ 🎬 YouTube URL: [___________] [🔍] │ │
│   Clipper              │  └───────────────────────────────────┘ │
│                        │                                        │
│ ⚙️ API Settings        │  📋 Detected Viral Clips              │
│ Groq: [**********]     │  ┌─────────────────────────────────┐  │
│ Gemini: [**********]   │  │ [✓] Clip 1: Title... [Score]    │  │
│ [💾 Save Keys]         │  │ [✓] Clip 2: Title... [Score]    │  │
│                        │  │ [✓] Clip 3: Title... [Score]    │  │
│ • Performance Mode     │  └─────────────────────────────────┘  │
│ ✅ FFmpeg Ready        │                                        │
│                        │  [💬 Subtitle ▼][🎙️ Dubbing ▼][🚀 RENDER]│
│ 🎨 Video Filter: [▼]   │  [═══════════════════════════════════] │
└─────────────────────────────────────────────────────────────────┘
```

## 📝 Changelog

### v1.0.0 (Dec 2024)
- Initial release with all core features
- Segment-based subtitle sync
- Ken Burns filter optimization
- Watermark center positioning
- TTS volume boost
