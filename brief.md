Project Specification: "Oplus Clipper" - Production Ready Desktop App
1. Role & Objective
Act as a Senior Python Software Architect. Build a complete, single-file (main.py) desktop application using customtkinter. The app is a video repurposing tool (Opus Clip clone) designed for low-end hardware (4GB RAM).

Core Philosophy:

Heavy Logic in Cloud: Use APIs for Transcription (Groq) and Analysis (Gemini).

Light Logic Locally: Only UI and FFmpeg rendering happen on the laptop.

Robustness: Handle all errors gracefully. Do not assume the user has dependencies installed globally; assume local paths where possible.

2. Tech Stack (Strict)
GUI: customtkinter (Dark mode).

Video Downloader: yt-dlp.

Transcription: groq (Client library). Model: whisper-large-v3.

AI Logic: google-generativeai (Gemini 1.5 Flash).

Translation: deep_translator (GoogleTranslator).

TTS (Dubbing): edge-tts (Must handle asyncio loop correctly within a thread).

Video Editing: ffmpeg-python.

System: threading, os, json, re.

3. Application Workflow & Architecture
The app has one main Window with a sidebar for settings and a main area for the workflow.

A. Initialization & Settings
On startup, check if ffmpeg.exe exists in a ./bin folder or System PATH. If not, show a warning.

Sidebar Settings:

Input fields for Groq API Key and Gemini API Key.

"Save Keys" button (Save to config.json).

Toggle: "Performance Mode" (If ON, download 720p. If OFF, download Best Quality).

B. Phase 1: Analysis (Cloud-First)
User Action: Input YouTube URL -> Click "Analyze".

Backend Process (Threaded):

Step 1: Download Audio Only (m4a/mp3) using yt-dlp to a temp folder.

Step 2 (Transcribe): Send audio to Groq API.

Crucial: Request response_format="verbose_json" to get the full transcript.

Step 3 (AI Agent): Send transcript to Gemini.

Prompt: "Analyze this transcript. Identify 3-5 viral short clips (30-60s). Return strictly valid JSON array."

JSON Structure: [{"start": 10.5, "end": 40.0, "title": "...", "score": 90, "text_segment": "..."}].

Safety: Use a Regex parser to strip Markdown (```json) before parsing.

UI Update: Clear previous results. Populate a Scrollable Frame with "Clip Cards".

C. Phase 2: Selection & Configuration
Each "Clip Card" must have:

Title, Duration, Viral Score (Green/Red color coding).

Checkbox (Selected by default if score > 80).

Global Render Options (Bottom Panel):

Dubbing Language: Dropdown [Original, Indonesian (Male), Indonesian (Female), English (Male), English (Female)].

Watermark: File picker (PNG only). Label shows selected filename.

D. Phase 3: The Rendering Engine (FFmpeg Complex Filter)
When "RENDER SELECTED" is clicked, iterate through selected clips. Use subprocess or ffmpeg-python to construct this EXACT logic:

For Each Clip:

Cut: Trim video from start to end.

Crop: Center crop to 9:16 (w=ih*(9/16):h=ih).

Logic: Dubbing (If Language != Original):

Translate text_segment using deep_translator.

Generate TTS audio (.mp3) using edge-tts.

Audio Ducking: Mix Original Audio (Volume 0.1) + TTS Audio (Volume 1.2).

Logic: Subtitles:

Create a temporary .ass file.

Style: Fontname=Arial, Fontsize=24, PrimaryColour=&H00FFFF00 (Yellow), Outline=2.

Burn subtitles using ass=filename.ass.

Logic: Watermark:

Overlay PNG at Bottom-Right (x=W-w-20:y=H-h-20).

Optimization:

Use -preset ultrafast (Vital for 4GB RAM laptops).

Use -crf 28 (Balance quality/speed).

4. Coding Requirements (Do not hallucinate)
Async Handling: edge-tts is asynchronous. You MUST run it like this inside the thread: asyncio.run(generate_tts(...)).

Path Handling: Use os.path.join for all file paths. Do not hardcode slashes.

Cleanup: Delete temp files (audio, raw video) after rendering to free up disk space.

FFmpeg Check: Explicitly look for bin/ffmpeg.exe if not found globally.

Error Popups: Use messagebox.showerror if API Keys are missing or Download fails.

DELIVERABLE: Write the full main.py code. Provide a requirements.txt content list at the end. Provide a brief guide on folder structure (where to put ffmpeg).