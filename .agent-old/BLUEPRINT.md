# GlobalViral Clipper - Blueprint

> Last Updated: 2025-12-21

## 🎯 Purpose
Repurpose YouTube videos → viral TikTok/Reels/Shorts clips

---

## ⛔ ABSOLUTE RULES - JANGAN UBAH!

> **Fitur yang TIDAK BOLEH diubah tanpa izin user:**

| Fitur | File | Alasan |
|-------|------|--------|
| Echo/Reverb Audio | `animator_v2.py` TTS | Variasi suara, hindari duplicate |
| Seed System | Line ~2763 | Konsistensi gambar |
| 2.5D Animation | `create_scene_video_2_5d()` | Efek parallax, zoom, pan |
| Filter Overlay | `FILTER_COMBOS` | 10 genre-matched filters |
| SFX Detection | `detect_sfx_from_text()` | Sound effects |
| Multi-Language | `{language}` variable | ID, EN support |
| Genre Templates | `GENRES` dict | 10 genre dengan tone |
| Caption Styles | Karaoke, Bounce, etc | Subtitle animations |

**PRINSIP: Jika error → PERBAIKI, bukan HAPUS!**

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                    USER INPUT                        │
│          (YouTube URL / Local Video File)            │
└─────────────────────┬───────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────┐
│                    5 TABS                            │
│  🎬 Viral Clipper    → Cut clips from video         │
│  🎭 Character Edit   → Face-based highlight reel    │
│  ✨ AI Animator      → AI-generated animations      │
│  🔑 API Settings     → Configure API keys           │
│  📚 Docs             → Documentation                │
└─────────────────────────────────────────────────────┘
```

---

## 📁 Key Files

| File | Purpose | Lines |
|------|---------|-------|
| `main.py` | Main app + UI | ~4050 |
| `animator_v2.py` | AI Animator engine | ~3000 |
| `character_edit.py` | Character Edit engine (NEW) | ~400 |
| `build_installer.py` | Build EXE | ~360 |

---

## 🎬 AI Animator Structure (Dec 2024)

**5-Part Cold Open Structure:**
```
PART 1 [HOOK]        - 15% - Dramatic opening
PART 2 [DETAIL]      - 30% - Context/background  
PART 3 [REALIZATION] - 20% - Twist/turning point
PART 4 [CLIMAX]      - 25% - Peak action
PART 5 [ENDING]      - 10% - Resolution/cliffhanger
```

**Each PART contains N scenes:**
- Scene = 1 short narration (~2-3 sec) + 1 image
- Total scenes = Image Count slider (5-75)

---

## 🔑 APIs

| API | Purpose |
|-----|---------|
| Groq | Transcription (whisper-large-v3-turbo) |
| Gemini | Story generation (gemini-2.5-flash) |
| Pollinations | Image generation (free) |
| Prodia | Image generation (backup) |
| edge-tts | TTS dubbing (free) |
