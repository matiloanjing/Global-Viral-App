"""
Quick demo showing the prompt extraction fix
"""

# Example from scenes.json
gemini_visual_prompt = "Man meticulously loading gunpowder into multiple gun barrels, dim light, inside a room, studio ghibli style, anime, watercolor, vivid colors, high contrast, beautiful scenery, miyazaki style, masterpiece, best quality, highly detailed, sharp focus, portrait composition, vertical format"

print("=" * 80)
print("ORIGINAL GEMINI PROMPT (STYLE-FLOODED):")
print("=" * 80)
print(gemini_visual_prompt)
print()

# OLD APPROACH (WRONG - causes repetition)
print("=" * 80)
print("❌ OLD APPROACH (All 4 images look identical):")
print("=" * 80)
old_prompts = [
    f"{gemini_visual_prompt}, dramatic lighting",
    f"{gemini_visual_prompt}, cinematic angle",
    f"{gemini_visual_prompt}, close-up detail",
    f"{gemini_visual_prompt}, wide establishing shot",
]
for i, p in enumerate(old_prompts, 1):
    print(f"Image {i}: {p[:100]}...")
print()

# NEW APPROACH (FIXED - extracts core content)
print("=" * 80)
print("✅ NEW APPROACH (Extract core content, create distinct moments):")
print("=" * 80)

# Extract content before "studio ghibli"
if "studio ghibli" in gemini_visual_prompt.lower():
    core_content = gemini_visual_prompt.split("studio ghibli")[0].strip().rstrip(',')
else:
    parts = [p.strip() for p in gemini_visual_prompt.split(',')]
    core_content = ', '.join(parts[:min(3, len(parts))])

print(f"Extracted Core Content: {core_content}")
print()

# Create 4 progressive prompts
new_prompts = [
    f"{core_content}, dramatic wide angle",
    f"{core_content}, intense medium shot",
    f"{core_content}, extreme close-up detail",
    f"{core_content}, cinematic aftermath shot"
]

print("Generated Prompts (will each get Ghibli style added by animator_v2.py):")
for i, p in enumerate(new_prompts, 1):
    print(f"  Image {i}: {p}")
print()

print("=" * 80)
print(f"Content-to-Style Ratio:")
print(f"  Content words: ~{len(core_content.split())}")
print(f"  Original style words: ~{len(gemini_visual_prompt.split()) - len(core_content.split())}")
print("=" * 80)
