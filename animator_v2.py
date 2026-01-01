"""
Kilat Code Clipper - AI Animator v2
====================================
Advanced 2.5D animation with:
- Prodia API (SD 1.5 + seed + img2img)
- Layer compositing (bg/char/fg)
- Parallax + Ken Burns effects
- Hardware-adaptive quality
- Clipper-style ASS subtitles

Target: 512x512 internal → upscale to 1080x1920
Optimized for 4GB RAM with CPU mode
"""

import os
import sys
import json
import time
import random
import asyncio
import subprocess
import requests
import urllib.parse
import platform
import psutil
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# Optional imports
try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    import edge_tts
except ImportError:
    edge_tts = None


# ============================================================================
# CONSTANTS
# ============================================================================
# Prodia API (Free tier: 1000/month, SD 1.5, img2img, seed)
PRODIA_API_URL = "https://api.prodia.com/v1"

# Image settings (Optimized for 9:16 Shorts - less upscaling needed)
IMAGE_WIDTH = 768   # Upgraded from 512
IMAGE_HEIGHT = 1344 # Upgraded from 768 - closer to 9:16 ratio
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

# Animation settings
DEFAULT_FPS = 24  # Smoother animation (was 12)
MAX_FPS = 30


# ============================================================================
# JSON CLEANUP HELPER
# ============================================================================
def fix_gemini_json(text: str) -> str:
    """
    Fix common JSON issues from LLM responses:
    - Smart/curly quotes to straight quotes
    - Mixed single/double quotes (normalize to double)
    - Embedded quotes in values ("word" -> 'word')
    - Trailing commas
    """
    import re
    
    # Replace smart/curly quotes
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    
    # Remove trailing commas
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    
    # Fix mixed quotes: convert Python dict format to JSON
    # Pattern: 'key': 'value' or 'key': "value" -> "key": "value"
    
    # Convert single-quoted keys to double-quoted: 'key': -> "key":
    text = re.sub(r"'([^']+)':\s*", r'"\1": ', text)
    
    # Convert single-quoted string values to double-quoted: : 'value' -> : "value"
    # But be careful not to mess up apostrophes inside strings
    text = re.sub(r":\s*'([^']*)'([,}\]])", r': "\1"\2', text)
    
    # Fix unquoted values from Groq LLaMA: "key": value, -> "key": "value",
    # Pattern: "key": text without quotes until comma or }
    text = re.sub(r'"([^"]+)":\s*([^",\[\]{}][^,\[\]{}]*?)(\s*[,}\]])', r'"\1": "\2"\3', text)
    
    # Fix embedded quotes in JSON string values
    # Process line by line for remaining issues
    fixed_lines = []
    for line in text.split('\n'):
        line = line.rstrip('\r')
        # Check if line has a JSON string value pattern with embedded quotes
        if '": "' in line:
            # Skip if already clean
            if line.count('"') > 4:  # More than key-value pair quotes
                parts = line.split('": "', 1)
                if len(parts) == 2:
                    key_part = parts[0] + '": "'
                    value_part = parts[1]
                    # Find end of value
                    if value_part.endswith('",'):
                        value_content = value_part[:-2]
                        suffix = '",'
                    elif value_part.endswith('"'):
                        value_content = value_part[:-1] 
                        suffix = '"'
                    else:
                        value_content = value_part
                        suffix = ''
                    # Replace embedded quotes with single quotes
                    value_content = value_content.replace('"', "'")
                    line = key_part + value_content + suffix
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)


def detect_gpu_encoder(ffmpeg_path: str = "ffmpeg") -> tuple:
    """
    Auto-detect available GPU hardware encoder.
    Returns: (encoder_name, encoder_preset)
    
    Priority: NVIDIA NVENC > Intel QSV > AMD AMF > CPU libx264
    
    GPU encoding can be 5-10x faster than CPU encoding.
    """
    import subprocess
    
    # Test encoders in priority order
    encoders = [
        # (encoder, test_args, preset)
        ("h264_nvenc", ["-c:v", "h264_nvenc", "-f", "null", "-"], "p4"),  # NVIDIA
        ("h264_qsv", ["-c:v", "h264_qsv", "-f", "null", "-"], "medium"),  # Intel
        ("h264_amf", ["-c:v", "h264_amf", "-f", "null", "-"], "balanced"), # AMD
    ]
    
    for encoder, test_args, preset in encoders:
        try:
            # Test if encoder is available by trying a null encode
            cmd = [
                ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1",
            ] + test_args
            
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0:
                print(f"GPU Encoder detected: {encoder}")
                return (encoder, preset)
        except Exception:
            continue
    
    # Fallback to CPU
    print("No GPU encoder found, using CPU (libx264)")
    return ("libx264", "medium")  # Changed from 'slow' to 'medium' for faster encoding


def calculate_optimal_scenes(transcript: str, audio_duration: float = 0) -> int:
    """
    ⚠️ DEPRECATED - This function is NOT USED!
    Scene count is now controlled directly by UI slider (1-100 range).
    Keeping for potential future auto-calculation feature.
    
    Original purpose:
    Calculate optimal number of scenes based on content.
    - ~3-4 seconds per scene is ideal
    - If audio duration available, use that; else estimate from word count
    """
    if audio_duration > 0:
        # Use audio duration: ~3.5 seconds per scene
        scenes = int(audio_duration / 3.5)
    else:
        # Estimate from word count: ~100 words = 30 seconds = 8-10 scenes
        words = len(transcript.split())
        scenes = max(5, min(15, words // 25))  # ~25 words per scene
    
    # Clamp to valid range
    return max(5, min(15, scenes))


# ============================================================================
# DATA CLASSES
# ============================================================================
@dataclass
class HardwareProfile:
    """System hardware capabilities"""
    ram_gb: float
    cpu_cores: int
    has_gpu: bool
    gpu_name: str = ""
    quality: str = "low"  # low, medium, high, ultra
    
    def __post_init__(self):
        if self.has_gpu:
            self.quality = "ultra"
        elif self.ram_gb >= 16:
            self.quality = "high"
        elif self.ram_gb >= 8:
            self.quality = "medium"
        else:
            self.quality = "low"


@dataclass
class SceneData:
    """Data for a single animated scene"""
    index: int
    narration: str
    visual_prompt: str
    character_desc: str
    background_desc: str
    mood: str
    camera: str
    image_path: Optional[str] = None
    audio_path: Optional[str] = None
    duration: float = 0.0


@dataclass 
class AnimationLayers:
    """Layer structure for compositing"""
    background: Optional[str] = None
    character: Optional[str] = None
    foreground: Optional[str] = None


# ============================================================================
# HARDWARE DETECTION
# ============================================================================
def detect_hardware() -> HardwareProfile:
    """Scan system hardware and return capability profile"""
    try:
        # RAM
        ram_bytes = psutil.virtual_memory().total
        ram_gb = ram_bytes / (1024 ** 3)
        
        # CPU cores
        cpu_cores = psutil.cpu_count(logical=False) or 2
        
        # GPU detection (basic)
        has_gpu = False
        gpu_name = ""
        
        try:
            # Check for NVIDIA GPU
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0 and result.stdout.strip():
                has_gpu = True
                gpu_name = result.stdout.strip().split('\n')[0]
        except FileNotFoundError:
            pass
        
        profile = HardwareProfile(
            ram_gb=round(ram_gb, 1),
            cpu_cores=cpu_cores,
            has_gpu=has_gpu,
            gpu_name=gpu_name
        )
        
        print(f"DEBUG: Hardware detected - RAM: {ram_gb:.1f}GB, CPU: {cpu_cores} cores, GPU: {gpu_name if has_gpu else 'None'}")
        print(f"DEBUG: Quality preset: {profile.quality}")
        
        return profile
        
    except Exception as e:
        print(f"Hardware detection error: {e}")
        return HardwareProfile(ram_gb=4, cpu_cores=2, has_gpu=False)


# ============================================================================
# GENRE & STYLE CONFIGURATIONS (Enhanced with detailed narration presets)
# ============================================================================

# Simplified GENRES - TONE only, with EXAMPLES to show delivery style
# Genre affects HOW the story is told, not WHICH words to use
GENRES = {
    "Motivational": {
        "tone": "uplifting, confident, empowering",
        "style": "Build momentum. Mix facts with inspiration. End with insight.",
        "example": "This simple habit changed everything. In just 30 days, researchers saw remarkable results.",
        # --- Cold Open Storytelling ---
        "narrative_structure": "cold_open",
        "cold_open_instruction": "Start with the BREAKTHROUGH or SUCCESS moment from transcript. Then explain the journey that led there.",
        "hook_style": "Bayangkan kalau kamu bisa...",
        "transition_phrases": ["Tapi tunggu", "Dan yang terjadi selanjutnya", "Inilah rahasianya"],
        "emotional_arc": ["triumph", "curiosity", "understanding", "inspiration"],
        "emoji": "💪",
        # --- Genre-Specific Language ---
        "power_words_id": ["Bayangkan,", "Percaya gak,", "Ini buktinya,", "Yang luar biasa,"],
        "power_words_en": ["Imagine,", "Believe it or not,", "Here's proof—", "What's amazing is,"],
        "tone_instruction_id": "Narator inspiratif. Bangun semangat tanpa bahasa terlalu gaul.",
        "tone_instruction_en": "Inspirational narrator. Build enthusiasm.",
        # --- Pronoun and Narration Style ---
        "pronoun_style": "semi-formal",  # Pakai Aku/Kamu, tidak Gue/Lu
        "forbidden_words_id": ["gue", "lu", "anjir", "gokil"],
        "narration_example_id": '''[THE HOOK] "Kebenaran memiliki caranya sendiri untuk muncul. Bahkan dari dalam perut seekor hiu di kedalaman samudra."
[THE DETAIL] "Lengan itu membawa tanda—sebuah tato yang menjadi identitas. Jejak yang tidak mudah dihapus."
[THE REALIZATION] "Potongannya terlalu rapi untuk serangan hewan. Ada tangan manusia di balik kegelapan ini."
[THE CLIMAX] "Korban memilih jalan gelap. Tapi dalam kejatuhannya, ia meninggalkan petunjuk bagi keadilan."
[THE ENDING] "Meski pelaku tak diadili, kisah ini mengingatkan: kebenaran tak bisa dikubur selamanya."''',
        "narration_example_en": '''[THE HOOK] "Truth has a way of rising to the surface. Even from the belly of a shark in the depths of the ocean."
[THE DETAIL] "That arm carried a mark—a tattoo that became an identity. A trail that couldn't be erased."
[THE REALIZATION] "The cut was too clean for an animal attack. There was a human hand behind this darkness."
[THE CLIMAX] "The victim chose a dark path. But in his fall, he left clues for justice."
[THE ENDING] "Though the killer was never tried, this story reminds us: truth cannot be buried forever."''',
    },
    "Horror": {
        "tone": "tense, atmospheric, suspenseful",
        "style": "Build suspense slowly. Use sensory details. Create unease.",
        "example": "Something was wrong. The air felt heavy. And then, they noticed the shadow in the corner.",
        # --- Cold Open Storytelling ---
        "narrative_structure": "cold_open",
        "cold_open_instruction": "Start with the TERRIFYING moment or disturbing revelation from transcript. Then build context.",
        "hook_style": "Malam itu, sesuatu yang mengerikan terjadi...",
        "transition_phrases": ["Tapi mereka tidak tahu", "Di balik kegelapan", "Dan kemudian—"],
        "emotional_arc": ["terror", "curiosity", "dread", "understanding"],
        "emoji": "😱",
        # --- Genre-Specific Language ---
        "power_words_id": ["Tiba-tiba,", "Perlahan,", "Di balik kegelapan,", "Tanpa disadari,"],
        "power_words_en": ["Suddenly,", "Slowly,", "In the darkness,", "Without warning,"],
        "tone_instruction_id": "Narator horor serius. Atmosferik dan menegangkan. JANGAN pakai bahasa gaul.",
        "tone_instruction_en": "Serious horror narrator. Atmospheric and tense. NO casual language.",
        # --- NEW: Pronoun and Narration Style ---
        "pronoun_style": "formal",  # formal = TIDAK pakai Gue/Lu, impersonal
        "forbidden_words_id": ["gue", "lu", "bro", "banget", "anjir", "sumpah", "gokil", "wkwk"],
        "narration_example_id": '''[THE HOOK] "Sesuatu yang mengerikan dipaksa naik dari kegelapan. Seekor hiu memuntahkan potongan lengan manusia... tepat di depan pengunjung yang terpaku."
[THE DETAIL] "Lengan itu pucat, dihiasi tato aneh. Polisi menemukan fakta yang lebih mengerikan: dagingnya tidak tercabik gigi hiu."
[THE REALIZATION] "Potongannya terlalu bersih. Seseorang telah menggunakan pisau tajam untuk memutilasinya..."
[THE CLIMAX] "Tato itu milik seorang kriminal yang hilang. Jejaknya mengarah pada sosok yang bersedia melakukan apa saja demi bungkam."
[THE ENDING] "Saksi kunci tewas ditembak sebelum bicara. Kasus ditutup, rahasianya terkubur selamanya."''',
        "narration_example_en": '''[THE HOOK] "Something terrifying was forced up from the darkness. A shark regurgitated a human arm... right in front of horrified visitors."
[THE DETAIL] "The arm was pale, marked with a strange tattoo. Police discovered something more chilling: the flesh wasn't torn by shark teeth."
[THE REALIZATION] "The cut was too clean. Someone had used a sharp knife to sever it..."
[THE CLIMAX] "That tattoo belonged to a missing criminal. The trail led to someone willing to do anything to keep secrets."
[THE ENDING] "The key witness was shot dead before he could talk. Case closed, the secret buried forever."''',
    },
    "Comedy": {
        "tone": "playful, witty, light-hearted",
        "style": "Add light humor. Use irony and playful observations. Keep facts but make them entertaining.",
        "example": "Surprise! Every time you flush, you're basically hosting a bacteria party. Free admission for all germs.",
        # --- Cold Open Storytelling ---
        "narrative_structure": "cold_open",
        "cold_open_instruction": "Start with the FUNNIEST or most ABSURD fact from transcript. Lead with the punchline!",
        "hook_style": "Tau gak sih kenapa...",
        "transition_phrases": ["Plot twist:", "Dan tau gak apa yang terjadi?", "Tapi tunggu—"],
        "emotional_arc": ["laughter", "curiosity", "amusement", "satisfaction"],
        "emoji": "😂",
        # --- Genre-Specific Language ---
        "power_words_id": ["Gila,", "Sumpah,", "Anjir,", "Woy,", "Tau gak,"],
        "power_words_en": ["Dude,", "Bro,", "No way,", "Get this—", "You know what,"],
        "tone_instruction_id": "Kayak curhat lucu ke temen. Santai dan menghibur.",
        "tone_instruction_en": "Like a funny friend telling a story. Casual and entertaining.",
        # --- Pronoun and Narration Style ---
        "pronoun_style": "casual",  # casual = pakai Gue/Lu, santai
        "forbidden_words_id": [],  # Comedy boleh pakai semua
        "narration_example_id": '''[THE HOOK] "Jadi gini ceritanya... ada hiu yang makan lengan orang, terus dia sendiri dimakan sama hiu lain. Double L banget!"
[THE DETAIL] "Pas di akuarium, hiu itu muntah dong. Keluar lengan pake tato. Pengunjung? Trauma seumur hidup."
[THE REALIZATION] "Polisi dateng, kok gak kegigit ini? Potongannya rapi kayak dipotong sama Gordon Ramsay."
[THE CLIMAX] "Tato-nya cocok sama preman yang lagi kabur. Dia lagi malak orang. Karma delivered express!"
[THE ENDING] "Tersangkanya mau ngaku, tapi ditembak duluan. Kasus closed. Moral: jangan malak orang yang punya koneksi hiu."''',
        "narration_example_en": '''[THE HOOK] "So here's the story... a shark ate someone's arm, then got eaten by ANOTHER shark. Double L!"
[THE DETAIL] "At the aquarium, the shark puked it up. Out comes an arm with a tattoo. Visitors? Traumatized for life."
[THE REALIZATION] "Police show up—wait, this wasn't bitten? The cut is clean like Gordon Ramsay did it."
[THE CLIMAX] "Tattoo matches a criminal on the run. He was blackmailing someone. Karma delivered express!"
[THE ENDING] "Suspect was ready to confess, but got shot first. Case closed. Moral: don't blackmail people with shark connections."''',
    },
    "Children's Story": {
        "tone": "warm, friendly, gentle",
        "style": "Simple words. Short sentences. Positive and encouraging.",
        "example": "One day, something amazing happened! A tiny seed grew into a big, beautiful flower.",
        # --- Cold Open Storytelling ---
        "narrative_structure": "cold_open",
        "cold_open_instruction": "Start with the WONDERFUL or MAGICAL moment from transcript. Then tell how it happened.",
        "hook_style": "Suatu hari, di sebuah tempat yang jauh...",
        "transition_phrases": ["Tapi ada masalah", "Lalu dia punya ide!", "Dan akhirnya—"],
        "emotional_arc": ["wonder", "curiosity", "understanding", "joy"],
        "emoji": "🌟",
        # --- Genre-Specific Language ---
        "power_words_id": ["Suatu hari,", "Wah,", "Asyik,", "Hebat,", "Lalu,"],
        "power_words_en": ["Once upon a time,", "Wow,", "Amazing,", "Great,", "Then,"],
        "tone_instruction_id": "Narator cerita anak. Lembut, hangat, kata-kata sederhana.",
        "tone_instruction_en": "Children's story narrator. Gentle, warm, simple words.",
        # --- Pronoun and Narration Style ---
        "pronoun_style": "formal",  # Tidak pakai gaul
        "forbidden_words_id": ["gue", "lu", "bro", "anjir", "sumpah", "gila"],
        "narration_example_id": '''[THE HOOK] "Di sebuah akuarium yang besar, ada seekor hiu yang perutnya terasa sangat aneh. Dia makan sesuatu yang tidak seharusnya!"
[THE DETAIL] "Hiu itu mengeluarkan sesuatu yang sangat aneh. Penjaga akuarium langsung memanggil polisi untuk membantu."
[THE REALIZATION] "Polisi yang pintar menemukan petunjuk! Ada gambar khusus yang membantu mereka mencari tahu."
[THE CLIMAX] "Dengan semangat pantang menyerah, polisi terus mencari jawaban dan menemukan orang yang bisa membantu."
[THE ENDING] "Tapi ceritanya belum selesai. Siapa yang tahu apa yang sebenarnya terjadi?"''',
        "narration_example_en": '''[THE HOOK] "In a big, beautiful aquarium, there was a shark with a very strange tummy. It ate something it shouldn't have!"
[THE DETAIL] "The shark let out something very strange. The kind helpers at the aquarium called the police right away."
[THE REALIZATION] "The clever police found a clue! There was a special picture that helped them find answers."
[THE CLIMAX] "With never-give-up spirit, the police kept searching and found someone who could help."
[THE ENDING] "But the story isn't over yet. Who knows what really happened?"''',
    },
    "Documentary": {
        "tone": "objective, informative, authoritative",
        "style": "State facts clearly. Explain cause and effect. Be neutral and educational.",
        "example": "Studies show that 60% of hand dryers contain bacteria. The particles spread when activated.",
        # --- Cold Open Storytelling ---
        "narrative_structure": "cold_open",
        "cold_open_instruction": "Start with the most SURPRISING or IMPORTANT finding from transcript. Then explain the evidence.",
        "hook_style": "80% orang tidak tahu tentang ini...",
        "transition_phrases": ["Data menunjukkan", "Artinya", "Implikasinya adalah"],
        "emotional_arc": ["surprise", "curiosity", "understanding", "awareness"],
        "emoji": "📊",
        # --- Genre-Specific Language ---
        "power_words_id": ["Menurut penelitian,", "Faktanya,", "Data menunjukkan,", "Yang menarik,"],
        "power_words_en": ["Research shows,", "In fact,", "Studies indicate,", "Interestingly,"],
        "tone_instruction_id": "Narator dokumenter profesional. Objektif, informatif, berwibawa.",
        "tone_instruction_en": "Professional documentary narrator. Objective and authoritative.",
        # --- Pronoun and Narration Style ---
        "pronoun_style": "formal",  # Tidak pakai gaul, objektif
        "forbidden_words_id": ["gue", "lu", "bro", "anjir", "banget", "sumpah", "gila"],
        "narration_example_id": '''[THE HOOK] "Pada tahun 1935, insiden tak terduga terjadi di akuarium Sydney. Seekor hiu memuntahkan potongan lengan manusia di hadapan pengunjung."
[THE DETAIL] "Lengan tersebut memiliki tato khas. Hasil otopsi menunjukkan daging itu bukan hasil gigitan—melainkan sayatan tajam."
[THE REALIZATION] "Tim forensik menyimpulkan: seseorang telah memotong lengan ini dengan alat tajam, kemungkinan saat korban masih hidup."
[THE CLIMAX] "Tato itu mengarah pada identitas seorang kriminal yang dilaporkan hilang. Ia diketahui tengah memeras seseorang."
[THE ENDING] "Tersangka setuju bersaksi, namun sebelum persidangan, ia ditemukan tewas tertembak. Kasus ini menjadi cold case ikonik."''',
        "narration_example_en": '''[THE HOOK] "In 1935, an unexpected incident occurred at Sydney Aquarium. A shark regurgitated a human arm segment in front of visitors."
[THE DETAIL] "The arm bore distinctive tattoos. Autopsy results revealed the flesh wasn't torn by teeth—it was a clean cut."
[THE REALIZATION] "Forensic teams concluded: someone had severed this arm with a sharp instrument, possibly while the victim was still alive."
[THE CLIMAX] "The tattoo led to the identity of a missing criminal. He was known to be blackmailing someone."
[THE ENDING] "The suspect agreed to testify, but before trial, he was found shot dead. This became an iconic cold case."''',
    },
    "Fairy Tale": {
        "tone": "whimsical, enchanting, magical",
        "style": "Describe wonder vividly. Classic storytelling structure.",
        "example": "Long ago, in a kingdom far away, there lived a brave hero with a special gift.",
        # --- Cold Open Storytelling ---
        "narrative_structure": "cold_open",
        "cold_open_instruction": "Start with the CLIMAX or most MAGICAL moment from transcript. Then reveal the journey.",
        "hook_style": "Alkisah, di sebuah kerajaan yang jauh...",
        "transition_phrases": ["Namun sang pahlawan", "Dengan keberanian", "Dan pada akhirnya"],
        "emotional_arc": ["wonder", "curiosity", "excitement", "warmth"],
        "emoji": "✨",
        # --- Genre-Specific Language ---
        "power_words_id": ["Alkisah,", "Konon,", "Di negeri antah berantah,", "Pada suatu masa,"],
        "power_words_en": ["Long ago,", "Legend has it,", "In a faraway land,", "Once upon a time,"],
        "tone_instruction_id": "Narator dongeng klasik. Magis, mempesona, bahasa sastra.",
        "tone_instruction_en": "Classic fairy tale narrator. Magical and enchanting.",
        # --- Pronoun and Narration Style ---
        "pronoun_style": "formal",  # Bahasa sastra, formal
        "forbidden_words_id": ["gue", "lu", "bro", "anjir", "banget"],
        "narration_example_id": '''[THE HOOK] "Alkisah, di kerajaan bawah laut, seekor hiu raksasa menyimpan rahasia kelam dalam perutnya. Rahasia itu akhirnya terbongkar."
[THE DETAIL] "Dari dalam perut sang hiu, muncul tanda misterius—lambang yang berkilau di bawah cahaya kristal akuarium."
[THE REALIZATION] "Para penjaga hukum dari kerajaan daratan menyadari: ini bukan perbuatan makhluk laut, tapi tangan manusia."
[THE CLIMAX] "Lambang itu menuntun pada pria yang hidup dalam bayang-bayang, mencuri rahasia orang lain untuk kekayaannya."
[THE ENDING] "Namun sang penjahat lenyap sebelum keadilan menjemputnya, meninggalkan misteri abadi yang berbisik di antara ombak."''',
        "narration_example_en": '''[THE HOOK] "Long ago, in an underwater kingdom, a great shark held a dark secret in its belly. That secret was finally revealed."
[THE DETAIL] "From within the shark emerged a mysterious mark—a symbol that glimmered beneath the aquarium's crystal light."
[THE REALIZATION] "The guardians of law from the land kingdom realized: this was not the work of a sea creature, but a human hand."
[THE CLIMAX] "The symbol led to a man who lived in shadows, stealing secrets for his own fortune."
[THE ENDING] "But the villain vanished before justice could find him, leaving an eternal mystery that whispers among the waves."''',
    },
    "Sci-Fi": {
        "tone": "futuristic, thought-provoking, awe-inspiring",
        "style": "Describe advanced concepts. Create wonder about technology.",
        "example": "By 2050, this technology will revolutionize everything. What once seemed impossible is now reality.",
        # --- Cold Open Storytelling ---
        "narrative_structure": "cold_open",
        "cold_open_instruction": "Start with the most MIND-BLOWING technological fact from transcript. Then explain how.",
        "hook_style": "Di tahun 2050, dunia akan berubah...",
        "transition_phrases": ["Yang dulunya mustahil", "Teknologi ini memungkinkan", "Bayangkan"],
        "emotional_arc": ["awe", "curiosity", "understanding", "excitement"],
        "emoji": "🚀",
        # --- Genre-Specific Language ---
        "power_words_id": ["Ternyata,", "Yang mengejutkan,", "Di masa depan,", "Teknologi ini,"],
        "power_words_en": ["Turns out,", "Surprisingly,", "In the future,", "This technology,"],
        "tone_instruction_id": "Narator dokumenter futuristik. Teknis tapi kagum.",
        "tone_instruction_en": "Futuristic documentary narrator. Technical but awe-struck.",
        # --- Pronoun and Narration Style ---
        "pronoun_style": "formal",  # Teknis, futuristik
        "forbidden_words_id": ["gue", "lu", "bro", "anjir"],
        "narration_example_id": '''[THE HOOK] "Unit forensik biomarine mendeteksi anomali: spesimen organik manusia ter-regurgitasi oleh predator apex di habitat terkontrol."
[THE DETAIL] "Analisis molekuler mengkonfirmasi: luka bukan hasil serangan biologis. Pola sayatan konsisten dengan blade mono-molecular."
[THE REALIZATION] "Biomarker pada spesimen teridentifikasi. Subject: criminal record aktif, status: MISSING."
[THE CLIMAX] "Algoritma prediktif mengarah pada satu tersangka. Subject bersedia kooperasi. Extraction data dijadwalkan."
[THE ENDING] "Subject terminated via projectile sebelum data upload. File status: CORRUPTED. Case: UNSOLVED."''',
        "narration_example_en": '''[THE HOOK] "Biomarine forensics unit detected anomaly: organic human specimen regurgitated by apex predator in controlled habitat."
[THE DETAIL] "Molecular analysis confirmed: wound inconsistent with biological attack. Incision pattern matches mono-molecular blade."
[THE REALIZATION] "Biomarkers on specimen identified. Subject: active criminal record, status: MISSING."
[THE CLIMAX] "Predictive algorithms converge on single suspect. Subject agreed to cooperate. Data extraction scheduled."
[THE ENDING] "Subject terminated via projectile before data upload. File status: CORRUPTED. Case designation: UNSOLVED."''',
    },
    "Viral Shorts": {
        "tone": "engaging, conversational, informative",
        "style": "Hook immediately. Present facts engagingly. End with insight.",
        "example": "You won't believe this. That everyday habit? It's actually changing your brain. Here's how.",
        # --- Cold Open Storytelling ---
        "narrative_structure": "cold_open",
        "cold_open_instruction": "Start with the most SHOCKING or UNEXPECTED fact from transcript. Grab attention instantly!",
        "hook_style": "Kamu tidak akan percaya ini...",
        "transition_phrases": ["Ternyata", "Yang lebih gila lagi", "Dan ini faktanya"],
        "emotional_arc": ["shock", "curiosity", "understanding", "share-worthy"],
        "emoji": "🔥",
        # --- Genre-Specific Language ---
        "power_words_id": ["Gue kaget,", "Lu gak akan percaya,", "Ternyata,", "Yang gila,"],
        "power_words_en": ["I was shocked,", "You won't believe,", "Here's the thing—", "What's crazy is,"],
        "tone_instruction_id": "Content creator viral. Engaging, punchy, bikin share.",
        "tone_instruction_en": "Viral content creator. Engaging, punchy, shareable.",
        # --- Pronoun and Narration Style ---
        "pronoun_style": "casual",  # Pakai Gue/Lu, viral style
        "forbidden_words_id": [],  # Viral boleh pakai semua
        "narration_example_id": '''[THE HOOK] "GUYS! Lo gak bakal percaya ini. Ada hiu yang MUNTAH lengan manusia di akuarium! PLOT TWIST-nya bikin merinding!"
[THE DETAIL] "Lengannya ada TATO! Tapi yang bikin gila, potongannya RAPI BANGET. Bukan digigit hiu—dipotong pake PISAU!"
[THE REALIZATION] "Polisi langsung gerak. Mereka sadar ini BUKAN kecelakaan. Ada PEMBUNUH di balik semua ini!"
[THE CLIMAX] "Tato-nya cocok sama orang yang HILANG. Tersangkanya KETEMU dan mau ngaku!"
[THE ENDING] "TAPI sebelum sidang, dia DITEMBAK MATI! Kasus ditutup! Like dan share kalau kalian penasaran!"''',
        "narration_example_en": '''[THE HOOK] "GUYS! You won't BELIEVE this. A shark PUKED UP a human arm at an aquarium! The PLOT TWIST will give you chills!"
[THE DETAIL] "The arm had a TATTOO! But here's the CRAZY part—the cut was CLEAN. Not bitten—SLICED with a KNIFE!"
[THE REALIZATION] "Police moved FAST. They realized this was NO accident. There's a KILLER behind all this!"
[THE CLIMAX] "The tattoo matched a MISSING person. They FOUND the suspect and he was ready to TALK!"
[THE ENDING] "BUT before trial, he got SHOT DEAD! Case closed! Like and share if you want to know more!"''',
    },
    "Brainrot": {
        "tone": "chaotic, ironic, unhinged, Gen-Z humor, absurd, over-the-top",
        "style": "Random tangents. Meme references. Exaggerated reactions. Fast-paced. Break fourth wall.",
        "example": "Bro literally woke up and chose violence. Like WHY is the king giving seeds to random kids?? That's lowkey sus. Anyway so basically this dude—wait hold up—this is actually crazy. No cap this might be the most unhinged thing ever.",
        # --- Cold Open Storytelling ---
        "narrative_structure": "cold_open",
        "cold_open_instruction": "Start with the most UNHINGED or INSANE moment from transcript. Maximum chaos!",
        "hook_style": "BRO THIS IS ACTUALLY INSANE—",
        "transition_phrases": ["Anyway so basically—", "Wait hold up—", "No but like—", "BRUH—"],
        "emotional_arc": ["chaos", "confusion", "laughter", "more chaos"],
        "emoji": "💀",
        # --- Genre-Specific Language ---
        "power_words_id": ["BRO,", "LITERALLY,", "NO CAP,", "HOLD UP—"],
        "power_words_en": ["BRO,", "LITERALLY,", "NO CAP,", "HOLD UP—"],
        "tone_instruction_id": "Chaotic Gen-Z energy. Over-the-top. Maximum absurd.",
        "tone_instruction_en": "Chaotic Gen-Z energy. Over-the-top reactions.",
        # --- Pronoun and Narration Style ---
        "pronoun_style": "casual",  # Full Gen-Z chaos
        "forbidden_words_id": [],  # Everything allowed
        "narration_example_id": '''[THE HOOK] "BRO a shark literally threw up a whole human arm 💀 and it STILL had a tattoo no cap this is unhinged"
[THE DETAIL] "The edge was clean af... someone really said lemme just slice this real quick 😭 absolute cinema"
[THE REALIZATION] "Police showed up and were like this ain't shark behavior fr fr 🗿"
[THE CLIMAX] "Tattoo matched a missing criminal who was blackmailing someone. Dude got caught in 4K!"
[THE ENDING] "BUT THEN he got unalived before trial 💀 case closed. Most sus unsolved case ever honestly"''',
    },
    "Brainrot ID": {
        "tone": "chaotic, ironic, unhinged, Gen-Z humor, absurd, over-the-top",
        "style": "Random tangents. Meme references. Exaggerated reactions. Fast-paced. Bahasa gaul.",
        "example": "Guys ini literally gila sih. Kayak KENAPA rajanya kasih biji ke anak-anak random?? Sus banget anjir. Anyway jadi basically nih—tunggu bentar—ini actually gila. No cap ini mungkin hal paling absurd yang pernah gue liat.",
        # --- Cold Open Storytelling ---
        "narrative_structure": "cold_open",
        "cold_open_instruction": "Mulai dengan momen paling GILA atau ABSURD dari transcript. Langsung chaos!",
        "hook_style": "GUYS INI LITERALLY GILA SIH—",
        "transition_phrases": ["Anyway jadi basically—", "Tunggu bentar—", "No tapi kayak—", "ANJIR—"],
        "emotional_arc": ["chaos", "confusion", "laughter", "more chaos"],
        "emoji": "💀",
        # --- Genre-Specific Language ---
        "power_words_id": ["ANJIR,", "BRO,", "LITERALLY,", "GILA SIH—"],
        "power_words_en": ["BRO,", "LITERALLY,", "NO CAP,", "INSANE—"],
        "tone_instruction_id": "Chaotic Gen-Z Indo. Over-the-top. Bahasa gaul total.",
        "tone_instruction_en": "Chaotic Gen-Z energy. Over-the-top reactions.",
        # --- Pronoun and Narration Style ---
        "pronoun_style": "casual",  # Full Gen-Z chaos Indonesia
        "forbidden_words_id": [],  # Everything allowed for brainrot
        "narration_example_id": '''[THE HOOK] "ANJIR! Hiu nya muntah lengan orang WKWK 💀 tato-nya masih kelihatan. Sus banget vibes-nya!"
[THE DETAIL] "Gila sih, potongannya rapi parah. Kayak dipotong pake pisau beneran. Bukan vibes hiu sama sekali."
[THE REALIZATION] "Polisi dateng, langsung curiga. Ini bukan serangan hiu. Ada manusia di balik semua ini."
[THE CLIMAX] "Tato-nya match sama orang yang ilang. Dia lagi malak orang sebelum kabur!"
[THE ENDING] "TAPI sebelum ngomong, dia ditembak mati 💀 Kasusnya tutup. Forever sus."''',
    }
}

# Visual Styles - Supports both Pollinations (Flux) and Prodia (SD 1.5)
# Each style has:
#   - model: for Pollinations (flux)
#   - prodia_model: for Prodia SD 1.5
#   - suffix: prompt suffix
#   - negative: negative prompt
VISUAL_STYLES = {
    # === ANIME & CARTOON ===
    "Ghibli Anime": {
        "model": "flux",
        "prodia_model": "meinamix_meinaV11.safetensors [b56ce717]",
        "suffix": "studio ghibli style, anime, watercolor, vivid colors, high contrast, beautiful scenery, miyazaki style",
        "negative": "realistic, photo, 3d render, ugly, deformed"
    },
    "Pixar 3D": {
        "model": "flux",
        "prodia_model": "dreamshaper_8.safetensors [9d40847d]",
        "suffix": "pixar style, 3d animation, vibrant colors, cute character, disney pixar, smooth render",
        "negative": "anime, realistic photo, dark, scary"
    },
    "2D Cartoon": {
        "model": "flux",
        "prodia_model": "toonyou_beta6.safetensors [980f6b15]",
        "suffix": "cartoon style, 2d animation, bold outlines, flat colors, vector art, clean lines",
        "negative": "realistic, photo, 3d, anime"
    },
    "Chibi Kawaii": {
        "model": "flux",
        "prodia_model": "meinamix_meinaV11.safetensors [b56ce717]",
        "suffix": "chibi style, kawaii, super deformed, cute, big head, small body, pastel colors, adorable, japanese cute style",
        "negative": "realistic, scary, dark, detailed"
    },
    "Manga": {
        "model": "flux",
        "prodia_model": "anythingV5_PrtRE.safetensors [893e49b9]",
        "suffix": "manga style, japanese comic, black and white, screentone, dramatic shading, action lines, shounen manga",
        "negative": "color, photo, 3d, western comic"
    },
    
    # === REALISTIC & CINEMATIC ===
    "Realistic": {
        "model": "flux",
        "prodia_model": "deliberate_v3.safetensors [afd9d2d4]",
        "suffix": "photorealistic, cinematic lighting, detailed, 8k quality, photography, lifelike", 
        "negative": "cartoon, anime, drawing, painting"
    },
    "Cyberpunk": {
        "model": "flux",
        "prodia_model": "deliberate_v3.safetensors [afd9d2d4]",
        "suffix": "cyberpunk 2077 style, neon lights, futuristic city, night scene, rain, hologram, blade runner aesthetic",
        "negative": "daylight, nature, cartoon, anime"
    },
    "Dark Fantasy": {
        "model": "flux",
        "prodia_model": "deliberate_v3.safetensors [afd9d2d4]",
        "suffix": "dark fantasy art, gothic, gritty, atmospheric, moody lighting, epic fantasy, dark souls aesthetic, dramatic shadows",
        "negative": "bright, cheerful, cartoon, cute"
    },
    "Noir Comic": {
        "model": "flux",
        "prodia_model": "deliberate_v3.safetensors [afd9d2d4]",
        "suffix": "sin city style, noir comic, high contrast black and white, dramatic shadows, film noir, graphic novel, frank miller style",
        "negative": "color, bright, cheerful, anime"
    },
    
    # === ARTISTIC & PAINTERLY ===
    "Watercolor": {
        "model": "flux",
        "prodia_model": "meinamix_meinaV11.safetensors [b56ce717]",
        "suffix": "watercolor painting style, soft edges, artistic brush strokes, pastel colors, delicate, traditional art",
        "negative": "photo, 3d render, digital art, sharp edges"
    },
    "Oil Painting": {
        "model": "flux",
        "prodia_model": "deliberate_v3.safetensors [afd9d2d4]",
        "suffix": "oil painting style, classical painting, rich textures, impasto, renaissance art, museum quality, rembrandt lighting",
        "negative": "photo, digital, flat colors, cartoon"
    },
    "Sketch": {
        "model": "flux",
        "prodia_model": "deliberate_v3.safetensors [afd9d2d4]",
        "suffix": "pencil sketch, hand drawn, rough lines, crosshatching, graphite drawing, concept art sketch, artist sketchbook",
        "negative": "color, photo, 3d, clean lines"
    },
    "Coloring Book": {
        "model": "flux",
        "prodia_model": "toonyou_beta6.safetensors [980f6b15]",
        "suffix": "coloring book style, thick black outlines, flat solid colors, simple shapes, children book illustration, clean vector lines",
        "negative": "realistic, shading, gradient, complex"
    },
    
    # === STYLIZED & POP ===
    "Pop Art": {
        "model": "flux",
        "prodia_model": "dreamshaper_8.safetensors [9d40847d]",
        "suffix": "pop art style, andy warhol, bold primary colors, halftone dots, comic book style, roy lichtenstein, bright and vibrant",
        "negative": "realistic, muted colors, dark, subtle"
    },
    "Low Poly 3D": {
        "model": "flux",
        "prodia_model": "dreamshaper_8.safetensors [9d40847d]",
        "suffix": "low poly 3d art, geometric shapes, polygon art, faceted, crystalline, minimalist 3d, flat shading, triangular mesh",
        "negative": "smooth, detailed, organic, realistic"
    },
    "Vintage Poster": {
        "model": "flux",
        "prodia_model": "dreamshaper_8.safetensors [9d40847d]",
        "suffix": "vintage propaganda poster, retro art deco, soviet constructivism, bold typography, limited color palette, 1950s illustration",
        "negative": "modern, photo, 3d, detailed"
    },
    
    # === MEME & CHAOS ===
    "Brainrot Meme": {
        "model": "flux",
        "prodia_model": "dreamshaper_8.safetensors [9d40847d]",
        "suffix": "meme style, deep fried, oversaturated, lens flare, chaotic composition, ironic shitpost aesthetic, jpeg artifacts, blown out colors, maximum chaos",
        "negative": "clean, professional, minimalist, subtle"
    }
}

# Filter Overlay Effects (FFmpeg color grading)
# Genre-matched combo filters for optimal mood per content type
FILTER_EFFECTS = {
    # No filter - original look
    "None": "",
    
    # Motivational - bright, inspiring, warm uplift
    "Bright Inspire": ",eq=saturation=1.3:contrast=1.15:brightness=0.05,colorbalance=rs=.1:gs=.05:bs=-.05,unsharp=3:3:0.8",
    
    # Horror - dark, desaturated, high contrast, vignette
    "Dark Terror": ",eq=saturation=0.6:contrast=1.4:brightness=-0.1,vignette=PI/3,colorbalance=rs=-.1:bs=.1",
    
    # Comedy - fun, vivid, bright pop
    "Fun Pop": ",eq=saturation=1.35:contrast=1.1:brightness=0.08,unsharp=3:3:0.6",
    
    # Children's Story - soft, warm, gentle dreamy
    "Soft Wonder": ",eq=saturation=1.1:contrast=1.0:brightness=0.1,colorbalance=rs=.15:gs=.1:bs=-.05,gblur=sigma=0.5",
    
    # Documentary - clean, professional, neutral sharp
    "Clean Pro": ",eq=contrast=1.1:brightness=0.02,unsharp=5:5:1.0",
    
    # Fairy Tale - magical, warm glow, dreamy
    "Magic Glow": ",eq=saturation=1.2:brightness=0.08,colorbalance=rs=.2:gs=.1:bs=.05,gblur=sigma=0.8",
    
    # Sci-Fi - cool blue, high contrast, futuristic
    "Cyber Neon": ",colorbalance=rs=-.15:gs=-.05:bs=.25,eq=saturation=1.3:contrast=1.3:brightness=-0.02",
    
    # Viral Shorts - punchy, saturated, sharp for attention
    "Viral Punch": ",eq=saturation=1.4:contrast=1.25,unsharp=5:5:1.2",
    
    # Brainrot - deep fried, chromatic, chaos
    "Meme Chaos": ",eq=saturation=2.0:contrast=1.6:brightness=0.15,rgbashift=rh=2:bh=-2,noise=c0s=20:allf=t",
}

# Image prompt suffix for each filter (affects AI generation style)
FILTER_IMAGE_SUFFIX = {
    "None": "",
    "Bright Inspire": ", uplifting bright atmosphere, warm inspiring tones, motivational mood",
    "Dark Terror": ", dark horror atmosphere, desaturated, high contrast shadows, terrifying mood",
    "Fun Pop": ", fun colorful atmosphere, vibrant playful tones, comedic mood",
    "Soft Wonder": ", soft dreamy atmosphere, gentle warm tones, magical children story mood",
    "Clean Pro": ", professional clean look, neutral tones, documentary style",
    "Magic Glow": ", magical enchanting atmosphere, warm fairy tale glow, fantasy mood",
    "Cyber Neon": ", cyberpunk neon aesthetic, cool blue futuristic, sci-fi atmosphere",
    "Viral Punch": ", attention-grabbing vibrant colors, high impact visual, viral content style",
    "Meme Chaos": ", deep fried meme aesthetic, chaotic oversaturated, brainrot style",
}

# SFX keyword mapping for auto-detection (English + Indonesian)
# REBALANCED: Each of 17 SFX files has dedicated keywords
SFX_KEYWORDS = {
    # === 1. BEEP (tech/computer sounds) ===
    "beep": "beep", "bunyi": "beep", "nada": "beep",
    "computer": "beep", "komputer": "beep",
    "robot": "beep", "ai": "beep", "sistem": "beep", "system": "beep",
    "notification": "beep", "notifikasi": "beep", "pesan": "beep",
    "error": "beep", "loading": "beep", "processing": "beep",
    "click": "beep", "klik": "beep", "tekan": "beep",
    
    # === 2. CRASH (impact/destruction) ===
    "crash": "crash", "tabrak": "crash", "menabrak": "crash",
    "break": "crash", "pecah": "crash", "hancur": "crash",
    "shatter": "crash", "remuk": "crash", "patah": "crash",
    "collision": "crash", "tabrakan": "crash", "tubruk": "crash",
    "smash": "crash", "hantam": "crash", "gebrak": "crash",
    "destroy": "crash", "rusak": "crash", "roboh": "crash",
    
    # === 3. CRY (sadness/emotion) ===
    "cry": "cry", "menangis": "cry", "nangis": "cry",
    "sad": "cry", "sedih": "cry", "pilu": "cry",
    "tears": "cry", "air mata": "cry", "mewek": "cry",
    "weep": "cry", "terisak": "cry", "sedu": "cry",
    "heartbroken": "cry", "patah hati": "cry", "galau": "cry",
    "tragic": "cry", "tragis": "cry", "menyedihkan": "cry",
    
    # === 4. DOOR_KNOCK (knocking/entering) ===
    "knock": "door_knock", "ketuk": "door_knock", "mengetuk": "door_knock",
    "door": "door_knock", "pintu": "door_knock", "gerbang": "door_knock",
    "enter": "door_knock", "masuk": "door_knock", "datang": "door_knock",
    "arrive": "door_knock", "tiba": "door_knock", "sampai": "door_knock",
    "visit": "door_knock", "berkunjung": "door_knock", "tamu": "door_knock",
    "open door": "door_knock", "buka pintu": "door_knock",
    
    # === 5. DOOR_SLAM (slamming/anger) ===
    "slam": "door_slam", "banting": "door_slam", "membanting": "door_slam",
    "shut": "door_slam", "tutup": "door_slam", "menutup": "door_slam",
    "angry": "door_slam", "marah": "door_slam", "kesal": "door_slam",
    "frustrated": "door_slam", "frustasi": "door_slam", "emosi": "door_slam",
    "leave": "door_slam", "pergi": "door_slam", "tinggalkan": "door_slam",
    "storm out": "door_slam", "keluar": "door_slam",
    
    # === 6. EXPLOSION (big impact/viral reactions) ===
    "explode": "explosion", "ledak": "explosion", "meledak": "explosion",
    "boom": "explosion", "dentuman": "explosion", "ledakan": "explosion",
    "blast": "explosion", "dahsyat": "explosion", "bombastis": "explosion",
    "wow": "explosion", "gila": "explosion", "parah": "explosion",
    "amazing": "explosion", "luar biasa": "explosion", "hebat": "explosion",
    "incredible": "explosion", "spektakuler": "explosion",
    
    # === 7. FOOTSTEPS (walking/movement) ===
    "walk": "footsteps", "jalan": "footsteps", "berjalan": "footsteps",
    "step": "footsteps", "langkah": "footsteps", "melangkah": "footsteps",
    "approach": "footsteps", "mendekat": "footsteps", "hampiri": "footsteps",
    "chase": "footsteps", "kejar": "footsteps", "mengejar": "footsteps",
    "follow": "footsteps", "ikuti": "footsteps", "mengikuti": "footsteps",
    "sneak": "footsteps", "mengendap": "footsteps", "diam-diam": "footsteps",
    
    # === 8. HEARTBEAT (tension/suspense) ===
    "heartbeat": "heartbeat", "jantung": "heartbeat", "detak": "heartbeat",
    "nervous": "heartbeat", "gugup": "heartbeat", "deg-degan": "heartbeat",
    "fear": "heartbeat", "takut": "heartbeat", "ketakutan": "heartbeat",
    "anxiety": "heartbeat", "cemas": "heartbeat", "khawatir": "heartbeat",
    "suspense": "heartbeat", "tegang": "heartbeat", "menegangkan": "heartbeat",
    "waiting": "heartbeat", "menunggu": "heartbeat", "harap-harap": "heartbeat",
    
    # === 9. LASER (sci-fi/tech action) ===
    "laser": "laser", "sinar": "laser", "cahaya": "laser",
    "zap": "laser", "tembak": "laser", "menembak": "laser",
    "beam": "laser", "sorot": "laser", "serang": "laser",
    "future": "laser", "masa depan": "laser", "futuristik": "laser",
    "space": "laser", "luar angkasa": "laser", "galaksi": "laser",
    "alien": "laser", "ufo": "laser", "teknologi": "laser",
    
    # === 10. LAUGH (comedy/humor) ===
    "laugh": "laugh", "tertawa": "laugh", "ketawa": "laugh",
    "funny": "laugh", "lucu": "laugh", "kocak": "laugh",
    "joke": "laugh", "lelucon": "laugh", "bercanda": "laugh",
    "humor": "laugh", "ngakak": "laugh", "wkwk": "laugh",
    "haha": "laugh", "lol": "laugh", "rofl": "laugh",
    "comedy": "laugh", "komedi": "laugh", "geli": "laugh",
    
    # === 11. MAGIC (fantasy/wonder) ===
    "magic": "magic", "sihir": "magic", "ajaib": "magic",
    "spell": "magic", "mantra": "magic", "jampi": "magic",
    "miracle": "magic", "keajaiban": "magic", "mukjizat": "magic",
    "transform": "magic", "berubah": "magic", "transformasi": "magic",
    "appear": "magic", "muncul": "magic", "nongol": "magic",
    "disappear": "magic", "hilang": "magic", "menghilang": "magic",
    "sparkle": "magic", "berkilau": "magic", "bersinar": "magic",
    "beautiful": "magic", "indah": "magic", "cantik": "magic",
    
    # === 12. RAIN (weather/atmosphere) ===
    "rain": "rain", "hujan": "rain", "gerimis": "rain",
    "storm": "rain", "badai": "rain", "topan": "rain",
    "wet": "rain", "basah": "rain", "lembab": "rain",
    "drip": "rain", "tetes": "rain", "menetes": "rain",
    "pour": "rain", "deras": "rain", "lebat": "rain",
    "flood": "rain", "banjir": "rain", "genangan": "rain",
    
    # === 13. SCREAM (horror/shock) ===
    "scream": "scream", "teriak": "scream", "berteriak": "scream",
    "shock": "scream", "kaget": "scream", "terkejut": "scream",
    "horror": "scream", "horor": "scream", "seram": "scream",
    "scary": "scream", "menakutkan": "scream", "ngeri": "scream",
    "ghost": "scream", "hantu": "scream", "pocong": "scream",
    "monster": "scream", "monster": "scream", "makhluk": "scream",
    "nightmare": "scream", "mimpi buruk": "scream", "terbangun": "scream",
    
    # === 14. THUNDER (dramatic/power) ===
    "thunder": "thunder", "petir": "thunder", "guntur": "thunder",
    "lightning": "thunder", "kilat": "thunder", "halilintar": "thunder",
    "power": "thunder", "kekuatan": "thunder", "dahsyat": "thunder",
    "dramatic": "thunder", "dramatis": "thunder", "epik": "thunder",
    "epic": "thunder", "mengguncang": "thunder", "menggelegar": "thunder",
    "god": "thunder", "dewa": "thunder", "langit": "thunder",
    
    # === 15. VINE_BOOM (meme/brainrot/reveal) ===
    "bruh": "vine_boom", "bro": "vine_boom", "dude": "vine_boom",
    "sus": "vine_boom", "sussy": "vine_boom", "amogus": "vine_boom",
    "sigma": "vine_boom", "chad": "vine_boom", "alpha": "vine_boom",
    "rizz": "vine_boom", "gyatt": "vine_boom", "bussin": "vine_boom",
    "skibidi": "vine_boom", "ohio": "vine_boom", "toilet": "vine_boom",
    "cap": "vine_boom", "nocap": "vine_boom", "fr": "vine_boom",
    "literally": "vine_boom", "anjir": "vine_boom", "anjay": "vine_boom",
    "ternyata": "vine_boom", "sebenarnya": "vine_boom", "padahal": "vine_boom",
    "akhirnya": "vine_boom", "finally": "vine_boom", "reveal": "vine_boom",
    "plot twist": "vine_boom", "twist": "vine_boom", "rahasia": "vine_boom",
    
    # === 16. WHOOSH (motion/speed/transition) ===
    "whoosh": "whoosh", "desir": "whoosh", "suara angin": "whoosh",
    "fast": "whoosh", "cepat": "whoosh", "kencang": "whoosh",
    "run": "whoosh", "lari": "whoosh", "berlari": "whoosh",
    "jump": "whoosh", "lompat": "whoosh", "melompat": "whoosh",
    "fly": "whoosh", "terbang": "whoosh", "melayang": "whoosh",
    "swipe": "whoosh", "geser": "whoosh", "usap": "whoosh",
    "suddenly": "whoosh", "tiba-tiba": "whoosh", "mendadak": "whoosh",
    "quickly": "whoosh", "segera": "whoosh", "langsung": "whoosh",
    
    # === 17. WIND (nature/atmosphere) ===
    "wind": "wind", "angin": "wind", "hembus": "wind",
    "breeze": "wind", "semilir": "wind", "sepoi": "wind",
    "blow": "wind", "tiup": "wind", "meniup": "wind",
    "cold": "wind", "dingin": "wind", "sejuk": "wind",
    "outside": "wind", "luar": "wind", "alam": "wind",
    "nature": "wind", "hutan": "wind", "gunung": "wind",
}

# Genre-based ambient sounds (mapped to existing SFX files)
GENRE_AMBIENT = {
    "Horror": "heartbeat",       # Use heartbeat for horror tension
    "Comedy": "laugh",           # Use laugh for comedy
    "Fairy Tale": "magic",       # Use magic for fantasy
    "Sci-Fi": "laser",           # Use laser for sci-fi
    "Documentary": "",           # No ambient for documentary (clean)
    "Motivational": "whoosh",    # Use whoosh for energy
    "Children's Story": "laugh", # Use laugh for playful
    "Viral Shorts": "whoosh",    # Use whoosh for viral energy
    "Brainrot": "vine_boom",     # Use vine boom for brainrot chaos
    "Brainrot ID": "vine_boom",  # Use vine boom for brainrot chaos
}


def detect_sfx_keywords(text: str) -> list:
    """
    Detect SFX keywords in narration text.
    Returns list of SFX filenames to mix.
    """
    text_lower = text.lower()
    detected = []
    for keyword, sfx_name in SFX_KEYWORDS.items():
        if keyword in text_lower and sfx_name not in detected:
            detected.append(sfx_name)
    return detected


def mix_audio_with_sfx(
    tts_path: str,
    sfx_paths: list,
    output_path: str,
    sfx_volume: float = 0.5,
    ffmpeg_path: str = "ffmpeg"
) -> bool:
    """
    Mix TTS audio with SFX using FFmpeg.
    Full features: atempo variation + loudnorm + volume boost
    With fallback to simple mixing if advanced fails.
    """
    if not sfx_paths or not os.path.exists(tts_path):
        return False
    
    # Debug log helper
    def log_mix(msg):
        try:
            log_path = os.path.join(os.path.dirname(output_path), "sfx_debug.txt")
            with open(log_path, "a", encoding='utf-8') as f:
                f.write(f"    [MIX] {msg}\n")
        except: pass
    
    def try_mix(filter_complex, label=""):
        """Helper to run ffmpeg with given filter"""
        inputs = ['-i', tts_path]
        for sfx in sfx_paths[:2]:
            if os.path.exists(sfx):
                inputs.extend(['-i', sfx])
        
        cmd = [ffmpeg_path, '-y'] + inputs + [
            '-filter_complex', filter_complex,
            '-map', '[out]',
            '-c:a', 'libmp3lame', '-b:a', '192k',
            output_path
        ]
        
        log_mix(f"{label} CMD: {ffmpeg_path} -y -i TTS -i SFX... -filter_complex ...")
        log_mix(f"{label} Filter: {filter_complex[:150]}...")
        
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            log_mix(f"{label} ✅ SUCCESS!")
            return True
        else:
            log_mix(f"{label} ❌ FAILED! Return={result.returncode}")
            if result.stderr:
                log_mix(f"{label} Error: {result.stderr[:400]}")
            return False
    
    try:
        log_mix(f"Starting mix: TTS={os.path.basename(tts_path)}, SFX count={len(sfx_paths)}")
        
        # Count valid SFX
        valid_sfx = [s for s in sfx_paths[:2] if os.path.exists(s)]
        sfx_count = len(valid_sfx)
        
        if sfx_count == 0:
            log_mix("No valid SFX files!")
            return False
        
        for sfx in valid_sfx:
            log_mix(f"  SFX: {os.path.basename(sfx)}")
        
        # ============ TRY 1: Full features (atempo + loudnorm) ============
        filter_parts = []
        for i in range(sfx_count):
            sfx_speed = random.uniform(0.9, 1.1)  # Slight speed variation
            filter_parts.append(f"[{i+1}]atempo={sfx_speed:.2f},volume={sfx_volume},loudnorm=I=-16:LRA=11:TP=-1.5[sfx{i}]")
        
        mix_inputs = "[0]" + "".join(f"[sfx{i}]" for i in range(sfx_count))
        filter_full = ";".join(filter_parts) + f";{mix_inputs}amix=inputs={sfx_count+1}:duration=first:normalize=0[out]"
        
        if try_mix(filter_full, "[FULL]"):
            return True
        
        # ============ TRY 2: Medium (atempo + volume, no loudnorm) ============
        log_mix("Fallback to MEDIUM mode...")
        filter_parts = []
        for i in range(sfx_count):
            sfx_speed = random.uniform(0.9, 1.1)
            filter_parts.append(f"[{i+1}]atempo={sfx_speed:.2f},volume={sfx_volume}[sfx{i}]")
        
        filter_medium = ";".join(filter_parts) + f";{mix_inputs}amix=inputs={sfx_count+1}:duration=first:normalize=0[out]"
        
        if try_mix(filter_medium, "[MEDIUM]"):
            return True
        
        # ============ TRY 3: Simple (volume only) ============
        log_mix("Fallback to SIMPLE mode...")
        filter_parts = []
        for i in range(sfx_count):
            filter_parts.append(f"[{i+1}]volume={sfx_volume}[sfx{i}]")
        
        filter_simple = ";".join(filter_parts) + f";{mix_inputs}amix=inputs={sfx_count+1}:duration=first:normalize=0[out]"
        
        if try_mix(filter_simple, "[SIMPLE]"):
            return True
        
        # ============ TRY 4: Ultra-simple (amerge) ============
        log_mix("Fallback to AMERGE mode...")
        if sfx_count == 1:
            filter_amerge = f"[0][1]amerge=inputs=2,pan=stereo|c0<c0+c2|c1<c1+c3[out]"
        else:
            filter_amerge = f"[0][1][2]amerge=inputs=3,pan=stereo|c0<c0+c2+c4|c1<c1+c3+c5[out]"
        
        if try_mix(filter_amerge, "[AMERGE]"):
            return True
        
        log_mix("ALL METHODS FAILED!")
        return False
        
    except Exception as e:
        log_mix(f"EXCEPTION: {e}")
        import traceback
        log_mix(traceback.format_exc())
        return False


def build_image_prompt(
    character_desc: str,
    action: str,
    background: str,
    style: str,
    camera: str = "medium shot",
    mood: str = "neutral",
    filter_overlay: str = "None"
) -> str:
    """
    Build optimized image prompt for consistency and detail.
    Combines: character + action + background + style + filter + quality keywords
    Character gender/appearance comes from character_desc - NOT hardcoded.
    """
    style_info = VISUAL_STYLES.get(style, VISUAL_STYLES["Ghibli Anime"])
    style_suffix = style_info.get("suffix", "anime style")
    
    # Get filter overlay suffix for image mood matching
    filter_suffix = FILTER_IMAGE_SUFFIX.get(filter_overlay, "")
    
    # Quality keywords for better detail
    quality_tags = "masterpiece, best quality, highly detailed, sharp focus"
    
    # Build structured prompt - character first for consistency
    # DO NOT hardcode gender - let character_desc determine it
    prompt_parts = [
        character_desc,  # Character desc should include gender from story
        action,
        background,
        camera,
        f"{mood} mood",
        style_suffix,
        quality_tags,
        "portrait composition, vertical format"
    ]
    
    # Add filter styling if not None
    if filter_suffix:
        prompt_parts.append(filter_suffix)
    
    return ", ".join(filter(None, prompt_parts))

VOICE_OPTIONS = {
    "Indonesian Female": "id-ID-GadisNeural",
    "Indonesian Male": "id-ID-ArdiNeural",
    "English Female": "en-US-JennyNeural",
    "English Male": "en-US-GuyNeural",
    "English UK Female": "en-GB-SoniaNeural",
    "Japanese Female": "ja-JP-NanamiNeural"
}


# ============================================================================
# HYBRID IMAGE GENERATION (Multiple Providers + Delay)
# ============================================================================
# Pollinations API key (set via set_pollinations_api_key)
_pollinations_api_key: Optional[str] = None

# Track which provider was used for the last successful image generation
# Values: "Pollinations NEW API", "Pollinations OLD API", "Prodia", "Stable Horde", "Dezgo", "Perchance"
_last_image_provider: str = ""

def get_last_image_provider() -> str:
    """Return the name of the last image provider that succeeded"""
    global _last_image_provider
    return _last_image_provider

def set_pollinations_api_key(key: str):
    """Set Pollinations API key for authenticated requests (faster, no queue)"""
    global _pollinations_api_key
    _pollinations_api_key = key if key else None
    if key:
        print(f"DEBUG: Pollinations API key configured (length: {len(key)})")


def generate_image_pollinations(prompt: str, width: int, height: int, seed: int, output_path: str) -> bool:
    """
    Try Pollinations.ai image generation.
    NEW API (with key): gen.pollinations.ai with Bearer auth - faster, no queue
    OLD API (no key): image.pollinations.ai - free but slower, may have queue
    Models fallback: flux → turbo → zimage
    """
    global _pollinations_api_key, _last_image_provider
    
    models = ['flux', 'turbo', 'zimage']
    encoded_prompt = urllib.parse.quote(prompt)
    
    for model in models:
        try:
            # Build URL with params (seed, width, height, nologo preserved)
            seed_param = f"&seed={seed}" if seed > 0 else ""
            
            if _pollinations_api_key:
                # NEW API with Bearer auth (faster, priority queue)
                url = f"https://gen.pollinations.ai/image/{encoded_prompt}?model={model}&width={width}&height={height}{seed_param}&nologo=true"
                headers = {'Authorization': f'Bearer {_pollinations_api_key}'}
                api_type = "NEW API"
                print(f"DEBUG: Trying Pollinations NEW API ({model})...")
                response = requests.get(url, headers=headers, timeout=120)
            else:
                # OLD API without auth (free tier, slower)
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?model={model}&width={width}&height={height}{seed_param}&nologo=true"
                api_type = "OLD API"
                print(f"DEBUG: Trying Pollinations OLD API ({model})...")
                response = requests.get(url, timeout=120)
            
            if response.status_code == 200 and len(response.content) > 1000:
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                _last_image_provider = f"Pollinations {api_type} ({model})"
                print(f"DEBUG: Pollinations {model} SUCCESS ({len(response.content)} bytes)")
                return True
            elif response.status_code == 429:
                print(f"DEBUG: Pollinations {model} rate limited (429)")
            elif response.status_code == 500:
                # Check for "No active X servers available" error
                try:
                    err_msg = response.json().get('error', {}).get('message', '')
                    if 'No active' in err_msg:
                        print(f"DEBUG: Pollinations {model} servers offline, trying next...")
                    else:
                        print(f"DEBUG: Pollinations {model} error 500: {err_msg[:100]}")
                except:
                    print(f"DEBUG: Pollinations {model} returned 500")
            else:
                print(f"DEBUG: Pollinations {model} returned {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"DEBUG: Pollinations {model} timeout")
        except Exception as e:
            print(f"DEBUG: Pollinations {model} error: {e}")
    
    print("DEBUG: All Pollinations models failed")
    return False


def generate_image_perchance(prompt: str, output_path: str) -> bool:
    """Try Perchance AI as fallback (no seed support)"""
    global _last_image_provider
    try:
        # Perchance uses different API format
        url = "https://image.perchance.org/api/text-to-image-v2"
        data = {
            "prompt": prompt[:500],  # Max 500 chars
            "negative_prompt": "ugly, deformed, blurry",
            "resolution": "512x768",
            "guidance_scale": 7.5
        }
        
        response = requests.post(url, json=data, timeout=120)
        
        if response.status_code == 200:
            # Response is base64 encoded image
            import base64
            img_data = base64.b64decode(response.json().get('imageBase64', ''))
            if len(img_data) > 1000:
                with open(output_path, 'wb') as f:
                    f.write(img_data)
                _last_image_provider = "Perchance"
                return True
    except Exception as e:
        print(f"DEBUG: Perchance error: {e}")
    return False


def generate_image_stable_horde(prompt: str, output_path: str, width: int = 512, height: int = 768) -> bool:
    """
    Try Stable Horde - FREE community-powered Stable Diffusion.
    No API key required (uses anonymous access).
    """
    global _last_image_provider
    try:
        import time as horde_time
        
        # Stable Horde API - anonymous key = "0000000000"
        api_key = "0000000000"  # Anonymous access - no registration needed!
        
        headers = {
            "apikey": api_key,
            "Content-Type": "application/json"
        }
        
        # Request image generation
        payload = {
            "prompt": prompt[:1000],  # Max 1000 chars
            "params": {
                "width": min(width, 1024),
                "height": min(height, 1024),
                "steps": 20,
                "cfg_scale": 7.5,
                "sampler_name": "k_euler_a"
            },
            "nsfw": False,
            "models": ["stable_diffusion"]  # Default model
        }
        
        # Step 1: Submit generation request
        gen_url = "https://aihorde.net/api/v2/generate/async"
        response = requests.post(gen_url, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 202:
            print(f"DEBUG: Stable Horde request failed: {response.status_code}")
            return False
        
        job_data = response.json()
        job_id = job_data.get("id")
        
        if not job_id:
            print("DEBUG: Stable Horde - no job ID returned")
            return False
        
        print(f"DEBUG: Stable Horde job submitted: {job_id}")
        
        # Step 2: Poll for completion (max 180s for free tier)
        check_url = f"https://aihorde.net/api/v2/generate/check/{job_id}"
        status_url = f"https://aihorde.net/api/v2/generate/status/{job_id}"
        
        for attempt in range(60):  # 60 * 3s = 180s max
            horde_time.sleep(3)
            
            check_resp = requests.get(check_url, headers=headers, timeout=10)
            if check_resp.status_code != 200:
                continue
            
            check_data = check_resp.json()
            
            if check_data.get("done"):
                # Get final result
                status_resp = requests.get(status_url, headers=headers, timeout=30)
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    generations = status_data.get("generations", [])
                    
                    if generations and generations[0].get("img"):
                        # Download image from URL
                        img_url = generations[0]["img"]
                        img_resp = requests.get(img_url, timeout=30)
                        
                        if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                            with open(output_path, 'wb') as f:
                                f.write(img_resp.content)
                            _last_image_provider = "Stable Horde"
                            print(f"DEBUG: Stable Horde image saved: {output_path}")
                            return True
                break
            
            if check_data.get("faulted"):
                print("DEBUG: Stable Horde job faulted")
                break
            
            queue_pos = check_data.get("queue_position", "?")
            wait_time = check_data.get("wait_time", "?")
            print(f"DEBUG: Stable Horde waiting... queue={queue_pos}, eta={wait_time}s")
        
        print("DEBUG: Stable Horde timeout")
        return False
        
    except Exception as e:
        print(f"DEBUG: Stable Horde error: {e}")
        return False


def generate_image_dezgo(prompt: str, output_path: str, seed: int = -1) -> bool:
    """Try Dezgo as fallback (free tier)"""
    global _last_image_provider
    try:
        encoded_prompt = urllib.parse.quote(prompt[:300])
        # Dezgo free API
        url = f"https://api.dezgo.com/text2image?prompt={encoded_prompt}&width=512&height=768"
        if seed > 0:
            url += f"&seed={seed}"
        
        response = requests.get(url, timeout=120)
        
        if response.status_code == 200 and len(response.content) > 1000:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            _last_image_provider = "Dezgo"
            return True
    except Exception as e:
        print(f"DEBUG: Dezgo error: {e}")
    return False


def generate_image_prodia_api(prompt: str, output_path: str, seed: int = -1, 
                               width: int = 512, height: int = 768,
                               prodia_key: str = "",
                               style_key: str = "Ghibli Anime") -> bool:
    """
    Try Prodia API (requires API key) for image generation.
    Uses SD 1.5 models based on selected art style.
    """
    global _last_image_provider
    if not prodia_key:
        print("DEBUG: Prodia API key not provided, skipping")
        return False
    
    try:
        import time
        
        # Get prodia model based on selected style
        style = VISUAL_STYLES.get(style_key, VISUAL_STYLES["Ghibli Anime"])
        prodia_model = style.get("prodia_model", "dreamshaper_8.safetensors [9d40847d]")
        negative = style.get("negative", "ugly, deformed, blurry, low quality")
        
        print(f"DEBUG: Prodia using model: {prodia_model}")
        
        # Step 1: Create generation job
        gen_url = f"{PRODIA_API_URL}/sd/generate"
        headers = {
            "X-Prodia-Key": prodia_key,
            "Content-Type": "application/json"
        }
        payload = {
            "model": prodia_model,
            "prompt": prompt[:500],  # Max 500 chars
            "negative_prompt": negative,
            "width": min(width, 768),  # Prodia max 768
            "height": min(height, 1024),  # Prodia max 1024
            "steps": 25,
            "cfg_scale": 7.0,
            "sampler": "DPM++ 2M Karras"
        }
        
        if seed > 0:
            payload["seed"] = seed
        
        response = requests.post(gen_url, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            print(f"DEBUG: Prodia create job failed: {response.status_code}")
            return False
        
        job_data = response.json()
        job_id = job_data.get("job")
        
        if not job_id:
            print("DEBUG: Prodia no job ID returned")
            return False
        
        # Step 2: Poll for completion (max 60s)
        status_url = f"{PRODIA_API_URL}/job/{job_id}"
        for _ in range(30):  # 30 * 2s = 60s max
            time.sleep(2)
            status_resp = requests.get(status_url, headers=headers, timeout=10)
            
            if status_resp.status_code != 200:
                continue
                
            status_data = status_resp.json()
            status = status_data.get("status")
            
            if status == "succeeded":
                image_url = status_data.get("imageUrl")
                if image_url:
                    # Download image
                    img_resp = requests.get(image_url, timeout=30)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        with open(output_path, 'wb') as f:
                            f.write(img_resp.content)
                        _last_image_provider = "Prodia"
                        print(f"DEBUG: Prodia image saved: {output_path}")
                        return True
                break
            elif status == "failed":
                print("DEBUG: Prodia job failed")
                break
        
        print("DEBUG: Prodia job timed out or failed")
        return False
        
    except Exception as e:
        print(f"DEBUG: Prodia API error: {e}")
        return False


# Global variable to store Prodia key (set from generate_animation_v2)
_prodia_api_key = ""


def set_prodia_api_key(key: str):
    """Set the Prodia API key for image generation fallback"""
    global _prodia_api_key
    _prodia_api_key = key
    if key:
        print(f"DEBUG: Prodia API key configured (length: {len(key)})")


def generate_image_hybrid(
    prompt: str,
    style_key: str,
    output_path: str,
    seed: int = -1,
    width: int = IMAGE_WIDTH,
    height: int = IMAGE_HEIGHT,
    max_retries: int = 10,  # Increased for Pollinations reliability (free tier is slow)
    delay_between: float = 3.0
) -> bool:
    """
    Generate image using multiple providers with fallback.
    Priority: Pollinations -> Prodia (if key) -> Dezgo -> Perchance
    Includes longer retry with extended delays for free API reliability.
    """
    global _prodia_api_key
    
    style = VISUAL_STYLES.get(style_key, VISUAL_STYLES["Ghibli Anime"])
    full_prompt = f"{prompt}, {style['suffix']}"
    
    print(f"DEBUG: Generating image with seed={seed}")
    
    # Build providers list based on API key availability
    # PRIORITY ADJUSTED: Pollinations (Fast/Key) -> Pollinations (Free) -> Prodia -> Stable Horde (Slow)
    if _prodia_api_key:
        print("DEBUG: Prodia API key detected - Primary: Prodia -> Pollinations -> Stable Horde")
        providers = [
            ("Pollinations", lambda: generate_image_pollinations(full_prompt, width, height, seed, output_path)), # Moved to TOP (Fastest response)
            ("Prodia", lambda: generate_image_prodia_api(full_prompt, output_path, seed, width, height, _prodia_api_key, style_key)),
            ("Stable Horde", lambda: generate_image_stable_horde(full_prompt, output_path, width, height)),
            ("Dezgo", lambda: generate_image_dezgo(full_prompt, output_path, seed)),
            ("Perchance", lambda: generate_image_perchance(full_prompt, output_path))
        ]
    else:
        print("DEBUG: No Prodia key - using Pollinations as PRIMARY (New+Old API)")
        providers = [
            ("Pollinations", lambda: generate_image_pollinations(full_prompt, width, height, seed, output_path)), # PRIMARY
            ("Stable Horde", lambda: generate_image_stable_horde(full_prompt, output_path, width, height)), # Fallback (Slow)
            ("Dezgo", lambda: generate_image_dezgo(full_prompt, output_path, seed)),
            ("Perchance", lambda: generate_image_perchance(full_prompt, output_path))
        ]
    
    for attempt in range(max_retries):
        for name, provider_fn in providers:
            try:
                print(f"DEBUG: Trying {name} (attempt {attempt+1}/{max_retries})...")
                success = provider_fn()
                
                if success and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    # _last_image_provider is set by the provider function with details like "Pollinations NEW API (flux)"
                    provider_detail = _last_image_provider if _last_image_provider else name
                    print(f"✅ Image via: {provider_detail} | Size: {os.path.getsize(output_path)} bytes")
                    # Add delay after successful request
                    time.sleep(delay_between)
                    return True
                    
            except Exception as e:
                print(f"DEBUG: {name} failed: {e}")
        
        # Wait before retry round - LONGER delay for Pollinations reliability
        if attempt < max_retries - 1:
            wait_time = min((attempt + 1) * 10, 60)  # 10s, 20s, 30s... max 60s
            print(f"DEBUG: All providers failed, waiting {wait_time}s before retry (attempt {attempt+1}/{max_retries})...")
            time.sleep(wait_time)
    
    print(f"DEBUG: Image generation failed after {max_retries} rounds")
    return False


# Alias for backward compatibility (test files and external code may use this)
generate_image_prodia = generate_image_hybrid


# ============================================================================
# GROQ TEXT GENERATION (LLaMA fallback)
# ============================================================================
def _generate_with_groq(prompt: str, api_key: str, target_language: str = "English") -> Optional[str]:
    """
    Generate text using Groq LLaMA as fallback.
    Returns raw response text or None on failure.
    """
    try:
        from groq import Groq
        
        client = Groq(api_key=api_key)
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"You are a JSON generator. Output ONLY valid JSON array. Every string value MUST be in double quotes. Write all narration text in {target_language.upper()} language. Keep character_desc in English for image prompts."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=4000,
            response_format={"type": "json_object"}
        )
        
        result = response.choices[0].message.content
        print("DEBUG: Groq LLaMA response received")
        return result
        
    except Exception as e:
        print(f"DEBUG: Groq LLaMA error: {e}")
        return None


def _generate_with_gemini(prompt: str, api_key: str) -> Optional[str]:
    """
    Generate text using Gemini with auto model detection.
    Tries multiple models in order: gemini-2.0-flash → gemini-1.5-flash → gemini-pro
    Returns raw response text or None on failure.
    """
    try:
        if genai is None:
            return None
            
        genai.configure(api_key=api_key)
        
        # Model fallback chain - try each until one works
        # Auto-detect available models from API
        model_candidates = []
        try:
            print("DEBUG: Auto-detecting Gemini models...")
            all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            
            # Priority: Newest 2.5 -> 2.0 -> 1.5
            priority_prefs = [
                'models/gemini-2.5-pro',
                'models/gemini-2.5-flash',
                'models/gemini-2.0-flash',
                'models/gemini-1.5-pro',
                'models/gemini-1.5-flash'
            ]
            
            # Add prioritized models if available
            for pref in priority_prefs:
                # Check for exact match or suffix match
                match = next((m for m in all_models if m == pref or m.endswith(f"/{pref}")), None)
                if match and match not in model_candidates:
                    model_candidates.append(match)
            
            # Fallback if no priority models found (unlikely)
            if not model_candidates:
                print("DEBUG: No priority models found, using default fallback list")
                model_candidates = [
                    'gemini-2.0-flash',
                    'gemini-1.5-flash',
                    'gemini-1.5-pro',
                    'gemini-pro'
                ]
            else:
                print(f"DEBUG: Selected models: {model_candidates}")
                
        except Exception as e:
            print(f"DEBUG: Model auto-detection failed ({e}), using fallback list")
            model_candidates = [
                'gemini-2.0-flash',
                'gemini-1.5-flash',
                'gemini-1.5-pro',
                'gemini-pro'
            ]
        
        for model_name in model_candidates:
            try:
                print(f"DEBUG: Trying Gemini model: {model_name}")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                print(f"DEBUG: Gemini response received from {model_name}")
                return response.text
            except Exception as model_error:
                error_str = str(model_error)
                if "429" in error_str or "quota" in error_str.lower():
                    print(f"DEBUG: {model_name} quota exceeded, trying next model...")
                    continue
                elif "not found" in error_str.lower() or "does not exist" in error_str.lower():
                    print(f"DEBUG: {model_name} not available, trying next model...")
                    continue
                else:
                    print(f"DEBUG: {model_name} error: {model_error}")
                    continue
        
        print("DEBUG: All Gemini models failed")
        return None
        
    except Exception as e:
        print(f"DEBUG: Gemini error: {e}")
        return None



# ============================================================================
# DURATION EXTRACTION HELPER
# ============================================================================
def extract_duration_from_transcript(transcript: str) -> float:
    """
    Extract video duration from transcript timestamps.
    
    Looks for timestamp patterns like:
    [0.00s] Text...
    [7.04s] More text...
    [24.44s] Final text
    
    Returns the last timestamp as total video duration.
    Falls back to 30.0 seconds if no timestamps found.
    
    Args:
        transcript: Transcript text with timestamps in [X.XXs] format
        
    Returns:
        float: Video duration in seconds (default: 30.0)
    """
    import re
    try:
        # Find all timestamp patterns: [0.00s] or [24.44s]
        timestamps = re.findall(r'\[(\d+\.?\d*)[s\]]', transcript)
        
        if timestamps:
            # Last timestamp = total video duration
            return float(timestamps[-1])
    except Exception as e:
        # If anything fails, use safe fallback
        print(f"DEBUG: Duration extraction failed: {e}, using default 30s")
    
    # Safe fallback for backwards compatibility
    return 30.0


def validate_scene_count(original_duration: float, user_scenes: int) -> tuple:
    """
    Validate scene count and provide warnings if outside optimal range.
    
    Images in Animator are displayed for the duration of their TTS narration.
    Optimal range: 2.0s - 5.0s per scene for good visual comprehension and pacing.
    
    Args:
        original_duration: Video duration in seconds (from transcript timestamps)
        user_scenes: Number of scenes requested by user from GUI
        
    Returns:
        tuple: (words_per_scene: int, warning_message: str or None)
        
    Example:
        >>> validate_scene_count(24.44, 7)
        (8, None)  # Optimal range, no warning
        
        >>> validate_scene_count(24.44, 20)
        (6, "⚠️ Scene Count Warning...")  # Too many, forced minimum
    """
    MIN_SCENE_DURATION = 2.0  # Minimum seconds per scene for visual comprehension
    MAX_SCENE_DURATION = 5.0  # Maximum before becoming boring/slow
    MIN_WORDS = 6  # Minimum words for natural narration (one good sentence)
    
    # Calculate optimal scene range for this video duration
    min_scenes = max(3, int(original_duration / MAX_SCENE_DURATION))
    max_scenes = int(original_duration / MIN_SCENE_DURATION)
    
    # Calculate words per scene (2.5 words/second for Indonesian TTS)
    words_per_scene = int((original_duration / user_scenes) * 2.5)
    
    warning = None
    
    # Check if too many scenes (images change too fast)
    if user_scenes > max_scenes:
        avg_duration = original_duration / user_scenes
        warning = (
            f"⚠️ Scene Count Warning:\n"
            f"  • Requested: {user_scenes} scenes for {original_duration:.1f}s video\n"
            f"  • Results in: ~{avg_duration:.1f}s per image (TOO FAST!)\n"
            f"  • Recommended: {min_scenes}-{max_scenes} scenes for optimal pacing\n"
            f"  • Issue: Images change too quickly for viewer comprehension\n"
        )
        # Force minimum words to keep narration natural
        if words_per_scene < MIN_WORDS:
            words_per_scene = MIN_WORDS
            expected_dur = (user_scenes * words_per_scene) / 2.5
            warning += (
                f"  • Adjustment: Forcing minimum {MIN_WORDS} words per scene\n"
                f"  • Expected output: ~{expected_dur:.1f}s total (may exceed target)\n"
            )
    
    # Check if too few scenes (slow paced, OK but inform user)
    elif user_scenes < min_scenes:
        avg_duration = original_duration / user_scenes
        warning = (
            f"ℹ️ Scene Count Note:\n"
            f"  • Requested: {user_scenes} scenes for {original_duration:.1f}s video\n"
            f"  • Results in: ~{avg_duration:.1f}s per image (slow paced)\n"
            f"  • This is OK for detailed, cinematic storytelling\n"
            f"  • Each narration will be longer (~{words_per_scene} words per scene)\n"
        )
    
    # Print warning if any
    if warning:
        print(warning)
    
    return words_per_scene, warning


# ============================================================================
# ENHANCED STORY GENERATION WITH FALLBACK
# ============================================================================
def generate_story_script(
    transcript: str,
    genre: str,
    style: str,
    api_key: str,
    num_scenes: int = 10,
    language: str = "English",
    groq_key: str = "",
    filter_overlay: str = "None"
) -> Optional[List[Dict]]:
    """
    Generate detailed story script with consistent character and scene descriptions.
    Supports MULTI-LANGUAGE (Indonesian/English) context adaptation.
    """
    try:
        import re
        
        # --- 1. LANGUAGE CONTEXT SETUP ---
        # Tentukan konteks bahasa untuk instruksi prompt agar AI lebih akurat
        is_english = "english" in language.lower()
        
        if is_english:
            # Konteks INGGRIS
            lang_context = {
                "banned_words": "horrifying, terrifying, creepy, scary, dark, ominous, spooky",
                "tautology_bad": "'a silent silence' or 'wet water'",
                "tautology_good": "'a profound silence' or 'the water'",
                "example_bad": "'The two rats connected', (has quotes)",
                "example_good": "The scientists successfully established a brain-to-brain connection.",
                "quote_rule": "Every sentence must start with a letter, NOT a quotation mark!",
                "anti_horror_msg": "Science video about rats = informative narration, NOT horror!",
                "vocab_instruction": f"Translate these vocabulary suggestions to {language.upper()} if necessary"
            }
        else:
            # Konteks INDONESIA (Default)
            lang_context = {
                "banned_words": "mengerikan, mencekam, menyeramkan, menakutkan, gelap, bayangan",
                "tautology_bad": "'kesunyian yang sunyi' (redundant)",
                "tautology_good": "'keheningan malam' atau 'suasana hening'",
                "example_bad": "'Dua tikus terhubung', (ada tanda kutip)",
                "example_good": "Para ilmuwan berhasil menciptakan koneksi pikiran antar tikus.",
                "quote_rule": "Setiap kalimat harus dimulai dengan huruf, BUKAN tanda kutip!",
                "anti_horror_msg": "Video sains tentang tikus = narasi informatif, BUKAN horor!",
                "vocab_instruction": "Gunakan kosakata ini dalam konteks yang tepat"
            }

        # --- 2. GENRE PRESET HANDLING (Enhanced with Storytelling) ---
        genre_preset = GENRES.get(genre, {
            "tone": "engaging, natural",
            "style": "Natural storytelling",
            "example": "Here is an interesting fact. This changes everything we know.",
            "narrative_structure": "cold_open",
            "cold_open_instruction": "Start with the most IMPACTFUL moment from transcript. Then provide context.",
            "hook_style": "Kamu tidak akan percaya ini...",
            "transition_phrases": ["Ternyata", "Dan selanjutnya", "Tapi"],
            "emotional_arc": ["curiosity", "interest", "insight"],
            "emoji": "📺"
        })
        
        genre_tone = genre_preset.get("tone", "natural, engaging")
        genre_style = genre_preset.get("style", "Natural storytelling")
        genre_example = genre_preset.get("example", "")
        narrative_structure = genre_preset.get("narrative_structure", "cold_open")
        cold_open_instruction = genre_preset.get("cold_open_instruction", "Start with the most IMPACTFUL moment from transcript. Then provide context.")
        hook_style = genre_preset.get("hook_style", "Kamu tidak akan percaya ini...")
        transition_phrases = genre_preset.get("transition_phrases", ["Ternyata", "Dan", "Tapi"])
        emotional_arc = genre_preset.get("emotional_arc", ["curiosity", "insight"])
        genre_emoji = genre_preset.get("emoji", "📺")
        
        # --- NEW: Genre-Specific Language (Dynamic Power Words & Tone) ---
        is_english = language.lower() in ["english", "en"]
        if is_english:
            genre_power_words = genre_preset.get("power_words_en", ["Here's the thing—", "Turns out,", "What's interesting is,"])
            genre_tone_instruction = genre_preset.get("tone_instruction_en", "Like a natural storyteller. Engaging and clear.")
        else:
            genre_power_words = genre_preset.get("power_words_id", ["Ternyata,", "Yang menarik,", "Jadi,"])
            genre_tone_instruction = genre_preset.get("tone_instruction_id", "Kayak cerita ke temen. Natural dan engaging.")
        
        # Format power words for prompt injection
        power_words_str = ", ".join(f'"{w}"' for w in genre_power_words)
        
        style_info = VISUAL_STYLES.get(style, VISUAL_STYLES["Ghibli Anime"])
        
        # --- NEW: Get genre-specific pronoun and forbidden words ---
        pronoun_style = genre_preset.get("pronoun_style", "casual")
        forbidden_words = genre_preset.get("forbidden_words_id", [])
        # Select narration example based on language
        if is_english:
            narration_example = genre_preset.get("narration_example_en", "")
        else:
            narration_example = genre_preset.get("narration_example_id", "")
        
        # --- Dynamic Language & Style Rules ---
        if language.lower() in ["indonesian", "bahasa", "id", "indo"]:
            # Build pronoun instruction based on genre
            if pronoun_style == "formal":
                pronoun_instruction = "- 🚫 DILARANG pakai bahasa gaul! Gunakan bahasa Indonesia baku/sastra.\n- JANGAN pakai: " + ", ".join(f'"{w}"' for w in forbidden_words) if forbidden_words else ""
            elif pronoun_style == "semi-formal":
                pronoun_instruction = "- USE: \"Aku/Kamu\" (NOT \"Gue/Lu\", NOT \"Anda\"!)\n- Bahasa natural tapi tidak terlalu gaul."
            else:  # casual
                pronoun_instruction = "- USE: \"Gue/Lu\" atau \"Aku/Kamu\" (Never \"Anda\"!)\n- PARTICLES: Variasikan \"sih\", \"dong\", \"deh\", \"tuh\"."
            
            language_rules = f"""
🌍 FOR INDONESIAN LANGUAGE (CRITICAL):
{pronoun_instruction}
- VOCAB TRANSFORMATION (jika genre mengizinkan gaul):
  * "Wajah" -> "Muka" | "Tidak" -> "Gak" | "Telah" -> "Udah" | "Sedang" -> "Lagi"
- PACING: Natural flow (8-15 words per sentence). Continuous!
- 🎯 POWER WORDS FOR {genre.upper()}: {power_words_str}
- 🚫 ANTI-REPETITION (WAJIB!): JANGAN mulai 2 scene berturut-turut dengan kata yang sama!
- 🎭 TONE FOR {genre.upper()}: {genre_tone_instruction}
"""
        else:
            language_rules = f"""
🌍 FOR ENGLISH LANGUAGE:
- Use VIRAL / ENGAGING / YOUTUBER tone!
- Use slang/contractions naturally ("gonna", "wanna", "kinda") if appropriate.
- 🎯 POWER WORDS FOR {genre.upper()}: {power_words_str}
- 🚫 ANTI-REPETITION (CRITICAL!): DO NOT start 2 consecutive scenes with the same word!
  * VARY your scene openers!
  * BAD: Scene 1: "Suddenly, ..." Scene 2: "Suddenly, ..." (REPETITIVE!)
  * GOOD: Scene 1: "Suddenly, ..." Scene 2: "But then, ..." (VARIED!)
- 🎭 TONE FOR {genre.upper()}: {genre_tone_instruction}
- Avoid textbook English. Speak like a real person!
"""

        prompt = f"""You are a professional narrator and storyteller retelling a video using COLD OPEN structure in {language.upper()}.

=== 🎭 GENRE: {genre} (READ THIS FIRST - CRITICAL!) ===
TONE: {genre_tone}
STYLE: {genre_style}
EMOTIONAL ARC: {' → '.join(emotional_arc)}

⚠️ GENRE ENFORCEMENT (YOU MUST FOLLOW THIS!):
- Your narration MUST sound like a {genre} video, NOT a formal documentary!
- MATCH the {genre} tone in EVERY sentence you write!

Genre-specific rules:
- Comedy → ADD JOKES, humor, funny observations, witty sarcasm!
- Horror → ADD tension, dread, creepy atmosphere, suspenseful pauses!
- Motivational → ADD inspiration, energy, empowerment, triumph!
- Documentary → Informative but ENGAGING, add "wow factor"!
- Children's Story → Warm, friendly, simple words, magical wonder!
- Fairy Tale → Whimsical, enchanting, wonder and awe!
- Drama → Emotional depth, human connection, heartfelt moments!
- Viral Shorts → Punchy, fast-paced, hook-driven, clickbait energy!
- Brainrot → CHAOTIC, GEN-Z humor, unhinged, meme energy!
- Brainrot ID → Bahasa gaul Indonesia, "gila sih", "sus banget"!

EXAMPLE of {genre} tone:
\"{genre_example}\"


📋 NARRATION STRUCTURE TEMPLATE (FOLLOW THIS FORMAT!):
{narration_example if narration_example else "Use 5 sections: [THE HOOK] → [THE DETAIL] → [THE REALIZATION] → [THE CLIMAX] → [THE ENDING]"}

=== ⏱️ CRITICAL DURATION CONSTRAINT ===

"""
        
        # Extract duration from transcript timestamps
        original_duration = extract_duration_from_transcript(transcript)
        
        # Validate scene count and get word limit with safeguards
        # This will warn user if they selected too many/few scenes
        max_words_per_scene, scene_warning = validate_scene_count(
            original_duration, 
            num_scenes
        )
        target_scenes = num_scenes
        
        # Detect if same language for anti-plagiarism
        same_language = False
        if language.lower() in ["indonesian", "bahasa", "id", "indo"]:
            indonesian_markers = ["yang", "dan", "dengan", "pada", "di", "ke", "ini", "itu"]
            same_language = any(marker in transcript.lower() for marker in indonesian_markers)
        elif language.lower() in ["english", "en"]:
            english_markers = [" the ", " a ", " an ", " and ", " with ", " at ", " to "]
            same_language = any(marker in transcript.lower() for marker in english_markers)
        
        # Build duration constraint and anti-plagiarism rules
        duration_constraint = f"""
⏱️ CRITICAL DURATION CONSTRAINT:
- Original video duration: {original_duration:.1f} seconds (extracted from timestamps)
- You MUST generate exactly {target_scenes} scenes
- TOTAL narration when spoken: MUST NOT EXCEED {original_duration:.1f} seconds
- Each scene narration: approximately {max_words_per_scene} words maximum (~3-5 seconds spoken)
- DO NOT add story details not in original transcript
- DO NOT expand or elaborate beyond original content
- ONLY retell what's in the transcript, CONCISELY
"""
        
        if same_language:
            anti_plagiarism = f"""
🚨 ANTI-PLAGIARISM CRITICAL (Source and target are SAME language!):
- You MUST completely REWRITE in your own words
- Use DIFFERENT sentence structures from the original
- Use DIFFERENT vocabulary choices  
- DO NOT copy exact phrases or sentence patterns from transcript
- Transform the story with {genre} tone and style
- Make it YOUR narration, not a paraphrase
"""
        else:
            anti_plagiarism = """
🌐 TRANSLATION REQUIREMENT:
- Translate naturally and idiomatically
- Adapt story to target language expression
- Transform with genre-appropriate tone
- Maintain facts but use natural native phrasing
"""
        
        prompt += duration_constraint + anti_plagiarism + f"""
=== SOURCE TRANSCRIPT (use ALL content, respect the {original_duration:.1f}s duration) ===
{transcript[:15000]}


=== 🚨 COLD OPEN STRUCTURE (MANDATORY!) ===

COLD OPEN means: Start with the CLIMAX/IMPACT first, THEN explain the backstory.

❌ WRONG: Tell story chronologically from beginning to end
✅ CORRECT: Start with the MOST DRAMATIC moment, then "But how did this happen? Let me explain..."

=== YOUR TASK: RETELL INTO 5 PARTS with MULTIPLE SCENES EACH ===
The transcript MUST be retold in EXACTLY 5 PARTS using COLD OPEN structure.
Each PART contains MULTIPLE SCENES. Each SCENE = 1 short narration (~{max_words_per_scene} words) + 1 image.

📋 5-PART STRUCTURE:
- PART 1 [THE HOOK]: Dramatic opening - START WITH CLIMAX/REVELATION!
- PART 2 [THE DETAIL]: Context and key information - "What led to this?"
- PART 3 [THE REALIZATION]: The twist or turning point
- PART 4 [THE CLIMAX]: Peak tension, action, or confrontation  
- PART 5 [THE ENDING]: Resolution, cliffhanger, or moral

📊 SCENE DISTRIBUTION (Total: {num_scenes} scenes):
Distribute scenes NATURALLY across parts (guideline below, can adjust ±1-2):
- HOOK: ~15% (~{int(num_scenes * 0.15)} scenes) - short, impactful
- DETAIL: ~30% (~{int(num_scenes * 0.30)} scenes) - more context needed
- REALIZATION: ~20% (~{int(num_scenes * 0.20)} scenes) - twist moment
- CLIMAX: ~25% (~{int(num_scenes * 0.25)} scenes) - peak action
- ENDING: ~10% (~{int(num_scenes * 0.10)} scenes) - quick resolution

⚠️ CRITICAL RULES:
1. PART 1 [THE HOOK] MUST start with climax/twist - NOT the beginning!
2. Each scene narration = approximately {max_words_per_scene} words (to fit {original_duration:.1f}s total)
3. Narration style MUST match genre (keep within {max_words_per_scene} words per scene):
   - Horror/Sci-Fi: Dark, atmospheric, suspenseful (concise and impactful)
   - Documentary/Motivational: Clear, informative, inspiring (factual but brief)
   - Fairy Tale/Children's: Gentle, magical, warm (simple and short)
   - Comedy/Viral: Punchy, conversational, witty (ultra-concise)
   - Brainrot/Brainrot ID: Short, chaotic, meme-speak (minimal words, max impact)
4. scene_visual MUST match what the narration describes
5. Sound like a HUMAN telling a story to a friend, NOT a robot reading news!

🎯 FOR {genre.upper()} GENRE:
{cold_open_instruction}

=== ✍️ WRITING STYLE (STORYTELLER MODE) ===
✅ DO:
- Act like a YouTuber/Influencer telling a crazy story to a friend
- Use "Forward Momentum": Every sentence must give NEW info or NEW emotion!
- Match the {genre} tone exactly!

{language_rules}

❌ DON'T:
- Repeat information (e.g., don't say "he was angry" then "he felt rage")
- "Spread" thin content just to fill time (Combine beats instead!)
- Sound like you are reading a script or news report
- Use filler words ("So then...", "Basically...", "As you can see")
- Use em-dash (—), en-dash (–), or double hyphen (--)

=== OUTPUT FORMAT (JSON) ===
Respond with a SINGLE Valid JSON object. No markdown code blocks.
{{
  "hook": "Short clickbait title (5-10 words) in {language}",
  "parts": [
    {{
      "part_name": "[THE HOOK]",
      "scenes": [
        {{
          "narration": "Natural narration in {language} - match {genre} tone!",
          "scene_visual": "ENGLISH: [SUBJECT] [ACTION], [SETTING], [LIGHTING]",
          "character_desc": "Main subject",
          "mood": "Emotional tone matching {genre}",
          "camera": "medium shot / close-up / wide shot"
        }},
        {{
          "narration": "Continue the story naturally...",
          "scene_visual": "..."
        }}
      ]
    }},
    {{
      "part_name": "[THE DETAIL]",
      "scenes": [...]
    }},
    {{
      "part_name": "[THE REALIZATION]",
      "scenes": [...]
    }},
    {{
      "part_name": "[THE CLIMAX]",
      "scenes": [...]
    }},
    {{
      "part_name": "[THE ENDING]",
      "scenes": [...]
    }}
  ]
}}
=== 🔴 FINAL REMINDER: GENRE = {genre.upper()} ===
EVERY narration sentence MUST match {genre} tone:
- {genre_tone}
- {genre_style}
DO NOT write boring documentary-style narration! Match the {genre} feeling!

=== 🪝 HOOK RULES ===
- 5-10 words maximum, catchy
- In {language.upper()}
- Think YouTube clickbait title
- Examples: "Jangan Pernah Lakukan Ini!", "Fakta Mengejutkan!"

=== 🖼️ VISUAL-NARRATION SYNC (CRITICAL!) ===
scene_visual MUST illustrate EXACTLY what narration says:
- Narration about "toilet" → visual shows toilet
- Narration about "bacteria" → visual shows bacteria/microscopic view
- Narration about "hand dryer" → visual shows hand dryer
- DO NOT add elements not mentioned in narration
- DO NOT invent fantasy/horror unless narration mentions it

Format: "[SUBJECT] [ACTION], [SETTING], [OBJECTS], [LIGHTING]"

=== 🔴 FINAL REMINDER: GENRE = {genre.upper()} ===
EVERY narration sentence MUST match {genre} tone:
- {genre_tone}
- {genre_style}
DO NOT write boring documentary-style narration! Match the {genre} feeling!

=== 🎯 COLD OPEN VERIFICATION ===
Before finalizing, check Scene 1:
☑️ Is it from the MIDDLE or END of the transcript? (Not the beginning!)
☑️ Does it have ACTION, DRAMA, or REVELATION?
☑️ Would a viewer say "Wait, what happened?!" and want to watch more?
☑️ Does Scene 2 start with "But before that..." or "It all started when..."?

❌ BAD Scene 1 (Beginning): "Seorang pria pergi ke kebun binatang."
✅ GOOD Scene 1 (Climax): "Wajahnya berubah menjadi monster! Ia menjerit kesakitan!"

❌ BAD Scene 2: (Continues story normally)
✅ GOOD Scene 2: "Tapi tunggu—bagaimana ini bisa terjadi? Mari kita mundur sebentar..."

JSON output (no markdown):""" 
        # Fallback chain: Gemini → Groq LLaMA → Gemini retry
        response_text = None
        
        # Try 1: Gemini
        print("DEBUG: Trying Gemini...")
        response_text = _generate_with_gemini(prompt, api_key)
        
        # Try 2: Groq LLaMA fallback if Gemini fails
        if not response_text and groq_key:
            print("DEBUG: Gemini failed, trying Groq LLaMA...")
            response_text = _generate_with_groq(prompt, groq_key, language)
        
        # Try 3: Gemini retry with delay
        if not response_text:
            print("DEBUG: Groq failed, waiting 30s for Gemini retry...")
            time.sleep(30)
            response_text = _generate_with_gemini(prompt, api_key)
        
        if not response_text:
            print("ERROR: All text generation providers failed")
            return None
        
        # Parse JSON with robust cleaning
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        
        response_text = response_text.strip()
        
        # Use helper function to fix LLM JSON issues
        response_text = fix_gemini_json(response_text)
        
        # Save debug file
        try:
            debug_path = os.path.join(os.path.dirname(__file__), "debug_gemini_response.txt")
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(response_text)
        except:
            pass
        # Fix escaped quotes inside strings: \"word\" -> 'word'
        # This pattern finds quotes inside JSON string values
        def fix_inner_quotes(match):
            s = match.group(0)
            # Replace \" with ' inside the string (not at boundaries)
            inner = s[1:-1]  # Remove outer quotes
            inner = re.sub(r'\\"([^"\\]*)\\"', r"'\1'", inner)
            return '"' + inner + '"'
        
        response_text = re.sub(r'"[^"]*(?:\\"[^"]*)*"', fix_inner_quotes, response_text)
        
        try:
            data = json.loads(response_text)
            print(f"DEBUG: Successfully parsed JSON")
        except json.JSONDecodeError as e:
            print(f"DEBUG: JSON parse error: {e}")
            print(f"DEBUG: Response text (first 500 chars): {response_text[:500]}")
            # Try to extract just the array if present
            match = re.search(r'\[[\s\S]*\]', response_text)
            if match:
                try:
                    # Clean the extracted array too
                    arr_text = match.group()
                    arr_text = re.sub(r',\s*]', ']', arr_text)
                    data = json.loads(arr_text)
                    print("DEBUG: Recovered JSON from array pattern")
                except Exception as e2:
                    print(f"DEBUG: Array recovery failed: {e2}")
                    return None
            else:
                return None
        
        # Handle new parts-based schema, or legacy scenes-based schema
        hook_text = ""
        scenes_list = []
        
        if isinstance(data, dict) and 'parts' in data:
            # NEW SCHEMA: {hook: "...", parts: [{part_name, narration, visuals: [...]}]}
            hook_text = data.get('hook', '')
            parts_list = data.get('parts', [])
            print(f"DEBUG: Hook: '{hook_text[:50] if hook_text else 'N/A'}...'")
            print(f"DEBUG: Generated {len(parts_list)} narration parts")
            
            # Check if new schema (scenes[]) or old schema (visuals[])
            first_part = parts_list[0] if parts_list else {}
            uses_scenes_schema = 'scenes' in first_part
            
            if uses_scenes_schema:
                # NEW SCHEMA: parts[].scenes[] - each scene has its own narration
                for part_idx, part in enumerate(parts_list):
                    part_name = part.get('part_name', f'[PART {part_idx + 1}]')
                    scenes = part.get('scenes', [])
                    
                    print(f"DEBUG: Part {part_idx + 1} ({part_name}): {len(scenes)} scenes")
                    
                    # If no scenes provided, create one placeholder
                    if not scenes:
                        scenes = [{'narration': f'{part_name}', 'scene_visual': f'{part_name} visual'}]
                    
                    # Each scene already has its own narration
                    for scene_idx, scene in enumerate(scenes):
                        scenes_list.append({
                            'narration': scene.get('narration', ''),
                            'scene_visual': scene.get('scene_visual', ''),
                            'character_desc': scene.get('character_desc', 'a person'),
                            'character_action': scene.get('character_action', ''),
                            'background_desc': scene.get('background_desc', ''),
                            'mood': scene.get('mood', 'neutral'),
                            'camera': scene.get('camera', 'medium shot'),
                            'part_name': part_name,
                            'part_idx': part_idx,
                            'scene_idx': scene_idx
                        })
            else:
                # OLD SCHEMA: parts[].visuals[] with one narration per part
                # Backward compatible - first visual gets narration
                for part_idx, part in enumerate(parts_list):
                    part_name = part.get('part_name', f'[PART {part_idx + 1}]')
                    part_narration = part.get('narration', '')
                    visuals = part.get('visuals', [])
                    
                    print(f"DEBUG: Part {part_idx + 1} ({part_name}): {len(visuals)} visuals (old schema)")
                    
                    if not visuals:
                        visuals = [{'scene_visual': f'{part_name} visual', 'camera': 'medium shot'}]
                    
                    for viz_idx, visual in enumerate(visuals):
                        scenes_list.append({
                            'narration': part_narration if viz_idx == 0 else '',
                            'scene_visual': visual.get('scene_visual', ''),
                            'character_desc': visual.get('character_desc', 'a person'),
                            'character_action': visual.get('character_action', ''),
                            'background_desc': visual.get('background_desc', ''),
                            'mood': visual.get('mood', 'neutral'),
                            'camera': visual.get('camera', 'medium shot'),
                            'part_name': part_name,
                            'part_idx': part_idx,
                            'is_first_in_part': viz_idx == 0
                        })
            
            print(f"DEBUG: Flattened to {len(scenes_list)} total scenes")
            base_character = None
            
        elif isinstance(data, dict) and 'scenes' in data:
            # LEGACY SCHEMA: {hook: "...", scenes: [...]}
            hook_text = data.get('hook', '')
            scenes_list = data.get('scenes', [])
            base_character = data.get('character', {}).get('appearance', 'a person') if isinstance(data.get('character'), dict) else None
            print(f"DEBUG: Legacy schema - Hook: '{hook_text[:50] if hook_text else 'N/A'}...'")
            print(f"DEBUG: Generated {len(scenes_list)} scenes")
            
        elif isinstance(data, list):
            # OLD FLAT SCHEMA: [...] - generate simple hook from first narration
            scenes_list = data
            base_character = None
            if scenes_list and scenes_list[0].get('narration'):
                words = scenes_list[0]['narration'].split()[:5]
                hook_text = " ".join(words) + "..."
            print(f"DEBUG: Flat schema - Generated {len(scenes_list)} scenes")
        else:
            print(f"DEBUG: Unexpected response format")
            return None
        
        # For parts schema, don't truncate - we already have correct distribution
        # For legacy schema, enforce scene count
        
        # Validate and enhance
        valid_scenes = []
        
        for i, scene in enumerate(scenes_list):
            # Extract narration from different possible fields
            # IMPORTANT: Empty string '' is valid (for non-speaking visuals), only fallback if None
            narration = scene.get('narration')
            if narration is None:
                narration = scene.get('transcript_portion')
            # Intentionally NO fallback to "Scene X" - empty narration means visual-only
            
            # Get character from first scene if not already set
            if i == 0 and not base_character:
                base_character = scene.get('character_desc', 'a person')
            
            # Build visual components
            visual = scene.get('visual', {})
            char_action = visual.get('character_action', scene.get('character_action', 'standing'))
            expression = visual.get('expression', '')
            bg_desc = visual.get('background', scene.get('background_desc', 'simple background'))
            camera = visual.get('camera', scene.get('camera', 'medium shot'))
            mood = scene.get('mood', 'neutral')
            
            # Get scene_visual for contextual image generation
            scene_visual = scene.get('scene_visual', '')
            
            # Clean scene_visual: remove quotes and extra spaces that AI may add
            if scene_visual:
                scene_visual = scene_visual.strip().strip("'\"").strip()
                # Remove any remaining internal single quotes that break prompts
                scene_visual = scene_visual.replace("'", "").replace('"', '')
            
            # Build enhanced visual prompt with scene_visual context
            if scene_visual:
                # scene_visual already contains: subject, action, setting, lighting
                # Use it DIRECTLY as the main content - don't add fallback fields!
                style_info = VISUAL_STYLES.get(style, VISUAL_STYLES["Ghibli Anime"])
                style_suffix = style_info.get("suffix", "anime style")
                filter_suffix = FILTER_IMAGE_SUFFIX.get(filter_overlay, "") if filter_overlay else ""
                
                # Build prompt: scene_visual + style + quality
                quality_tags = "masterpiece, best quality, highly detailed, sharp focus"
                prompt_parts = [
                    scene_visual,  # Already complete: "King on throne, coffee cup, castle interior"
                    style_suffix,
                    quality_tags,
                    "portrait composition, vertical format"
                ]
                if filter_suffix:
                    prompt_parts.append(filter_suffix)
                    
                visual_prompt = ", ".join(filter(None, prompt_parts))
                print(f"DEBUG: Scene {i} using scene_visual: {scene_visual[:60]}...")
            else:
                # Fallback to character action if scene_visual not provided
                action_text = char_action
                if expression:
                    action_text = f"{char_action}, {expression} expression"
                
                visual_prompt = build_image_prompt(
                    character_desc=base_character,
                    action=action_text,
                    background=bg_desc,
                    style=style,
                    camera=camera,
                    mood=mood,
                    filter_overlay=filter_overlay or "None"
                )
            
            valid_scenes.append({
                'index': i,
                'narration': narration,
                'visual_prompt': visual_prompt,
                'character_desc': base_character,
                'background_desc': bg_desc,
                'mood': mood,
                'camera': camera,
                'style': style
            })
        
        # Store hook_text in first scene for later use in video rendering
        if valid_scenes and hook_text:
            valid_scenes[0]['hook_text'] = hook_text
            print(f"DEBUG: Stored hook in scene 0: '{hook_text}'")
        
        print(f"DEBUG: {len(valid_scenes)} valid scenes prepared")
        return valid_scenes
        
    except Exception as e:
        print(f"Story generation error: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# TTS GENERATION (Simple & Clean)
# ============================================================================
def clean_narration_text(text: str) -> str:
    """
    Clean narration text for TTS - remove any markup, timestamps, tags, and quotes.
    Returns only pure readable text suitable for natural speech.
    """
    import re
    
    # === QUOTE REMOVAL (Critical for natural TTS) ===
    # Remove leading/trailing quotes from entire text
    text = text.strip("'\"")
    
    # Fix pattern: 'word', or "word", (AI often wraps sentences in quotes)
    text = re.sub(r"^['\"](.+?)['\"],?\s*", r"\1 ", text)
    
    # Remove quotes around sentences mid-text: 'Sentence here', next
    text = re.sub(r"['\"]([^'\"]+?)['\"],\s*", r"\1, ", text)
    
    # Remove any remaining stray single/double quotes
    text = re.sub(r"['\"]", "", text)
    
    # Fix double commas that may result from cleanup
    text = re.sub(r",\s*,", ",", text)
    
    # === ORIGINAL CLEANUP ===
    # Remove any XML/HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove timestamps like [00:00] or (00:00:00)
    text = re.sub(r'\[\d+:\d+(?::\d+)?\]', '', text)
    text = re.sub(r'\(\d+:\d+(?::\d+)?\)', '', text)
    
    # Remove SSML-like tags if any leaked through
    text = re.sub(r'<speak[^>]*>', '', text)
    text = re.sub(r'</speak>', '', text)
    text = re.sub(r'<prosody[^>]*>', '', text)
    text = re.sub(r'</prosody>', '', text)
    text = re.sub(r'<break[^>]*/>', '', text)
    
    # === FINAL CLEANUP ===
    # Remove multiple spaces and trim
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Ensure proper sentence ending
    if text and not text[-1] in '.!?':
        text += '.'
    
    return text


async def generate_tts_async(text: str, voice: str, output_path: str) -> bool:
    """
    Generate TTS using Edge-TTS with natural prosody settings.
    Optimized for human-like delivery similar to ElevenLabs:
    - Slight pitch variation for expressiveness
    - Natural speaking rate (not too fast, not robotic)
    - Volume boost for clarity on mobile devices
    """
    if edge_tts is None:
        return False
    
    try:
        voice_id = VOICE_OPTIONS.get(voice, "en-US-JennyNeural")
        
        # Clean the text - remove any tags, timestamps, markup
        clean_text = clean_narration_text(text)
        
        if not clean_text:
            print(f"TTS error: Empty text after cleaning")
            return False
        
        print(f"DEBUG TTS: '{clean_text[:80]}...' -> {voice_id}")
        
        # Natural prosody settings for human-like delivery:
        # - rate: +0% (normal speed, humanize_audio adds slight tempo variation later)
        # - volume: +10% (clearer on mobile speakers)
        communicate = edge_tts.Communicate(
            clean_text, 
            voice_id, 
            rate="+35%",      # VIRAL SPEED: +35% (TikToK Standard)
            volume="+10%"    # Louder for mobile clarity
        )
        await communicate.save(output_path)
        
        return os.path.exists(output_path)
    except Exception as e:
        print(f"TTS error: {e}")
        return False


def generate_tts(text: str, voice: str, output_path: str, humanize: bool = True) -> bool:
    """Sync wrapper for TTS with optional humanization"""
    try:
        result = asyncio.run(generate_tts_async(text, voice, output_path))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(generate_tts_async(text, voice, output_path))
        loop.close()
    
    # Apply humanization post-processing if enabled and TTS succeeded
    if result and humanize and os.path.exists(output_path):
        result = humanize_audio(output_path)
    
    return result


def humanize_audio(audio_path: str, ffmpeg_path: str = "ffmpeg") -> bool:
    """
    Apply humanization effects to TTS audio to bypass YouTube's mass-produced content detection.
    
    Effects applied:
    1. Random pitch variation (±3%) - Makes voice sound slightly different each time
    2. Subtle speed variation (±2%) - Breaks TTS pattern
    3. Light room reverb - "Recorded in room" feel vs clean TTS
    4. Micro ambient noise - Adds slight background texture
    
    Returns True if successful, False on error (original file kept on failure)
    """
    import random
    
    try:
        # Generate random EQ variations for unique audio fingerprint
        # NOTE: Pitch manipulation removed - caused speed issues due to sample rate mismatch
        # Edge-TTS outputs 24000Hz, not 48000Hz as previously assumed
        eq_freq = random.randint(150, 400)
        eq_gain = random.uniform(-1.0, 1.0)
        
        # VIRAL SWEET SPOT: 1.10x to 1.25x (Fast but Clear)
        speed_var = random.uniform(1.10, 1.25)
        
        # Build audio filter chain:
        # 1. atempo: Dynamic speed/pacing
        # 2. aecho: Distinct reverb (Anti-duplication signature)
        # 3. equalizer: Random tone variation
        audio_filter = (
            f"atempo={speed_var:.2f},"
            f"aecho=0.8:0.9:40:0.3,"                         # Stronger reverb for unique signature
            f"equalizer=f={eq_freq}:width_type=h:width=100:gain={eq_gain:.2f},"
            f"volume=1.0"
        )
        
        # Create temp output
        temp_output = audio_path.replace('.mp3', '_humanized.mp3').replace('.wav', '_humanized.wav')
        
        cmd = [
            ffmpeg_path, '-y',
            '-i', audio_path,
            '-af', audio_filter,
            '-c:a', 'libmp3lame',
            '-q:a', '2',  # High quality
            temp_output
        ]
        
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        if result.returncode == 0 and os.path.exists(temp_output):
            # Replace original with humanized version
            try:
                os.remove(audio_path)
                os.rename(temp_output, audio_path)
                print(f"DEBUG: Audio humanized (EQ: {eq_freq}Hz, gain: {eq_gain:.2f}dB)")
                return True
            except Exception as e:
                print(f"DEBUG: Humanize file swap error: {e}")
                # Cleanup temp if swap failed
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                return True  # Original file still exists
        else:
            print(f"DEBUG: Humanize FFmpeg failed: {result.stderr[:100] if result.stderr else 'Unknown'}")
            return True  # Return True - original file is still usable
            
    except Exception as e:
        print(f"DEBUG: Humanize error: {e}")
        return True  # Return True - original file is still usable


# ============================================================================
# ASS SUBTITLE (Clipper Style)
# ============================================================================
def create_ass_subtitle_clipper_style(
    scenes: List[Dict],
    durations: List[float],
    output_path: str,
    caption_style: str = "Karaoke (Bounce)"
) -> bool:
    """
    Create ASS subtitle with configurable styles.
    
    Styles:
    - Karaoke (Bounce): Word-by-word yellow highlight (default)
    - Minimal: Simple white text, fade in/out
    - Bold Boxed: White text with black box background
    - Typewriter: Character-by-character reveal effect
    """
    
    # Caption style configurations
    CAPTION_STYLES = {
        "Karaoke (Bounce)": {
            "font": "Arial Black",
            "size": 80,
            "outline": 5,
            "effect": "karaoke"
        },
        "Minimal": {
            "font": "Arial",
            "size": 60,
            "outline": 2,
            "effect": "fade"
        },
        "Bold Boxed": {
            "font": "Impact",
            "size": 72,
            "outline": 0,
            "effect": "boxed"  # BorderStyle=3 for opaque box
        },
        "Typewriter": {
            "font": "Courier New",
            "size": 56,
            "outline": 3,
            "effect": "typewriter"
        }
    }
    
    style_config = CAPTION_STYLES.get(caption_style, CAPTION_STYLES["Karaoke (Bounce)"])
    print(f"DEBUG: Using caption style: {caption_style}")
    
    def seconds_to_ass(secs: float) -> str:
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = secs % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    
    events = []
    current_time = 0.0
    
    for i, scene in enumerate(scenes):
        # Clean narration text - remove quotes and fix formatting
        raw_text = scene.get('narration', '')
        text = clean_narration_text(raw_text)
        duration = durations[i] if i < len(durations) else 3.0
        
        words = text.split()
        if not words:
            current_time += duration
            continue
        
        effect_type = style_config["effect"]
        
        if effect_type == "karaoke":
            # Word-by-word highlight with yellow color
            chunk_size = 3
            chunks = [words[j:j+chunk_size] for j in range(0, len(words), chunk_size)]
            chunk_duration = duration / len(chunks) if chunks else duration
            
            for chunk_idx, chunk in enumerate(chunks):
                chunk_start = current_time + (chunk_idx * chunk_duration)
                word_dur = chunk_duration / len(chunk)
                
                for word_idx, word in enumerate(chunk):
                    word_start = chunk_start + (word_idx * word_dur)
                    word_end = chunk_start + ((word_idx + 1) * word_dur)
                    
                    line_parts = []
                    for j, w in enumerate(chunk):
                        if j == word_idx:
                            line_parts.append(f"{{\\c&H00FFFF&\\b1}}{w}{{\\c&HFFFFFF&\\b0}}")
                        else:
                            line_parts.append(w)
                    
                    line_text = " ".join(line_parts)
                    events.append(f"Dialogue: 0,{seconds_to_ass(word_start)},{seconds_to_ass(word_end)},Default,,0,0,0,,{line_text}")
        
        elif effect_type == "fade":
            # Simple fade in/out for entire text
            events.append(f"Dialogue: 0,{seconds_to_ass(current_time)},{seconds_to_ass(current_time + duration)},Default,,0,0,0,,{{\\fad(300,300)}}{text}")
        
        elif effect_type == "boxed":
            # Text with opaque background box
            events.append(f"Dialogue: 0,{seconds_to_ass(current_time)},{seconds_to_ass(current_time + duration)},Boxed,,0,0,0,,{text}")
        
        elif effect_type == "typewriter":
            # Character-by-character reveal
            char_dur = duration / len(text) if text else duration
            revealed = ""
            for char_idx, char in enumerate(text):
                revealed += char
                char_start = current_time + (char_idx * char_dur)
                char_end = current_time + ((char_idx + 1) * char_dur)
                events.append(f"Dialogue: 0,{seconds_to_ass(char_start)},{seconds_to_ass(char_end)},Default,,0,0,0,,{revealed}")
        
        current_time += duration
    
    # Build ASS style based on configuration
    font = style_config["font"]
    size = style_config["size"]
    outline = style_config["outline"]
    border_style = 3 if style_config["effect"] == "boxed" else 1
    
    ass_content = f"""[Script Info]
Title: Kilat Animator Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,{border_style},{outline},2,8,40,40,300,1
Style: Boxed,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&HCC000000,-1,0,0,0,100,100,0,0,3,0,0,8,40,40,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        return True
    except Exception as e:
        print(f"ASS subtitle error: {e}")
        return False


# ============================================================================
# 2.5D EFFECTS ENGINE
# ============================================================================
def get_audio_duration(audio_path: str, ffprobe_path: str = "ffprobe") -> float:
    """Get audio duration in seconds"""
    try:
        cmd = [
            ffprobe_path, '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        return float(result.stdout.strip()) if result.stdout.strip() else 3.0
    except:
        return 3.0


def render_scene_with_effects(
    image_path: str,
    audio_path: str,
    subtitle_path: str,
    output_path: str,
    duration: float,
    effect_type: str,
    scene_index: int,
    ffmpeg_path: str = "ffmpeg",
    watermark_path: str = "",
    filter_overlay: str = "None",
    hook_text: str = "",  # Hook text overlay for first 5 seconds
    enable_flash: bool = True  # White flash at scene start for overstimulation
) -> bool:
    """
    Render scene with 2.5D effects:
    - Ken Burns (zoom + pan)
    - Parallax simulation (offset movement)
    - Smooth fade transitions
    - ASS subtitle overlay
    - Color filter overlay (Sepia, Noir, VHS, Vivid)
    - Hook text overlay (first 5 seconds, like Clipper does)
    - White flash at scene start (overstimulation effect)
    
    Output: 1080x1920 portrait at 24fps
    """
    # Use GLOBAL FILTER_EFFECTS defined at top of file (line ~530)
    # DO NOT redefine local - it has 10 genre-matched filters:
    # None, Bright Inspire, Dark Terror, Fun Pop, Soft Wonder, 
    # Clean Pro, Magic Glow, Cyber Neon, Viral Punch, Meme Chaos
    
    try:
        if not os.path.exists(image_path):
            print(f"ERROR: Image not found: {image_path}")
            return False
        
        frame_count = int(duration * DEFAULT_FPS)
        
        # Define effect variations
        effects = {
            "zoom_in": f"zoompan=z='min(zoom+0.0015,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frame_count}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={DEFAULT_FPS}",
            "zoom_out": f"zoompan=z='if(lte(zoom,1.0),1.3,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frame_count}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={DEFAULT_FPS}",
            "pan_right": f"zoompan=z='1.2':x='(iw-iw/zoom)/2-100*sin(on/{frame_count}*PI)':y='ih/2-(ih/zoom/2)':d={frame_count}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={DEFAULT_FPS}",
            "pan_left": f"zoompan=z='1.2':x='(iw-iw/zoom)/2+100*sin(on/{frame_count}*PI)':y='ih/2-(ih/zoom/2)':d={frame_count}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={DEFAULT_FPS}",
            "pan_up": f"zoompan=z='1.2':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)/2+80*sin(on/{frame_count}*PI)':d={frame_count}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={DEFAULT_FPS}",
            "breathing": f"zoompan=z='1.15+0.03*sin(on/30)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frame_count}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={DEFAULT_FPS}"
        }
        
        effect_filter = effects.get(effect_type, effects["zoom_in"])
        
        # Get color filter for overlay
        color_filter = FILTER_EFFECTS.get(filter_overlay, "")
        if color_filter:
            print(f"DEBUG: Applying filter overlay: {filter_overlay}")
        
        # Build transition effect - faster fade for overstimulation effect
        if enable_flash and scene_index > 0:  # Fast fade on scene change (not first scene)
            # Quick fade in (0.15s) creates attention-grabbing effect like flash
            flash_effect = f",fade=t=in:st=0:d=0.15,fade=t=out:st={max(0.1, duration-0.2)}:d=0.2"
        else:
            # Standard fade for first scene
            flash_effect = f",fade=t=in:st=0:d=0.3,fade=t=out:st={max(0.1, duration-0.3)}:d=0.3"
        
        # Build filter chain: scale → zoompan → flash/fade → color filter → subtitle
        filter_complex = (
            f"[0:v]scale=2160:3840:force_original_aspect_ratio=increase,"
            f"crop=2160:3840,"
            f"{effect_filter}"
            f"{flash_effect}"
            f"{color_filter}"  # Apply color filter after fade
        )
        
        # Add subtitle if exists
        if subtitle_path and os.path.exists(subtitle_path):
            # Escape path for Windows
            safe_sub_path = subtitle_path.replace('\\', '/').replace(':', '\\:')
            filter_complex += f",ass='{safe_sub_path}'"
        
        # Determine input count for filter mapping
        has_watermark = watermark_path and os.path.exists(watermark_path)
        
        if has_watermark:
            # Add watermark FIRST with overlay - scale to 10% of video width, centered
            filter_complex += f"[v1];[2:v]scale=108:-1[wm];[v1][wm]overlay=(W-w)/2:(H-h)/2"
        
        # Add hook text AFTER watermark (so hook appears ON TOP of everything!)
        # This is the LAST layer - will not be covered by anything
        if hook_text and scene_index == 0:  # Only show hook on first scene
            # Clean hook text: remove problematic characters
            escaped_hook = hook_text.replace("\\", "").replace("'", "").replace('"', "")
            escaped_hook = escaped_hook.replace(":", " ").replace("\n", " ").replace("\r", " ")
            escaped_hook = escaped_hook[:60]  # Limit total length
            
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
                
                # REFERENCE STYLE: White/Gray box with BLACK text (like screenshot)
                # Single unified card appearance
                # Line 1 - upper part of hook box
                filter_complex += (
                    f",drawtext=text='{line1}':"
                    f"fontsize=64:fontcolor=black:"
                    f"x=(w-text_w)/2:y=(h/2)-70:"
                    f"enable='between(t,0,5)':"
                    f"box=1:boxcolor=white@0.95:boxborderw=25"
                )
                
                # Draw line 2 if exists - positioned right below line 1
                if line2.strip():
                    filter_complex += (
                        f",drawtext=text='{line2}':"
                        f"fontsize=64:fontcolor=black:"
                        f"x=(w-text_w)/2:y=(h/2)+20:"
                        f"enable='between(t,0,5)':"
                        f"box=1:boxcolor=white@0.95:boxborderw=25"
                    )
        
        # Final output label
        filter_complex += "[v]"
        
        cmd = [
            ffmpeg_path, '-y',
            '-loop', '1',
            '-i', image_path,
            '-i', audio_path,
        ]
        
        if has_watermark:
            cmd.extend(['-i', watermark_path])
        
        cmd.extend([
            '-filter_complex', filter_complex,
            '-map', '[v]',
            '-map', '1:a',
            # Video: H.264 High Profile for YouTube HD
            '-c:v', 'libx264',
            '-profile:v', 'high',      # YouTube recommended profile
            '-level:v', '4.0',         # Level 4.0 for 1080p
            '-pix_fmt', 'yuv420p',     # Max compatibility
            '-preset', 'slow',         # Better quality (was medium)
            '-crf', '17',              # Higher quality (was 18)
            '-b:v', '20M',             # INCREASED bitrate for larger files (was 12M)
            '-maxrate', '25M',         # INCREASED peak bitrate (was 15M)
            '-bufsize', '30M',         # INCREASED buffer (was 20M)
            # Audio: AAC with higher bitrate
            '-c:a', 'aac',
            '-b:a', '256k',            # Higher audio quality (was 192k)
            '-ar', '48000',            # 48kHz sample rate (YouTube preferred)
            # Duration and output
            '-t', str(duration),
            '-shortest',
            '-movflags', '+faststart', # Enable streaming/quick playback
            output_path
        ])
        
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        success = os.path.exists(output_path) and os.path.getsize(output_path) > 1000
        if not success:
            print(f"ERROR: Scene render failed: {result.stderr[:300] if result.stderr else 'Unknown'}")
        
        return success
        
    except Exception as e:
        print(f"Render error: {e}")
        return False


def assemble_final_video(
    scene_videos: List[str],
    output_path: str,
    ffmpeg_path: str = "ffmpeg",
    enable_progress_bar: bool = True  # Add progress bar at bottom
) -> bool:
    """Concatenate all scenes with smooth transitions and optional progress bar overlay"""
    try:
        if not scene_videos:
            print("ERROR: No scene videos to assemble")
            return False
        
        valid_videos = [v for v in scene_videos if os.path.exists(v) and os.path.getsize(v) > 1000]
        
        if not valid_videos:
            print("ERROR: No valid scene videos")
            return False
        
        print(f"DEBUG: Assembling {len(valid_videos)} scenes")
        
        # Create concat file
        concat_file = output_path.replace('.mp4', '_concat.txt')
        with open(concat_file, 'w', encoding='utf-8') as f:
            for video in valid_videos:
                safe_path = video.replace('\\', '/')
                f.write(f"file '{safe_path}'\n")
        
        # TWO-PASS PROGRESS BAR APPROACH:
        # Pass 1: Concatenate videos to temp file
        # Pass 2: Apply progress bar with known duration
        
        if enable_progress_bar:
            temp_concat = output_path.replace('.mp4', '_temp_concat.mp4')
        else:
            temp_concat = output_path  # Skip temp, output directly
        
        # Pass 1: Concatenate without filter
        cmd_concat = [
            ffmpeg_path, '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',  # Fast copy, no re-encode
            temp_concat
        ]
        
        result = subprocess.run(
            cmd_concat, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        if result.returncode != 0 or not os.path.exists(temp_concat):
            print(f"ERROR: Concat failed: {result.stderr[:200] if result.stderr else 'Unknown'}")
            try:
                os.remove(concat_file)
            except:
                pass
            return False
        
        # Pass 2: Add progress bar if enabled
        if enable_progress_bar:
            # Get duration from concatenated video
            total_duration = get_audio_duration(temp_concat, ffmpeg_path.replace('ffmpeg', 'ffprobe'))
            if total_duration <= 0:
                total_duration = 60  # Fallback 60s
            
            print(f"DEBUG: Applying progress bar (duration: {total_duration:.1f}s)")
            
            # HIGH-CONTRAST PROGRESS BAR using overlay with animated x position
            # CRITICAL: color sources MUST have duration to avoid infinite loop!
            bar_height = 10
            border = 2
            bar_y_pos = 25  # Distance from bottom
            
            # filter_complex: create color bars and overlay with animation
            # NOTE: :d={duration} is CRITICAL, without it FFmpeg creates infinite frames!
            progress_filter = (
                # Black border bar (full width, static) - WITH DURATION
                f"color=c=black:s=1080x{bar_height+border*2}:d={total_duration}[border];"
                # Cyan fill bar (animated) - WITH DURATION
                f"color=c=0x00FFFF:s=1080x{bar_height}:d={total_duration}[fill];"
                # Overlay border on video
                f"[0:v][border]overlay=0:H-{bar_height+border*2+bar_y_pos}:shortest=1[with_border];"
                # Overlay animated fill on top (x slides from -W to 0) - WITH SHORTEST
                f"[with_border][fill]overlay=x='W*(t/{total_duration}-1)':y=H-{bar_height+border+bar_y_pos}:shortest=1"
            )
            
            # Detect GPU encoder for faster encoding
            encoder, enc_preset = detect_gpu_encoder(ffmpeg_path)
            print(f"DEBUG: [Animator] GPU Encoder Detection:")
            print(f"DEBUG:   Detected encoder: {encoder}")
            
            # Build encoding parameters based on detected encoder
            # Using BEST QUALITY preset for each encoder type
            if encoder == "libx264":
                # CPU: slow = best quality/size ratio
                enc_params = [
                    '-c:v', 'libx264',
                    '-profile:v', 'high',
                    '-level:v', '4.0',
                    '-pix_fmt', 'yuv420p',
                    '-preset', 'slow',  # BEST quality for libx264
                    '-crf', '17',
                    '-b:v', '20M',
                    '-maxrate', '25M',
                    '-bufsize', '30M',
                ]
            elif encoder == "h264_nvenc":
                # NVIDIA: p7 = HIGHEST quality (slowest)
                enc_params = [
                    '-c:v', 'h264_nvenc',
                    '-profile:v', 'high',
                    '-pix_fmt', 'yuv420p',
                    '-preset', 'p7',  # BEST quality for NVENC (slow)
                    '-rc', 'vbr',
                    '-cq', '17',  # Same quality as CRF 17
                    '-b:v', '20M',
                    '-maxrate', '25M',
                    '-bufsize', '30M',
                ]
            elif encoder == "h264_qsv":
                # Intel: veryslow = HIGHEST quality
                enc_params = [
                    '-c:v', 'h264_qsv',
                    '-profile:v', 'high',
                    '-pix_fmt', 'nv12',
                    '-preset', 'veryslow',  # BEST quality for Intel QSV
                    '-global_quality', '17',  # Same quality as CRF 17
                    '-b:v', '20M',
                    '-maxrate', '25M',
                    '-bufsize', '30M',
                ]
            else:
                # AMD: quality = HIGHEST quality
                enc_params = [
                    '-c:v', 'h264_amf',
                    '-profile:v', 'high',
                    '-pix_fmt', 'yuv420p',
                    '-quality', 'quality',  # BEST quality for AMD AMF
                    '-rc', 'vbr_peak',
                    '-qp_i', '17',
                    '-qp_p', '17',
                    '-b:v', '20M',
                    '-maxrate', '25M',
                    '-bufsize', '30M',
                ]
            
            # Log encoder settings
            print(f"DEBUG:   Encoding params: {' '.join(enc_params[:6])}...")
            print(f"DEBUG:   Quality: CRF/CQ=17, Bitrate=12M, MaxRate=15M")
            
            cmd_progress = [
                ffmpeg_path, '-y',
                '-i', temp_concat,
                '-filter_complex', progress_filter,
            ] + enc_params + [
                '-c:a', 'copy',  # Keep audio as-is
                '-movflags', '+faststart',
                output_path
            ]
            
            result = subprocess.run(
                cmd_progress, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            try:
                os.remove(temp_concat)
            except:
                pass
        
        # Cleanup
        try:
            os.remove(concat_file)
        except:
            pass
        
        success = os.path.exists(output_path) and os.path.getsize(output_path) > 1000
        if success:
            print(f"DEBUG: Final video: {output_path} ({os.path.getsize(output_path)} bytes)")
            if enable_progress_bar:
                print("DEBUG: Progress bar overlay added")
        else:
            print(f"ERROR: Assembly failed: {result.stderr[:300] if result.stderr else 'Unknown'}")
        
        return success
        
    except Exception as e:
        print(f"Assembly error: {e}")
        return False


# ============================================================================
# MAIN GENERATION PIPELINE
# ============================================================================
def generate_animation_v2(
    transcript: str,
    genre: str,
    style: str,
    voice: str,
    num_scenes: int,
    gemini_key: str,
    output_folder: str,
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
    progress_callback = None,
    groq_key: str = "",
    watermark_path: str = "",
    filter_overlay: str = "None",
    caption_style: str = "Karaoke (Bounce)",
    language_override: str = "",
    animation_mode: str = "Full 2.5D"  # NEW: Kling AI 3D mode (Full 2.5D, Hybrid, Full 3D)
) -> Optional[str]:
    """
    Complete animation generation pipeline v2.
    Returns path to final video or None on failure.
    
    New parameters:
    - filter_overlay: Video filter effect (None, Sepia, Noir B&W, Vintage VHS, Vivid)
    - caption_style: Subtitle animation style (Karaoke, Minimal, Bold Boxed, Typewriter)
    - language_override: Override auto-detected language
    - animation_mode: Animation type (Full 2.5D, Hybrid, Full 3D) - Kling AI integration
    """
    try:
        # Detect hardware
        hw = detect_hardware()
        
        # === CRITICAL: Force resolve bundled FFmpeg/FFprobe ===
        # In distribution, "ffmpeg" is not in PATH. We must find it in bin/.
        if ffmpeg_path == "ffmpeg" or not os.path.exists(ffmpeg_path):
             possible_bins = [
                 os.path.join(os.getcwd(), "bin", "ffmpeg.exe"),
                 os.path.join(os.path.dirname(__file__), "bin", "ffmpeg.exe"),
                 os.path.join(os.path.dirname(__file__), "_internal", "bin", "ffmpeg.exe"),
             ]
             for p in possible_bins:
                 if os.path.exists(p):
                     ffmpeg_path = p
                     print(f"DEBUG: Auto-resolved Bundled FFmpeg: {ffmpeg_path}")
                     break
        
        if ffprobe_path == "ffprobe" or not os.path.exists(ffprobe_path):
             expected_ffprobe = os.path.join(os.path.dirname(ffmpeg_path), "ffprobe.exe")
             if os.path.exists(expected_ffprobe):
                 ffprobe_path = expected_ffprobe
        print(f"DEBUG: Using quality preset: {hw.quality}")
        print(f"DEBUG: Filter: {filter_overlay}, Caption: {caption_style}")
        
        os.makedirs(output_folder, exist_ok=True)
        
        # Step 1: Generate story script
        if progress_callback:
            progress_callback(0.1, "✍️ AI is writing the story...")
        
        # SUBTITLE language: from Language dropdown (language_override)
        # VOICE language: determined by voice name (e.g., "Indonesian Female" → Indonesian TTS)
        # These can be DIFFERENT! Example: English voice + Indonesian subtitles
        
        # Subtitle language (for narration text generation)
        if language_override and language_override not in ["Auto-Detect", ""]:
            subtitle_language = language_override.replace(" (US)", "").replace(" (UK)", "")
        else:
            # Auto-detect from voice name
            subtitle_language = "Indonesian" if "Indonesian" in voice else "English"
        
        # Voice language (for TTS) - always from voice dropdown
        voice_language = "Indonesian" if "Indonesian" in voice else "English"
        
        print(f"DEBUG: Subtitle language: {subtitle_language}")
        print(f"DEBUG: Voice language: {voice_language} (from voice: {voice})")
        
        scenes = generate_story_script(transcript, genre, style, gemini_key, num_scenes, subtitle_language, groq_key, filter_overlay)
        if not scenes:
            raise Exception("Failed to generate story script")
        
        print(f"DEBUG: Generated {len(scenes)} scenes in {subtitle_language}")
        
        # Save transcript to temp folder for debugging/reference
        try:
            transcript_path = os.path.join(output_folder, "transcript.txt")
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write("=== ORIGINAL TRANSCRIPT ===\n\n")
                f.write(transcript)
                f.write("\n\n=== GENERATION INFO ===\n")
                f.write(f"Genre: {genre}\n")
                f.write(f"Style: {style}\n")
                f.write(f"Language: {subtitle_language}\n")
                f.write(f"Scenes: {len(scenes)}\n")
            print(f"DEBUG: Transcript saved to {transcript_path}")
        except Exception as e:
            print(f"DEBUG: Failed to save transcript: {e}")
        
        # Step 2: Generate images with seed consistency
        if progress_callback:
            progress_callback(0.2, "🎨 Generating consistent visuals...")
        
        base_seed = 42000  # Fixed seed for character consistency
        
        for i, scene in enumerate(scenes):
            image_path = os.path.join(output_folder, f"scene_{i:02d}.jpg")
            
            # Use base_seed + offset for variety while keeping style
            scene_seed = base_seed + (i * 10)
            
            success = generate_image_hybrid(
                scene['visual_prompt'],
                style,
                image_path,
                seed=scene_seed,
                width=IMAGE_WIDTH,
                height=IMAGE_HEIGHT
            )
            
            if success:
                scene['image_path'] = image_path
            
            if progress_callback:
                prog = 0.2 + (0.3 * (i + 1) / len(scenes))
                # Include provider info in log for transparency
                provider_info = f" via {_last_image_provider}" if _last_image_provider else ""
                progress_callback(prog, f"🎨 Generated image {i+1}/{len(scenes)}{provider_info}")
        
        # Step 3: Generate audio (TTS)
        if progress_callback:
            progress_callback(0.5, "🎙️ Generating narration...")
        
        durations = []
        for i, scene in enumerate(scenes):
            audio_path = os.path.join(output_folder, f"scene_{i:02d}.mp3")
            
            success = generate_tts(scene['narration'], voice, audio_path)
            
            if success:
                scene['audio_path'] = audio_path
                duration = get_audio_duration(audio_path, ffprobe_path)
                scene['duration'] = duration
                durations.append(duration)
            else:
                durations.append(3.0)
            
            if progress_callback:
                prog = 0.5 + (0.1 * (i + 1) / len(scenes))
                progress_callback(prog, f"🎙️ Generated audio {i+1}/{len(scenes)}")
        
        # Step 3.5: Add SFX to audio (optional)
        # SFX Debug Logging
        def log_sfx_debug(msg):
            try:
                with open(os.path.join(output_folder, "sfx_debug.txt"), "a", encoding='utf-8') as f:
                    f.write(f"{msg}\n")
            except: pass

        log_sfx_debug("=== SFX DEBUG START ===")
        log_sfx_debug(f"FFmpeg Path: {ffmpeg_path}")
        log_sfx_debug(f"FFmpeg Exists: {os.path.exists(ffmpeg_path)}")
        
        # Priority: Check _internal first (Standard for Dist)
        current_dir = os.path.dirname(__file__)
        sfx_folder = os.path.join(current_dir, "_internal", "sfx")
        
        # Handle "Double Internal" issue (common in OneDir)
        if "_internal\\_internal" in sfx_folder:
             sfx_folder = sfx_folder.replace("_internal\\_internal", "_internal")
             
        log_sfx_debug(f"Checking _internal path: {sfx_folder}")
        
        # Fallback for Dev Environment
        if not os.path.exists(sfx_folder):
             log_sfx_debug("_internal not found. Checking root/sfx...")
             # Dev environment: sibling to script
             sfx_folder = os.path.join(current_dir, "sfx")
        
        log_sfx_debug(f"Resolved SFX Folder: {sfx_folder}")
        log_sfx_debug(f"Folder Exists: {os.path.exists(sfx_folder)}")
        
        if os.path.exists(sfx_folder):
            files = os.listdir(sfx_folder)
            log_sfx_debug(f"Files found ({len(files)}): {files[:5]}...")
        
        if os.path.exists(sfx_folder):
            available_sfx = [f for f in os.listdir(sfx_folder) if f.endswith(('.mp3', '.wav'))]
            print(f"DEBUG SFX: Available files: {available_sfx}")
            # Show SFX status in UI log
            if progress_callback:
                progress_callback(0.51, f"🔊 SFX Folder: {len(available_sfx)} files found")
            
            # First, try to add genre ambient background to first scene
            genre_ambient_name = GENRE_AMBIENT.get(genre, "")
            if genre_ambient_name:
                ambient_path = None
                for ext in ['.mp3', '.wav']:
                    test_path = os.path.join(sfx_folder, f"{genre_ambient_name}{ext}")
                    if os.path.exists(test_path):
                        ambient_path = test_path
                        break
                
                if ambient_path and scenes and scenes[0].get('audio_path'):
                    print(f"DEBUG SFX: Adding genre ambient: {genre_ambient_name}")
                    mixed_path = os.path.join(output_folder, "scene_00_ambient.mp3")
                    if mix_audio_with_sfx(scenes[0]['audio_path'], [ambient_path], mixed_path, 0.3, ffmpeg_path):
                        scenes[0]['audio_path'] = mixed_path
                        print(f"DEBUG SFX: Genre ambient added successfully!")
                    else:
                        print(f"DEBUG SFX: Genre ambient mix failed")
                else:
                    print(f"DEBUG SFX: Genre ambient file not found: {genre_ambient_name}")
            
            # Then, add SFX based on keywords in narration
            for i, scene in enumerate(scenes):
                if not scene.get('audio_path'):
                    print(f"DEBUG SFX: Scene {i} has no audio, skipping")
                    continue
                    
                # Detect SFX keywords in narration
                narration = scene.get('narration', '')
                detected_sfx = detect_sfx_keywords(narration)
                log_sfx_debug(f"Scene {i}: Text='{narration[:30]}...' -> Detected={detected_sfx}")
                
                if detected_sfx:
                    # Show detection in UI
                    if progress_callback:
                        progress_callback(0.52 + (0.05 * i / len(scenes)), f"🔊 Scene {i}: {detected_sfx}")
                    # Build list of SFX file paths
                    sfx_paths = []
                    for sfx_name in detected_sfx[:2]:  # Max 2 SFX per scene
                        for ext in ['.mp3', '.wav']:
                            sfx_path = os.path.join(sfx_folder, f"{sfx_name}{ext}")
                            log_sfx_debug(f"  Checking: {sfx_path}")
                            if os.path.exists(sfx_path):
                                sfx_paths.append(sfx_path)
                                log_sfx_debug(f"  ✓ Found: {sfx_name}{ext}")
                                break
                            else:
                                log_sfx_debug(f"  ✗ Not found: {sfx_name}{ext}")
                    
                    log_sfx_debug(f"  SFX Paths to Mix: {sfx_paths}")
                    
                    if sfx_paths:
                        # Mix SFX with TTS audio - use full volume 0.7
                        mixed_path = os.path.join(output_folder, f"scene_{i:02d}_mixed.mp3")
                        log_sfx_debug(f"  Calling mix_audio_with_sfx()...")
                        log_sfx_debug(f"    TTS: {scene['audio_path']}")
                        log_sfx_debug(f"    Output: {mixed_path}")
                        result = mix_audio_with_sfx(scene['audio_path'], sfx_paths, mixed_path, 0.7, ffmpeg_path)
                        log_sfx_debug(f"  Mix Result: {result}")
                        if result:
                            scene['audio_path'] = mixed_path
                            log_sfx_debug(f"  ✅ Scene {i} - SFX ADDED!")
                            if progress_callback:
                                progress_callback(0.52 + (0.05 * i / len(scenes)), f"✅ Scene {i}: SFX Mixed")
                        else:
                            log_sfx_debug(f"  ❌ Scene {i} - Mix FAILED!")
                            if progress_callback:
                                progress_callback(0.52 + (0.05 * i / len(scenes)), f"❌ Scene {i}: Mix Failed")
                    else:
                        log_sfx_debug(f"  Scene {i}: No SFX files found for: {detected_sfx}")
                else:
                    log_sfx_debug(f"Scene {i}: No keywords detected")
        else:
            log_sfx_debug(f"❌ CRITICAL: SFX FOLDER NOT FOUND AT {sfx_folder}")
        
        # Step 4: Generate subtitles (Clipper style)
        if progress_callback:
            progress_callback(0.6, "📝 Creating subtitles...")
        
        subtitle_path = os.path.join(output_folder, "subtitles.ass")
        create_ass_subtitle_clipper_style(scenes, durations, subtitle_path, caption_style)
        
        # Step 5: Render scenes with effects
        if progress_callback:
            progress_callback(0.65, "🎬 Rendering 2.5D effects...")
        
        scene_videos = []
        effects = ["zoom_in", "pan_right", "breathing", "zoom_out", "pan_left", "pan_up"]
        
        # Get AI-generated clickbait hook (stored in first scene)
        hook_text = ""
        if scenes and scenes[0].get('hook_text'):
            # Use AI-generated clickbait hook
            hook_text = scenes[0]['hook_text']
            print(f"DEBUG: Using AI-generated hook: '{hook_text}'")
        elif scenes and scenes[0].get('narration'):
            # Fallback: extract first 5 words if no AI hook
            first_narration = scenes[0]['narration']
            words = first_narration.split()[:5]
            hook_text = " ".join(words) + "..."
            print(f"DEBUG: Fallback hook: '{hook_text}'")
        
        for i, scene in enumerate(scenes):
            if not scene.get('image_path') or not scene.get('audio_path'):
                continue
            
            video_path = os.path.join(output_folder, f"scene_video_{i:02d}.mp4")
            effect = effects[i % len(effects)]
            
            # Create per-scene subtitle
            scene_sub_path = os.path.join(output_folder, f"scene_{i:02d}.ass")
            create_ass_subtitle_clipper_style([scene], [scene['duration']], scene_sub_path, caption_style)
            
            success = render_scene_with_effects(
                scene['image_path'],
                scene['audio_path'],
                scene_sub_path,
                video_path,
                scene['duration'],
                effect,
                i,
                ffmpeg_path,
                watermark_path,
                filter_overlay,  # Pass color filter to render
                hook_text  # Pass hook text - only shows on scene 0
            )
            
            if success:
                scene_videos.append(video_path)
            
            if progress_callback:
                prog = 0.65 + (0.25 * (i + 1) / len(scenes))
                progress_callback(prog, f"🎬 Rendered scene {i+1}/{len(scenes)}")
        
        # Step 6: Assemble final video
        if progress_callback:
            progress_callback(0.9, "🔧 Assembling final video...")
        
        output_filename = f"animated_{genre.lower().replace(' ', '_')}_{style.lower().replace(' ', '_')}.mp4"
        output_path = os.path.join(output_folder, output_filename)
        
        success = assemble_final_video(scene_videos, output_path, ffmpeg_path)
        
        if success:
            if progress_callback:
                progress_callback(1.0, "✅ Animation complete!")
            return output_path
        else:
            raise Exception("Failed to assemble final video")
        
    except Exception as e:
        print(f"Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return None
