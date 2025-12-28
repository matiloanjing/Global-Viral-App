"""
Character Edit Engine - Create character-focused highlight reels
Kilat Code Clipper - Character Edit Tab

Features:
- Face detection & identification
- Character moment extraction
- Rapid face ending (5 seconds)
- Beat-synced transitions
"""

import os
import subprocess
import tempfile
import json
import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

# Try to import face_recognition (optional - fallback to transcript-only)
# Note: face_recognition may fail in PyInstaller due to dlib/model file issues
HAS_FACE_RECOGNITION = False
face_recognition = None
np = None

try:
    import numpy as np
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError as e:
    print(f"[CharacterEdit] face_recognition not installed: {e}")
except Exception as e:
    # Catch all errors including path issues in PyInstaller bundle
    print(f"[CharacterEdit] face_recognition failed to load: {e}")
    print("[CharacterEdit] Running in transcript-only mode")


# Try to import Groq for transcription
HAS_GROQ = False
Groq = None
try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    print("[CharacterEdit] Groq not installed - transcription disabled")


# Try to import Gemini for smart analysis
HAS_GEMINI = False
genai = None
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    print("[CharacterEdit] Google Generative AI not installed - using keyword matching")


# Try to import video filter effects and ASS subtitle from animator_v2
FILTER_EFFECTS = {}
create_ass_subtitle_clipper_style = None
try:
    from animator_v2 import FILTER_EFFECTS, create_ass_subtitle_clipper_style
except ImportError:
    # Fallback minimal filters if animator_v2 not available
    FILTER_EFFECTS = {
        "None": "",
        "Viral Punch": ",eq=saturation=1.4:contrast=1.25,unsharp=5:5:1.2",
        "Bright Inspire": ",eq=saturation=1.3:contrast=1.15:brightness=0.05",
        "Dark Terror": ",eq=saturation=0.6:contrast=1.4:brightness=-0.1,vignette=PI/3",
    }



# ============================================================================
# CONSTANTS
# ============================================================================

TRANSITION_EFFECTS = {
    "Cut": "",  # No effect, just cut
    "Shake": "crop=iw-10:ih-10:x='5+random(1)*5':y='5+random(1)*5',scale=iw+10:ih+10",
    "Zoom": "zoompan=z='min(zoom+0.002,1.2)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920",
    "Flash": "fade=t=in:st=0:d=0.1,fade=t=out:st=0.2:d=0.1",
}

# Optimal face sample rate (extract 1 frame per second for speed)
FACE_SAMPLE_RATE = 1.0

# Bilingual action keywords for climax detection (Indonesia + English)
ACTION_KEYWORDS = {
    # English - Fight
    "fight", "punch", "kick", "attack", "hit", "slam", "battle",
    # English - Emotion
    "scream", "cry", "yell", "laugh", "angry", "scared", "shock",
    # English - Drama
    "die", "kill", "dead", "death", "betrayal", "reveal", "truth",
    # English - Movement
    "run", "chase", "escape", "jump", "fall", "crash", "explosion",
    # Indonesia - Pertarungan
    "pukul", "tendang", "hajar", "serang", "tinju", "banting",
    # Indonesia - Emosi
    "teriak", "tangis", "marah", "takut", "kaget", "terkejut",
    # Indonesia - Drama
    "mati", "bunuh", "tewas", "khianati", "rahasia", "kebenaran",
    # Indonesia - Gerakan
    "lari", "kejar", "kabur", "loncat", "jatuh", "ledak", "tembak", "bakar"
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class CharacterMoment:
    """A single moment where the character appears"""
    start: float
    end: float
    confidence: float
    frame_path: Optional[str] = None
    face_center_x: Optional[int] = None  # Horizontal center of face for cropping


@dataclass
class FaceData:
    """Detected face with encoding"""
    timestamp: float
    encoding: any  # numpy array
    frame_path: str
    location: Tuple[int, int, int, int]  # top, right, bottom, left


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_video_duration(video_path: str, ffprobe_path: str = "ffprobe") -> float:
    """Get video duration in seconds"""
    try:
        cmd = [
            ffprobe_path, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        print(f"[CharacterEdit] Error getting duration: {e}")
        return 0.0


def get_video_dimensions(video_path: str, ffprobe_path: str = "ffprobe") -> Tuple[int, int]:
    """Get video width and height. Returns (width, height)."""
    try:
        cmd = [
            ffprobe_path, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if streams:
            return int(streams[0]["width"]), int(streams[0]["height"])
        return 0, 0
    except Exception as e:
        print(f"[CharacterEdit] Error getting dimensions: {e}")
        return 0, 0


def transcribe_video_audio(
    video_path: str,
    groq_api_key: str,
    ffmpeg_path: str = "ffmpeg"
) -> List[Dict]:
    """
    Extract audio from video and transcribe using Groq Whisper.
    Returns list of segments with start/end/text.
    """
    if not HAS_GROQ or not groq_api_key:
        print("[CharacterEdit] Groq not available or no API key")
        return []
    
    temp_audio = None
    try:
        # Step 1: Extract audio to temp mp3
        temp_audio = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        temp_audio.close()
        
        print(f"[CharacterEdit] Extracting audio for transcription...")
        cmd = [
            ffmpeg_path, "-y",
            "-i", video_path,
            "-vn", "-acodec", "mp3",
            "-ar", "16000",  # 16kHz for Whisper
            "-ac", "1",      # Mono
            "-b:a", "64k",   # Lower bitrate for smaller file
            temp_audio.name
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if not os.path.exists(temp_audio.name) or os.path.getsize(temp_audio.name) < 1000:
            print(f"[CharacterEdit] Audio extraction failed")
            return []
        
        # Step 2: Call Groq API with Whisper - request WORD-level timestamps
        print(f"[CharacterEdit] Transcribing with Groq Whisper...")
        client = Groq(api_key=groq_api_key)
        
        with open(temp_audio.name, 'rb') as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(temp_audio.name), audio_file),
                model="whisper-large-v3-turbo",
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"]  # Request word-level timestamps
            )
        
        # Step 3: Extract WORD-level timestamps for accurate sync
        segments = []
        
        # First try to get word-level timestamps
        if hasattr(transcription, 'words') and transcription.words:
            for word_data in transcription.words:
                start_time = word_data.get('start', 0) if isinstance(word_data, dict) else getattr(word_data, 'start', 0)
                end_time = word_data.get('end', start_time + 0.5) if isinstance(word_data, dict) else getattr(word_data, 'end', start_time + 0.5)
                word = word_data.get('word', '') if isinstance(word_data, dict) else getattr(word_data, 'word', '')
                
                segments.append({
                    'start': float(start_time),
                    'end': float(end_time),
                    'text': word.strip(),
                    'is_word': True  # Mark as individual word
                })
            print(f"[CharacterEdit] Got {len(segments)} word-level timestamps")
        
        # Fallback to segment-level if no words
        if not segments and hasattr(transcription, 'segments') and transcription.segments:
            for seg in transcription.segments:
                start_time = seg.get('start', 0) if isinstance(seg, dict) else getattr(seg, 'start', 0)
                end_time = seg.get('end', start_time + 2) if isinstance(seg, dict) else getattr(seg, 'end', start_time + 2)
                text = seg.get('text', '') if isinstance(seg, dict) else getattr(seg, 'text', '')
                
                segments.append({
                    'start': float(start_time),
                    'end': float(end_time),
                    'text': text.strip(),
                    'is_word': False
                })
            print(f"[CharacterEdit] Fallback to {len(segments)} segment-level timestamps")
        
        print(f"[CharacterEdit] Transcribed {len(segments)} segments")
        return segments
        
    except Exception as e:
        print(f"[CharacterEdit] Transcription error: {e}")
        return []
    
    finally:
        # Cleanup temp audio
        if temp_audio and os.path.exists(temp_audio.name):
            try:
                os.unlink(temp_audio.name)
            except:
                pass


def create_ass_from_transcript(
    transcript_segments: List[Dict],
    moments: List,  # CharacterMoment objects
    output_path: str,
    caption_style: str = "Karaoke (Bounce)"
) -> bool:
    """
    Create ASS subtitle file from transcript segments for CHARACTER EDIT.
    Uses Karaoke-style word-by-word timing adjusted to clip timeframes.
    """
    if not transcript_segments or not moments:
        return False
    
    def seconds_to_ass(secs: float) -> str:
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = secs % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    
    # ASS header - Subtitle in BLACK BAR area (top 420px)
    # Video layout: [BLACK BAR 420px] + [VIDEO 1080x1080] + [BLACK BAR 420px]
    # Alignment=8=top center, MarginV=150 centers text in 420px black bar
    header = """[Script Info]
Title: Character Edit Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,70,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,8,40,40,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    events = []
    current_output_time = 0.0  # Track time in output video
    
    for moment in moments:
        moment_start = moment.start
        moment_end = moment.end
        moment_duration = moment_end - moment_start
        
        # Check if we have word-level timestamps
        has_word_level = any(seg.get('is_word', False) for seg in transcript_segments)
        
        if has_word_level:
            # WORD-LEVEL TIMESTAMPS - use directly for accurate sync
            # Group words into display chunks for readability
            moment_words = []
            for seg in transcript_segments:
                if not seg.get('is_word', False):
                    continue
                seg_start = seg.get('start', 0)
                seg_end = seg.get('end', seg_start + 0.3)
                # Check if word falls within this moment
                if seg_start >= moment_start and seg_start < moment_end:
                    word = seg.get('text', '').strip()
                    if word:
                        # Adjust timing relative to moment
                        adj_start = seg_start - moment_start
                        adj_end = min(seg_end - moment_start, moment_duration)
                        
                        moment_words.append({
                            'word': word,
                            'abs_start': current_output_time + adj_start,
                            'abs_end': current_output_time + adj_end
                        })
            
            # Create karaoke subtitle per word with context
            chunk_size = 6  # Show 6 words at a time for readability
            for i in range(0, len(moment_words), chunk_size):
                chunk = moment_words[i:i+chunk_size]
                if not chunk:
                    continue
                
                # Build the full chunk text (stays the same, only highlight changes)
                chunk_words = [wd['word'] for wd in chunk]
                
                # For each word in chunk, create a dialogue line with that word highlighted
                # FIX: Use non-overlapping timing with 0.01s gap to prevent ASS renderer overlap
                for word_idx, word_data in enumerate(chunk):
                    # Start time is this word's start
                    start_time = word_data['abs_start']
                    # End time is 0.01s BEFORE next word's start (prevents overlap display)
                    if word_idx + 1 < len(chunk):
                        end_time = chunk[word_idx + 1]['abs_start'] - 0.01
                    else:
                        end_time = word_data['abs_end']
                    
                    # Skip if duration too short
                    if end_time <= start_time:
                        continue
                    
                    # Build highlighted line (current word in yellow)
                    line_parts = []
                    for j, wd in enumerate(chunk):
                        if j == word_idx:
                            line_parts.append(f"{{\\c&H00FFFF&\\b1}}{wd['word']}{{\\c&HFFFFFF&\\b0}}")
                        else:
                            line_parts.append(wd['word'])
                    
                    line_text = " ".join(line_parts)
                    events.append(f"Dialogue: 0,{seconds_to_ass(start_time)},{seconds_to_ass(end_time)},Default,,0,0,0,,{line_text}")
        else:
            # SEGMENT-LEVEL FALLBACK - calculate word duration by dividing evenly
            for seg in transcript_segments:
                seg_start = seg.get('start', 0)
                seg_end = seg.get('end', seg_start + 3)
                # Check overlap
                if seg_start < moment_end and seg_end > moment_start:
                    text = seg.get('text', '').strip()
                    if not text:
                        continue
                    
                    # Adjust timing relative to moment start
                    adj_start = max(0, seg_start - moment_start)
                    adj_end = min(moment_duration, seg_end - moment_start)
                    
                    # Calculate absolute time in output video
                    abs_start = current_output_time + adj_start
                    abs_end = current_output_time + adj_end
                    
                    words = text.split()
                    if not words:
                        continue
                    
                    seg_duration = abs_end - abs_start
                    word_duration = seg_duration / len(words) if words else seg_duration
                    
                    # Karaoke: word-by-word highlight (yellow)
                    # FIX: Add 0.01s gap to prevent overlap display
                    for word_idx, word in enumerate(words):
                        word_start = abs_start + (word_idx * word_duration)
                        word_end = abs_start + ((word_idx + 1) * word_duration) - 0.01
                        
                        # Skip if duration too short
                        if word_end <= word_start:
                            continue
                        
                        # Build highlighted line (current word in yellow)
                        line_parts = []
                        for j, w in enumerate(words):
                            if j == word_idx:
                                line_parts.append(f"{{\\c&H00FFFF&\\b1}}{w}{{\\c&HFFFFFF&\\b0}}")
                            else:
                                line_parts.append(w)
                        
                        line_text = " ".join(line_parts)
                        events.append(f"Dialogue: 0,{seconds_to_ass(word_start)},{seconds_to_ass(word_end)},Default,,0,0,0,,{line_text}")
        
        current_output_time += moment_duration
    
    # Write ASS file
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(header)
            for event in events:
                f.write(event + "\n")
        print(f"[CharacterEdit] Created ASS subtitle: {len(events)} events")
        return True
    except Exception as e:
        print(f"[CharacterEdit] ASS creation error: {e}")
        return False


def analyze_with_gemini(
    transcript_segments: List[Dict],
    video_duration: float,
    gemini_api_key: str
) -> Dict:
    """
    Use Gemini AI to analyze transcript and identify best moments.
    Returns dict with intro_time, mid_time, climax_time, rapid_ending_time.
    Anti-hallucination: validates timestamps exist in transcript.
    """
    if not HAS_GEMINI or not gemini_api_key or not transcript_segments:
        print("[CharacterEdit] Gemini analysis not available - using keyword matching")
        return {}
    
    try:
        # Build transcript text - use SEGMENT-level for more context
        # Filter to segment-level only (not individual words)
        segment_transcripts = [seg for seg in transcript_segments if not seg.get('is_word', False)]
        if not segment_transcripts:
            segment_transcripts = transcript_segments[:100]  # Fallback to first 100
        
        # Build transcript with timestamps - limit to avoid token overflow
        transcript_text = "\n".join([
            f"[{seg['start']:.1f}s]: {seg['text']}"
            for seg in segment_transcripts[:60]
        ])
        
        # Get valid timestamp range from transcript
        valid_timestamps = [seg['start'] for seg in segment_transcripts]
        min_ts = min(valid_timestamps) if valid_timestamps else 0
        max_ts = max(valid_timestamps) if valid_timestamps else video_duration
        
        # Configure Gemini with temperature=0 for consistency
        genai.configure(api_key=gemini_api_key)
        
        # Dynamic model detection - get valid models from user's account
        model = None
        model_name = None
        try:
            # List all models that support generateContent
            my_models = [
                m.name for m in genai.list_models() 
                if 'generateContent' in m.supported_generation_methods
            ]
            # Prioritize: flash models first, then pro models
            flash_models = [m for m in my_models if 'flash' in m.lower()]
            pro_models = [m for m in my_models if 'pro' in m.lower()]
            candidates = flash_models + pro_models
            
            if candidates:
                model_name = candidates[0]
                # Remove 'models/' prefix if present
                if model_name.startswith('models/'):
                    model_name = model_name[7:]
                model = genai.GenerativeModel(
                    model_name,
                    generation_config=genai.GenerationConfig(temperature=0)
                )
                print(f"[CharacterEdit] Using Gemini model: {model_name}")
            else:
                print("[CharacterEdit] No valid Gemini models found in account")
                return {}
        except Exception as e:
            print(f"[CharacterEdit] Error listing Gemini models: {e}")
            return {}
        
        # Professional prompt with anti-hallucination constraints
        prompt = f"""Act as a professional Video Editor and Content Strategist specializing in YouTube Shorts and TikTok.

I will provide you with a movie transcript that includes timestamps. The video is {video_duration:.0f} seconds long.

### TRANSCRIPT (with timestamps):
{transcript_text}

### YOUR TASK:
Identify the EXACT timestamps for these four markers:

1. **INTRO (The Hook)**: The moment the main character is introduced or first speaks. Look for high "character presence."
2. **MID (The Turning Point)**: Where the primary conflict is triggered or a major plot development occurs.
3. **CLIMAX (The Peak)**: The most intense, high-stakes, or action-packed moment.
4. **RAPID_ENDING**: A brief, impactful moment (after climax) showing the main character's face/reaction.

### STRICT RULES (ANTI-HALLUCINATION):
- You MUST ONLY use timestamps that EXIST in the transcript above
- Valid timestamp range: {min_ts:.1f}s to {max_ts:.1f}s
- DO NOT invent or estimate timestamps that are not in the transcript
- If you cannot find a perfect match, use the CLOSEST timestamp from the transcript

### OUTPUT FORMAT (JSON ONLY, no explanation):
{{"intro_time": X.X, "mid_time": X.X, "climax_time": X.X, "rapid_ending_time": X.X}}"""

        response = model.generate_content(prompt)
        
        # Parse JSON response
        import re
        json_match = re.search(r'\{[^}]+\}', response.text)
        if json_match:
            result = json.loads(json_match.group())
            
            # ANTI-HALLUCINATION: Validate timestamps exist in transcript (within 5s tolerance)
            validated_result = {}
            for key in ['intro_time', 'mid_time', 'climax_time', 'rapid_ending_time']:
                if key in result:
                    ts = float(result[key])
                    # Find closest valid timestamp
                    closest = min(valid_timestamps, key=lambda x: abs(x - ts)) if valid_timestamps else ts
                    # If Gemini's timestamp is within 5s of a valid one, use Gemini's
                    # Otherwise use the closest valid timestamp
                    if abs(ts - closest) <= 5.0:
                        validated_result[key] = ts
                    else:
                        validated_result[key] = closest
                        print(f"[CharacterEdit] Corrected {key}: {ts}s -> {closest}s (closest valid)")
            
            print(f"[CharacterEdit] Gemini analysis: intro={validated_result.get('intro_time')}s, mid={validated_result.get('mid_time')}s, climax={validated_result.get('climax_time')}s, rapid={validated_result.get('rapid_ending_time')}s")
            return validated_result
        
        print("[CharacterEdit] Could not parse Gemini response")
        return {}
        
    except Exception as e:
        print(f"[CharacterEdit] Gemini analysis error: {e}")
        return {}


def extract_frames(
    video_path: str,
    output_dir: str,
    sample_rate: float = 1.0,
    ffmpeg_path: str = "ffmpeg"
) -> List[Tuple[str, float]]:
    """
    Extract frames from video at given sample rate.
    Returns list of (frame_path, timestamp) tuples.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Extract 1 frame per sample_rate seconds
    fps_filter = f"fps=1/{sample_rate}"
    output_pattern = os.path.join(output_dir, "frame_%04d.jpg")
    
    cmd = [
        ffmpeg_path, "-i", video_path,
        "-vf", fps_filter,
        "-q:v", "2",  # High quality JPEG
        "-y", output_pattern
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, timeout=300)
    except Exception as e:
        print(f"[CharacterEdit] Frame extraction error: {e}")
        return []
    
    # Get list of extracted frames with timestamps
    frames = []
    frame_files = sorted([f for f in os.listdir(output_dir) if f.startswith("frame_")])
    for i, fname in enumerate(frame_files):
        timestamp = i * sample_rate
        frames.append((os.path.join(output_dir, fname), timestamp))
    
    return frames


# ============================================================================
# FACE DETECTION FUNCTIONS
# ============================================================================

def detect_faces_in_frames(frames: List[Tuple[str, float]]) -> List[FaceData]:
    """
    Detect all faces in extracted frames.
    Returns list of FaceData with encodings.
    """
    if not HAS_FACE_RECOGNITION:
        return []
    
    all_faces = []
    
    for frame_path, timestamp in frames:
        try:
            # Load image
            image = face_recognition.load_image_file(frame_path)
            
            # Find face locations and encodings
            locations = face_recognition.face_locations(image, model="hog")  # hog is faster
            encodings = face_recognition.face_encodings(image, locations)
            
            for loc, enc in zip(locations, encodings):
                all_faces.append(FaceData(
                    timestamp=timestamp,
                    encoding=enc,
                    frame_path=frame_path,
                    location=loc
                ))
        except Exception as e:
            print(f"[CharacterEdit] Face detection error at {timestamp}s: {e}")
            continue
    
    return all_faces


def cluster_faces(faces: List[FaceData], tolerance: float = 0.6) -> Dict[int, List[FaceData]]:
    """
    Cluster faces by similarity.
    Returns dict of cluster_id -> list of FaceData.
    """
    if not HAS_FACE_RECOGNITION or not faces:
        return {}
    
    clusters = {}
    cluster_encodings = []
    
    for face in faces:
        matched = False
        
        # Compare with existing clusters
        for cluster_id, cluster_enc in enumerate(cluster_encodings):
            distance = face_recognition.face_distance([cluster_enc], face.encoding)[0]
            if distance < tolerance:
                clusters[cluster_id].append(face)
                matched = True
                break
        
        # New cluster
        if not matched:
            new_id = len(cluster_encodings)
            cluster_encodings.append(face.encoding)
            clusters[new_id] = [face]
    
    return clusters


def identify_main_character(
    clusters: Dict[int, List[FaceData]],
    character_name: Optional[str] = None,
    transcript_segments: Optional[List[Dict]] = None,
    video_duration: float = 0.0
) -> Tuple[int, List[FaceData]]:
    """
    Identify the main character more accurately.
    Strategy (in order of priority):
    1. If character_name provided, try to match with transcript mentions
    2. Prioritize faces from FIRST 30 SECONDS (intro usually shows main character)
    3. Prioritize LARGER faces (main character = more close-ups, center frame)
    4. Fallback to most frequent cluster
    """
    if not clusters:
        return -1, []
    
    # Calculate face size from location (top, right, bottom, left)
    def get_face_size(face: FaceData) -> int:
        if not face.location:
            return 0
        top, right, bottom, left = face.location
        return (bottom - top) * (right - left)  # Area
    
    # If character name provided and we have transcript
    if transcript_segments and character_name:
        # Find timestamps where character is mentioned
        mention_times = []
        char_lower = character_name.lower()
        
        for seg in transcript_segments:
            if char_lower in seg.get("text", "").lower():
                mention_times.append(seg.get("start", 0))
        
        # Match clusters to mention times
        if mention_times:
            best_cluster_id = -1
            best_match_count = 0
            
            for cluster_id, faces in clusters.items():
                match_count = 0
                for face in faces:
                    for mention_time in mention_times:
                        if abs(face.timestamp - mention_time) < 5:  # Within 5 seconds
                            match_count += 1
                            break
                
                if match_count > best_match_count:
                    best_match_count = match_count
                    best_cluster_id = cluster_id
            
            if best_cluster_id >= 0:
                print(f"[CharacterEdit] Main character identified via transcript: cluster {best_cluster_id} ({len(clusters[best_cluster_id])} faces)")
                return best_cluster_id, clusters[best_cluster_id]
    
    # IMPROVED: Score clusters based on intro presence + face size
    cluster_scores = {}
    intro_cutoff = 30.0  # First 30 seconds = intro
    
    for cluster_id, faces in clusters.items():
        # Count faces in intro (first 30 seconds)
        intro_faces = [f for f in faces if f.timestamp < intro_cutoff]
        intro_count = len(intro_faces)
        
        # Calculate average face size (larger = main character)
        avg_face_size = sum(get_face_size(f) for f in faces) / len(faces) if faces else 0
        
        # Score = intro_presence * 10 + frequency * 1 + avg_size * 0.0001
        # Prioritize: intro presence > frequency > size
        score = (intro_count * 10) + (len(faces) * 1) + (avg_face_size * 0.0001)
        
        cluster_scores[cluster_id] = {
            'score': score,
            'intro_count': intro_count,
            'total_count': len(faces),
            'avg_size': avg_face_size
        }
        
        print(f"[CharacterEdit] Cluster {cluster_id}: intro={intro_count}, total={len(faces)}, avg_size={int(avg_face_size)}, score={score:.1f}")
    
    # Select cluster with highest score
    main_cluster_id = max(cluster_scores.keys(), key=lambda k: cluster_scores[k]['score'])
    selected = cluster_scores[main_cluster_id]
    
    print(f"[CharacterEdit] Selected main character: cluster {main_cluster_id} (intro={selected['intro_count']}, total={selected['total_count']})")
    
    return main_cluster_id, clusters[main_cluster_id]


# ============================================================================
# MOMENT SELECTION
# ============================================================================

def select_story_moments(
    character_faces: List[FaceData],
    video_duration: float,
    transcript_segments: List[Dict],
    target_duration: float = 60.0,
    ending_duration: float = 5.0,
    gemini_hints: Dict = None  # Gemini-suggested timestamps
) -> Tuple[List[CharacterMoment], List[FaceData]]:
    """
    Select moments that tell a story (trailer style):
    - INTRO (0-20%): Character introduction
    - MID (20-60%): Development/conflict  
    - CLIMAX (60-90%): Peak action/intense moment (or Gemini-suggested)
    - ENDING: Rapid face montage from all parts
    
    Uses Gemini hints (if available) + transcript keywords + face density.
    """
    if not character_faces:
        return [], []
    
    gemini_hints = gemini_hints or {}
    
    # Sort by timestamp
    sorted_faces = sorted(character_faces, key=lambda f: f.timestamp)
    
    # Calculate story sections (by video duration)
    intro_end = video_duration * 0.20
    mid_end = video_duration * 0.60
    climax_end = video_duration * 0.90
    
    # Calculate clip durations (proportional to total duration)
    main_duration = target_duration - ending_duration
    intro_clip_duration = main_duration * 0.20  # 20% for intro
    mid_clip_duration = main_duration * 0.35    # 35% for mid
    climax_clip_duration = main_duration * 0.45 # 45% for climax
    
    print(f"[CharacterEdit] Story sections: INTRO(0-{intro_end:.0f}s), MID({intro_end:.0f}-{mid_end:.0f}s), CLIMAX({mid_end:.0f}-{climax_end:.0f}s)")
    print(f"[CharacterEdit] Clip durations: INTRO={intro_clip_duration:.1f}s, MID={mid_clip_duration:.1f}s, CLIMAX={climax_clip_duration:.1f}s, ENDING={ending_duration:.1f}s")
    
    def score_segment(start: float, end: float) -> Tuple[float, float]:
        """
        Score a segment based on:
        1. Transcript action keywords (bilingual ID+EN)
        2. Face density (more appearances = important)
        3. Face size (larger = main action)
        Returns: (score, best_timestamp)
        """
        # Count action keywords in transcript
        keyword_score = 0
        keyword_timestamp = None
        for seg in transcript_segments:
            if seg['start'] >= start and seg['end'] <= end:
                text_lower = seg['text'].lower()
                for keyword in ACTION_KEYWORDS:
                    if keyword in text_lower:
                        keyword_score += 1
                        keyword_timestamp = seg['start']
        
        # Count faces in segment
        segment_faces = [f for f in sorted_faces if start <= f.timestamp < end]
        face_count = len(segment_faces)
        
        # Calculate average face size
        avg_size = 0
        best_face_ts = None
        if segment_faces:
            sizes = []
            for f in segment_faces:
                if f.location:
                    top, right, bottom, left = f.location
                    sizes.append((bottom - top) * (right - left))
            avg_size = sum(sizes) / len(sizes) if sizes else 0
            # Pick face with largest size
            if sizes:
                max_idx = sizes.index(max(sizes))
                best_face_ts = segment_faces[max_idx].timestamp
        
        # Combined score: keywords * 100 + face_count * 10 + size * 0.001
        total_score = (keyword_score * 100) + (face_count * 10) + (avg_size * 0.001)
        
        # Best timestamp: prefer keyword location, fallback to largest face
        best_ts = keyword_timestamp or best_face_ts or ((start + end) / 2)
        
        return total_score, best_ts
    
    def find_best_moment(section_start: float, section_end: float, clip_duration: float, min_start_time: float = 0) -> Optional[CharacterMoment]:
        """
        Find best moment within a story section.
        min_start_time: Moment must start AFTER this time to avoid overlap with previous moment.
        """
        # Ensure section_start is at least min_start_time to avoid overlap
        actual_start = max(section_start, min_start_time)
        
        # Check if there's enough room for a clip
        if actual_start + clip_duration > section_end:
            # Not enough room, try to fit as much as possible
            actual_start = max(section_start, section_end - clip_duration)
        
        if actual_start >= section_end:
            return None
        
        # Divide section into sub-segments and score each
        section_length = section_end - actual_start
        segment_count = max(3, int(section_length / 30))  # ~30s per segment
        segment_len = section_length / segment_count
        
        best_score = -1
        best_ts = None
        
        for i in range(segment_count):
            seg_start = actual_start + (i * segment_len)
            seg_end = seg_start + segment_len
            score, ts = score_segment(seg_start, seg_end)
            
            # Ensure the timestamp is within valid range
            if ts >= actual_start and score > best_score:
                best_score = score
                best_ts = ts
        
        if best_ts is None:
            # Fallback: use middle of valid section
            best_ts = (actual_start + section_end) / 2
        
        # Create moment centered on best timestamp, but clamp to avoid overlap
        moment_start = max(actual_start, best_ts - clip_duration / 2)
        moment_end = min(video_duration, moment_start + clip_duration)
        
        # Make sure start is at least actual_start
        moment_start = max(moment_start, actual_start)
        
        # Calculate face_center_x from faces in this moment timeframe
        moment_faces = [f for f in sorted_faces if moment_start <= f.timestamp < moment_end and f.location]
        face_center_x = None
        if moment_faces:
            # Calculate average horizontal center of all faces
            centers = []
            for f in moment_faces:
                top, right, bottom, left = f.location
                centers.append((left + right) // 2)
            face_center_x = sum(centers) // len(centers)
        
        return CharacterMoment(
            start=moment_start,
            end=moment_end,
            confidence=1.0,
            face_center_x=face_center_x
        )
    
    # Find best moments for each story section - with NON-OVERLAP guarantee
    moments = []
    last_end_time = 0  # Track where the last moment ended
    
    # INTRO: First appearance of character
    intro_moment = find_best_moment(0, intro_end, intro_clip_duration, min_start_time=last_end_time)
    if intro_moment:
        moments.append(intro_moment)
        last_end_time = intro_moment.end + 1  # Add 1 second gap
        print(f"[CharacterEdit] INTRO moment: {intro_moment.start:.1f}s - {intro_moment.end:.1f}s")
    
    # MID: Development/conflict - must start after INTRO ends
    mid_moment = find_best_moment(intro_end, mid_end, mid_clip_duration, min_start_time=last_end_time)
    if mid_moment:
        moments.append(mid_moment)
        last_end_time = mid_moment.end + 1  # Add 1 second gap
        print(f"[CharacterEdit] MID moment: {mid_moment.start:.1f}s - {mid_moment.end:.1f}s")
    
    # CLIMAX: Peak action - use Gemini hint if available, but VALIDATE with keywords
    gemini_climax = gemini_hints.get('climax_time')
    use_gemini_climax = False
    
    # Function to find best action scene by keywords
    def find_action_scene(search_start: float, search_end: float) -> Optional[float]:
        """Find timestamp with most action keywords in transcript"""
        best_time = None
        best_score = 0
        for seg in transcript_segments:
            if seg.get('is_word', False):
                continue
            seg_start = seg.get('start', 0)
            if search_start <= seg_start <= search_end:
                text_lower = seg.get('text', '').lower()
                score = sum(1 for kw in ACTION_KEYWORDS if kw in text_lower)
                if score > best_score:
                    best_score = score
                    best_time = seg_start
        return best_time if best_score > 0 else None
    
    # Validate Gemini climax contains action keywords
    if gemini_climax and isinstance(gemini_climax, (int, float)):
        # Check if transcript around Gemini timestamp contains action keywords
        has_action = False
        for seg in transcript_segments:
            seg_start = seg.get('start', 0)
            # Check segments within 10 seconds of Gemini suggestion
            if abs(seg_start - gemini_climax) <= 10:
                text_lower = seg.get('text', '').lower()
                if any(kw in text_lower for kw in ACTION_KEYWORDS):
                    has_action = True
                    break
        
        if has_action:
            use_gemini_climax = True
        else:
            # Gemini missed action scene - try to find one with keywords
            print(f"[CharacterEdit] Gemini climax {gemini_climax}s has no action keywords - searching...")
            keyword_climax = find_action_scene(mid_end, climax_end)
            if keyword_climax:
                print(f"[CharacterEdit] Found action scene at {keyword_climax}s via keywords")
                gemini_climax = keyword_climax
                use_gemini_climax = True
            else:
                # No action found, still use Gemini
                use_gemini_climax = True
    
    if use_gemini_climax and gemini_climax:
        # Use validated/keyword-based climax time (but ensure no overlap)
        climax_start = max(last_end_time, gemini_climax - climax_clip_duration / 2)
        climax_end_ts = min(video_duration, climax_start + climax_clip_duration)
        
        # Calculate face_center_x for climax moment
        climax_faces = [f for f in sorted_faces if climax_start <= f.timestamp < climax_end_ts and f.location]
        climax_face_center_x = None
        if climax_faces:
            centers = [(f.location[3] + f.location[1]) // 2 for f in climax_faces]  # (left + right) / 2
            climax_face_center_x = sum(centers) // len(centers)
        
        climax_moment = CharacterMoment(start=climax_start, end=climax_end_ts, confidence=1.0, face_center_x=climax_face_center_x)
        print(f"[CharacterEdit] CLIMAX: {climax_moment.start:.1f}s - {climax_moment.end:.1f}s (source: {'gemini' if gemini_hints.get('climax_time') == gemini_climax else 'keyword'})")
    else:
        # Fallback to standard section-based selection
        climax_moment = find_best_moment(mid_end, climax_end, climax_clip_duration, min_start_time=last_end_time)
        if climax_moment:
            print(f"[CharacterEdit] CLIMAX moment: {climax_moment.start:.1f}s - {climax_moment.end:.1f}s")
    
    if climax_moment:
        moments.append(climax_moment)
    
    # Select faces for ending - ONLY from main character, EXCLUDING last 10s (end credits)
    end_credits_cutoff = video_duration - 10.0
    main_char_faces_no_credits = [f for f in sorted_faces if f.timestamp < end_credits_cutoff]
    
    if not main_char_faces_no_credits:
        main_char_faces_no_credits = sorted_faces
    
    # Select diverse faces spread across the video for rapid ending
    # FIX: Use time-gap based selection to prevent duplicate/similar faces
    ending_face_count = int(ending_duration / 0.3)  # ~0.3s per face
    total_faces = len(main_char_faces_no_credits)
    
    # Select faces with minimum 1.5s time gap to ensure visual diversity
    ending_faces = []
    last_time = -2.0  # Start with negative to include first face
    for face in main_char_faces_no_credits:
        if face.timestamp - last_time >= 1.5:  # At least 1.5s apart
            ending_faces.append(face)
            last_time = face.timestamp
            if len(ending_faces) >= ending_face_count:
                break
    
    # If not enough faces with gap, fallback to evenly distributed selection
    if len(ending_faces) < ending_face_count // 2 and total_faces >= ending_face_count:
        step = total_faces // ending_face_count
        ending_faces = main_char_faces_no_credits[::step][:ending_face_count]
    
    print(f"[CharacterEdit] ENDING: {len(ending_faces)} rapid face clips (from {total_faces} main char faces)")
    
    return moments, ending_faces


# Keep old function for backwards compatibility
def select_best_moments(
    character_faces: List[FaceData],
    video_duration: float,
    target_duration: float = 60.0,
    moment_count: int = 3,
    ending_duration: float = 5.0
) -> Tuple[List[CharacterMoment], List[FaceData]]:
    """DEPRECATED: Use select_story_moments instead. This is a wrapper for backwards compatibility."""
    return select_story_moments(
        character_faces=character_faces,
        video_duration=video_duration,
        transcript_segments=[],  # Empty transcript
        target_duration=target_duration,
        ending_duration=ending_duration
    )


# ============================================================================
# VIDEO RENDERING
# ============================================================================

def create_character_edit(
    video_path: str,
    output_path: str,
    moments: List[CharacterMoment],
    ending_faces: List[FaceData],
    transcript_segments: List[Dict] = None,  # For subtitle overlay
    transition: str = "Random",
    filter_effect: str = "Viral Punch",  # Default to Viral Punch for engaging look
    watermark_path: Optional[str] = None,
    ffmpeg_path: str = "ffmpeg",
    progress_callback=None  # NEW: Forward logs to UI
) -> bool:
    """
    Create the final character edit video.
    Now with subtitle overlay and color filter for viral engagement!
    """
    # Log helper - prints to console AND sends to UI callback
    def log(msg, progress=0.85):
        print(f"[CharacterEdit] {msg}")
        if progress_callback:
            progress_callback(progress, msg)
    
    if not moments:
        log("No moments to render", 0.85)
        return False
    
    temp_dir = tempfile.mkdtemp(prefix="character_edit_")
    log(f"Temp dir: {temp_dir}", 0.86)
    
    # Detect video dimensions to determine crop strategy
    video_width, video_height = get_video_dimensions(video_path)
    is_landscape = video_width > video_height
    log(f"Video dimensions: {video_width}x{video_height} ({'landscape' if is_landscape else 'portrait'})", 0.86)
    
    try:
        # Step 1: Cut moment clips
        # Use -ss AFTER -i for frame-accurate seeking (slower but no blank frames)
        clip_paths = []
        for i, moment in enumerate(moments):
            clip_path = os.path.join(temp_dir, f"clip_{i:02d}.mp4")
            
            # Get transition effect - only use simple effects
            if transition == "Random":
                effect_name = random.choice(["Cut", "Flash"])  # Only simple effects
            else:
                effect_name = transition
            
            # Only apply simple effects that don't cause blank frames
            vf_effect = ""
            if effect_name == "Flash":
                vf_effect = ",fade=t=in:st=0:d=0.2"
            # Skip Shake/Zoom as they cause issues with short clips
            
            # Build video filter - 1:1 SQUARE CROP with BLACK BARS for subtitle area
            # Layout: [BLACK BAR TOP 420px for subtitle] + [VIDEO 1080x1080] + [BLACK BAR BOTTOM 420px]
            # Total: 1080x1920 (9:16 aspect ratio for Shorts)
            # Use is_landscape detected earlier to choose correct crop
            if is_landscape:
                # Landscape: crop to height (ih:ih), center horizontally
                vf_base = "crop=ih:ih:(iw-ih)/2:0,scale=1080:1080,pad=1080:1920:0:420:black"
            else:
                # Portrait: crop to width (iw:iw), center vertically
                vf_base = "crop=iw:iw:0:(ih-iw)/2,scale=1080:1080,pad=1080:1920:0:420:black"
            
            # Apply color filter from FILTER_EFFECTS for viral look
            color_filter = FILTER_EFFECTS.get(filter_effect, "")
            
            # NOTE: Subtitles will be applied via ASS file on final render (not per-clip)
            # This ensures proper Karaoke-style word-by-word sync
            
            vf_full = f"{vf_base}{color_filter}{vf_effect}"
            
            # Calculate clip duration
            clip_duration = moment.end - moment.start
            
            # Use -ss AFTER -i for accurate frame-level seeking (prevents blank frames)
            cmd = [
                ffmpeg_path, "-y",
                "-i", video_path,
                "-ss", str(moment.start),
                "-t", str(clip_duration),
                "-vf", vf_full,
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac", "-b:a", "128k",
                clip_path
            ]
            
            log(f"Cutting clip {i+1}/{len(moments)} (t={moment.start:.1f}s, dur={clip_duration:.1f}s)", 0.87)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                print(f"[CharacterEdit] Clip {i} error: {result.stderr[:200] if result.stderr else 'unknown'}")
            
            # Validate clip has actual content (at least 10KB)
            if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10000:
                clip_paths.append(clip_path)
                log(f"Clip {i+1} created: {os.path.getsize(clip_path)} bytes", 0.88)
            else:
                print(f"[CharacterEdit] Clip {i+1} too small or failed, skipping")
        
        if not clip_paths:
            log("No clips were created successfully", 0.85)
            return False
        
        # Step 2: Create SLOW-MO FLASH face ending
        # Fewer clips (5 max), longer duration (1s each), slow motion + flash effect
        ending_path = os.path.join(temp_dir, "ending.mp4")
        if ending_faces and len(ending_faces) > 0:
            # Sort by timestamp to ensure chronological distribution
            sorted_ending_faces = sorted(ending_faces, key=lambda f: f.timestamp)
            
            # Select 5 faces evenly distributed across the timeline
            num_faces_to_use = min(5, len(sorted_ending_faces))
            if num_faces_to_use < len(sorted_ending_faces):
                # Calculate indices for even distribution
                indices = [int(i * (len(sorted_ending_faces) - 1) / (num_faces_to_use - 1)) 
                          for i in range(num_faces_to_use)]
                selected_faces = [sorted_ending_faces[i] for i in indices]
            else:
                selected_faces = sorted_ending_faces
            
            # Debug: show selected timestamps
            timestamps = [f"{f.timestamp:.1f}s" for f in selected_faces]
            print(f"[CharacterEdit] Creating slow-mo flash ending with {len(selected_faces)} clips at: {timestamps}")
            
            # Each face gets 1.0s with slow motion and flash
            face_clip_paths = []
            source_clip_duration = 0.7  # Capture 0.7s of video
            
            for j, face in enumerate(selected_faces):
                face_clip_path = os.path.join(temp_dir, f"face_{j:02d}.mp4")
                
                # Calculate clip start (centered on face timestamp)
                # Use longer source (1.0s) to allow for slow-mo stretch
                clip_start = max(0, face.timestamp - 0.5)
                
                # Crop to 1:1 SQUARE with black bars
                if is_landscape:
                    crop_filter = "crop=ih:ih:(iw-ih)/2:0,scale=1080:1080,pad=1080:1920:0:420:black"
                else:
                    crop_filter = "crop=iw:iw:0:(ih-iw)/2,scale=1080:1080,pad=1080:1920:0:420:black"
                
                # SLOW-MO effect only (flash removed due to timing issues)
                # setpts=2.0*PTS slows video to half speed
                # NOTE: Flash effect will be added via xfade between clips instead
                slowmo_filter = f"{crop_filter},setpts=2.0*PTS"
                
                # HYBRID SEEKING for accuracy
                fast_seek = max(0, clip_start - 5)
                fine_seek = clip_start - fast_seek
                
                cmd = [
                    ffmpeg_path, "-y",
                    "-ss", str(fast_seek),
                    "-i", video_path,
                    "-ss", str(fine_seek),
                    "-t", "1.0",  # Capture 1.0s of source
                    "-vf", slowmo_filter,
                    "-t", "1.0",  # Output 1.0s (will be slowed from 0.5s source)
                    "-c:v", "libx264", "-preset", "fast",
                    "-r", "30",  # Force 30fps output
                    "-an",  # No audio for face clips
                    face_clip_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                
                if result.returncode != 0:
                    print(f"[CharacterEdit] Face clip {j} error: {result.stderr[:100] if result.stderr else 'unknown'}")
                
                if os.path.exists(face_clip_path) and os.path.getsize(face_clip_path) > 1000:
                    face_clip_paths.append(face_clip_path)
                    print(f"[CharacterEdit] Face clip {j+1}/{len(selected_faces)}: {os.path.getsize(face_clip_path)} bytes")
            
            print(f"[CharacterEdit] Created {len(face_clip_paths)} slow-mo clips")
            
            # Concat all face clips into ending.mp4 WITH WHITE FLASH between each
            if len(face_clip_paths) >= 3:  # Need at least 3 clips for a good ending
                # Step 2a: Generate white flash frame (0.1s white clip)
                flash_path = os.path.join(temp_dir, "flash.mp4")
                flash_cmd = [
                    ffmpeg_path, "-y",
                    "-f", "lavfi",
                    "-i", "color=c=0x888888:s=1080x1920:r=30:d=0.1",  # Medium gray flash (visible)
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-t", "0.1",
                    flash_path
                ]
                subprocess.run(flash_cmd, capture_output=True, text=True, timeout=30)
                
                has_flash = os.path.exists(flash_path) and os.path.getsize(flash_path) > 500
                if has_flash:
                    print(f"[CharacterEdit] Gray flash created: {os.path.getsize(flash_path)} bytes")
                
                # Step 2b: Create concat list with flash-face interleave
                face_concat_file = os.path.join(temp_dir, "face_concat.txt")
                with open(face_concat_file, "w", encoding="utf-8") as f:
                    for fc in face_clip_paths:
                        # Add flash before each face clip
                        if has_flash:
                            escaped_flash = flash_path.replace("\\", "/").replace("'", "'\\''")
                            f.write(f"file '{escaped_flash}'\n")
                        # Add face clip
                        escaped = fc.replace("\\", "/").replace("'", "'\\''")
                        f.write(f"file '{escaped}'\n")
                
                # Face clips are already 1080x1920 with proper 1:1 crop and black bars
                # Just concat them without additional filters
                
                cmd = [
                    ffmpeg_path, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", face_concat_file,
                    "-c:v", "libx264", "-preset", "fast",
                    "-t", "5",  # Max 5 seconds for ending
                    ending_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                
                if os.path.exists(ending_path) and os.path.getsize(ending_path) > 10000:  # At least 10KB
                    clip_paths.append(ending_path)
                    log(f"Rapid face ending created: {os.path.getsize(ending_path)} bytes", 0.90)
                else:
                    log(f"Ending concat failed: {result.stderr[:200] if result.stderr else 'unknown'}", 0.90)
            else:
                log(f"Not enough face clips for ending ({len(face_clip_paths)} < 3)", 0.90)
        
        # Step 3: Concat all clips
        log(f"Concatenating {len(clip_paths)} clips", 0.91)
        # DEBUG: Show all clip paths being concatenated
        for idx, cp in enumerate(clip_paths):
            if os.path.exists(cp):
                print(f"[CharacterEdit] Clip {idx}: {os.path.basename(cp)} ({os.path.getsize(cp)} bytes)")
            else:
                print(f"[CharacterEdit] Clip {idx}: {os.path.basename(cp)} (MISSING!)")
        
        concat_list = os.path.join(temp_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for clip in clip_paths:
                escaped_path = clip.replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")
        
        concat_output = os.path.join(temp_dir, "concat.mp4")
        
        # Use filter_complex concat instead of concat protocol
        # This properly merges clips with different encodings
        cmd = [ffmpeg_path, "-y"]
        
        # Add each clip as separate input
        for clip in clip_paths:
            cmd.extend(["-i", clip])
        
        # Build filter_complex concat
        n_clips = len(clip_paths)
        filter_parts = []
        
        # Scale all video streams
        for i in range(n_clips):
            filter_parts.append(f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=disable,setsar=1[v{i}]")
        
        # Concat video streams
        video_inputs = "".join([f"[v{i}]" for i in range(n_clips)])
        filter_parts.append(f"{video_inputs}concat=n={n_clips}:v=1:a=0[outv]")
        
        # Concat audio from story clips only (0,1,2 have audio, ending doesn't)
        # Add anullsrc for ending clip to maintain sync
        n_story = n_clips - 1  # Story clips count (exclude ending)
        if n_story > 0:
            audio_inputs = "".join([f"[{i}:a]" for i in range(n_story)])
            filter_parts.append(f"{audio_inputs}concat=n={n_story}:v=0:a=1[outa]")
        
        filter_str = ";".join(filter_parts)
        
        # Map both video and audio (if audio exists)
        cmd.extend([
            "-filter_complex", filter_str,
            "-map", "[outv]",
        ])
        
        if n_story > 0:
            cmd.extend(["-map", "[outa]"])
        
        cmd.extend([
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            concat_output
        ])
        
        print(f"[CharacterEdit] DEBUG: Concat cmd = {len(cmd)} args, {n_clips} clips ({n_story} with audio)")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if not os.path.exists(concat_output) or os.path.getsize(concat_output) == 0:
            print(f"[CharacterEdit] Concat failed: {result.stderr[:200] if result.stderr else 'unknown'}")
            return False
        
        print(f"[CharacterEdit] Concat output: {os.path.getsize(concat_output)} bytes")
        
        # DEBUG: Check concat duration with ffprobe
        try:
            ffprobe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0", concat_output
            ]
            probe_result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, timeout=30)
            concat_duration = float(probe_result.stdout.strip())
            print(f"[CharacterEdit] DEBUG: Concat duration = {concat_duration:.2f}s")
        except Exception as e:
            print(f"[CharacterEdit] DEBUG: Could not probe concat duration: {e}")
        
        # Step 4: Create ASS subtitle file for Karaoke-style word-by-word sync
        ass_subtitle_path = os.path.join(temp_dir, "subtitles.ass")
        has_subtitles = False
        if transcript_segments and moments:
            has_subtitles = create_ass_from_transcript(
                transcript_segments, moments, ass_subtitle_path, "Karaoke (Bounce)"
            )
        
        # Step 5: Apply final effects (filter, watermark, subtitles)
        vf_filters = []
        
        # Add subtitle first (bottom layer)
        if has_subtitles and os.path.exists(ass_subtitle_path):
            # Escape path for FFmpeg (Windows backslashes need escaping)
            ass_escaped = ass_subtitle_path.replace("\\", "/").replace(":", "\\:")
            vf_filters.append(f"subtitles='{ass_escaped}'")
        
        if filter_effect and filter_effect != "None":
            # Apply genre-matched video filters (match all filter names)
            filter_lower = filter_effect.lower()
            if "dark" in filter_lower or "terror" in filter_lower:
                vf_filters.append("curves=preset=darker,eq=contrast=1.1:saturation=0.9")
            elif "bright" in filter_lower or "inspire" in filter_lower:
                vf_filters.append("curves=preset=lighter,eq=contrast=1.1:saturation=1.1")
            elif "punch" in filter_lower or "viral" in filter_lower:
                vf_filters.append("eq=contrast=1.3:saturation=1.4:brightness=0.05")
            elif "pop" in filter_lower or "fun" in filter_lower:
                vf_filters.append("eq=saturation=1.5:contrast=1.2")
            elif "soft" in filter_lower or "wonder" in filter_lower:
                vf_filters.append("gblur=sigma=0.5,eq=contrast=0.95:saturation=1.1")
            elif "clean" in filter_lower or "pro" in filter_lower:
                vf_filters.append("eq=contrast=1.1:saturation=1.05")
            elif "magic" in filter_lower or "glow" in filter_lower:
                vf_filters.append("curves=preset=lighter,eq=saturation=1.3")
            elif "cyber" in filter_lower or "neon" in filter_lower:
                vf_filters.append("eq=contrast=1.4:saturation=1.6,curves=preset=darker")
            elif "meme" in filter_lower or "chaos" in filter_lower:
                vf_filters.append("eq=contrast=1.5:saturation=1.8:brightness=0.1")
            print(f"[CharacterEdit] Applying filter: {filter_effect}")
        
        # Final render with proper filter chain
        # Order: subtitle -> color filter -> watermark overlay
        has_watermark = watermark_path and os.path.exists(watermark_path)
        
        if vf_filters or has_watermark:
            input_args = [ffmpeg_path, "-y", "-i", concat_output]
            
            if has_watermark:
                # Add watermark as second input
                input_args.extend(["-i", watermark_path])
                
                # Build filter_complex: [0:v] -> filters -> [v1]; [1:v] scale -> [wm]; [v1][wm] overlay
                # Join vf_filters (subtitle, color) and apply to main video first
                if vf_filters:
                    base_filter = f"[0:v]{','.join(vf_filters)}[v1]"
                else:
                    base_filter = "[0:v]copy[v1]"
                
                # Scale watermark to max 200px height, center in bottom 420px bar
                # Position: x=(W-w)/2 (center), y=1500+(420-h)/2 ≈ 1610 for 200px height
                wm_scale = "[1:v]scale=-1:200[wm]"
                wm_overlay = "[v1][wm]overlay=(main_w-overlay_w)/2:1610"
                
                filter_complex = f"{base_filter};{wm_scale};{wm_overlay}"
                
                cmd = input_args + [
                    "-filter_complex", filter_complex,
                    "-c:v", "libx264", "-preset", "fast",
                    "-c:a", "aac",
                    output_path
                ]
            else:
                # No watermark - use simple -vf
                vf_string = ",".join(vf_filters)
                cmd = input_args + [
                    "-vf", vf_string,
                    "-c:v", "libx264", "-preset", "fast",
                    "-c:a", "aac",
                    output_path
                ]
        else:
            # Just copy
            cmd = [
                ffmpeg_path, "-y",
                "-i", concat_output,
                "-c", "copy",
                output_path
            ]
        
        print(f"[CharacterEdit] Final render...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"[CharacterEdit] Output created: {os.path.getsize(output_path)} bytes")
            return True
        else:
            print(f"[CharacterEdit] Final render failed: {result.stderr[:300] if result.stderr else 'unknown'}")
            return False
        
    except Exception as e:
        print(f"[CharacterEdit] Render error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup temp files
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except:
            pass


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

def generate_character_edit(
    video_path: str,
    output_path: str,
    character_name: Optional[str] = None,
    target_duration: float = 60.0,
    moment_count: int = 5,  # KEPT for backwards compatibility with main.py
    groq_api_key: str = "",  # For transcription
    gemini_api_key: str = "",  # For smart moment analysis
    transition: str = "Random",
    filter_effect: str = "None",
    watermark_path: Optional[str] = None,
    transcript_segments: Optional[List[Dict]] = None,
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
    progress_callback=None
) -> bool:
    """
    Main function to generate character edit video (trailer style).
    
    Story Structure:
    - INTRO (0-20%): Character introduction  
    - MID (20-60%): Development/conflict
    - CLIMAX (60-90%): Peak action moment
    - RAPID ENDING: Fast face montage
    
    Args:
        video_path: Path to input video
        output_path: Path for output video
        character_name: Optional name of character to focus on
        target_duration: Target duration of output (30-180 seconds, default 60)
        groq_api_key: Groq API key for Whisper transcription (REQUIRED)
        transition: Transition effect (Cut/Shake/Zoom/Flash/Random)
        filter_effect: Video filter to apply
        watermark_path: Optional watermark image path
        transcript_segments: Optional pre-transcribed segments (if not provided, will transcribe)
        ffmpeg_path: Path to ffmpeg binary
        ffprobe_path: Path to ffprobe binary
        progress_callback: Optional callback(progress: float, message: str)
    """
    
    def log(msg, progress=0):
        print(f"[CharacterEdit] {msg}")
        if progress_callback:
            progress_callback(progress, msg)
    
    log("Starting character edit generation...", 0.0)
    
    # Step 1: Get video duration
    duration = get_video_duration(video_path, ffprobe_path)
    if duration <= 0:
        log("Failed to get video duration", 0)
        return False
    
    log(f"Video duration: {duration:.1f}s", 0.1)
    
    # Step 2: Transcribe audio (if not already provided)
    if not transcript_segments and groq_api_key:
        log("Transcribing audio with Groq Whisper...", 0.15)
        transcript_segments = transcribe_video_audio(video_path, groq_api_key, ffmpeg_path)
        log(f"Transcribed {len(transcript_segments)} segments", 0.2)
    elif not transcript_segments:
        log("No Groq API key - skipping transcription", 0.15)
        transcript_segments = []
    
    # Step 3: Extract frames
    temp_dir = tempfile.mkdtemp(prefix="char_frames_")
    log("Extracting frames for face detection...", 0.25)
    frames = extract_frames(video_path, temp_dir, FACE_SAMPLE_RATE, ffmpeg_path)
    
    if not frames:
        log("Failed to extract frames", 0)
        return False
    
    log(f"Extracted {len(frames)} frames", 0.35)
    
    # Step 4: Detect faces
    log("Detecting faces in frames...", 0.4)
    
    if HAS_FACE_RECOGNITION:
        all_faces = detect_faces_in_frames(frames)
        log(f"Detected {len(all_faces)} faces", 0.55)
        
        # Step 5: Cluster faces
        log("Clustering faces by identity...", 0.58)
        clusters = cluster_faces(all_faces)
        log(f"Found {len(clusters)} unique identities", 0.6)
        
        # Step 6: Identify main character
        log("Identifying main character...", 0.65)
        char_id, character_faces = identify_main_character(
            clusters, character_name, transcript_segments, duration
        )
        log(f"Main character has {len(character_faces)} appearances", 0.7)
    else:
        # Fallback: create fake "moments" evenly distributed
        log("Face recognition not available - using distributed moments", 0.5)
        character_faces = []
        
        # Create synthetic FaceData at regular intervals
        for i, (frame_path, timestamp) in enumerate(frames):
            if i % 5 == 0:  # Every 5 seconds
                character_faces.append(FaceData(
                    timestamp=timestamp,
                    encoding=None,
                    frame_path=frame_path,
                    location=(0, 0, 0, 0)
                ))
    
    # Step 7: Use Gemini AI to analyze transcript and find key moments
    gemini_hints = {}
    if transcript_segments and gemini_api_key:
        log("Analyzing transcript with Gemini AI...", 0.72)
        gemini_hints = analyze_with_gemini(transcript_segments, duration, gemini_api_key)
        if gemini_hints:
            log(f"Gemini suggested: intro={gemini_hints.get('intro_time')}s, mid={gemini_hints.get('mid_time')}s, climax={gemini_hints.get('climax_time')}s", 0.74)
    
    # Step 8: Select story moments (trailer style) with Gemini hints
    log("Selecting story moments (INTRO → MID → CLIMAX → ENDING)...", 0.75)
    moments, ending_faces = select_story_moments(
        character_faces, duration, transcript_segments, target_duration,
        gemini_hints=gemini_hints  # Pass Gemini suggestions for smarter selection
    )
    log(f"Selected {len(moments)} story moments + {len(ending_faces)} faces for ending", 0.8)
    
    # Step 7: Create the edit
    log("Rendering character edit...", 0.85)
    success = create_character_edit(
        video_path, output_path, moments, ending_faces,
        transcript_segments, transition, filter_effect, watermark_path, ffmpeg_path,
        progress_callback=progress_callback  # Forward logs to UI
    )
    
    # Cleanup
    try:
        import shutil
        shutil.rmtree(temp_dir)
    except:
        pass
    
    if success:
        log(f"Character edit saved to {output_path}", 1.0)
    else:
        log("Failed to create character edit", 0)
    
    return success


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    print("Character Edit Engine")
    print(f"Face Recognition Available: {HAS_FACE_RECOGNITION}")
    print("Use generate_character_edit() to create character edits")
