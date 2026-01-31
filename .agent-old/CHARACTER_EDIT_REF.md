# Character Edit - Current State Reference

**Last Updated:** Dec 26, 2025  
**File:** `character_edit.py` (1535 lines)

## ⚠️ JANGAN UBAH TANPA DOKUMENTASI
Setiap perubahan WAJIB dicatat di CHANGELOG.md dengan format:
- **Before:** kode lama
- **After:** kode baru
- **Line:** nomor baris

---

## 📍 Current Implementation (Line Numbers)

### 1. Face Ending Filter (Line 1133-1136)
```python
# CURRENT:
slowmo_filter = f"{crop_filter},setpts=2.0*PTS"
# NOTE: No flash effect - removed due to FFmpeg timing issues
```

**HISTORY:**
- Original: `setpts=1.43*PTS,fade=t=in:st=0:d=0.15:c=white`
- Changed to 2.0 for more visible slow-mo
- Flash removed because `fade=t=out:st=0.7:d=0.3:c=white` caused 4KB corrupt clips

### 2. Face Selection (Lines 1099-1114)
```python
# CURRENT:
sorted_ending_faces = sorted(ending_faces, key=lambda f: f.timestamp)
indices = [int(i * (len(sorted_ending_faces) - 1) / (num_faces_to_use - 1)) 
          for i in range(num_faces_to_use)]
selected_faces = [sorted_ending_faces[i] for i in indices]
```

**PURPOSE:** Evenly distribute 5 face clips across video timeline

### 3. Concat with Audio (Lines 1216-1259)
```python
# CURRENT: filter_complex concat
# Video: [0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[outv]
# Audio: [0:a][1:a][2:a]concat=n=3:v=0:a=1[outa] (story clips only)
```

**NOTE:** Face ending (clip 3) has no audio

### 4. Subtitle ASS Generation (Lines 269-425)
```python
# CURRENT: Karaoke word-by-word with 6-word chunks
# chunk_size = 6
# Yellow highlight: {\c&H00FFFF&\b1}word{\c&HFFFFFF&\b0}
# Alignment=8 (top center), MarginV=150
```

### 5. Story Moment Selection (Lines 753-973)
```python
# CURRENT:
# INTRO: 0-20% of video
# MID: 20-60% of video
# CLIMAX: 60-90% of video (uses Gemini hints)
# ENDING: Face montage
```

---

## 🔑 Key Functions

| Function | Lines | Purpose |
|----------|-------|---------|
| `transcribe_video_audio` | 173-266 | Groq Whisper transcription |
| `create_ass_from_transcript` | 269-425 | ASS subtitle for karaoke |
| `analyze_with_gemini` | 428-550 | AI moment analysis |
| `detect_faces_in_frames` | 596-626 | Face recognition |
| `cluster_faces` | 629-657 | Group similar faces |
| `identify_main_character` | 660-746 | Select main char cluster |
| `select_story_moments` | 753-973 | Pick INTRO/MID/CLIMAX |
| `create_character_edit` | 998-1374 | FFmpeg render |
| `generate_character_edit` | 1381-1524 | Main orchestrator |

---

## 🐛 Known Issues

1. **White Flash tidak bekerja** - FFmpeg fade dengan setpts timing conflict
2. **Subtitle mungkin bertumpuk** - Cek chunk_size dan timing
3. **Fight scene bisa hilang** - Gemini suggested timestamps bervariasi

---

## 📋 Before Making Changes

1. READ this file first
2. DOCUMENT before/after in CHANGELOG.md
3. TEST with same video to compare
4. DO NOT remove working code - only ADD or FIX
