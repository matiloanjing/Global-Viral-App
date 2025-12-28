"""
Kilat Code Clipper - Production Ready Desktop App
A video repurposing tool designed for low-end hardware (4GB RAM)
Heavy Logic in Cloud (Groq + Gemini), Light Logic Locally (UI + FFmpeg)
Optimized for PyInstaller compilation

Licensed software - requires valid license key
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog
import threading
import os
import sys
import json
import re
import subprocess
import shutil
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

# Third-party imports with fallback
try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# License module
try:
    from license import verify_license, check_license_online, activate_license, get_machine_id
    HAS_LICENSE_MODULE = True
except ImportError:
    HAS_LICENSE_MODULE = False

# ⚠️ DEPRECATED: Old animator module (no longer exists, kept for backward compatibility)
# This import will always fail - HAS_ANIMATOR_MODULE will be False
try:
    from animator import (
        GENRES, VISUAL_STYLES, VOICE_OPTIONS,
        generate_restory_script, generate_image_pollinations,
        generate_scene_audio, get_audio_duration, render_2_5d_scene,
        assemble_final_video, generate_assets_parallel, SceneData
    )
    HAS_ANIMATOR_MODULE = True
except ImportError:
    HAS_ANIMATOR_MODULE = False

# Animator v2 module (improved)
try:
    from animator_v2 import generate_animation_v2, GENRES as GENRES_V2, VISUAL_STYLES as STYLES_V2, VOICE_OPTIONS as VOICES_V2, FILTER_EFFECTS, detect_gpu_encoder, set_prodia_api_key, detect_sfx_keywords, mix_audio_with_sfx, SFX_KEYWORDS
    HAS_ANIMATOR_V2 = True
except ImportError:
    HAS_ANIMATOR_V2 = False
    FILTER_EFFECTS = {"None": ""}  # Fallback if import fails

# Character Edit module
try:
    from character_edit import generate_character_edit, HAS_FACE_RECOGNITION
    HAS_CHARACTER_EDIT = True
except ImportError:
    HAS_CHARACTER_EDIT = False
    HAS_FACE_RECOGNITION = False


# ============================================================================
# PYINSTALLER RESOURCE PATH HANDLING
# ============================================================================
def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    if hasattr(sys, '_MEIPASS'):
        # Running as compiled exe
        return os.path.join(sys._MEIPASS, relative_path)
    # Running in development
    return os.path.join(os.path.abspath("."), relative_path)


# Add FFmpeg bin folder to PATH for both dev and compiled exe
os.environ["PATH"] += os.pathsep + resource_path("bin")


# ============================================================================
# CONSTANTS & CONFIGURATION
# ============================================================================
APP_NAME = "Kilat Code Clipper"
APP_VERSION = "1.0.0"
CONFIG_FILE = "config.json"
BIN_FOLDER = "bin"
TEMP_FOLDER = "temp"

# OUTPUT_FOLDER uses absolute path based on app location to work correctly in EXE
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FOLDER = os.path.join(_APP_DIR, "output")  # Final videos saved here

DUBBING_OPTIONS = [
    "Original",  # Keep original audio - Clipper only
    "Indonesian Female",
    "Indonesian Male",
    "English Female",
    "English Male",
    "English UK Female",
    "Japanese Female"
]

# Voice mapping for TTS (must match DUBBING_OPTIONS exactly, except Original)
EDGE_TTS_VOICES = {
    "Indonesian Female": "id-ID-GadisNeural",
    "Indonesian Male": "id-ID-ArdiNeural",
    "English Female": "en-US-JennyNeural",
    "English Male": "en-US-GuyNeural",
    "English UK Female": "en-GB-SoniaNeural",
    "Japanese Female": "ja-JP-NanamiNeural"
}

TRANSLATE_LANGS = {
    "Indonesian Female": "id",
    "Indonesian Male": "id",
    "English Female": "en",
    "English Male": "en",
    "English UK Female": "en",
    "Japanese Female": "ja"
}

VIDEO_FILTER_OPTIONS = [
    "None",
    "Bright Inspire",   # Motivational
    "Dark Terror",      # Horror
    "Fun Pop",          # Comedy
    "Soft Wonder",      # Children's Story
    "Clean Pro",        # Documentary
    "Magic Glow",       # Fairy Tale
    "Cyber Neon",       # Sci-Fi
    "Viral Punch",      # Viral Shorts
    "Meme Chaos",       # Brainrot
]

SUBTITLE_OPTIONS = [
    "Original (No Translation)",
    "Indonesian",
    "English"
]

SUBTITLE_LANGS = {
    "Indonesian": "id",
    "English": "en"
}

# FILTER_EFFECTS is imported from animator_v2 (line 71)
# Contains 10 genre-matched FFmpeg color grading filters:
# None, Bright Inspire, Dark Terror, Fun Pop, Soft Wonder,
# Clean Pro, Magic Glow, Cyber Neon, Viral Punch, Meme Chaos

# ============================================================================
# DATA CLASSES
# ============================================================================
@dataclass
class ClipData:
    """Data class for a single clip"""
    start: float
    end: float
    title: str
    score: int
    text_segment: str
    category: str = "General"
    reason: str = ""
    selected: bool = True
    thumbnail_path: Optional[str] = None
    hook_text: str = ""  # Auto Hook: First 15 words for thumbnail/video overlay


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
def get_config_path() -> str:
    """Get config file path (writable location)"""
    if hasattr(sys, '_MEIPASS'):
        # When running as exe, use executable directory
        return os.path.join(os.path.dirname(sys.executable), CONFIG_FILE)
    return os.path.join(os.path.abspath("."), CONFIG_FILE)


def get_temp_folder() -> str:
    """Get temp folder path (writable location)"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(os.path.dirname(sys.executable), TEMP_FOLDER)
    return os.path.join(os.path.abspath("."), TEMP_FOLDER)


def get_ffmpeg_path() -> Optional[str]:
    """Check for FFmpeg in bin folder (supports PyInstaller)"""
    # Check bundled bin folder first (works for both dev and exe)
    local_ffmpeg = os.path.join(resource_path(BIN_FOLDER), "ffmpeg.exe")
    if os.path.isfile(local_ffmpeg):
        return local_ffmpeg
    
    # Check system PATH
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0:
            return "ffmpeg"
    except FileNotFoundError:
        pass
    
    return None


def get_ffprobe_path() -> Optional[str]:
    """Check for FFprobe in bin folder (supports PyInstaller)"""
    local_ffprobe = os.path.join(resource_path(BIN_FOLDER), "ffprobe.exe")
    if os.path.isfile(local_ffprobe):
        return local_ffprobe
    
    try:
        result = subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0:
            return "ffprobe"
    except FileNotFoundError:
        pass
    
    return None


def load_config() -> Dict[str, Any]:
    """Load configuration from JSON file"""
    config_path = get_config_path()
    if os.path.isfile(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"groq_api_key": "", "gemini_api_key": "", "performance_mode": True}


def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration to JSON file"""
    config_path = get_config_path()
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        return True
    except IOError:
        return False


def ensure_temp_folder() -> str:
    """Create and return temp folder path"""
    temp_path = get_temp_folder()
    os.makedirs(temp_path, exist_ok=True)
    return temp_path


def clean_temp_folder():
    """Clean up temporary files"""
    temp_path = get_temp_folder()
    if os.path.isdir(temp_path):
        try:
            shutil.rmtree(temp_path)
        except Exception:
            pass


def parse_json_from_response(text: str) -> List[Dict]:
    """Parse JSON from AI response, stripping markdown code blocks"""
    # Remove markdown code blocks
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    
    # Try to find JSON array
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []


def format_duration(seconds: float) -> str:
    """Format duration in seconds to MM:SS"""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def get_video_duration(video_path: str, ffprobe_path: str) -> float:
    """Get video duration using FFprobe"""
    try:
        cmd = [
            ffprobe_path, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


# ============================================================================
# ASYNC TTS HELPER
# ============================================================================
async def generate_tts_async(text: str, voice: str, output_path: str) -> bool:
    """Generate TTS audio using edge-tts (async)"""
    if edge_tts is None:
        return False
    try:
        # Slightly faster rate (+5%) for energetic feel, humanize_audio adds tempo variation
        communicate = edge_tts.Communicate(text, voice, rate="+5%")
        await communicate.save(output_path)
        return True
    except Exception as e:
        print(f"TTS Error: {e}")
        return False


def generate_tts(text: str, voice: str, output_path: str, humanize: bool = True) -> bool:
    """Wrapper to run async TTS in thread with optional humanization"""
    result = asyncio.run(generate_tts_async(text, voice, output_path))
    
    # Apply humanization post-processing if enabled
    if result and humanize and os.path.exists(output_path):
        result = humanize_audio(output_path)
    
    return result


def humanize_audio(audio_path: str) -> bool:
    """
    Apply humanization effects to TTS audio to bypass YouTube's mass-produced content detection.
    
    Effects:
    1. Random pitch variation (±3%)
    2. Subtle speed variation (±2%)
    3. Light room reverb
    4. Random EQ signature
    """
    import random
    
    try:
        ffmpeg_path = get_ffmpeg_path()
        
        # Generate random EQ variations for unique audio fingerprint
        # NOTE: Pitch manipulation removed - caused speed issues
        # Edge-TTS outputs 24000Hz, not 48000Hz as previously assumed
        eq_freq = random.randint(150, 400)
        eq_gain = random.uniform(-1.0, 1.0)
        
        # Audio filter chain - reverb + EQ only (proven to work)
        # Still provides unique audio signature for anti-detection
        audio_filter = (
            f"aecho=0.8:0.88:25:0.08,"                      # Light room reverb
            f"equalizer=f={eq_freq}:width_type=h:width=100:gain={eq_gain:.2f},"  # Random EQ
            f"volume=1.0"                                   # Normalize
        )
        
        # Create temp output
        temp_output = audio_path.replace('.mp3', '_humanized.mp3').replace('.wav', '_humanized.wav')
        
        cmd = [
            ffmpeg_path, '-y',
            '-i', audio_path,
            '-af', audio_filter,
            '-c:a', 'libmp3lame',
            '-q:a', '2',
            temp_output
        ]
        
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        if result.returncode == 0 and os.path.exists(temp_output):
            try:
                os.remove(audio_path)
                os.rename(temp_output, audio_path)
                print(f"DEBUG: Clipper audio humanized (EQ: {eq_freq}Hz, gain: {eq_gain:.2f}dB)")
                return True
            except Exception:
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                return True
        else:
            return True  # Original file still usable
            
    except Exception as e:
        print(f"DEBUG: Clipper humanize error: {e}")
        return True  # Original file still usable


# ============================================================================
# ASS SUBTITLE GENERATOR (CapCut Style)
# ============================================================================
def create_ass_subtitle(text: str, start: float, end: float, output_path: str):
    """Create ASS subtitle file with CapCut-style formatting - 3 words at a time"""
    def seconds_to_ass_time(secs: float) -> str:
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = secs % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    
    words = text.split()
    duration = end - start
    
    if not words:
        return
    
    events = []
    
    # Group words into chunks of 3
    chunk_size = 3
    chunks = [words[i:i+chunk_size] for i in range(0, len(words), chunk_size)]
    chunk_duration = duration / len(chunks) if chunks else duration
    
    for chunk_idx, chunk in enumerate(chunks):
        chunk_start_time = chunk_idx * chunk_duration
        word_dur = chunk_duration / len(chunk)
        
        # For each word in the chunk, create a highlight event
        for word_idx, word in enumerate(chunk):
            word_start = chunk_start_time + (word_idx * word_dur)
            word_end = chunk_start_time + ((word_idx + 1) * word_dur)
            
            # Build the line with current word highlighted
            line_text = ""
            for j, w in enumerate(chunk):
                if j == word_idx:
                    line_text += f"{{\\c&H00FFFF&\\b1}}{w}{{\\c&HFFFFFF&\\b0}} "
                else:
                    line_text += f"{w} "
            
            events.append(f"Dialogue: 0,{seconds_to_ass_time(word_start)},{seconds_to_ass_time(word_end)},Default,,0,0,0,,{line_text.strip()}")
    
    ass_content = f"""[Script Info]
Title: GlobalViral Clipper Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,80,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,8,40,40,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)


def create_ass_subtitle_from_segments(
    segments: List[Dict],
    clip_start: float,
    clip_end: float,
    output_path: str,
    translate_to: str = None
):
    """
    Create ASS subtitle file using REAL timestamps from Groq segments.
    This provides Netflix/CapCut-style accurate sync regardless of translation.
    
    segments: List of {'start': float, 'end': float, 'text': str}
    clip_start/end: The clip boundaries in original video time
    translate_to: 'id' or 'en' for translation, None for original
    """
    def seconds_to_ass_time(secs: float) -> str:
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = secs % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    
    # Filter segments that fall within clip boundaries
    clip_segments = []
    for seg in segments:
        seg_start = seg.get('start', 0)
        seg_end = seg.get('end', seg_start + 2)
        
        # Check if segment overlaps with clip
        if seg_end > clip_start and seg_start < clip_end:
            # Adjust timing relative to clip start
            rel_start = max(0, seg_start - clip_start)
            rel_end = min(clip_end - clip_start, seg_end - clip_start)
            text = seg.get('text', '').strip()
            
            if text:
                clip_segments.append({
                    'start': rel_start,
                    'end': rel_end,
                    'text': text
                })
    
    if not clip_segments:
        # Fallback: create simple subtitle
        return
    
    # Translate if needed
    if translate_to and GoogleTranslator is not None:
        try:
            translator = GoogleTranslator(source='auto', target=translate_to)
            for seg in clip_segments:
                seg['text'] = translator.translate(seg['text'])
        except Exception:
            pass  # Keep original if translation fails
    
    events = []
    
    # Create subtitle events - use 3 words at a time with highlight
    for seg in clip_segments:
        words = seg['text'].split()
        seg_duration = seg['end'] - seg['start']
        
        if not words:
            continue
        
        # Group into chunks of 3 words
        chunk_size = 3
        chunks = [words[i:i+chunk_size] for i in range(0, len(words), chunk_size)]
        chunk_duration = seg_duration / len(chunks) if chunks else seg_duration
        
        for chunk_idx, chunk in enumerate(chunks):
            chunk_start = seg['start'] + (chunk_idx * chunk_duration)
            word_dur = chunk_duration / len(chunk)
            
            for word_idx, word in enumerate(chunk):
                word_start = chunk_start + (word_idx * word_dur)
                word_end = chunk_start + ((word_idx + 1) * word_dur)
                
                # Build line with current word highlighted
                line_text = ""
                for j, w in enumerate(chunk):
                    if j == word_idx:
                        line_text += f"{{\\c&H00FFFF&\\b1}}{w}{{\\c&HFFFFFF&\\b0}} "
                    else:
                        line_text += f"{w} "
                
                events.append(f"Dialogue: 0,{seconds_to_ass_time(word_start)},{seconds_to_ass_time(word_end)},Default,,0,0,0,,{line_text.strip()}")
    
    ass_content = f"""[Script Info]
Title: GlobalViral Clipper Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,80,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,8,40,40,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)


# ============================================================================
# CLIP CARD WIDGET (OpusClip-Style Design)
# ============================================================================
class ClipCard(ctk.CTkFrame):
    """Widget for displaying a single clip with OpusClip-style large vertical card"""
    
    # Card dimensions (larger for better visibility)
    CARD_WIDTH = 260
    CARD_HEIGHT = 380
    THUMB_HEIGHT = 280
    
    def __init__(self, parent, clip_data: ClipData, index: int, **kwargs):
        super().__init__(parent, **kwargs)
        self.clip_data = clip_data
        self.index = index
        
        # Card styling - fixed size for grid layout
        self.configure(
            fg_color=("#ffffff", "#1a1a2e"),
            corner_radius=12,
            border_width=2,
            border_color=("#e0e0e0", "#6366F1") if clip_data.selected else ("#e0e0e0", "#3a3a5e"),
            width=self.CARD_WIDTH,
            height=self.CARD_HEIGHT
        )
        self.grid_propagate(False)
        self.pack_propagate(False)
        
        # ======== THUMBNAIL WITH OVERLAYS ========
        self.thumb_container = ctk.CTkFrame(
            self, width=self.CARD_WIDTH - 10, height=self.THUMB_HEIGHT,
            fg_color=("#e0e0e0", "#2a2a4e"),
            corner_radius=10
        )
        self.thumb_container.pack(padx=5, pady=(5, 0))
        self.thumb_container.pack_propagate(False)
        
        # Load thumbnail
        if clip_data.thumbnail_path and os.path.exists(clip_data.thumbnail_path):
            try:
                from PIL import Image
                img = Image.open(clip_data.thumbnail_path)
                # Resize to fill container (crop to 9:16 if needed)
                img = img.resize((self.CARD_WIDTH - 10, self.THUMB_HEIGHT), Image.Resampling.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, 
                                       size=(self.CARD_WIDTH - 10, self.THUMB_HEIGHT))
                self.thumb_label = ctk.CTkLabel(self.thumb_container, image=ctk_img, text="")
                self.thumb_label.place(x=0, y=0, relwidth=1, relheight=1)
            except Exception:
                self._create_placeholder_thumb()
        else:
            self._create_placeholder_thumb()
        
        # Time range badge (top-left overlay)
        duration = clip_data.end - clip_data.start
        time_text = f"{format_duration(clip_data.start)} - {format_duration(clip_data.end)}"
        self.time_badge = ctk.CTkLabel(
            self.thumb_container, text=time_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#000000", text_color="white",
            corner_radius=4, padx=6, pady=2
        )
        self.time_badge.place(x=5, y=5)
        
        # Score badge (top-right overlay)
        score_color = "#10B981" if clip_data.score >= 80 else ("#F59E0B" if clip_data.score >= 60 else "#EF4444")
        self.score_badge = ctk.CTkLabel(
            self.thumb_container, text=f"🔥 {clip_data.score}",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=score_color, text_color="white",
            corner_radius=4, padx=6, pady=2
        )
        self.score_badge.place(relx=1.0, x=-5, y=5, anchor="ne")
        
        # Hook text overlay (bottom of thumbnail) - THE KEY FEATURE
        if clip_data.hook_text:
            hook_display = clip_data.hook_text[:60] + "..." if len(clip_data.hook_text) > 60 else clip_data.hook_text
            self.hook_frame = ctk.CTkFrame(
                self.thumb_container, fg_color="#000000", corner_radius=6,
                bg_color="transparent"
            )
            self.hook_frame.place(relx=0.5, rely=1.0, y=-8, anchor="s", relwidth=0.95)
            
            self.hook_label = ctk.CTkLabel(
                self.hook_frame, text=f'"{hook_display}"',
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="white", wraplength=self.CARD_WIDTH - 30,
                justify="center"
            )
            self.hook_label.pack(padx=8, pady=6)
        
        # ======== CHECKBOX (top-right of card) ========
        self.selected_var = ctk.BooleanVar(value=clip_data.selected)
        self.checkbox = ctk.CTkCheckBox(
            self.thumb_container, text="",
            variable=self.selected_var,
            command=self._on_selection_change,
            checkbox_width=22, checkbox_height=22,
            fg_color="#6366F1", hover_color="#818CF8",
            border_color="white", border_width=2
        )
        self.checkbox.place(relx=1.0, rely=1.0, x=-8, y=-8, anchor="se")
        
        # ======== TITLE & INFO SECTION (below thumbnail) ========
        self.info_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.info_frame.pack(fill="x", padx=8, pady=(8, 5))
        
        # Category badge
        category_colors = {
            "Funny": "#FFD700", "Educational": "#00BFFF", 
            "Controversial": "#FF6B6B", "Inspiring": "#90EE90",
            "Action": "#FF6B6B", "Emotional": "#FF69B4",
            "Aesthetic": "#9B59B6", "Motivational": "#10B981", "General": "#888888"
        }
        cat_color = category_colors.get(clip_data.category, "#888888")
        
        self.cat_label = ctk.CTkLabel(
            self.info_frame, text=f"📌 {clip_data.category}",
            font=ctk.CTkFont(size=10, weight="bold"), text_color=cat_color
        )
        self.cat_label.pack(anchor="w")
        
        # Title (truncated)
        title_text = clip_data.title[:35] + "..." if len(clip_data.title) > 35 else clip_data.title
        self.title_label = ctk.CTkLabel(
            self.info_frame, text=title_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("black", "white"),
            anchor="w", wraplength=self.CARD_WIDTH - 20
        )
        self.title_label.pack(anchor="w", pady=(2, 0))
        
        # Duration
        self.duration_label = ctk.CTkLabel(
            self.info_frame, text=f"⏱ {format_duration(duration)}",
            font=ctk.CTkFont(size=10), text_color="#888888"
        )
        self.duration_label.pack(anchor="w")
    
    def _create_placeholder_thumb(self):
        """Create placeholder when no thumbnail available"""
        self.thumb_label = ctk.CTkLabel(
            self.thumb_container, text="🎬\nNo Preview",
            font=ctk.CTkFont(size=32),
            text_color="#666666"
        )
        self.thumb_label.place(relx=0.5, rely=0.5, anchor="center")
    
    def _on_selection_change(self):
        self.clip_data.selected = self.selected_var.get()
        # Update border color based on selection
        border_color = ("#e0e0e0", "#6366F1") if self.clip_data.selected else ("#e0e0e0", "#3a3a5e")
        self.configure(border_color=border_color)
    
    def is_selected(self) -> bool:
        return self.selected_var.get()


# ============================================================================
# LICENSE ACTIVATION DIALOG
# ============================================================================
class LicenseDialog(ctk.CTkToplevel):
    """License activation dialog window"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.title("⚡ Kilat Code Clipper - License Activation")
        self.geometry("500x350")
        self.resizable(False, False)
        
        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 350) // 2
        self.geometry(f"+{x}+{y}")
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        self.activated = False
        self._create_widgets()
    
    def _create_widgets(self):
        # Logo
        logo_label = ctk.CTkLabel(
            self, text="⚡ Kilat Code Clipper",
            font=ctk.CTkFont(size=28, weight="bold")
        )
        logo_label.pack(pady=(30, 5))
        
        sub_label = ctk.CTkLabel(
            self, text="Professional Video Clipper",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        sub_label.pack(pady=(0, 30))
        
        # License key entry
        key_label = ctk.CTkLabel(
            self, text="Enter License Key:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        key_label.pack(pady=(10, 5))
        
        self.key_entry = ctk.CTkEntry(
            self, width=350, height=45,
            placeholder_text="XXXX-XXXX-XXXX-XXXX",
            font=ctk.CTkFont(size=16)
        )
        self.key_entry.pack(pady=10)
        
        # Status label
        self.status_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.status_label.pack(pady=5)
        
        # Activate button
        self.activate_btn = ctk.CTkButton(
            self, text="🔓 Activate License",
            command=self._activate,
            width=200, height=45,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#00D4FF",
            hover_color="#00A0CC"
        )
        self.activate_btn.pack(pady=20)
        
        # Exit button
        exit_btn = ctk.CTkButton(
            self, text="Exit",
            command=self._exit,
            width=100, height=30,
            fg_color="transparent",
            text_color="gray",
            hover_color="#333333"
        )
        exit_btn.pack(pady=5)
    
    def _activate(self):
        license_key = self.key_entry.get().strip().upper()
        
        if not license_key:
            self.status_label.configure(text="⚠️ Please enter a license key", text_color="orange")
            return
        
        self.activate_btn.configure(state="disabled", text="Checking...")
        self.status_label.configure(text="Verifying license...", text_color="gray")
        self.update()
        
        # Check license
        if HAS_LICENSE_MODULE:
            valid, message, _ = check_license_online(license_key)
            
            if valid:
                # Activate
                success, act_message = activate_license(license_key)
                if success:
                    self.status_label.configure(text="✅ " + act_message, text_color="green")
                    self.activated = True
                    self.after(1500, self.destroy)
                else:
                    self.status_label.configure(text="❌ " + act_message, text_color="red")
            else:
                self.status_label.configure(text="❌ " + message, text_color="red")
        else:
            self.status_label.configure(text="❌ License module not available", text_color="red")
        
        self.activate_btn.configure(state="normal", text="🔓 Activate License")
    
    def _exit(self):
        self.activated = False
        self.destroy()


# ============================================================================
# MAIN APPLICATION
# ============================================================================
class KilatCodeClipperApp(ctk.CTk):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        
        # Configure appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Window setup
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1200x800")
        self.minsize(1000, 700)
        
        # State variables
        self.config = load_config()
        self.ffmpeg_path = get_ffmpeg_path()
        self.ffprobe_path = get_ffprobe_path()
        self.clips: List[ClipData] = []
        self.clip_cards: List[ClipCard] = []
        self.video_path: Optional[str] = None
        self.video_url: Optional[str] = None
        self.transcript: Optional[str] = None
        self.transcript_segments: List[Dict] = []  # Raw segments with timestamps
        self.watermark_path: Optional[str] = None
        self.animator_watermark_path: Optional[str] = None  # Animator tab watermark
        self.is_processing = False
        
        # Build UI
        self._create_layout()
        self._check_dependencies()
    
    def _create_layout(self):
        """Create the main application layout - FULLSCREEN (no sidebar)"""
        # Configure grid for fullscreen
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # Status bar
        self.grid_rowconfigure(1, weight=1)  # Main content
        
        # Status bar at top
        self._create_status_bar()
        
        # Compatibility: create sidebar variables without displaying
        self._create_sidebar_compat()
        
        # Main content area (fullscreen tabs)
        self._create_main_content()
    
    def _create_status_bar(self):
        """Create the top status bar with logo and status indicators"""
        self.status_bar = ctk.CTkFrame(self, height=50, corner_radius=0, fg_color="#1a1a2e")
        self.status_bar.grid(row=0, column=0, sticky="ew")
        self.status_bar.grid_propagate(False)
        
        # Left side: Logo
        self.logo_frame = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        self.logo_frame.pack(side="left", padx=20, pady=10)
        
        self.logo_label = ctk.CTkLabel(
            self.logo_frame, text="⚡ Kilat Code Clipper",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#00D4FF"
        )
        self.logo_label.pack(side="left")
        
        self.version_label = ctk.CTkLabel(
            self.logo_frame, text=f"  v{APP_VERSION}",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.version_label.pack(side="left")
        
        # Right side: Status indicators
        self.status_frame = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        self.status_frame.pack(side="right", padx=20, pady=10)
        
        # Licensed status
        license_ok = self._check_license_status()
        license_status = "✅ Licensed" if license_ok else "⚠️ Unlicensed"
        license_color = "#10B981" if license_ok else "#F59E0B"
        self.license_indicator = ctk.CTkLabel(
            self.status_frame, text=license_status,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=license_color
        )
        self.license_indicator.pack(side="left", padx=10)
        
        # FFmpeg status
        ffmpeg_ok = self.ffmpeg_path and os.path.exists(self.ffmpeg_path)
        ffmpeg_status = "✅ FFmpeg" if ffmpeg_ok else "❌ FFmpeg"
        ffmpeg_color = "#10B981" if ffmpeg_ok else "#EF4444"
        self.ffmpeg_indicator = ctk.CTkLabel(
            self.status_frame, text=ffmpeg_status,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ffmpeg_color
        )
        self.ffmpeg_indicator.pack(side="left", padx=10)
    
    def _check_license_status(self):
        """Check if license is valid"""
        if HAS_LICENSE_MODULE:
            try:
                valid, message = verify_license()  # Returns (bool, str)
                print(f"DEBUG: License check: {valid} - {message}")
                return valid
            except Exception as e:
                print(f"DEBUG: License check error: {e}")
                return False
        return True  # No license module = always valid
    
    def _create_sidebar_compat(self):
        """Create sidebar variables for backward compatibility (sidebar hidden)"""
        # These variables may be referenced by other methods
        self.perf_mode_var = ctk.BooleanVar(value=self.config.get("performance_mode", True))
        
        # Min/max clips defaults (can be overridden in Clipper tab settings)
        self.min_clips_value = 3
        self.max_clips_value = 8
        
        # Filter combo will be created in Clipper tab
        # Groq/Gemini entries will be created in API Settings tab
    
    def _create_sidebar(self):
        """DEPRECATED: Original sidebar - kept for reference but not displayed\"\"\""""
        # This method is no longer called - layout is now fullscreen
        pass
    
    def _create_sidebar_original(self):
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        
        # Logo/Title
        self.logo_label = ctk.CTkLabel(
            self.sidebar, text="⚡ Kilat Code",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        self.logo_label.pack(pady=(20, 0))
        
        self.logo_sub = ctk.CTkLabel(
            self.sidebar, text="Clipper",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#00D4FF"
        )
        self.logo_sub.pack(pady=(0, 5))
        
        self.version_label = ctk.CTkLabel(
            self.sidebar, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.version_label.pack(pady=(0, 20))
        
        # Settings section
        self.settings_label = ctk.CTkLabel(
            self.sidebar, text="⚙️ API Settings",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.settings_label.pack(pady=(10, 10), padx=20, anchor="w")
        
        # Groq API Key
        self.groq_label = ctk.CTkLabel(self.sidebar, text="Groq API Key:", anchor="w")
        self.groq_label.pack(pady=(5, 2), padx=20, anchor="w")
        self.groq_entry = ctk.CTkEntry(self.sidebar, width=240, show="•")
        self.groq_entry.pack(pady=(0, 10), padx=20)
        self.groq_entry.insert(0, self.config.get("groq_api_key", ""))
        
        # Gemini API Key
        self.gemini_label = ctk.CTkLabel(self.sidebar, text="Gemini API Key:", anchor="w")
        self.gemini_label.pack(pady=(5, 2), padx=20, anchor="w")
        self.gemini_entry = ctk.CTkEntry(self.sidebar, width=240, show="•")
        self.gemini_entry.pack(pady=(0, 10), padx=20)
        self.gemini_entry.insert(0, self.config.get("gemini_api_key", ""))
        
        # Save Keys Button
        self.save_keys_btn = ctk.CTkButton(
            self.sidebar, text="💾 Save Keys",
            command=self._save_keys, width=240
        )
        self.save_keys_btn.pack(pady=(5, 20), padx=20)
        
        # Performance Mode Toggle
        self.perf_mode_var = ctk.BooleanVar(value=self.config.get("performance_mode", True))
        self.perf_mode_switch = ctk.CTkSwitch(
            self.sidebar, text="Performance Mode (720p)",
            variable=self.perf_mode_var,
            command=self._on_perf_mode_change
        )
        self.perf_mode_switch.pack(pady=(10, 5), padx=20, anchor="w")
        
        self.perf_mode_info = ctk.CTkLabel(
            self.sidebar,
            text="ON: Faster (720p)\nOFF: Best Quality",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            justify="left"
        )
        self.perf_mode_info.pack(pady=(0, 10), padx=20, anchor="w")
        
        # Clip Settings Section
        self.clip_settings_label = ctk.CTkLabel(
            self.sidebar, text="🎬 Clip Settings",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.clip_settings_label.pack(pady=(10, 5), padx=20, anchor="w")
        
        # Min Clips Slider
        self.min_clips_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.min_clips_frame.pack(fill="x", padx=20)
        
        self.min_clips_label = ctk.CTkLabel(
            self.min_clips_frame, text="Min Clips:",
            font=ctk.CTkFont(size=12), width=70, anchor="w"
        )
        self.min_clips_label.pack(side="left")
        
        self.min_clips_var = ctk.IntVar(value=self.config.get("min_clips", 5))
        self.min_clips_slider = ctk.CTkSlider(
            self.min_clips_frame, from_=3, to=10,
            variable=self.min_clips_var, width=120,
            command=self._on_min_clips_change
        )
        self.min_clips_slider.pack(side="left", padx=5)
        
        self.min_clips_value = ctk.CTkLabel(
            self.min_clips_frame, text="5",
            font=ctk.CTkFont(size=12, weight="bold"), width=30
        )
        self.min_clips_value.pack(side="left")
        
        # Max Clips Slider
        self.max_clips_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.max_clips_frame.pack(fill="x", padx=20, pady=(5, 10))
        
        self.max_clips_label = ctk.CTkLabel(
            self.max_clips_frame, text="Max Clips:",
            font=ctk.CTkFont(size=12), width=70, anchor="w"
        )
        self.max_clips_label.pack(side="left")
        
        self.max_clips_var = ctk.IntVar(value=self.config.get("max_clips", 15))
        self.max_clips_slider = ctk.CTkSlider(
            self.max_clips_frame, from_=5, to=20,
            variable=self.max_clips_var, width=120,
            command=self._on_max_clips_change
        )
        self.max_clips_slider.pack(side="left", padx=5)
        
        self.max_clips_value = ctk.CTkLabel(
            self.max_clips_frame, text="15",
            font=ctk.CTkFont(size=12, weight="bold"), width=30
        )
        self.max_clips_value.pack(side="left")
        
        # FFmpeg Status
        self.ffmpeg_status_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.ffmpeg_status_frame.pack(pady=(10, 10), padx=20, fill="x")
        
        status_text = "✅ FFmpeg Ready" if self.ffmpeg_path else "❌ FFmpeg Missing"
        status_color = "#00FF00" if self.ffmpeg_path else "#FF4444"
        self.ffmpeg_status = ctk.CTkLabel(
            self.ffmpeg_status_frame, text=status_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=status_color
        )
        self.ffmpeg_status.pack(anchor="w")
        
        # Video Filter Dropdown
        self.filter_label = ctk.CTkLabel(
            self.sidebar, text="🎨 Video Filter:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.filter_label.pack(pady=(20, 5), padx=20, anchor="w")
        
        self.filter_combo = ctk.CTkComboBox(
            self.sidebar, values=VIDEO_FILTER_OPTIONS,
            width=240, state="readonly"
        )
        self.filter_combo.set("None")
        self.filter_combo.pack(pady=(0, 20), padx=20)
        
        # Spacer
        self.sidebar.pack_propagate(False)
    
    def _create_main_content(self):
        """Create the main content area with TabView - FULLSCREEN"""
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)  # Row 1 (below status bar)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
        
        # ======== TABVIEW ========
        self.tabview = ctk.CTkTabview(
            self.main_frame,
            corner_radius=12,
            segmented_button_fg_color=("#e0e0e0", "#1a1a2e"),
            segmented_button_selected_color="#6366F1",
            segmented_button_selected_hover_color="#4F46E5"
        )
        self.tabview.grid(row=0, column=0, sticky="nsew")
        
        # Add all tabs
        self.tab_clipper = self.tabview.add("🎬 Viral Clipper")
        self.tab_character = self.tabview.add("🎭 Character Edit")
        self.tab_animator = self.tabview.add("✨ AI Animator")
        self.tab_api_settings = self.tabview.add("🔑 API Settings")
        self.tab_docs = self.tabview.add("📚 Docs")
        
        # No sidebar toggle needed - fullscreen layout
        
        # Configure tab content - Clipper has 4 rows: Header, Label, Clips (expand), Bottom
        self.tab_clipper.grid_columnconfigure(0, weight=1)
        self.tab_clipper.grid_rowconfigure(2, weight=3)  # Clips grid gets most space
        
        self.tab_animator.grid_columnconfigure(0, weight=1)
        self.tab_animator.grid_rowconfigure(1, weight=1)
        
        self.tab_api_settings.grid_columnconfigure(0, weight=1)
        self.tab_api_settings.grid_rowconfigure(0, weight=1)
        
        self.tab_docs.grid_columnconfigure(0, weight=1)
        self.tab_docs.grid_rowconfigure(0, weight=1)
        
        # ======== TAB 1: CLIPPER CONTENT ========
        self._create_clipper_tab_content()
        
        # ======== TAB 2: CHARACTER EDIT CONTENT ========
        self._create_character_edit_tab_content()
        
        # ======== TAB 3: ANIMATOR CONTENT ========
        self._create_animator_tab_content()
        
        # ======== TAB 4: API SETTINGS CONTENT ========
        self._create_api_settings_tab_content()
        
        # ======== TAB 5: DOCS CONTENT ========
        self._create_docs_tab_content()
    
    def _on_tab_change(self):
        """DEPRECATED: Tab change callback - no longer needed with fullscreen layout"""
        # Sidebar has been removed, this function is kept for backward compatibility
        # Previously toggled sidebar widget visibility based on active tab
        pass
    
    def _create_clipper_tab_content(self):
        """Create content for Clipper tab - OpusClip-style layout"""
        # Row 0: URL + Settings Header
        self._create_url_header_section()
        
        # Row 1: Clips label
        # Row 2: Clips Display (full expansion)
        self._create_clips_section()
        
        # Row 3: Bottom Panel (Debug Console + Render Controls side by side)
        self._create_bottom_panel()
    
    def _create_url_header_section(self):
        """Create the URL + Settings header section (compact 2-row design)"""
        self.header_frame = ctk.CTkFrame(self.tab_clipper, fg_color="#1a1a2e", corner_radius=12)
        self.header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        
        # ===== Row 0: URL Input + Analyze =====
        self.url_row = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.url_row.pack(fill="x", padx=10, pady=(8, 4))
        self.url_row.grid_columnconfigure(1, weight=1)
        
        self.url_label = ctk.CTkLabel(
            self.url_row, text="🎬 YouTube URL:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.url_label.grid(row=0, column=0, padx=(5, 8))
        
        self.url_entry = ctk.CTkEntry(
            self.url_row,
            placeholder_text="https://www.youtube.com/watch?v=...",
            height=32
        )
        self.url_entry.grid(row=0, column=1, padx=5, sticky="ew")
        
        self.analyze_btn = ctk.CTkButton(
            self.url_row, text="🔍 Analyze",
            command=self._start_analysis,
            width=100, height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#6366F1", hover_color="#4F46E5"
        )
        self.analyze_btn.grid(row=0, column=2, padx=(8, 5))
        
        # ===== Row 1: Settings (Performance, Min/Max, Filter) =====
        self.settings_row = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.settings_row.pack(fill="x", padx=10, pady=(0, 8))
        
        # Performance Mode
        self.perf_mode_switch = ctk.CTkSwitch(
            self.settings_row, text="⚡720p",
            variable=self.perf_mode_var,
            command=self._on_perf_mode_change,
            font=ctk.CTkFont(size=11),
            width=50, progress_color="#6366F1"
        )
        self.perf_mode_switch.pack(side="left", padx=(0, 15))
        
        # Min Clips
        ctk.CTkLabel(self.settings_row, text="Min:", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(side="left")
        self.min_clips_var = ctk.IntVar(value=self.config.get("min_clips", 5))
        self.min_clips_slider = ctk.CTkSlider(
            self.settings_row, from_=3, to=10, variable=self.min_clips_var, width=80,
            command=self._on_min_clips_change, progress_color="#6366F1", button_color="#6366F1"
        )
        self.min_clips_slider.pack(side="left", padx=3)
        self.min_clips_value = ctk.CTkLabel(self.settings_row, text=str(self.min_clips_var.get()), 
                                            font=ctk.CTkFont(size=11, weight="bold"), text_color="#6366F1", width=20)
        self.min_clips_value.pack(side="left", padx=(0, 10))
        
        # Max Clips
        ctk.CTkLabel(self.settings_row, text="Max:", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(side="left")
        self.max_clips_var = ctk.IntVar(value=self.config.get("max_clips", 15))
        self.max_clips_slider = ctk.CTkSlider(
            self.settings_row, from_=5, to=20, variable=self.max_clips_var, width=80,
            command=self._on_max_clips_change, progress_color="#6366F1", button_color="#6366F1"
        )
        self.max_clips_slider.pack(side="left", padx=3)
        self.max_clips_value = ctk.CTkLabel(self.settings_row, text=str(self.max_clips_var.get()),
                                            font=ctk.CTkFont(size=11, weight="bold"), text_color="#6366F1", width=20)
        self.max_clips_value.pack(side="left", padx=(0, 15))
        
        # Video Filter
        ctk.CTkLabel(self.settings_row, text="🎨 Filter:", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(side="left")
        self.filter_combo = ctk.CTkComboBox(
            self.settings_row, values=VIDEO_FILTER_OPTIONS,
            width=140, height=26, state="readonly", font=ctk.CTkFont(size=11)
        )
        self.filter_combo.set("None")
        self.filter_combo.pack(side="left", padx=5)
    
    def _create_clips_section(self):
        """Create the clips display section"""
        self.clips_label = ctk.CTkLabel(
            self.tab_clipper, text="📋 Detected Viral Clips",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        self.clips_label.grid(row=1, column=0, sticky="w", pady=(10, 5))
        
        self.clips_scroll = ctk.CTkScrollableFrame(self.tab_clipper, height=500)
        self.clips_scroll.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        self.clips_scroll.grid_columnconfigure(0, weight=1)
        
        # Placeholder text
        self.no_clips_label = ctk.CTkLabel(
            self.clips_scroll,
            text="🎯 Enter a YouTube URL and click Analyze to find viral clips",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        self.no_clips_label.grid(row=0, column=0, pady=50)
    
    def _create_bottom_panel(self):
        """Create the bottom panel with Debug Console (left) + Render Controls (right)"""
        SURFACE_DARKER = "#111111"
        
        self.bottom_frame = ctk.CTkFrame(self.tab_clipper, fg_color="#1a1a2e", corner_radius=10)
        self.bottom_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.bottom_frame.grid_columnconfigure(0, weight=3)  # Debug console gets more space
        self.bottom_frame.grid_columnconfigure(1, weight=2)  # Render controls
        
        # ========== LEFT: Debug Console ==========
        self.debug_section = ctk.CTkFrame(self.bottom_frame, fg_color="transparent")
        self.debug_section.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=8)
        
        ctk.CTkLabel(
            self.debug_section, text="📋 Console",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="white"
        ).pack(anchor="w", pady=(0, 4))
        
        self.clipper_log = ctk.CTkTextbox(
            self.debug_section, height=80,
            fg_color=SURFACE_DARKER, corner_radius=6,
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#94a3b8"
        )
        self.clipper_log.pack(fill="both", expand=True)
        self.clipper_log.insert("1.0", "[Ready] Enter URL and click Analyze\n")
        self.clipper_log.configure(state="disabled")
        
        # ========== RIGHT: Render Controls ==========
        self.render_section = ctk.CTkFrame(self.bottom_frame, fg_color="transparent")
        self.render_section.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=8)
        
        # Row 0: Subtitle + Dubbing
        render_row0 = ctk.CTkFrame(self.render_section, fg_color="transparent")
        render_row0.pack(fill="x", pady=(0, 4))
        
        ctk.CTkLabel(render_row0, text="💬", font=ctk.CTkFont(size=11)).pack(side="left")
        self.sub_combo = ctk.CTkComboBox(
            render_row0, values=SUBTITLE_OPTIONS, width=130, height=26,
            state="readonly", font=ctk.CTkFont(size=10)
        )
        self.sub_combo.set("Original (No Translation)")
        self.sub_combo.pack(side="left", padx=(3, 8))
        
        ctk.CTkLabel(render_row0, text="🎙️", font=ctk.CTkFont(size=11)).pack(side="left")
        self.dub_combo = ctk.CTkComboBox(
            render_row0, values=DUBBING_OPTIONS, width=120, height=26,
            state="readonly", font=ctk.CTkFont(size=10)
        )
        self.dub_combo.set("Original")
        self.dub_combo.pack(side="left", padx=3)
        
        # Row 1: Watermark + Render Button
        render_row1 = ctk.CTkFrame(self.render_section, fg_color="transparent")
        render_row1.pack(fill="x", pady=(4, 0))
        
        ctk.CTkLabel(render_row1, text="🖼️", font=ctk.CTkFont(size=11)).pack(side="left")
        self.wm_filename_label = ctk.CTkLabel(
            render_row1, text="None", font=ctk.CTkFont(size=10), text_color="gray", width=60
        )
        self.wm_filename_label.pack(side="left", padx=3)
        
        self.wm_btn = ctk.CTkButton(
            render_row1, text="Browse", command=self._browse_watermark,
            width=50, height=24, font=ctk.CTkFont(size=10)
        )
        self.wm_btn.pack(side="left", padx=(3, 15))
        
        self.render_btn = ctk.CTkButton(
            render_row1, text="🚀 RENDER",
            command=self._start_render,
            width=100, height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#10B981", hover_color="#059669"
        )
        self.render_btn.pack(side="right")
        
        # Progress bar (full width at bottom)
        self.progress_bar = ctk.CTkProgressBar(self.bottom_frame, height=6)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 5))
        self.progress_bar.set(0)
    
    def _log_clipper(self, message: str):
        """Append message to Clipper debug log"""
        def update():
            self.clipper_log.configure(state="normal")
            self.clipper_log.insert("end", f"{message}\n")
            self.clipper_log.see("end")
            self.clipper_log.configure(state="disabled")
        self.after(0, update)
    
    def _create_character_edit_tab_content(self):
        """Create content for Character Edit tab - Create character-focused highlight reels"""
        
        # Color scheme (matching Obsidian theme)
        BG_DARK = "#0F0F0F"
        SURFACE = "#1C1C1C"
        INPUT_BG = "#2A2A2A"
        PRIMARY = "#8B5CF6"  # Purple for Character Edit
        
        # Configure tab grid
        self.tab_character.grid_columnconfigure(0, weight=1)
        self.tab_character.grid_rowconfigure(1, weight=1)
        
        # Main container
        main_container = ctk.CTkFrame(self.tab_character, fg_color=BG_DARK, corner_radius=0)
        main_container.pack(fill="both", expand=True, padx=0, pady=0)
        
        # Scrollable content
        scroll_container = ctk.CTkScrollableFrame(main_container, fg_color=BG_DARK, corner_radius=0)
        scroll_container.pack(fill="both", expand=True, padx=20, pady=15)
        
        # ======== MAIN CARD ========
        main_card = ctk.CTkFrame(scroll_container, fg_color=SURFACE, corner_radius=16)
        main_card.pack(fill="x", pady=(0, 15))
        
        # Header bar
        gradient_bar = ctk.CTkFrame(main_card, height=4, fg_color=PRIMARY, corner_radius=0)
        gradient_bar.pack(fill="x", side="top")
        
        card_content = ctk.CTkFrame(main_card, fg_color=SURFACE, corner_radius=0)
        card_content.pack(fill="x", padx=25, pady=25)
        
        # ======== HEADER ========
        header_frame = ctk.CTkFrame(card_content, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_row.pack(fill="x")
        
        ctk.CTkLabel(title_row, text="🎭", font=ctk.CTkFont(size=28)).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(title_row, text="Character Edit", font=ctk.CTkFont(size=24, weight="bold"), text_color="white").pack(side="left")
        
        # Face recognition status
        fr_status = "✅ Face Detection Ready" if HAS_FACE_RECOGNITION else "⚠️ Face Detection Unavailable (Transcript Mode)"
        fr_color = "#10B981" if HAS_FACE_RECOGNITION else "#F59E0B"
        ctk.CTkLabel(title_row, text=fr_status, font=ctk.CTkFont(size=11), text_color=fr_color).pack(side="right")
        
        ctk.CTkLabel(
            header_frame,
            text="Create character-focused highlight reels from films and videos. AI detects and compiles best moments of your chosen character.",
            font=ctk.CTkFont(size=12), text_color="#94a3b8"
        ).pack(anchor="w", pady=(8, 0))
        
        # ======== VIDEO INPUT SECTION ========
        input_section = ctk.CTkFrame(card_content, fg_color="transparent")
        input_section.pack(fill="x", pady=(15, 20))
        
        ctk.CTkLabel(input_section, text="Video Source", font=ctk.CTkFont(size=13, weight="bold"), text_color="#e2e8f0").pack(anchor="w", pady=(0, 8))
        
        input_row = ctk.CTkFrame(input_section, fg_color="transparent")
        input_row.pack(fill="x")
        input_row.grid_columnconfigure(0, weight=1)
        
        url_input_frame = ctk.CTkFrame(input_row, fg_color=INPUT_BG, corner_radius=12, height=50)
        url_input_frame.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        url_input_frame.pack_propagate(False)
        
        ctk.CTkLabel(url_input_frame, text="🔗", font=ctk.CTkFont(size=16)).pack(side="left", padx=(15, 0))
        
        self.char_url_entry = ctk.CTkEntry(
            url_input_frame, placeholder_text="YouTube URL or local video path...",
            font=ctk.CTkFont(size=13), fg_color="transparent", border_width=0, text_color="white"
        )
        self.char_url_entry.pack(side="left", fill="both", expand=True, padx=10)
        
        self.char_browse_btn = ctk.CTkButton(
            input_row, text="📂 Browse", width=100, height=50,
            font=ctk.CTkFont(size=12, weight="bold"), fg_color="#374151", hover_color="#4b5563",
            corner_radius=12, command=self._browse_char_video
        )
        self.char_browse_btn.grid(row=0, column=1)
        
        # ======== SETTINGS GRID ========
        settings_grid = ctk.CTkFrame(card_content, fg_color="transparent")
        settings_grid.pack(fill="x", pady=(10, 20))
        settings_grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="col")
        
        # --- Column 1: Character ---
        col1 = ctk.CTkFrame(settings_grid, fg_color="transparent")
        col1.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        ctk.CTkLabel(col1, text="🎭 CHARACTER", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b").pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(col1, text="Character Name (optional)", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(0, 4))
        self.char_name_entry = ctk.CTkEntry(
            col1, placeholder_text="Leave empty for auto-detect", width=180, height=35,
            fg_color=INPUT_BG, border_color="#374151", font=ctk.CTkFont(size=12)
        )
        self.char_name_entry.pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(col1, text="Transition Effect", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(0, 4))
        self.char_transition_combo = ctk.CTkComboBox(
            col1, values=["Random", "Cut", "Shake", "Zoom", "Flash"], width=180, height=35,
            fg_color=INPUT_BG, border_color="#374151", button_color="#374151",
            dropdown_fg_color=INPUT_BG, dropdown_hover_color="#374151",
            state="readonly", font=ctk.CTkFont(size=12)
        )
        self.char_transition_combo.set("Random")
        self.char_transition_combo.pack(anchor="w")
        
        # --- Column 2: Duration & Moments ---
        col2 = ctk.CTkFrame(settings_grid, fg_color="transparent")
        col2.grid(row=0, column=1, sticky="nsew", padx=10)
        
        ctk.CTkLabel(col2, text="⏱️ TIMING", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b").pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(col2, text="Target Duration", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(0, 4))
        self.char_duration_combo = ctk.CTkComboBox(
            col2, values=["30 seconds", "45 seconds", "60 seconds"], width=180, height=35,
            fg_color=INPUT_BG, border_color="#374151", button_color="#374151",
            dropdown_fg_color=INPUT_BG, dropdown_hover_color="#374151",
            state="readonly", font=ctk.CTkFont(size=12)
        )
        self.char_duration_combo.set("30 seconds")
        self.char_duration_combo.pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(col2, text="Number of Moments", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(0, 4))
        
        moments_frame = ctk.CTkFrame(col2, fg_color="transparent")
        moments_frame.pack(anchor="w")
        
        self.char_moments_var = ctk.IntVar(value=5)
        self.char_moments_slider = ctk.CTkSlider(
            moments_frame, from_=3, to=10, variable=self.char_moments_var, width=130,
            progress_color=PRIMARY, button_color=PRIMARY, command=self._on_char_moments_change
        )
        self.char_moments_slider.pack(side="left")
        self.char_moments_label = ctk.CTkLabel(moments_frame, text="5", font=ctk.CTkFont(size=12, weight="bold"), text_color=PRIMARY, width=30)
        self.char_moments_label.pack(side="left", padx=5)
        
        # --- Column 3: Effects ---
        col3 = ctk.CTkFrame(settings_grid, fg_color="transparent")
        col3.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        
        ctk.CTkLabel(col3, text="🎨 EFFECTS", font=ctk.CTkFont(size=10, weight="bold"), text_color="#64748b").pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(col3, text="Video Filter", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(0, 4))
        filter_options = list(FILTER_EFFECTS.keys()) if HAS_ANIMATOR_V2 else ["None", "Dark Terror", "Bright Inspire", "Viral Punch"]
        self.char_filter_combo = ctk.CTkComboBox(
            col3, values=filter_options, width=180, height=35,
            fg_color=INPUT_BG, border_color="#374151", button_color="#374151",
            dropdown_fg_color=INPUT_BG, dropdown_hover_color="#374151",
            state="readonly", font=ctk.CTkFont(size=12)
        )
        self.char_filter_combo.set("None")
        self.char_filter_combo.pack(anchor="w", pady=(0, 12))
        
        # Watermark
        wm_frame = ctk.CTkFrame(col3, fg_color="transparent")
        wm_frame.pack(anchor="w")
        
        ctk.CTkLabel(wm_frame, text="🖼️ Watermark:", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(side="left")
        self.char_wm_label = ctk.CTkLabel(wm_frame, text="None", font=ctk.CTkFont(size=10), text_color="gray", width=60)
        self.char_wm_label.pack(side="left", padx=5)
        self.char_wm_btn = ctk.CTkButton(
            wm_frame, text="Browse", width=60, height=25, font=ctk.CTkFont(size=10),
            fg_color="#374151", hover_color="#4b5563", command=self._browse_char_watermark
        )
        self.char_wm_btn.pack(side="left", padx=5)
        
        # ======== GENERATE BUTTON ========
        generate_frame = ctk.CTkFrame(card_content, fg_color="transparent")
        generate_frame.pack(fill="x", pady=(20, 10))
        
        self.char_generate_btn = ctk.CTkButton(
            generate_frame, text="🎬 GENERATE CHARACTER EDIT",
            command=self._start_character_edit, width=300, height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=PRIMARY, hover_color="#7C3AED", corner_radius=12
        )
        self.char_generate_btn.pack()
        
        # Progress bar
        self.char_progress = ctk.CTkProgressBar(card_content, height=8, progress_color=PRIMARY)
        self.char_progress.pack(fill="x", pady=(10, 5))
        self.char_progress.set(0)
        
        # Status label
        self.char_status_label = ctk.CTkLabel(
            card_content, text="Ready - Enter video URL or browse local file",
            font=ctk.CTkFont(size=12), text_color="#94a3b8"
        )
        self.char_status_label.pack(pady=(5, 10))
        
        # ======== DEBUG LOG ========
        log_card = ctk.CTkFrame(scroll_container, fg_color=SURFACE, corner_radius=16)
        log_card.pack(fill="x", pady=(15, 0))
        
        log_header = ctk.CTkFrame(log_card, fg_color="transparent")
        log_header.pack(fill="x", padx=20, pady=(15, 10))
        
        ctk.CTkLabel(log_header, text="📋 Process Log", font=ctk.CTkFont(size=14, weight="bold"), text_color="white").pack(side="left")
        
        self.char_log = ctk.CTkTextbox(
            log_card, height=120, fg_color="#111111", corner_radius=8,
            font=ctk.CTkFont(family="Consolas", size=10), text_color="#94a3b8"
        )
        self.char_log.pack(fill="x", padx=20, pady=(0, 15))
        self.char_log.insert("1.0", "[Ready] Character Edit initialized\n")
        self.char_log.configure(state="disabled")
        
        # Store watermark path
        self.char_watermark_path = None
    
    def _on_char_moments_change(self, value):
        """Update moments label when slider changes"""
        self.char_moments_label.configure(text=str(int(value)))
    
    def _browse_char_video(self):
        """Browse for local video file"""
        file_path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm"), ("All files", "*.*")]
        )
        if file_path:
            self.char_url_entry.delete(0, "end")
            self.char_url_entry.insert(0, file_path)
    
    def _browse_char_watermark(self):
        """Browse for watermark image"""
        file_path = filedialog.askopenfilename(
            title="Select Watermark Image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif"), ("All files", "*.*")]
        )
        if file_path:
            self.char_watermark_path = file_path
            self.char_wm_label.configure(text=os.path.basename(file_path)[:15])
    
    def _log_char(self, message: str):
        """Append message to Character Edit log"""
        def update():
            self.char_log.configure(state="normal")
            self.char_log.insert("end", f"{message}\n")
            self.char_log.see("end")
            self.char_log.configure(state="disabled")
        self.after(0, update)
    
    def _start_character_edit(self):
        """Start character edit generation in background thread"""
        video_input = self.char_url_entry.get().strip()
        
        if not video_input:
            messagebox.showwarning("Input Required", "Please enter a YouTube URL or browse for a local video file.")
            return
        
        # Disable button during processing
        self.char_generate_btn.configure(state="disabled", text="Processing...")
        self.char_progress.set(0)
        
        # Run in background thread
        thread = threading.Thread(target=self._run_character_edit, args=(video_input,), daemon=True)
        thread.start()
    
    def _run_character_edit(self, video_input: str):
        """Run character edit generation (background thread)"""
        try:
            # Get settings
            character_name = self.char_name_entry.get().strip() or None
            duration_str = self.char_duration_combo.get()
            target_duration = int(duration_str.split()[0])
            moment_count = self.char_moments_var.get()
            transition = self.char_transition_combo.get()
            filter_effect = self.char_filter_combo.get()
            
            self._log_char(f"[Start] Video: {video_input[:50]}...")
            self._log_char(f"[Settings] Duration: {target_duration}s, Moments: {moment_count}, Transition: {transition}")
            
            # Progress callback
            def progress_callback(progress: float, message: str):
                self.after(0, lambda: self.char_progress.set(progress))
                self.after(0, lambda: self.char_status_label.configure(text=message))
                self._log_char(f"[{int(progress*100)}%] {message}")
            
            # Download if YouTube URL
            if "youtube.com" in video_input or "youtu.be" in video_input:
                self._log_char("[Download] Downloading from YouTube...")
                self.after(0, lambda: self.char_status_label.configure(text="Downloading video..."))
                
                temp_folder = ensure_temp_folder()
                video_path = os.path.join(temp_folder, "char_input_video.mp4")
                
                ydl_opts = {
                    'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                    'outtmpl': video_path.replace('.mp4', '.%(ext)s'),
                    'merge_output_format': 'mp4',
                    'quiet': True
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_input])
                
                # Find the downloaded file
                for f in os.listdir(temp_folder):
                    if f.startswith("char_input_video"):
                        video_path = os.path.join(temp_folder, f)
                        break
                
                self._log_char(f"[Download] Complete: {video_path}")
            else:
                video_path = video_input
            
            # Output path
            output_folder = os.path.join(os.path.expanduser("~"), "Desktop", "CharacterEdits")
            os.makedirs(output_folder, exist_ok=True)
            output_path = os.path.join(output_folder, f"character_edit_{int(__import__('time').time())}.mp4")
            
            # Run character edit
            if HAS_CHARACTER_EDIT:
                # Get API keys from existing config for transcription + analysis
                groq_key = self.config.get("groq_api_key", "")
                gemini_key = self.config.get("gemini_api_key", "")
                
                success = generate_character_edit(
                    video_path=video_path,
                    output_path=output_path,
                    character_name=character_name,
                    target_duration=float(target_duration),
                    moment_count=moment_count,
                    groq_api_key=groq_key,  # Use existing API key from config
                    gemini_api_key=gemini_key,  # Use existing Gemini API key
                    transition=transition,
                    filter_effect=filter_effect,
                    watermark_path=self.char_watermark_path,  # Defined in _create_character_tab_content
                    ffmpeg_path=self.ffmpeg_path,
                    ffprobe_path=self.ffprobe_path,
                    progress_callback=progress_callback
                )
                
                if success:
                    self._log_char(f"[Complete] Saved to: {output_path}")
                    self.after(0, lambda: self.char_status_label.configure(text=f"✅ Saved to Desktop/CharacterEdits"))
                    self.after(0, lambda: messagebox.showinfo("Success", f"Character Edit saved to:\n{output_path}"))
                else:
                    self._log_char("[Error] Failed to generate character edit")
                    self.after(0, lambda: self.char_status_label.configure(text="❌ Generation failed"))
            else:
                self._log_char("[Error] Character Edit module not loaded")
                self.after(0, lambda: messagebox.showerror("Error", "Character Edit module not available"))
            
        except Exception as e:
            self._log_char(f"[Error] {str(e)}")
            self.after(0, lambda: self.char_status_label.configure(text=f"❌ Error: {str(e)[:50]}"))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        
        finally:
            self.after(0, lambda: self.char_generate_btn.configure(state="normal", text="🎬 GENERATE CHARACTER EDIT"))
    
    def _create_animator_tab_content(self):
        """Create content for AI Animator tab - Premium Obsidian UI"""
        
        # Color scheme (Obsidian theme)
        BG_DARK = "#0F0F0F"
        SURFACE = "#1C1C1C"
        SURFACE_DARKER = "#111111"
        INPUT_BG = "#2A2A2A"
        PRIMARY = "#059669"  # Emerald
        SECONDARY = "#2563eb"  # Sapphire
        
        # Main container with dark background
        main_container = ctk.CTkFrame(self.tab_animator, fg_color=BG_DARK, corner_radius=0)
        main_container.pack(fill="both", expand=True, padx=0, pady=0)
        
        # ======== SCROLLABLE CONTENT ========
        scroll_container = ctk.CTkScrollableFrame(
            main_container, fg_color=BG_DARK, corner_radius=0
        )
        scroll_container.pack(fill="both", expand=True, padx=20, pady=15)
        
        # ======== MAIN CARD ========
        main_card = ctk.CTkFrame(scroll_container, fg_color=SURFACE, corner_radius=16)
        main_card.pack(fill="x", pady=(0, 15))
        
        # Gradient header bar (simulated with colored frame)
        gradient_bar = ctk.CTkFrame(main_card, height=4, fg_color=PRIMARY, corner_radius=0)
        gradient_bar.pack(fill="x", side="top")
        
        card_content = ctk.CTkFrame(main_card, fg_color=SURFACE, corner_radius=0)
        card_content.pack(fill="x", padx=25, pady=25)
        
        # ======== HEADER ========
        header_frame = ctk.CTkFrame(card_content, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))
        
        # Icon + Title
        title_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_row.pack(fill="x")
        
        ctk.CTkLabel(
            title_row, text="🎬",
            font=ctk.CTkFont(size=28)
        ).pack(side="left", padx=(0, 10))
        
        ctk.CTkLabel(
            title_row, text="AI Story Animator",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="white"
        ).pack(side="left")
        
        ctk.CTkLabel(
            header_frame,
            text="Transform any standard video into a cinematic 2.5D animated masterpiece with our advanced AI engine.",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8"
        ).pack(anchor="w", pady=(8, 0))
        
        # ======== VIDEO URL INPUT ========
        url_section = ctk.CTkFrame(card_content, fg_color="transparent")
        url_section.pack(fill="x", pady=(15, 20))
        
        ctk.CTkLabel(
            url_section, text="Source Video URL",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#e2e8f0"
        ).pack(anchor="w", pady=(0, 8))
        
        url_input_frame = ctk.CTkFrame(url_section, fg_color=INPUT_BG, corner_radius=12, height=50)
        url_input_frame.pack(fill="x")
        url_input_frame.pack_propagate(False)
        
        ctk.CTkLabel(
            url_input_frame, text="🔗",
            font=ctk.CTkFont(size=16)
        ).pack(side="left", padx=(15, 0))
        
        self.animator_url_entry = ctk.CTkEntry(
            url_input_frame,
            placeholder_text="Paste YouTube link here...",
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            border_width=0,
            text_color="white"
        )
        self.animator_url_entry.pack(side="left", fill="both", expand=True, padx=10)
        
        paste_btn = ctk.CTkButton(
            url_input_frame, text="Paste",
            width=70, height=35,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#374151", hover_color="#4b5563",
            corner_radius=8,
            command=lambda: self.animator_url_entry.insert(0, self.clipboard_get() if hasattr(self, 'clipboard_get') else "")
        )
        paste_btn.pack(side="right", padx=8)
        
        # ======== 4-COLUMN SETTINGS GRID ========
        settings_grid = ctk.CTkFrame(card_content, fg_color="transparent")
        settings_grid.pack(fill="x", pady=(10, 20))
        settings_grid.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="col")
        
        # --- Column 1: Narrative Style ---
        col1 = ctk.CTkFrame(settings_grid, fg_color="transparent")
        col1.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        ctk.CTkLabel(
            col1, text="🎭 NARRATIVE STYLE",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#64748b"
        ).pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(col1, text="Genre", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(0, 4))
        genre_options = list(GENRES_V2.keys()) if HAS_ANIMATOR_V2 else ["Motivational", "Horror", "Comedy", "Documentary", "Sci-Fi", "Viral Shorts"]
        self.genre_combo = ctk.CTkComboBox(
            col1, values=genre_options, width=180, height=35,
            fg_color=INPUT_BG, border_color="#374151", button_color="#374151",
            dropdown_fg_color=INPUT_BG, dropdown_hover_color="#374151",
            state="readonly", font=ctk.CTkFont(size=12)
        )
        self.genre_combo.set("Horror")
        self.genre_combo.pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(col1, text="Voiceover", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(0, 4))
        voice_options = list(VOICES_V2.keys()) if HAS_ANIMATOR_V2 else ["Indonesian Female", "Indonesian Male", "English Female", "English Male"]
        self.voice_combo = ctk.CTkComboBox(
            col1, values=voice_options, width=180, height=35,
            fg_color=INPUT_BG, border_color="#374151", button_color="#374151",
            dropdown_fg_color=INPUT_BG, dropdown_hover_color="#374151",
            state="readonly", font=ctk.CTkFont(size=12)
        )
        self.voice_combo.set("Indonesian Female")
        self.voice_combo.pack(anchor="w")
        
        # --- Column 2: Visual Aesthetic ---
        col2 = ctk.CTkFrame(settings_grid, fg_color="transparent")
        col2.grid(row=0, column=1, sticky="nsew", padx=10)
        
        ctk.CTkLabel(
            col2, text="🎨 VISUAL AESTHETIC",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#64748b"
        ).pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(col2, text="Art Style", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(0, 4))
        # Use STYLES_V2 from animator_v2 which has current styles including Brainrot Meme
        style_options = list(STYLES_V2.keys()) if HAS_ANIMATOR_V2 else ["Ghibli Anime", "Pixar 3D", "2D Cartoon", "Realistic", "Cyberpunk", "Watercolor", "Brainrot Meme"]
        self.style_combo = ctk.CTkComboBox(
            col2, values=style_options, width=180, height=35,
            fg_color=INPUT_BG, border_color="#374151", button_color="#374151",
            dropdown_fg_color=INPUT_BG, dropdown_hover_color="#374151",
            state="readonly", font=ctk.CTkFont(size=12)
        )
        self.style_combo.set("Ghibli Anime")
        self.style_combo.pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(col2, text="Filter Overlay", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(0, 4))
        # Use FILTER_EFFECTS from animator_v2 (10 genre-matched combo filters)
        filter_options = list(FILTER_EFFECTS.keys()) if HAS_ANIMATOR_V2 else ["None", "Bright Inspire", "Dark Terror", "Fun Pop", "Soft Wonder", "Clean Pro", "Magic Glow", "Cyber Neon", "Viral Punch", "Meme Chaos"]
        self.animator_filter_combo = ctk.CTkComboBox(
            col2, values=filter_options, width=180, height=35,
            fg_color=INPUT_BG, border_color="#374151", button_color="#374151",
            dropdown_fg_color=INPUT_BG, dropdown_hover_color="#374151",
            state="readonly", font=ctk.CTkFont(size=12)
        )
        self.animator_filter_combo.set("None")
        self.animator_filter_combo.pack(anchor="w")
        
        # --- Column 3: Captions & Subs ---
        col3 = ctk.CTkFrame(settings_grid, fg_color="transparent")
        col3.grid(row=0, column=2, sticky="nsew", padx=10)
        
        ctk.CTkLabel(
            col3, text="💬 CAPTIONS & SUBS",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#64748b"
        ).pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(col3, text="Language", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(0, 4))
        lang_options = ["Auto-Detect", "Indonesian", "English (US)", "Japanese"]
        self.animator_lang_combo = ctk.CTkComboBox(
            col3, values=lang_options, width=180, height=35,
            fg_color=INPUT_BG, border_color="#374151", button_color="#374151",
            dropdown_fg_color=INPUT_BG, dropdown_hover_color="#374151",
            state="readonly", font=ctk.CTkFont(size=12)
        )
        self.animator_lang_combo.set("Indonesian")
        self.animator_lang_combo.pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(col3, text="Caption Style", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(0, 4))
        caption_options = ["Karaoke (Bounce)", "Minimal", "Bold Boxed", "Typewriter"]
        self.caption_style_combo = ctk.CTkComboBox(
            col3, values=caption_options, width=180, height=35,
            fg_color=INPUT_BG, border_color="#374151", button_color="#374151",
            dropdown_fg_color=INPUT_BG, dropdown_hover_color="#374151",
            state="readonly", font=ctk.CTkFont(size=12)
        )
        self.caption_style_combo.set("Karaoke (Bounce)")
        self.caption_style_combo.pack(anchor="w")
        
        # --- Column 4: Composition ---
        col4 = ctk.CTkFrame(settings_grid, fg_color=INPUT_BG, corner_radius=12)
        col4.grid(row=0, column=3, sticky="nsew", padx=(10, 0))
        col4_inner = ctk.CTkFrame(col4, fg_color="transparent")
        col4_inner.pack(fill="both", expand=True, padx=15, pady=15)
        
        ctk.CTkLabel(
            col4_inner, text="📊 COMPOSITION",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#64748b"
        ).pack(anchor="w", pady=(0, 15))
        
        scene_header = ctk.CTkFrame(col4_inner, fg_color="transparent")
        scene_header.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(scene_header, text="Image Count", font=ctk.CTkFont(size=12), text_color="#e2e8f0").pack(side="left")
        
        self.scene_count_var = ctk.IntVar(value=20)  # Default 20 for Fast Pacing (2-3s)
        self.scene_count_label = ctk.CTkLabel(
            scene_header, text="20",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=PRIMARY
        )
        self.scene_count_label.pack(side="right")
        
        # Image slider: 5-75 to support up to 3 minutes (images change every 2-3s)
        self.scene_slider = ctk.CTkSlider(
            col4_inner, from_=5, to=75,
            variable=self.scene_count_var, width=150,
            progress_color=PRIMARY, button_color=PRIMARY,
            command=lambda v: self.scene_count_label.configure(text=str(int(v)))
        )
        self.scene_slider.pack(fill="x", pady=(0, 8))
        
        slider_labels = ctk.CTkFrame(col4_inner, fg_color="transparent")
        slider_labels.pack(fill="x")
        ctk.CTkLabel(slider_labels, text="15s (5)", font=ctk.CTkFont(size=9), text_color="#64748b").pack(side="left")
        ctk.CTkLabel(slider_labels, text="3min (75)", font=ctk.CTkFont(size=9), text_color="#64748b").pack(side="right")
        
        # Animation Mode dropdown (NEW: Kling AI 3D integration)
        ctk.CTkLabel(col4_inner, text="Animation Mode", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(anchor="w", pady=(12, 4))
        animation_mode_options = ["Full 2.5D", "Hybrid (3D + 2.5D)", "Full 3D"]
        self.animation_mode_combo = ctk.CTkComboBox(
            col4_inner, values=animation_mode_options, width=180, height=35,
            fg_color=INPUT_BG, border_color="#374151", button_color="#374151",
            dropdown_fg_color=INPUT_BG, dropdown_hover_color="#374151",
            state="readonly", font=ctk.CTkFont(size=12)
        )
        self.animation_mode_combo.set("Full 2.5D")  # Default - backward compatible
        self.animation_mode_combo.pack(anchor="w")
        
        # ======== FOOTER: INFO + GENERATE BUTTON ========
        footer_frame = ctk.CTkFrame(card_content, fg_color="transparent")
        footer_frame.pack(fill="x", pady=(20, 0))
        
        # Separator
        ctk.CTkFrame(footer_frame, height=1, fg_color="#374151").pack(fill="x", pady=(0, 20))
        
        footer_row = ctk.CTkFrame(footer_frame, fg_color="transparent")
        footer_row.pack(fill="x")
        
        # Left side info
        ctk.CTkLabel(
            footer_row, text="ℹ️ Estimated rendering time: ~10-30 mins",
            font=ctk.CTkFont(size=12),
            text_color="#64748b"
        ).pack(side="left")
        
        # Generate button (rightmost)
        self.animate_btn = ctk.CTkButton(
            footer_row, text="✨ Generate Story",
            command=self._start_animation,
            width=180, height=45,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=PRIMARY, hover_color="#047857",
            corner_radius=10
        )
        self.animate_btn.pack(side="right")
        
        # Watermark browse button (next to generate button)
        self.animator_wm_label = ctk.CTkLabel(
            footer_row, text="None",
            font=ctk.CTkFont(size=10),
            text_color="#94a3b8"
        )
        self.animator_wm_label.pack(side="right", padx=(0, 10))
        
        self.animator_wm_btn = ctk.CTkButton(
            footer_row, text="🖼️ Watermark",
            command=self._browse_animator_watermark,
            width=100, height=35,
            font=ctk.CTkFont(size=11),
            fg_color="#374151", hover_color="#475569",
            corner_radius=8
        )
        self.animator_wm_btn.pack(side="right", padx=(10, 5))
        
        # ======== PROGRESS + PREVIEW SECTION (2 columns) ========
        bottom_section = ctk.CTkFrame(scroll_container, fg_color="transparent")
        bottom_section.pack(fill="x", pady=(0, 20))
        bottom_section.grid_columnconfigure(0, weight=2)
        bottom_section.grid_columnconfigure(1, weight=1)
        
        # --- Left: Processing Panel ---
        process_card = ctk.CTkFrame(bottom_section, fg_color=SURFACE, corner_radius=16)
        process_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        process_inner = ctk.CTkFrame(process_card, fg_color="transparent")
        process_inner.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header row
        process_header = ctk.CTkFrame(process_inner, fg_color="transparent")
        process_header.pack(fill="x", pady=(0, 15))
        
        header_left = ctk.CTkFrame(process_header, fg_color="transparent")
        header_left.pack(side="left")
        
        self.animator_status_label = ctk.CTkLabel(
            header_left, text="Processing Job",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        )
        self.animator_status_label.pack(anchor="w")
        
        self.animator_step_label = ctk.CTkLabel(
            header_left, text="Ready to start...",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        self.animator_step_label.pack(anchor="w", pady=(2, 0))
        
        self.animator_percent_label = ctk.CTkLabel(
            process_header, text="0%",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=PRIMARY
        )
        self.animator_percent_label.pack(side="right")
        
        # Progress bar
        self.animator_progress = ctk.CTkProgressBar(
            process_inner, width=500, height=12,
            progress_color=PRIMARY, fg_color="#374151",
            corner_radius=6
        )
        self.animator_progress.pack(fill="x", pady=(0, 15))
        self.animator_progress.set(0)
        
        # Log console
        self.animator_log = ctk.CTkTextbox(
            process_inner, height=180,
            fg_color=SURFACE_DARKER, corner_radius=10,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#94a3b8"
        )
        self.animator_log.pack(fill="x")
        self.animator_log.insert("1.0", "[Ready] Waiting for input...\n")
        self.animator_log.configure(state="disabled")
        
        # --- Right: Scene Preview Panel ---
        preview_card = ctk.CTkFrame(bottom_section, fg_color=SURFACE, corner_radius=16)
        preview_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        preview_inner = ctk.CTkFrame(preview_card, fg_color="transparent")
        preview_inner.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(
            preview_inner, text="Scene Preview",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        ).pack(anchor="w", pady=(0, 15))
        
        # Preview placeholder
        preview_placeholder = ctk.CTkFrame(
            preview_inner, fg_color=INPUT_BG, corner_radius=12, height=200
        )
        preview_placeholder.pack(fill="both", expand=True)
        preview_placeholder.pack_propagate(False)
        
        placeholder_content = ctk.CTkFrame(preview_placeholder, fg_color="transparent")
        placeholder_content.place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(
            placeholder_content, text="📸",
            font=ctk.CTkFont(size=40),
            text_color="#475569"
        ).pack()
        
        ctk.CTkLabel(
            placeholder_content, text="No scenes ready yet",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#94a3b8"
        ).pack(pady=(10, 5))
        
        ctk.CTkLabel(
            placeholder_content, text="Generated scenes will appear here",
            font=ctk.CTkFont(size=10),
            text_color="#64748b"
        ).pack()
        
        self.scenes_preview_frame = preview_placeholder  # Reference for later
        
        # Footer
        preview_footer = ctk.CTkFrame(preview_inner, fg_color="transparent")
        preview_footer.pack(fill="x", pady=(15, 0))
        
        ctk.CTkFrame(preview_footer, height=1, fg_color="#374151").pack(fill="x", pady=(0, 10))
        
        duration_row = ctk.CTkFrame(preview_footer, fg_color="transparent")
        duration_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(duration_row, text="Total Duration", font=ctk.CTkFont(size=11), text_color="#64748b").pack(side="left")
        self.duration_label = ctk.CTkLabel(duration_row, text="--:--", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94a3b8")
        self.duration_label.pack(side="right")
        
        self.download_btn = ctk.CTkButton(
            preview_footer, text="Download Video",
            width=200, height=38,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#374151", hover_color="#4b5563",
            text_color="#64748b",
            corner_radius=8,
            state="disabled"
        )
        self.download_btn.pack(fill="x")
    
    def _check_dependencies(self):
        """Check for required dependencies on startup"""
        missing = []
        
        if Groq is None:
            missing.append("groq")
        if genai is None:
            missing.append("google-generativeai")
        if GoogleTranslator is None:
            missing.append("deep-translator")
        if edge_tts is None:
            missing.append("edge-tts")
        if yt_dlp is None:
            missing.append("yt-dlp")
        
        if missing:
            messagebox.showwarning(
                "Missing Dependencies",
                f"The following packages are missing:\n{', '.join(missing)}\n\n"
                "Please install them with:\npip install " + " ".join(missing)
            )
        
        if not self.ffmpeg_path:
            messagebox.showwarning(
                "FFmpeg Not Found",
                "FFmpeg was not found.\n\n"
                "If running from source: Place ffmpeg.exe in ./bin folder.\n"
                "If running .exe: FFmpeg should be bundled automatically."
            )
    
    def _save_keys(self):
        """Save API keys to config file"""
        self.config["groq_api_key"] = self.groq_entry.get().strip()
        self.config["gemini_api_key"] = self.gemini_entry.get().strip()
        self.config["prodia_api_key"] = self.prodia_entry.get().strip()
        
        if save_config(self.config):
            messagebox.showinfo("Success", "API keys saved successfully!")
        else:
            messagebox.showerror("Error", "Failed to save configuration.")
    
    def _on_perf_mode_change(self):
        """Handle performance mode toggle"""
        self.config["performance_mode"] = self.perf_mode_var.get()
        save_config(self.config)
    
    def _start_animation(self):
        """Start the AI animation generation process"""
        if not HAS_ANIMATOR_V2:
            messagebox.showerror("Error", "Animator module not loaded!")
            return
        
        url = self.animator_url_entry.get().strip()
        if not url:
            messagebox.showwarning("Input Required", "Please enter a YouTube URL.")
            return
        
        groq_key = self.groq_entry.get().strip()
        gemini_key = self.gemini_entry.get().strip()
        
        if not groq_key or not gemini_key:
            messagebox.showwarning("API Keys Required", "Please enter Groq and Gemini API keys in the sidebar.")
            return
        
        # Get ALL settings from UI dropdowns
        genre = self.genre_combo.get()
        style = self.style_combo.get()
        voice = self.voice_combo.get()
        num_scenes = int(self.scene_count_var.get())
        
        # Get new UI settings
        filter_overlay = self.animator_filter_combo.get()
        caption_style = self.caption_style_combo.get()
        language = self.animator_lang_combo.get()
        animation_mode = self.animation_mode_combo.get()  # NEW: Kling AI 3D mode
        
        # Disable button
        self.animate_btn.configure(state="disabled", text="⏳ Processing...")
        
        # Clear preview
        for widget in self.scenes_preview_frame.winfo_children():
            widget.destroy()
        
        # Log settings
        self._update_animator_progress(0, f"Settings: {genre}, {style}, {voice}, {filter_overlay}, {caption_style}, {language}, Mode: {animation_mode}", "")
        
        # Set Prodia API key for fallback image generation
        if HAS_ANIMATOR_V2:
            prodia_key = self.config.get("prodia_api_key", "")
            set_prodia_api_key(prodia_key)
        
        # Start thread with ALL parameters
        thread = threading.Thread(
            target=self._run_animation_thread,
            args=(url, genre, style, voice, num_scenes, groq_key, gemini_key, filter_overlay, caption_style, language, animation_mode),
            daemon=True
        )
        thread.start()
    
    def _update_animator_progress(self, value: float, status: str, step: str = ""):
        """Update animator progress UI with new premium design"""
        # Update progress bar
        self.after(0, lambda: self.animator_progress.set(value))
        
        # Update percent label
        percent = int(value * 100)
        self.after(0, lambda: self.animator_percent_label.configure(text=f"{percent}%"))
        
        # Update status and step labels
        self.after(0, lambda: self.animator_status_label.configure(text="Processing Job"))
        if step:
            self.after(0, lambda: self.animator_step_label.configure(text=step))
        else:
            self.after(0, lambda: self.animator_step_label.configure(text=status))
        
        # Add to log console
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {status}\n"
        
        def append_log():
            try:
                self.animator_log.configure(state="normal")
                self.animator_log.insert("end", log_entry)
                self.animator_log.see("end")
                self.animator_log.configure(state="disabled")
            except:
                pass
        
        self.after(0, append_log)
    
    def _run_animation_thread(self, url: str, genre: str, style: str, voice: str, num_scenes: int, groq_key: str, gemini_key: str, filter_overlay: str = "None", caption_style: str = "Karaoke (Bounce)", language: str = "Indonesian", animation_mode: str = "Full 2.5D"):
        """Execute the animation generation pipeline using animator_v2"""
        try:
            from datetime import datetime
            
            temp_folder = get_temp_folder()
            
            # Clean temp folder to prevent cache issues
            if os.path.exists(temp_folder):
                shutil.rmtree(temp_folder, ignore_errors=True)
                print(f"DEBUG: Cleaned temp folder: {temp_folder}")
            os.makedirs(temp_folder, exist_ok=True)
            
            # Create output folder for final videos
            os.makedirs(OUTPUT_FOLDER, exist_ok=True)
            print(f"DEBUG: Output folder ready: {OUTPUT_FOLDER}")
            
            # Log all settings received
            self._update_animator_progress(0.02, f"🎬 Genre: {genre}, Style: {style}", "")
            self._update_animator_progress(0.03, f"🎙️ Voice: {voice}, Filter: {filter_overlay}", "")
            self._update_animator_progress(0.04, f"📝 Caption: {caption_style}, Lang: {language}", "")
            self._update_animator_progress(0.04, f"🎥 Animation Mode: {animation_mode}", "")  # NEW: Log animation mode
            
            # Step 1: Download and transcribe audio
            self._update_animator_progress(0.05, "📥 Downloading audio...", "Step 1/5: Extracting content")
            audio_path = self._download_audio(url, temp_folder)
            if not audio_path:
                raise Exception("Failed to download audio.")
            
            self._update_animator_progress(0.1, "🎤 Transcribing...", "Step 1/5: Getting transcript")
            transcript = self._transcribe_audio(audio_path, groq_key)
            if not transcript:
                raise Exception("Transcription failed.")
            
            self._update_animator_progress(0.15, f"✓ Transcript: {transcript[:100]}...", "")
            
            # Use animator_v2 pipeline (with proper language handling!)
            if HAS_ANIMATOR_V2:
                from animator_v2 import generate_animation_v2
                
                # Progress callback adapter
                def progress_adapter(value, status):
                    # Scale progress: 0.15 to 1.0
                    scaled_value = 0.15 + (value * 0.85)
                    self._update_animator_progress(scaled_value, status, "")
                
                # Generate animation using v2 pipeline
                output_path = generate_animation_v2(
                    transcript=transcript,
                    genre=genre,
                    style=style,
                    voice=voice,
                    num_scenes=num_scenes,
                    gemini_key=gemini_key,
                    output_folder=temp_folder,
                    ffmpeg_path=self.ffmpeg_path,
                    ffprobe_path=self.ffprobe_path,
                    progress_callback=progress_adapter,
                    groq_key=groq_key,
                    watermark_path=self.animator_watermark_path or "",  # Use animator watermark
                    filter_overlay=filter_overlay,
                    caption_style=caption_style,
                    language_override=language,
                    animation_mode=animation_mode  # NEW: Pass to animator_v2
                )
                
                if output_path and os.path.exists(output_path):
                    # Ensure output folder exists
                    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
                    
                    # Copy final video to output folder with timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_filename = f"animation_{genre.lower().replace(' ', '_')}_{timestamp}.mp4"
                    final_output_path = os.path.join(OUTPUT_FOLDER, output_filename)
                    shutil.copy(output_path, final_output_path)
                    print(f"DEBUG: Video saved to output folder: {final_output_path}")
                    
                    self._update_animator_progress(1.0, "✅ Animation Complete!", f"Saved to: {final_output_path}")
                    
                    # Store path for download button
                    self.last_output_path = final_output_path
                    
                    # Show video preview in Scene Preview area
                    def show_preview():
                        # Clear previous preview
                        for widget in self.scenes_preview_frame.winfo_children():
                            widget.destroy()
                        
                        # Add video info label
                        preview_label = ctk.CTkLabel(
                            self.scenes_preview_frame,
                            text=f"🎬 {output_filename}",
                            font=("Arial", 14, "bold"),
                            text_color="#10B981"
                        )
                        preview_label.pack(pady=10)
                        
                        # Add file size info
                        file_size = os.path.getsize(final_output_path) / (1024 * 1024)
                        info_label = ctk.CTkLabel(
                            self.scenes_preview_frame,
                            text=f"📦 Size: {file_size:.1f} MB",
                            font=("Arial", 12),
                            text_color="#9CA3AF"
                        )
                        info_label.pack(pady=5)
                        
                        # Add "Open Folder" button in preview
                        open_folder_btn = ctk.CTkButton(
                            self.scenes_preview_frame,
                            text="📂 Open Output Folder",
                            command=lambda: os.startfile(OUTPUT_FOLDER) if os.name == 'nt' else None,
                            fg_color="#3B82F6",
                            hover_color="#2563EB",
                            height=35,
                            width=180
                        )
                        open_folder_btn.pack(pady=10)
                        
                        print("DEBUG: Video preview updated")
                    
                    self.after(0, show_preview)
                    
                    # Enable download button - opens output folder
                    def enable_download():
                        self.download_btn.configure(
                            state="normal",
                            text="📂 Open Output Folder",
                            fg_color="#059669",
                            text_color="white",
                            command=lambda: os.startfile(OUTPUT_FOLDER) if os.name == 'nt' else None
                        )
                        # Update duration label
                        try:
                            duration = self._get_video_duration(final_output_path)
                            mins = int(duration // 60)
                            secs = int(duration % 60)
                            self.duration_label.configure(text=f"{mins:02d}:{secs:02d}")
                        except:
                            self.duration_label.configure(text="--:--")
                    
                    self.after(0, enable_download)
                    self.after(0, lambda: messagebox.showinfo(
                        "Success!",
                        f"🎬 Your 2.5D animation is ready!\n\nSaved to:\n{final_output_path}\n\nClick 'Open Output Folder' to view."
                    ))
                else:
                    raise Exception("Animation generation failed - no output file.")
            else:
                raise Exception("Animator V2 module not available!")
            
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Animation Error", str(e)))
            self._update_animator_progress(0, f"❌ Error: {str(e)}", "")
        
        finally:
            self.after(0, self._reset_animation_button)
    
    def _get_video_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe"""
        try:
            cmd = [self.ffprobe_path, '-v', 'error', '-show_entries', 'format=duration',
                   '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            return float(result.stdout.strip())
        except:
            return 0.0
    
    def _reset_animation_button(self):
        """Reset the animate button state"""
        self.animate_btn.configure(state="normal", text="✨ Generate Story")
    
    def _on_min_clips_change(self, value):
        """Handle min clips slider change"""
        val = int(value)
        self.min_clips_value.configure(text=str(val))
        # Ensure max is always >= min
        if val > self.max_clips_var.get():
            self.max_clips_var.set(val)
            self.max_clips_value.configure(text=str(val))
        self.config["min_clips"] = val
        save_config(self.config)
    
    def _on_max_clips_change(self, value):
        """Handle max clips slider change"""
        val = int(value)
        self.max_clips_value.configure(text=str(val))
        # Ensure min is always <= max
        if val < self.min_clips_var.get():
            self.min_clips_var.set(val)
            self.min_clips_value.configure(text=str(val))
        self.config["max_clips"] = val
        save_config(self.config)
    
    def _extract_thumbnail(self, video_path: str, timestamp: float, output_path: str) -> bool:
        """Extract a single frame as thumbnail using FFmpeg (120x68)"""
        try:
            if not self.ffmpeg_path or not os.path.isfile(video_path):
                return False
            
            cmd = [
                self.ffmpeg_path,
                '-y',
                '-ss', str(timestamp),
                '-i', video_path,
                '-vframes', '1',
                '-s', '120x68',
                '-q:v', '5',
                output_path
            ]
            
            subprocess.run(
                cmd,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            return os.path.isfile(output_path)
        except Exception:
            return False
    
    def _extract_frames_for_vision(self, video_path: str, output_folder: str, interval: int = 5) -> List[str]:
        """Extract frames every N seconds for vision analysis (max 16 frames)"""
        frames = []
        try:
            if not self.ffmpeg_path or not os.path.isfile(video_path):
                return frames
            
            # Get video duration
            probe_cmd = [
                self.ffprobe_path,
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            result = subprocess.run(
                probe_cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            duration = float(result.stdout.strip()) if result.stdout.strip() else 60
            
            # Calculate timestamps (max 16 frames)
            num_frames = min(16, int(duration / interval))
            timestamps = [i * interval for i in range(num_frames)]
            
            # Extract frames
            for i, ts in enumerate(timestamps):
                frame_path = os.path.join(output_folder, f"frame_{i:03d}.jpg")
                cmd = [
                    self.ffmpeg_path,
                    '-y',
                    '-ss', str(ts),
                    '-i', video_path,
                    '-vframes', '1',
                    '-s', '512x288',  # Good size for Gemini Vision
                    '-q:v', '3',
                    frame_path
                ]
                subprocess.run(
                    cmd,
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                if os.path.isfile(frame_path):
                    frames.append(frame_path)
            
            return frames
        except Exception:
            return frames
    
    def _browse_watermark(self):
        """Open file dialog to select watermark PNG (Clipper tab)"""
        filepath = filedialog.askopenfilename(
            title="Select Watermark Image",
            filetypes=[("PNG files", "*.png")]
        )
        if filepath:
            self.watermark_path = filepath
            self.wm_filename_label.configure(text=os.path.basename(filepath))
    
    def _browse_animator_watermark(self):
        """Open file dialog to select watermark PNG (Animator tab)"""
        filepath = filedialog.askopenfilename(
            title="Select Watermark Image",
            filetypes=[("PNG files", "*.png")]
        )
        if filepath:
            self.animator_watermark_path = filepath
            self.animator_wm_label.configure(text=os.path.basename(filepath))
    
    def _start_analysis(self):
        """Start the analysis process in a background thread"""
        if self.is_processing:
            messagebox.showwarning("Warning", "A process is already running.")
            return
        
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a YouTube URL.")
            return
        
        groq_key = self.groq_entry.get().strip()
        gemini_key = self.gemini_entry.get().strip()
        
        if not groq_key:
            messagebox.showerror("Error", "Groq API Key is required for transcription.")
            return
        
        if not gemini_key:
            messagebox.showerror("Error", "Gemini API Key is required for AI analysis.")
            return
        
        self.is_processing = True
        self.analyze_btn.configure(state="disabled", text="⏳ Analyzing...")
        self.progress_bar.set(0)
        self._log_clipper("🚀 Starting analysis...")
        
        # Clear previous clips
        self._clear_clips()
        
        thread = threading.Thread(
            target=self._analysis_worker,
            args=(url, groq_key, gemini_key),
            daemon=True
        )
        thread.start()
    
    def _analysis_worker(self, url: str, groq_key: str, gemini_key: str):
        """Background worker for analysis"""
        try:
            temp_folder = ensure_temp_folder()
            
            # Step 1: Download audio
            self._update_progress(0.1, "📥 Downloading audio from YouTube...")
            audio_path = self._download_audio(url, temp_folder)
            if not audio_path:
                raise Exception("Failed to download audio from YouTube.")
            
            # Step 2: Transcribe with Groq
            self._update_progress(0.3, "🎤 Transcribing with Groq Whisper...")
            transcript = self._transcribe_audio(audio_path, groq_key)
            if not transcript:
                raise Exception("Failed to transcribe audio.")
            
            self.transcript = transcript
            
            # Step 3: Analyze with Gemini (transcript or visual)
            clips_data = None
            use_visual = False
            
            # Check if transcript is sufficient for text analysis
            if transcript and len(transcript.strip()) > 100:
                self._update_progress(0.5, "🤖 Analyzing transcript with Gemini AI...")
                clips_data = self._analyze_transcript(transcript, gemini_key)
            
            # Fallback to visual analysis if transcript is empty/short or failed
            if not clips_data:
                use_visual = True
                self._update_progress(0.5, "🎬 No narration detected, using visual analysis...")
                # Need to download video first for vision analysis
                video_path = self._download_video(url, temp_folder)
                if video_path:
                    self.video_path = video_path
                    clips_data = self._analyze_visual(video_path, gemini_key, temp_folder)
            
            if not clips_data:
                raise Exception("Failed to analyze content. No clips identified.")
            
            # Step 4: Download video (if not already done for vision)
            if not use_visual:
                self._update_progress(0.7, "📹 Downloading video for rendering...")
                video_path = self._download_video(url, temp_folder)
                if not video_path:
                    raise Exception("Failed to download video.")
                self.video_path = video_path
            
            self.video_url = url
            
            # Step 5: Create clip objects with thumbnails
            self._update_progress(0.85, "🖼️ Generating thumbnails...")
            self.clips = []
            for i, clip in enumerate(clips_data):
                selected = clip.get("score", 0) > 80
                
                # Extract thumbnail for this clip
                thumbnail_path = os.path.join(temp_folder, f"thumb_{i}.jpg")
                start_time = float(clip.get("start", 0))
                self._extract_thumbnail(self.video_path, start_time + 1, thumbnail_path)
                
                # Hook = TITLE (clickbait from AI analysis, NOT transcript words!)
                # Title is already clickbait style from Gemini: "Clickbait_Style_Title_Max_6_Words"
                hook_text = str(clip.get("title", ""))
                text_segment = str(clip.get("text_segment", ""))
                
                self.clips.append(ClipData(
                    start=start_time,
                    end=float(clip.get("end", 0)),
                    title=hook_text,  # Title = Hook (same clickbait text)
                    score=int(clip.get("score", 0)),
                    text_segment=text_segment,
                    category=str(clip.get("category", "General")),
                    reason=str(clip.get("reason", "")),
                    selected=selected,
                    thumbnail_path=thumbnail_path if os.path.exists(thumbnail_path) else None,
                    hook_text=hook_text  # Hook = Title (clickbait)
                ))
            
            self._update_progress(1.0, f"✅ Found {len(self.clips)} viral clips!")
            self.after(0, self._display_clips)
            
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Analysis Error", str(e)))
            self._update_progress(0, f"❌ Error: {str(e)}")
        
        finally:
            self.after(0, self._reset_analysis_button)
    
    def _download_audio(self, url: str, output_folder: str) -> Optional[str]:
        """Download audio only from YouTube"""
        if yt_dlp is None:
            return None
        
        output_template = os.path.join(output_folder, "audio.%(ext)s")
        
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'extractaudio': True,
            # Anti-bot options (cookies removed - using clean IP)
            'extractor_args': {'youtube': {'player_client': ['web']}},  # Use web client
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # Find the downloaded file
                for ext in ['m4a', 'mp3', 'webm', 'opus']:
                    potential_path = os.path.join(output_folder, f"audio.{ext}")
                    if os.path.isfile(potential_path):
                        return potential_path
        except Exception as e:
            print(f"Audio download error: {e}")
        
        return None
    
    def _download_video(self, url: str, output_folder: str) -> Optional[str]:
        """Download video from YouTube with format fallback"""
        if yt_dlp is None:
            self._log_clipper("❌ yt-dlp module not available")
            return None
        
        output_template = os.path.join(output_folder, "video.%(ext)s")
        
        # Try multiple format strategies
        format_strategies = [
            'bestvideo[height<=720]+bestaudio/best[height<=720]' if self.perf_mode_var.get() else 'bestvideo+bestaudio/best',
            'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',  # Prefer MP4
            'bestvideo+bestaudio/best',  # Fallback to best available
            'best',  # Final fallback - single file format
        ]
        
        for format_str in format_strategies:
            ydl_opts = {
                'format': format_str,
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',
                # Anti-bot options (cookies removed - using clean IP)
                'extractor_args': {'youtube': {'player_client': ['web']}},  # Use web client
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                },
            }
            
            try:
                self._log_clipper(f"📹 Trying format: {format_str[:50]}...")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    # Find the downloaded file
                    for ext in ['mp4', 'mkv', 'webm']:
                        potential_path = os.path.join(output_folder, f"video.{ext}")
                        if os.path.isfile(potential_path):
                            self._log_clipper(f"✅ Video downloaded: {ext}")
                            return potential_path
            except Exception as e:
                self._log_clipper(f"⚠️ Format failed: {str(e)[:50]}")
                continue
        
        self._log_clipper("❌ All download strategies failed")
        return None
    
    def _transcribe_audio(self, audio_path: str, api_key: str) -> Optional[str]:
        """Transcribe audio using Groq API with timestamps"""
        if Groq is None:
            return None
        
        try:
            client = Groq(api_key=api_key)
            
            with open(audio_path, 'rb') as audio_file:
                transcription = client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), audio_file),
                    model="whisper-large-v3-turbo",
                    response_format="verbose_json"
                )
            
            # Extract and save raw segments for accurate subtitle timing
            raw_segments = []
            formatted_lines = []
            
            if hasattr(transcription, 'segments') and transcription.segments:
                for seg in transcription.segments:
                    start_time = seg.get('start', 0) if isinstance(seg, dict) else getattr(seg, 'start', 0)
                    end_time = seg.get('end', start_time + 2) if isinstance(seg, dict) else getattr(seg, 'end', start_time + 2)
                    text = seg.get('text', '') if isinstance(seg, dict) else getattr(seg, 'text', '')
                    
                    raw_segments.append({
                        'start': float(start_time),
                        'end': float(end_time),
                        'text': text.strip()
                    })
                    formatted_lines.append(f"[{start_time:.2f}s] {text.strip()}")
                    
            elif isinstance(transcription, dict) and 'segments' in transcription:
                for seg in transcription['segments']:
                    start_time = seg.get('start', 0)
                    end_time = seg.get('end', start_time + 2)
                    text = seg.get('text', '')
                    
                    raw_segments.append({
                        'start': float(start_time),
                        'end': float(end_time),
                        'text': text.strip()
                    })
                    formatted_lines.append(f"[{start_time:.2f}s] {text.strip()}")
            
            # Save raw segments for subtitle sync
            self.transcript_segments = raw_segments
            
            if formatted_lines:
                return "\n".join(formatted_lines)
            elif hasattr(transcription, 'text'):
                return transcription.text
            elif isinstance(transcription, dict) and 'text' in transcription:
                return transcription['text']
            return str(transcription)
            
        except Exception as e:
            print(f"Transcription error: {e}")
            return None
    
    def _analyze_transcript(self, transcript: str, api_key: str) -> Optional[List[Dict]]:
        """Analyze transcript using Gemini API with professional prompt"""
        if genai is None:
            return None
        
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            # Get clip settings from sliders
            min_clips = self.min_clips_var.get()
            max_clips = self.max_clips_var.get()
            
            prompt = f"""
### ROLE:
Act as a Senior Viral Video Editor & Content Strategist for TikTok, Instagram Reels, and YouTube Shorts.
Your goal is to repurpose this long-form video transcript into highly shareable, short-form clips (30-60 seconds).

### INPUT TRANSCRIPT:
{transcript}

### INSTRUCTIONS:
1. **Identify Viral Drivers:** Scan the text for segments that match these specific criteria:
   - **Controversy/Debate:** Strong, polarizing opinions.
   - **Humor:** A setup followed by a clear punchline.
   - **Insight/Education:** A "Lightbulb Moment" or specific life hack.
   - **Relatability:** Emotional stories that make people say "That's me."

2. **Ensure "Stand-Alone" Context (CRITICAL):**
   - The selected clip MUST make sense without watching the rest of the video.
   - **Do NOT** start a clip with conjunctions or references to previous topics (e.g., "And then...", "Like I said...", "Because of that...").
   - Find the exact sentence where a new thought begins.

3. **The Hook Requirement:**
   - The first 3 seconds of the clip (the first sentence) MUST be attention-grabbing to stop the scroll.

4. **Clip Count:**
   - Output MINIMUM {min_clips} clips, MAXIMUM {max_clips} clips.
   - Aim for the higher end if content is rich.
   - Order clips by viral potential score (highest first).

5. **Timestamp Precision:**
   - Use the provided timestamps in the transcript to determine strict start and end times.
   - Ensure the clip ends after a complete sentence. Do NOT cut off mid-thought.

### OUTPUT FORMAT:
Return ONLY a valid JSON Array. Do not use Markdown code blocks. Do not add explanation text.

JSON Structure:
[
  {{
    "start": <float_seconds>,
    "end": <float_seconds>,
    "title": "<Clickbait_Style_Title_Max_6_Words>",
    "score": <viral_score_0_100>,
    "category": "<Funny/Educational/Controversial/Inspiring>",
    "reason": "<Why_is_this_viral?_One_short_sentence>",
    "text_segment": "<The_exact_text_content>"
  }}
]
"""
            
            response = model.generate_content(prompt)
            response_text = response.text
            
            clips = parse_json_from_response(response_text)
            
            # Validate structure
            valid_clips = []
            for clip in clips:
                if all(k in clip for k in ['start', 'end', 'title', 'score']):
                    valid_clips.append(clip)
            
            return valid_clips if valid_clips else None
            
        except Exception as e:
            print(f"Gemini analysis error: {e}")
            return None
    
    def _analyze_visual(self, video_path: str, api_key: str, temp_folder: str) -> Optional[List[Dict]]:
        """Analyze video visually using Gemini Vision for videos without narration"""
        if genai is None:
            return None
        
        try:
            self._update_progress(0.4, "🖼️ Extracting frames for visual analysis...")
            
            # Extract frames
            frames = self._extract_frames_for_vision(video_path, temp_folder, interval=5)
            
            if not frames:
                return None
            
            self._update_progress(0.5, f"🧠 Analyzing {len(frames)} frames with AI...")
            
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            # Get clip settings
            min_clips = self.min_clips_var.get()
            max_clips = self.max_clips_var.get()
            
            # Load images for Gemini Vision
            import PIL.Image
            images = []
            for frame_path in frames:
                try:
                    img = PIL.Image.open(frame_path)
                    images.append(img)
                except Exception:
                    continue
            
            if not images:
                return None
            
            prompt = f"""
### ROLE:
You are a Senior Viral Video Editor analyzing VIDEO FRAMES (not transcript).
Your goal is to find visually engaging moments that would make viral TikTok/Reels/Shorts clips.

### CONTEXT:
- These are frames extracted from a video every 5 seconds
- Frame 0 = 0 seconds, Frame 1 = 5 seconds, Frame 2 = 10 seconds, etc.
- Total frames: {len(images)}

### INSTRUCTIONS:
1. **Identify Visual Viral Moments:**
   - Action highlights (sports moments, stunts, reactions)
   - Emotional expressions (surprise, joy, shock)
   - Funny/awkward situations
   - Beautiful/aesthetic scenes
   - Dramatic tension

2. **For each clip, estimate:**
   - Start frame number → start timestamp (frame_num × 5 seconds)
   - End frame number → end timestamp  
   - Duration should be 15-60 seconds

3. **Clip Count:**
   - Output MINIMUM {min_clips} clips, MAXIMUM {max_clips} clips
   - Order by visual impact score (highest first)

### OUTPUT FORMAT:
Return ONLY a valid JSON Array. No markdown, no explanation.

[
  {{
    "start": <float_seconds>,
    "end": <float_seconds>,
    "title": "<Clickbait_Style_Title_Max_6_Words>",
    "score": <viral_score_0_100>,
    "category": "<Action/Funny/Emotional/Aesthetic>",
    "reason": "<Why_visually_viral?_One_sentence>",
    "text_segment": "<Visual_description_of_moment>"
  }}
]
"""
            
            # Send images + prompt to Gemini
            content = images + [prompt]
            response = model.generate_content(content)
            response_text = response.text
            
            # Close images to free memory
            for img in images:
                img.close()
            
            clips = parse_json_from_response(response_text)
            
            # Validate structure
            valid_clips = []
            for clip in clips:
                if all(k in clip for k in ['start', 'end', 'title', 'score']):
                    valid_clips.append(clip)
            
            # Cleanup frame files
            for frame_path in frames:
                try:
                    os.remove(frame_path)
                except Exception:
                    pass
            
            return valid_clips if valid_clips else None
            
        except Exception as e:
            print(f"Visual analysis error: {e}")
            return None
    
    def _update_progress(self, value: float, text: str):
        """Update progress bar and log from any thread"""
        def update():
            try:
                self.progress_bar.set(value)
            except Exception:
                pass  # Progress bar may not exist in some states
        self.after(0, update)
        # Log to debug console
        self._log_clipper(text)
    
    def _reset_analysis_button(self):
        """Reset the analyze button state"""
        self.is_processing = False
        self.analyze_btn.configure(state="normal", text="🔍 Analyze")
    
    def _clear_clips(self):
        """Clear all clip cards from display and reset cached data"""
        for card in self.clip_cards:
            card.destroy()
        self.clip_cards = []
        self.clips = []
        
        # CRITICAL: Clear cached data from previous video to prevent data mixing
        self.transcript_segments = []
        self.transcript = None
        self.video_path = None
        self.video_url = None
        
        # CRITICAL: Clean temp folder to prevent cross-tab cache issues
        # This prevents Animator files from mixing with Clipper
        try:
            temp_folder = get_temp_folder()
            if os.path.exists(temp_folder):
                import glob
                # Remove video, audio, and subtitle files from previous sessions
                patterns_to_clean = ['video.*', 'audio.*', '*.ass', 'thumb_*.jpg', 'temp_*.mp4']
                for pattern in patterns_to_clean:
                    for file_path in glob.glob(os.path.join(temp_folder, pattern)):
                        try:
                            os.remove(file_path)
                        except:
                            pass  # Ignore locked files
                self._log_clipper("🧹 Temp folder cleaned")
        except Exception as e:
            pass  # Non-critical, continue anyway
        
        # Show placeholder
        self.no_clips_label = ctk.CTkLabel(
            self.clips_scroll,
            text="🎯 Enter a YouTube URL and click Analyze to find viral clips",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        self.no_clips_label.grid(row=0, column=0, pady=50)
    
    def _display_clips(self):
        """Display clip cards in grid layout (OpusClip-style)"""
        # Remove placeholder
        if hasattr(self, 'no_clips_label') and self.no_clips_label.winfo_exists():
            self.no_clips_label.destroy()
        
        # Configure grid for 3 columns (larger cards)
        COLUMNS = 3
        for col in range(COLUMNS):
            self.clips_scroll.grid_columnconfigure(col, weight=1)
        
        # Create clip cards in grid layout
        for i, clip in enumerate(self.clips):
            row = i // COLUMNS
            col = i % COLUMNS
            card = ClipCard(self.clips_scroll, clip, i)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="n")
            self.clip_cards.append(card)
    
    def _start_render(self):
        """Start the rendering process"""
        if self.is_processing:
            messagebox.showwarning("Warning", "A process is already running.")
            return
        
        if not self.video_path or not os.path.isfile(self.video_path):
            messagebox.showerror("Error", "No video loaded. Please analyze a URL first.")
            return
        
        if not self.ffmpeg_path:
            messagebox.showerror("Error", "FFmpeg not found. Please install FFmpeg.")
            return
        
        # Get selected clips
        selected_clips = [c for c in self.clips if c.selected]
        if not selected_clips:
            messagebox.showwarning("Warning", "No clips selected for rendering.")
            return
        
        # Ask for output folder
        output_folder = filedialog.askdirectory(title="Select Output Folder")
        if not output_folder:
            return
        
        self.is_processing = True
        self.render_btn.configure(state="disabled", text="⏳ Rendering...")
        self.progress_bar.set(0)
        
        thread = threading.Thread(
            target=self._render_worker,
            args=(selected_clips, output_folder),
            daemon=True
        )
        thread.start()
    
    def _render_worker(self, clips: List[ClipData], output_folder: str):
        """Background worker for rendering with detailed logging"""
        temp_folder = ensure_temp_folder()
        dubbing_option = self.dub_combo.get()
        subtitle_option = self.sub_combo.get()
        video_filter = self.filter_combo.get()
        total_clips = len(clips)
        rendered_count = 0
        
        self._log_clipper(f"📂 Output folder: {output_folder}")
        self._log_clipper(f"🎛️ Subtitle: {subtitle_option}, Dubbing: {dubbing_option}, Filter: {video_filter}")
        
        try:
            for idx, clip in enumerate(clips):
                clip_progress = idx / total_clips
                self._update_progress(clip_progress, f"🎬 Rendering clip {idx + 1}/{total_clips}: {clip.title[:30]}...")
                
                try:
                    output_path = self._render_single_clip(
                        clip, idx + 1, output_folder, temp_folder,
                        dubbing_option, subtitle_option, self.watermark_path, video_filter
                    )
                    
                    # Verify file was created
                    if output_path and os.path.isfile(output_path):
                        file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
                        self._log_clipper(f"✅ Clip {idx + 1} saved: {os.path.basename(output_path)} ({file_size:.1f}MB)")
                        rendered_count += 1
                    else:
                        self._log_clipper(f"❌ Clip {idx + 1} FAILED: No output file created")
                        
                except Exception as e:
                    self._log_clipper(f"❌ Clip {idx + 1} ERROR: {str(e)[:60]}")
                    print(f"Error rendering clip {idx + 1}: {e}")
                    continue
            
            if rendered_count > 0:
                self._update_progress(1.0, f"✅ Rendering complete! {rendered_count}/{total_clips} clips saved.")
                self.after(0, lambda: messagebox.showinfo(
                    "Success", f"Rendered {rendered_count} clips to:\n{output_folder}"
                ))
            else:
                self._update_progress(0, f"❌ Rendering failed! No clips were saved.")
                self.after(0, lambda: messagebox.showerror(
                    "Error", "No clips were rendered. Check debug console for details."
                ))
            
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Render Error", str(e)))
            self._update_progress(0, f"❌ Error: {str(e)}")
        
        finally:
            # Cleanup temp files
            clean_temp_folder()
            self.after(0, self._reset_render_button)
    
    def _render_single_clip(
        self,
        clip: ClipData,
        clip_num: int,
        output_folder: str,
        temp_folder: str,
        dubbing_option: str,
        subtitle_option: str,
        watermark_path: Optional[str],
        video_filter: str = "None"
    ) -> Optional[str]:
        """Render a single clip with all processing. Returns output path on success."""
        # Safe filename
        safe_title = re.sub(r'[^\w\s-]', '', clip.title)[:30].strip()
        output_filename = f"clip_{clip_num:02d}_{safe_title}.mp4"
        output_path = os.path.join(output_folder, output_filename)
        
        self._log_clipper(f"🎬 Rendering clip {clip_num}: {clip.title[:35]}...")
        
        # Temp files
        temp_cut = os.path.join(temp_folder, f"temp_cut_{clip_num}.mp4")
        temp_filtered = os.path.join(temp_folder, f"temp_filtered_{clip_num}.mp4")
        temp_cropped = os.path.join(temp_folder, f"temp_cropped_{clip_num}.mp4")
        temp_tts = os.path.join(temp_folder, f"temp_tts_{clip_num}.mp3")
        temp_ass = os.path.join(temp_folder, f"temp_sub_{clip_num}.ass")
        
        duration = clip.end - clip.start
        
        # Verify source video exists
        if not os.path.isfile(self.video_path):
            self._log_clipper(f"   ❌ Source video not found: {self.video_path}")
            return None
        
        # Step 1: Cut the video segment
        cut_cmd = [
            self.ffmpeg_path, "-y",
            "-ss", str(clip.start),
            "-i", self.video_path,
            "-t", str(duration),
            "-c", "copy",
            temp_cut
        ]
        subprocess.run(cut_cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        
        # Verify cut succeeded
        if not os.path.isfile(temp_cut):
            self._log_clipper(f"   ❌ Cut step failed - no temp file")
            return None
        
        # Step 1.5: Video filter is applied in crop step (Step 2) via FILTER_EFFECTS
        # Color grading from FILTER_EFFECTS dict is applied during crop/scale
        video_for_crop = temp_cut
        
        # Step 2: Crop to 9:16 + Auto Hook overlay (first 5 seconds)
        # Escape hook text for FFmpeg drawtext filter (must escape in correct order)
        hook_text = clip.hook_text if hasattr(clip, 'hook_text') and clip.hook_text else ""
        
        # Clean hook text: remove problematic characters first
        escaped_hook = hook_text.replace("\\", "").replace("'", "").replace('"', "")
        escaped_hook = escaped_hook.replace(":", " ").replace("\n", " ").replace("\r", " ")
        escaped_hook = escaped_hook[:60]  # Limit total length
        
        # Build filter chain: crop + UPSCALE to 1080x1920 + hook overlay (LAST layer, on top)
        # CRITICAL: Upscale ensures HD output even from 720p source
        if escaped_hook.strip():
            # Split text into 2 lines if too long (max ~30 chars per line)
            words = escaped_hook.strip().split()
            line1 = ""
            line2 = ""
            for word in words:
                if len(line1) + len(word) + 1 <= 30:
                    line1 += (" " if line1 else "") + word
                else:
                    line2 += (" " if line2 else "") + word
            
            # Build filter: crop + upscale + COLOR FILTER + hook in CENTER with WHITE BOX
            # REFERENCE STYLE: White box with BLACK text (like screenshot)
            # Get color filter from FILTER_EFFECTS (imported from animator_v2)
            color_filter = FILTER_EFFECTS.get(video_filter, "")
            
            filter_chain = (
                f"crop=ih*(9/16):ih,"
                f"scale=1080:1920:force_original_aspect_ratio=decrease,"
                f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
                f"{color_filter},"  # Apply color filter (Sepia, Noir, Vintage, Vivid)
                f"drawtext=text='{line1}':"
                f"fontsize=64:fontcolor=black:"
                f"x=(w-text_w)/2:y=100:"
                f"enable='between(t,0,5)':"
                f"box=1:boxcolor=white@0.95:boxborderw=25"
            )
            
            # Add line 2 if exists - positioned right below line 1
            if line2.strip():
                filter_chain += (
                    f",drawtext=text='{line2}':"
                    f"fontsize=64:fontcolor=black:"
                    f"x=(w-text_w)/2:y=190:"
                    f"enable='between(t,0,5)':"
                    f"box=1:boxcolor=white@0.95:boxborderw=25"
                )
            
            self._log_clipper(f"   Hook: \"{line1}\" | \"{line2}\"")
            self._log_clipper(f"   Filter: {video_filter}")
        else:
            # Crop + Upscale + Color Filter (ensures 1080x1920 HD output)
            color_filter = FILTER_EFFECTS.get(video_filter, "")
            filter_chain = f"crop=ih*(9/16):ih,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2{color_filter}"
        
        crop_cmd = [
            self.ffmpeg_path, "-y",
            "-i", video_for_crop,
            "-vf", filter_chain,
            # Video: H.264 High Profile for YouTube HD
            "-c:v", "libx264",
            "-profile:v", "high",
            "-level:v", "4.0",
            "-pix_fmt", "yuv420p",
            "-preset", "slow",
            "-crf", "17",
            "-b:v", "12M",
            "-maxrate", "15M",
            "-bufsize", "20M",
            "-movflags", "+faststart",
            temp_cropped
        ]
        crop_result = subprocess.run(crop_cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        
        # Check if crop succeeded
        if crop_result.returncode != 0 or not os.path.isfile(temp_cropped):
            # Try without hook overlay but keep upscale
            self._log_clipper(f"   ⚠️ Crop with hook failed, trying without...")
            crop_cmd_simple = [
                self.ffmpeg_path, "-y",
                "-i", video_for_crop,
                "-vf", "crop=ih*(9/16):ih,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                # Video: H.264 High Profile for YouTube HD
                "-c:v", "libx264",
                "-profile:v", "high",
                "-level:v", "4.0",
                "-pix_fmt", "yuv420p",
                "-preset", "slow",
                "-crf", "17",
                "-b:v", "12M",
                "-maxrate", "15M",
                "-bufsize", "20M",
                "-movflags", "+faststart",
                temp_cropped
            ]
            subprocess.run(crop_cmd_simple, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        
        # Verify crop succeeded
        if not os.path.isfile(temp_cropped):
            self._log_clipper(f"   ❌ Crop step failed - no output file")
            return None  # Exit early if crop failed
        
        # Step 3: Create subtitles (CapCut style) - use real timestamps if available
        subtitle_text = clip.text_segment if clip.text_segment else clip.title
        
        # Determine translation language for subtitles
        translate_to = None
        if subtitle_option != "Original (No Translation)":
            translate_to = SUBTITLE_LANGS.get(subtitle_option, None)
        
        # Use segment-based subtitles if we have transcript segments (for accurate sync)
        if self.transcript_segments:
            create_ass_subtitle_from_segments(
                self.transcript_segments,
                clip.start,
                clip.end,
                temp_ass,
                translate_to
            )
        else:
            # Fallback: use old method with text divided evenly
            if translate_to and GoogleTranslator is not None:
                try:
                    translator = GoogleTranslator(source='auto', target=translate_to)
                    subtitle_text = translator.translate(subtitle_text)
                except Exception:
                    pass
            create_ass_subtitle(subtitle_text, 0, duration, temp_ass)
        
        # Step 4: Handle dubbing if not Original
        has_dubbing = False
        if dubbing_option != "Original" and GoogleTranslator is not None and edge_tts is not None:
            # Translate text
            target_lang = TRANSLATE_LANGS.get(dubbing_option, "en")
            try:
                translator = GoogleTranslator(source='auto', target=target_lang)
                translated_text = translator.translate(subtitle_text)
            except Exception:
                translated_text = subtitle_text
            
            # Generate TTS
            voice = EDGE_TTS_VOICES.get(dubbing_option, "en-US-GuyNeural")
            has_dubbing = generate_tts(translated_text, voice, temp_tts)
        
        # Step 5: Build final render command with subtitles
        # For Windows FFmpeg, we need to escape the path properly
        # Replace backslashes with forward slashes, escape colons and special chars
        def escape_ffmpeg_path(path):
            # Convert to forward slashes
            escaped = path.replace('\\', '/')
            # Escape special characters for FFmpeg filter
            escaped = escaped.replace(':', '\\:')
            escaped = escaped.replace("'", "\\'")
            return escaped
        
        ass_escaped = escape_ffmpeg_path(temp_ass)
        
        # Step 5a: Burn subtitles AND progress bar into video
        # Using filter_complex for animated progress bar (drawbox animation doesn't work!)
        temp_with_subs = os.path.join(temp_folder, f"temp_subs_{clip_num}.mp4")
        
        # Progress bar settings
        bar_height = 10
        border = 2
        bar_y_pos = 25  # Distance from bottom
        
        # filter_complex: subtitles + progress bar overlay
        # CRITICAL: color sources MUST have :d= duration to avoid infinite loop!
        progress_filter = (
            # Apply subtitles to input video
            f"[0:v]subtitles='{ass_escaped}'[subbed];"
            # Black border bar (static) - WITH DURATION
            f"color=c=black:s=1080x{bar_height+border*2}:d={duration}[border];"
            # Cyan fill bar (animated) - WITH DURATION
            f"color=c=0x00FFFF:s=1080x{bar_height}:d={duration}[fill];"
            # Overlay border on subbed video - WITH SHORTEST
            f"[subbed][border]overlay=0:H-{bar_height+border*2+bar_y_pos}:shortest=1[with_border];"
            # Overlay animated fill on top - WITH SHORTEST
            f"[with_border][fill]overlay=x='W*(t/{duration}-1)':y=H-{bar_height+border+bar_y_pos}:shortest=1"
        )
        
        # Detect GPU encoder for faster and high quality encoding
        try:
            encoder, _ = detect_gpu_encoder(self.ffmpeg_path)
            print(f"DEBUG: [Clipper] GPU Encoder Detection:")
            print(f"DEBUG:   Detected encoder: {encoder}")
        except Exception as e:
            encoder = "libx264"  # Fallback to CPU
            print(f"DEBUG: [Clipper] GPU detection failed ({e}), using CPU")
        
        # Build encoding params based on detected GPU - BEST QUALITY for each
        if encoder == "h264_nvenc":
            enc_params = ["-c:v", "h264_nvenc", "-profile:v", "high", "-pix_fmt", "yuv420p",
                          "-preset", "p7", "-rc", "vbr", "-cq", "17",
                          "-b:v", "20M", "-maxrate", "25M", "-bufsize", "30M"]
        elif encoder == "h264_qsv":
            enc_params = ["-c:v", "h264_qsv", "-profile:v", "high", "-pix_fmt", "nv12",
                          "-preset", "veryslow", "-global_quality", "17",
                          "-b:v", "20M", "-maxrate", "25M", "-bufsize", "30M"]
        elif encoder == "h264_amf":
            enc_params = ["-c:v", "h264_amf", "-profile:v", "high", "-pix_fmt", "yuv420p",
                          "-quality", "quality", "-rc", "vbr_peak", "-qp_i", "17", "-qp_p", "17",
                          "-b:v", "20M", "-maxrate", "25M", "-bufsize", "30M"]
        else:
            # CPU libx264 - BEST quality preset
            enc_params = ["-c:v", "libx264", "-profile:v", "high", "-level:v", "4.0",
                          "-pix_fmt", "yuv420p", "-preset", "slow", "-crf", "17",
                          "-b:v", "20M", "-maxrate", "25M", "-bufsize", "30M"]
        
        # Log encoding settings
        print(f"DEBUG:   Encoding params: {' '.join(enc_params[:6])}...")
        print(f"DEBUG:   Quality: CRF/CQ=17, Bitrate=20M, MaxRate=25M")
        
        subs_cmd = [
            self.ffmpeg_path, "-y",
            "-i", temp_cropped,
            "-filter_complex", progress_filter,
        ] + enc_params + [
            "-c:a", "copy",
            "-movflags", "+faststart",
            temp_with_subs
        ]
        
        subs_result = subprocess.run(
            subs_cmd,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        # If subtitles filter failed, try ASS filter
        if subs_result.returncode != 0:
            subs_cmd = [
                self.ffmpeg_path, "-y",
                "-i", temp_cropped,
                "-vf", f"ass='{ass_escaped}'",
                # Video: H.264 High Profile for YouTube HD
                "-c:v", "libx264",
                "-profile:v", "high",
                "-level:v", "4.0",
                "-pix_fmt", "yuv420p",
                "-preset", "slow",
                "-crf", "17",
                "-b:v", "12M",
                "-maxrate", "15M",
                "-bufsize", "20M",
                "-c:a", "copy",
                "-movflags", "+faststart",
                temp_with_subs
            ]
            subs_result = subprocess.run(
                subs_cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
        
        # Use video with subs if successful, otherwise use cropped video
        video_for_final = temp_with_subs if (subs_result.returncode == 0 and os.path.isfile(temp_with_subs)) else temp_cropped
        
        # Step 5b: Add watermark if provided
        if watermark_path and os.path.isfile(watermark_path):
            temp_with_wm = os.path.join(temp_folder, f"temp_wm_{clip_num}.mp4")
            wm_cmd = [
                self.ffmpeg_path, "-y",
                "-i", video_for_final,
                "-i", watermark_path,
                "-filter_complex", "[1:v]scale=108:-1[wm];[0:v][wm]overlay=(W-w)/2:(H-h)/2",
                # Video: H.264 High Profile for YouTube HD
                "-c:v", "libx264",
                "-profile:v", "high",
                "-level:v", "4.0",
                "-pix_fmt", "yuv420p",
                "-preset", "slow",
                "-crf", "17",
                "-b:v", "12M",
                "-maxrate", "15M",
                "-bufsize", "20M",
                "-c:a", "copy",
                "-movflags", "+faststart",
                temp_with_wm
            ]
            wm_result = subprocess.run(
                wm_cmd,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if wm_result.returncode == 0 and os.path.isfile(temp_with_wm):
                video_for_final = temp_with_wm
        
        # Step 5.5: SFX - Detect keywords and mix sound effects (NEW!)
        sfx_detected = []
        temp_sfx_audio = None
        try:
            # Detect SFX keywords from clip transcript
            sfx_text = clip.text_segment if clip.text_segment else clip.title
            sfx_detected = detect_sfx_keywords(sfx_text)
            
            if sfx_detected:
                self._log_clipper(f"   🔊 SFX Detected: {sfx_detected}")
                
                # Find SFX folder (same logic as animator_v2)
                current_dir = os.path.dirname(__file__)
                sfx_folder = os.path.join(current_dir, "_internal", "sfx")
                if not os.path.exists(sfx_folder):
                    sfx_folder = os.path.join(current_dir, "sfx")
                
                if os.path.exists(sfx_folder):
                    # Extract audio from video
                    temp_extracted_audio = os.path.join(temp_folder, f"temp_audio_{clip_num}.mp3")
                    extract_cmd = [
                        self.ffmpeg_path, "-y",
                        "-i", video_for_final,
                        "-vn", "-acodec", "libmp3lame", "-b:a", "192k",
                        temp_extracted_audio
                    ]
                    subprocess.run(extract_cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    
                    if os.path.isfile(temp_extracted_audio):
                        # Build SFX paths (max 2)
                        sfx_paths = []
                        for sfx_name in sfx_detected[:2]:
                            for ext in ['.mp3', '.wav']:
                                sfx_path = os.path.join(sfx_folder, f"{sfx_name}{ext}")
                                if os.path.exists(sfx_path):
                                    sfx_paths.append(sfx_path)
                                    break
                        
                        if sfx_paths:
                            # Mix SFX with extracted audio
                            temp_sfx_audio = os.path.join(temp_folder, f"temp_sfx_mixed_{clip_num}.mp3")
                            mix_result = mix_audio_with_sfx(temp_extracted_audio, sfx_paths, temp_sfx_audio, 0.5, self.ffmpeg_path)
                            if mix_result and os.path.isfile(temp_sfx_audio):
                                self._log_clipper(f"   ✅ SFX Mixed: {[os.path.basename(p) for p in sfx_paths]}")
                            else:
                                self._log_clipper(f"   ⚠️ SFX Mix failed, using original audio")
                                temp_sfx_audio = None
                        else:
                            self._log_clipper(f"   ⚠️ SFX files not found for: {sfx_detected}")
                    else:
                        self._log_clipper(f"   ⚠️ Audio extraction failed")
                else:
                    self._log_clipper(f"   ⚠️ SFX folder not found")
            # else: no keywords detected, skip silently
        except Exception as e:
            self._log_clipper(f"   ⚠️ SFX Error: {str(e)[:50]}")
            temp_sfx_audio = None
        
        # Step 6: Handle dubbing or final output (with SFX support)
        if has_dubbing and os.path.isfile(temp_tts):
            # Mix original audio (ducked) with TTS
            final_cmd = [
                self.ffmpeg_path, "-y",
                "-i", video_for_final,
                "-i", temp_tts,
                "-filter_complex", "[0:a]volume=0.05[orig];[1:a]volume=5.0[tts];[orig][tts]amix=inputs=2:duration=longest[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                # Video: H.264 High Profile for YouTube HD
                "-c:v", "libx264",
                "-profile:v", "high",
                "-level:v", "4.0",
                "-pix_fmt", "yuv420p",
                "-preset", "slow",
                "-crf", "17",
                "-b:v", "12M",
                "-maxrate", "15M",
                "-bufsize", "20M",
                # Audio: AAC with higher bitrate  
                "-c:a", "aac",
                "-b:a", "256k",
                "-ar", "48000",
                "-movflags", "+faststart",
                output_path
            ]
        elif temp_sfx_audio and os.path.isfile(temp_sfx_audio):
            # Use SFX-mixed audio (Step 5.5 result)
            self._log_clipper(f"   🎵 Using SFX-mixed audio in final render")
            final_cmd = [
                self.ffmpeg_path, "-y",
                "-i", video_for_final,
                "-i", temp_sfx_audio,
                "-map", "0:v",  # Video from original
                "-map", "1:a",  # Audio from SFX-mixed
                "-c:v", "copy",  # Copy video (already encoded)
                "-c:a", "aac",
                "-b:a", "256k",
                "-ar", "48000",
                "-movflags", "+faststart",
                output_path
            ]
        else:
            # Just copy to final output (no SFX, no dubbing)
            final_cmd = [
                self.ffmpeg_path, "-y",
                "-i", video_for_final,
                "-c", "copy",
                output_path
            ]
        
        # Run final render
        result = subprocess.run(
            final_cmd,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        if result.returncode != 0:
            # Log the error
            error_msg = result.stderr[:200] if result.stderr else "Unknown error"
            self._log_clipper(f"⚠️ FFmpeg error: {error_msg[:80]}...")
            # Fallback: simple re-encode with full quality
            fallback_cmd = [
                self.ffmpeg_path, "-y",
                "-i", video_for_final,
                # Video: H.264 High Profile for YouTube HD
                "-c:v", "libx264",
                "-profile:v", "high",
                "-level:v", "4.0",
                "-pix_fmt", "yuv420p",
                "-preset", "slow",
                "-crf", "17",
                "-b:v", "12M",
                "-maxrate", "15M",
                "-bufsize", "20M",
                # Audio: AAC with higher bitrate
                "-c:a", "aac",
                "-b:a", "256k",
                "-ar", "48000",
                "-movflags", "+faststart",
                output_path
            ]
            fallback_result = subprocess.run(
                fallback_cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if fallback_result.returncode != 0:
                self._log_clipper(f"⚠️ FFmpeg fallback also failed")
        
        # Cleanup temp files for this clip (including SFX temp files)
        for temp_file in [temp_cut, temp_filtered, temp_cropped, temp_tts, temp_ass, temp_with_subs, 
                          os.path.join(temp_folder, f"temp_wm_{clip_num}.mp4"),
                          os.path.join(temp_folder, f"temp_audio_{clip_num}.mp3"),
                          os.path.join(temp_folder, f"temp_sfx_mixed_{clip_num}.mp3")]:
            if os.path.isfile(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
        
        # Return output path for verification
        return output_path
    
    def _reset_render_button(self):
        """Reset the render button state"""
        self.is_processing = False
        self.render_btn.configure(state="normal", text="🚀 RENDER SELECTED")
    
    # ============================================================================
    # TAB 3: API SETTINGS CONTENT
    # ============================================================================
    def _create_api_settings_tab_content(self):
        """Create API Settings tab content with API key inputs"""
        # Scrollable container (so Prodia field is visible on small screens)
        container = ctk.CTkScrollableFrame(self.tab_api_settings, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=40, pady=30)
        
        # Header
        header = ctk.CTkLabel(
            container, text="🔑 API Settings",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#ffffff"
        )
        header.pack(pady=(0, 10))
        
        subtitle = ctk.CTkLabel(
            container, text="Configure your API keys for AI-powered features",
            font=ctk.CTkFont(size=14),
            text_color="#9CA3AF"
        )
        subtitle.pack(pady=(0, 30))
        
        # API Keys Card
        card = ctk.CTkFrame(container, fg_color="#1E293B", corner_radius=16)
        card.pack(fill="x", pady=10)
        
        card_inner = ctk.CTkFrame(card, fg_color="transparent")
        card_inner.pack(fill="x", padx=30, pady=30)
        
        # Groq API Key
        groq_frame = ctk.CTkFrame(card_inner, fg_color="transparent")
        groq_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            groq_frame, text="🎙️ Groq API Key",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ffffff"
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            groq_frame, text="Used for audio transcription (Whisper)",
            font=ctk.CTkFont(size=11),
            text_color="#6B7280"
        ).pack(anchor="w", pady=(0, 5))
        
        self.groq_entry = ctk.CTkEntry(groq_frame, width=500, height=40, show="•", 
                                        placeholder_text="gsk_xxxxxxxxxxxxxxxxxxxx")
        self.groq_entry.pack(fill="x")
        self.groq_entry.insert(0, self.config.get("groq_api_key", ""))
        
        # Gemini API Key
        gemini_frame = ctk.CTkFrame(card_inner, fg_color="transparent")
        gemini_frame.pack(fill="x", pady=20)
        
        ctk.CTkLabel(
            gemini_frame, text="🤖 Gemini API Key",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ffffff"
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            gemini_frame, text="Used for AI story generation and analysis",
            font=ctk.CTkFont(size=11),
            text_color="#6B7280"
        ).pack(anchor="w", pady=(0, 5))
        
        self.gemini_entry = ctk.CTkEntry(gemini_frame, width=500, height=40, show="•",
                                          placeholder_text="AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxx")
        self.gemini_entry.pack(fill="x")
        self.gemini_entry.insert(0, self.config.get("gemini_api_key", ""))
        
        # Prodia API Key (for AI Image Generation fallback)
        prodia_frame = ctk.CTkFrame(card_inner, fg_color="transparent")
        prodia_frame.pack(fill="x", pady=20)
        
        ctk.CTkLabel(
            prodia_frame, text="🖼️ Prodia API Key (Optional)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ffffff"
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            prodia_frame, text="Used for AI image generation (fallback provider)",
            font=ctk.CTkFont(size=11),
            text_color="#6B7280"
        ).pack(anchor="w", pady=(0, 5))
        
        self.prodia_entry = ctk.CTkEntry(prodia_frame, width=500, height=40, show="•",
                                          placeholder_text="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        self.prodia_entry.pack(fill="x")
        self.prodia_entry.insert(0, self.config.get("prodia_api_key", ""))
        
        # Save Button
        self.save_keys_btn = ctk.CTkButton(
            card_inner, text="💾 Save API Keys",
            command=self._save_keys,
            width=200, height=45,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#6366F1",
            hover_color="#4F46E5",
            corner_radius=10
        )
        self.save_keys_btn.pack(pady=(20, 0))
        
        # Info section
        info_card = ctk.CTkFrame(container, fg_color="#0F172A", corner_radius=12)
        info_card.pack(fill="x", pady=20)
        
        info_inner = ctk.CTkFrame(info_card, fg_color="transparent")
        info_inner.pack(fill="x", padx=20, pady=15)
        
        ctk.CTkLabel(
            info_inner, text="ℹ️ Where to get API keys:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#60A5FA"
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            info_inner, 
            text="• Groq: https://console.groq.com/keys\n• Gemini: https://aistudio.google.com/app/apikey\n• Prodia: https://app.prodia.com/api",
            font=ctk.CTkFont(size=11),
            text_color="#9CA3AF",
            justify="left"
        ).pack(anchor="w", pady=(5, 0))
    
    # ============================================================================
    # TAB 4: DOCS CONTENT (INDONESIAN)
    # ============================================================================
    def _create_docs_tab_content(self):
        """Create Docs tab content with Indonesian tutorial"""
        # Scrollable container
        scroll = ctk.CTkScrollableFrame(self.tab_docs, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Header
        header = ctk.CTkLabel(
            scroll, text="📚 Panduan Penggunaan",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#ffffff"
        )
        header.pack(pady=(0, 20))
        
        # Section 1: Viral Clipper
        self._create_docs_section(scroll, 
            "🎬 CARA MENGGUNAKAN VIRAL CLIPPER",
            """1. Paste URL video YouTube atau TikTok di kolom input
2. Klik tombol 'Analyze' untuk menganalisis video
3. Tunggu proses analisis selesai (1-2 menit)
4. Pilih klip yang ingin di-export dengan checkbox
5. Pilih Filter Overlay (10 combo filters)
6. Klik 'Process Selected' untuk memproses klip
7. Video hasil akan tersimpan di folder 'clips/'"""
        )
        
        # Section 2: AI Animator
        self._create_docs_section(scroll,
            "✨ CARA MENGGUNAKAN AI ANIMATOR",
            """1. Paste URL video apapun (YouTube, TikTok, dll)
2. Pilih Genre cerita (Horror, Comedy, dll)
3. Pilih Art Style untuk visualnya (Anime, Pixar 3D, dll)
4. Pilih Filter Overlay (Magic Glow, Dark Terror, dll)
5. Pilih Voice untuk narasi (Indonesian/English)
6. Pilih Language untuk bahasa subtitle
7. Atur Image Count (jumlah gambar):
   • 10-15 gambar untuk video 30 detik
   • 20-30 gambar untuk video 1 menit
   • 40-60 gambar untuk video 2-3 menit
8. Klik 'Generate Story' dan tunggu proses selesai
9. Video hasil akan tersimpan di folder 'output/'

📋 STRUKTUR NARASI (5 PARTS):
• [THE HOOK] - Pembuka dramatis (klimaks/twist)
• [THE DETAIL] - Konteks dan informasi kunci
• [THE REALIZATION] - Plot twist / turning point
• [THE CLIMAX] - Puncak ketegangan
• [THE ENDING] - Resolusi / cliffhanger"""
        )
        
        # Section 3: Features Update
        self._create_docs_section(scroll,
            "🆕 FITUR TERBARU (Dec 2025)",
            """• Fixed 5-Parts Narration Structure
  → Hook → Detail → Realization → Climax → Ending
  → Gambar berubah tiap 2-3 detik (engaging)

• Image Count Slider: 5-75 gambar
  → Terpisah dari struktur narasi
  → Max 3 menit video (YouTube Shorts)

• Genre-Specific Templates (10 genre)
  → Formal: Horror, Documentary, Fairy Tale, Children's, Sci-Fi
  → Casual: Comedy, Viral Shorts, Brainrot, Brainrot ID
  → Semi-formal: Motivational

• Filter Overlay Baru: 10 combo filters
  → Magic Glow, Dark Terror, Cyber Neon, Fun Pop, dll

• Hook Text: Box PUTIH dengan text HITAM
  → Tampil 5 detik pertama video
  → AI generate clickbait hook otomatis"""
        )
        
        # Section 4: API Settings
        self._create_docs_section(scroll,
            "🔑 PENGATURAN API KEY",
            """• Groq API: Digunakan untuk transcribe audio (GRATIS)
  → Daftar di: console.groq.com/keys

• Gemini API: Digunakan untuk generate cerita (GRATIS)
  → Daftar di: aistudio.google.com/app/apikey

• Pollinations.ai: Generate gambar (GRATIS, no API key)

API Key disimpan lokal di config.json (aman)"""
        )
        
        # Section 5: FAQ
        self._create_docs_section(scroll,
            "❓ FAQ (Pertanyaan Umum)",
            """Q: Berapa durasi maksimal video yang bisa diproses?
A: Maksimal 3 menit (sesuai durasi max YouTube Shorts).
   Gunakan 30-45 scene untuk video 3 menit.

Q: Kenapa proses generate lama?
A: Proses AI membutuhkan waktu untuk generate gambar dan audio.
   • 8 scene = 2-3 menit
   • 20 scene = 5-7 menit
   • 45 scene = 10-15 menit

Q: Error "API Key Invalid"?
A: Pastikan API key sudah benar dan tidak ada spasi.
   Coba generate key baru jika masih error.

Q: Narasi tidak sesuai dengan video asli?
A: Coba naikkan jumlah scene untuk konten yang lebih lengkap.
   AI akan membagi konten ke lebih banyak scene."""
        )
        
        # Section 6: Troubleshooting
        self._create_docs_section(scroll,
            "🔧 TROUBLESHOOTING",
            """Error: 'FFmpeg not found'
→ Restart aplikasi, FFmpeg bundled otomatis

Error: 'Failed to download audio'
→ Cek koneksi internet
→ URL mungkin tidak valid atau video di-private

Error: 'Generation failed'
→ Cek API key di tab API Settings
→ Coba dengan video yang lebih pendek

App crash/freeze:
→ Tutup dan buka ulang aplikasi
→ Hapus folder 'temp/' jika ada"""
        )
    
    def _create_docs_section(self, parent, title, content):
        """Helper to create a docs section card"""
        card = ctk.CTkFrame(parent, fg_color="#1E293B", corner_radius=12)
        card.pack(fill="x", pady=10)
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=15)
        
        ctk.CTkLabel(
            inner, text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#10B981"
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            inner, text=content,
            font=ctk.CTkFont(size=12),
            text_color="#D1D5DB",
            justify="left",
            anchor="w"
        ).pack(anchor="w", pady=(10, 0))


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    # Check license first
    licensed = False
    
    if HAS_LICENSE_MODULE:
        valid, message = verify_license()
        if valid:
            licensed = True
        else:
            # Show license activation dialog
            root = ctk.CTk()
            root.withdraw()  # Hide main window
            
            dialog = LicenseDialog(root)
            root.wait_window(dialog)
            
            if dialog.activated:
                licensed = True
            
            root.destroy()
    else:
        # No license module - run in dev mode
        licensed = True
    
    if licensed:
        app = KilatCodeClipperApp()
        app.mainloop()
    else:
        # User cancelled or license invalid
        import sys
        sys.exit(0)
