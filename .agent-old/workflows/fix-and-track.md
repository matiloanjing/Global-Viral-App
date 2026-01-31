---
description: Load project context and track all changes with documentation
---

# Fix and Track

Perintah ini akan:
1. Baca context proyek dari .agent/
2. Dokumentasikan semua perubahan (before/after)
3. Update progress dan blueprint

## Saat Sesi Baru - AI Akan:

1. **Baca file context (urutan prioritas):**
   - `.agent/QUICK_REF.md` (wajib, ~30 baris)
   - `.agent/RECENT.md` (wajib, ~15 baris) 
   - `.agent/BLUEPRINT.md` (jika perlu detail arsitektur)
   - `.agent/CHANGELOG.md` (jika debugging)

2. **Setelah setiap perubahan kode, update:**
   - `RECENT.md` - Tambah entry baru (max 5, hapus yang lama)
   - `CHANGELOG.md` - Log lengkap dengan before/after
   - `BLUEPRINT.md` - Update jika ada perubahan arsitektur

## Format Log di CHANGELOG.md:

```markdown
### [DATE] [Emoji] Nama Fix
**Problem:** Deskripsi masalah
**Cause:** Penyebab
**Fix:** Solusi
**File:** `filename.py` line ~XXX
**Before:**
\`\`\`python
kode lama
\`\`\`
**After:**
\`\`\`python
kode baru
\`\`\`
```

## Format di RECENT.md:
```
1. **[Nama Fix]** - deskripsi singkat (line ~XXX)
```

## Cara Pakai:
Cukup bilang: "lanjutkan project" atau "/fix-and-track"
AI akan otomatis load context dan siap melanjutkan.
