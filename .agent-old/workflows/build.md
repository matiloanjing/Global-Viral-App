---
description: Build the GlobalViral Clipper EXE application
---

# Build Application

This workflow builds the GlobalViral Clipper into a standalone Windows EXE.

## Steps

// turbo-all

1. Navigate to project directory:
   ```bash
   cd c:\Users\TO THE MOON\Downloads\BotYTS\OplusClip
   ```

2. Kill any running instances:
   ```bash
   taskkill /F /IM GlobalViralClipper.exe 2>$null
   ```

3. Clean previous build:
   ```bash
   Remove-Item -Recurse -Force dist\GlobalViralClipper -ErrorAction SilentlyContinue
   ```

4. Run the build script:
   ```bash
   python build_installer.py
   ```

## Output

The EXE will be created at:
```
dist/GlobalViralClipper/GlobalViralClipper.exe
```

## Notes
- Build takes ~3-5 minutes
- FFmpeg is bundled automatically
- Output size: ~20.7 MB
