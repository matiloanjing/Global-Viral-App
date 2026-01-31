---
description: Test subtitle and dubbing features
---

# Test Subtitle & Dubbing

Quick test workflow for subtitle/dubbing features.

## Test Steps

1. Run the app (dev or EXE)

2. Enter a YouTube URL

3. Click "Analyze" and wait for clips

4. Test configurations:

### Original Audio + Indonesian Subtitle
- Subtitle: `Indonesian`
- Dubbing: `Original`

### Full Indonesian Dub
- Subtitle: `Indonesian`  
- Dubbing: `Indonesian (Female)`

### Full English Dub
- Subtitle: `English`
- Dubbing: `English (Male)`

5. Select clips and click "RENDER SELECTED"

## Expected Results

| Feature | Expected |
|---------|----------|
| Subtitle position | Top-center, above watermark |
| Subtitle timing | Synced with original speech |
| Dubbing volume | Loud, clear audio |
| Original audio | Very low background |
| 3 words at a time | Word-by-word with highlight |

## Verify Sync

For subtitle sync testing:
1. Compare original speech timing with subtitle appearance
2. Subtitle should appear when speaker says those words
3. Translation should NOT affect timing
