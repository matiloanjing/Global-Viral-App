---
description: Common fixes for GlobalViral Clipper issues
---

# Troubleshooting Guide

Quick fixes for common issues.

## Build Issues

### "PermissionError: Access is denied"
The EXE or its files are locked.

```bash
taskkill /F /IM GlobalViralClipper.exe 2>$null
taskkill /F /IM ffmpeg.exe 2>$null
Remove-Item -Recurse -Force dist\GlobalViralClipper -ErrorAction SilentlyContinue
python build_installer.py
```

### "FFmpeg not found"
FFmpeg missing from bin folder.

```bash
python build_installer.py  # Auto-downloads FFmpeg
```

## Runtime Issues

### "NoAudioReceived" (edge-tts)
Edge-TTS failing to generate audio.

```bash
pip install --upgrade edge-tts
```

### "Rate Limit" (Groq)
Groq API quota exceeded.
- Wait a few minutes
- Free tier: 7200 seconds audio/hour

### Rendering too slow
- Ken Burns filter was causing this (fixed in latest)
- Use "None" filter for fastest rendering

## Code Locations

| Issue | File | Line Range |
|-------|------|------------|
| Subtitle style | main.py | 353 (ASS Style) |
| Watermark position | main.py | ~1485 (overlay filter) |
| TTS volume | main.py | ~1475 (volume filter) |
| Ken Burns | main.py | ~1355 (scale+crop) |
