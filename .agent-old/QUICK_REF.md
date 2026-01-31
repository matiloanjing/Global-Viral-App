# Quick Reference - Kilat Code Clipper

## ⛔ JANGAN UBAH (Tanpa Izin User)
- Echo/Reverb audio
- Seed system (42000)
- 2.5D Animation effects
- Filter/SFX system
- Multi-language support
- Genre templates
- **Character Edit moment selection logic**
- **Working functions - only FIX, don't REMOVE**

## 📁 Main Files
- `main.py` - UI + Clipper tab (~4050 lines)
- `animator_v2.py` - AI Animator engine (~3000 lines)
- `character_edit.py` - Character Edit engine (~1617 lines)
- `build_installer.py` - Build EXE

## 🎭 Character Edit Key Lines
- Face ending filter: **Line 1133-1136**
- Face selection: **Lines 1099-1114**
- Audio concat: **Lines 1216-1259**
- Subtitle ASS: **Lines 269-425**
- Story moments: **Lines 753-973**
- **READ `.agent/CHARACTER_EDIT_REF.md` for details!**

## 🏗️ Current Architecture (Dec 2024)
- **5-Part Structure:** HOOK → DETAIL → REALIZATION → CLIMAX → ENDING
- **Each Part:** Contains N scenes (distributed by %)
- **Each Scene:** 1 narration (~2-3 sec) + 1 image
- **Image Count:** 5-75 (slider controls total scenes)

## 📋 Key Lines in animator_v2.py
- `GENRES` dict: ~291-555
- Prompt generation: ~1571-1700
- JSON parsing: ~1785-1840
- Seed system: ~2763
- TTS generation: ~1940-2050
- 2.5D effects: ~2287-2445
- SFX detection: ~631-780

## 🔧 Build Command
```bash
python build_installer.py
```

## ✅ Before Any Change
1. Read this file
2. Read RECENT.md
3. Read CHARACTER_EDIT_REF.md (for character_edit.py)
4. If architecture change → read BLUEPRINT.md
5. If debugging → read CHANGELOG.md

## 🚨 MANDATORY: Document EVERY Change
After EVERY code change, update:
1. `RECENT.md` - Add entry (max 5)
2. `CHANGELOG.md` - Full before/after with line numbers
