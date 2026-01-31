# 🚀 GlobalViral App

<p align="center">
  <img src="logo.png" width="180" alt="GlobalViral App">
  <br><br>
  <b>Repurpose YouTube videos into viral TikTok/Reels/Shorts with AI automation</b>
  <br><br>
  <a href="#-features">Features</a> •
  <a href="#-installation">Installation</a> •
  <a href="#-usage">Usage</a> •
  <a href="#-api-keys">API Keys</a>
</p>

---

## ✨ Features

| Tab | Description |
|-----|-------------|
| 🎬 **Viral Clipper** | Extract highlight clips from YouTube videos with smart engagement detection |
| 🎭 **Character Edit** | Face-based highlight reel with character tracking |
| ✨ **AI Animator** | Generate AI animations from transcripts with 2.5D parallax effects |
| 🔑 **API Settings** | Configure API keys for AI services |
| 📚 **Docs** | Built-in Indonesian tutorial |

### 🎨 AI Animator Highlights
- 10 genre templates (Documentary, Horror, Comedy, Romance...)
- 10 art styles (Ghibli Anime, Realistic, Vintage, Cyberpunk...)
- 5-Part Cold Open storytelling structure
- Edge-TTS dubbing (Indonesian, English voices)
- 10 video filter combinations

---

## 🚀 Installation

```bash
# Clone repository
git clone https://github.com/matiloanjing/Global-Viral-App.git
cd Global-Viral-App

# Install dependencies
pip install -r requirements.txt

# Run application
python main.py
```

### Build EXE
```bash
python build_installer.py
# Output: dist/KilatCodeClipper.exe
```

---

## 🔑 API Keys

Configure in **API Settings** tab:

| API | Purpose | Required |
|-----|---------|:--------:|
| Groq | Transcription | ✅ |
| Gemini | Story generation | Optional |
| Prodia | Image backup | Optional |

**Free (no key needed):** Pollinations.ai, Edge-TTS

---

## 🎯 Usage

1. Launch `python main.py` or `KilatCodeClipper.exe`
2. Select tab: Viral Clipper / AI Animator / Character Edit
3. Paste YouTube URL or upload local video
4. Configure: genre, style, voice, filter
5. Click generate and wait
6. Download result

---

## 📁 Structure

```
├── main.py              # Main UI (Gradio)
├── animator_v2.py       # AI Animator engine
├── character_edit.py    # Character Edit engine
├── license.py           # License management
├── build_installer.py   # Build script
├── bin/                 # FFmpeg binaries
└── sfx/                 # Sound effects
```

---

## ⚠️ Notes

- Add Python exception in antivirus if image gen fails
- Requires internet for API calls
- FFmpeg bundled in `bin/`

---

## 📄 License

Proprietary - License key required for activation.

---

<p align="center">
  <img src="https://img.shields.io/badge/Made%20with-❤️-red" alt="Made with love">
  <br><br>
  <b>🚀 KilatCode Studio © 2025</b>
</p>
