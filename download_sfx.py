"""
Generate high-quality SFX using FFmpeg synthesis.
Creates realistic sound effects using frequency modulation and layering.
"""
import os
import subprocess

SFX_DIR = os.path.join(os.path.dirname(__file__), "sfx")
os.makedirs(SFX_DIR, exist_ok=True)

# SFX specifications: (duration_seconds, ffmpeg_filter)
SFX_SPECS = {
    "door_knock": (0.3, "aevalsrc=sin(150*2*PI*t)*exp(-10*t):s=44100:d=0.3"),
    "door_slam": (0.5, "aevalsrc=sin(80*2*PI*t)*exp(-5*t)+0.5*sin(120*2*PI*t)*exp(-8*t):s=44100:d=0.5"),
    "footsteps": (0.4, "aevalsrc=sin(100*2*PI*t)*exp(-20*t):s=44100:d=0.4"),
    "explosion": (1.5, "aevalsrc='sin(40*2*PI*t)*exp(-2*t)+0.3*sin(80*2*PI*t)*exp(-3*t)+0.2*random(0)':s=44100:d=1.5"),
    "thunder": (2.0, "aevalsrc='(sin(30*2*PI*t)+0.5*sin(60*2*PI*t))*exp(-t)+0.3*random(0)*exp(-0.5*t)':s=44100:d=2"),
    "rain": (3.0, "aevalsrc='0.2*random(0)':s=44100:d=3"),
    "wind": (3.0, "aevalsrc='0.15*sin(2*PI*0.5*t)*random(0)':s=44100:d=3"),
    "whoosh": (0.5, "aevalsrc='sin(200*(1+2*t)*2*PI*t)*exp(-4*t)':s=44100:d=0.5"),
    "laugh": (1.0, "aevalsrc='sin(300*2*PI*t)*(1+0.5*sin(8*2*PI*t))*exp(-2*t)':s=44100:d=1"),
    "scream": (1.0, "aevalsrc='sin(1000*2*PI*t)*(1+0.5*sin(5*2*PI*t))*exp(-1.5*t)':s=44100:d=1"),
    "cry": (1.5, "aevalsrc='sin(400*2*PI*t)*(1+0.3*sin(3*2*PI*t))*exp(-1*t)':s=44100:d=1.5"),
    "heartbeat": (1.0, "aevalsrc='(sin(60*2*PI*t)*exp(-10*(t-0.1)^2)+sin(60*2*PI*t)*exp(-10*(t-0.3)^2))*0.5':s=44100:d=1"),
    "magic": (1.0, "aevalsrc='sin(800*2*PI*t*(1+0.1*sin(5*2*PI*t)))*exp(-2*t)+0.3*sin(1200*2*PI*t)*exp(-3*t)':s=44100:d=1"),
    "beep": (0.3, "aevalsrc='sin(1000*2*PI*t)*0.5':s=44100:d=0.3"),
    "laser": (0.5, "aevalsrc='sin(3000*(1-t)*2*PI*t)*exp(-3*t)':s=44100:d=0.5"),
}


def generate_sfx(name: str, duration: float, filter_expr: str) -> bool:
    """Generate SFX using FFmpeg synthesis."""
    output_path = os.path.join(SFX_DIR, f"{name}.mp3")
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", filter_expr,
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        output_path
    ]
    
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            size_kb = os.path.getsize(output_path) / 1024
            print(f"  ✓ {name}.mp3 ({size_kb:.1f} KB)")
            return True
        else:
            print(f"  ✗ {name}: Generation failed")
            if result.stderr:
                print(f"     {result.stderr[:100]}")
            return False
    except Exception as e:
        print(f"  ✗ {name}: {e}")
        return False


def main():
    print("=" * 50)
    print("GENERATING SFX WITH FFMPEG")
    print("=" * 50)
    
    # Clean old files
    for f in os.listdir(SFX_DIR):
        if f.endswith('.wav'):
            os.remove(os.path.join(SFX_DIR, f))
            print(f"  Removed: {f}")
    
    generated = 0
    failed = 0
    
    for name, (duration, filter_expr) in SFX_SPECS.items():
        if generate_sfx(name, duration, filter_expr):
            generated += 1
        else:
            failed += 1
    
    print(f"\n" + "=" * 50)
    print(f"RESULT: {generated} generated, {failed} failed")
    
    # List files
    files = [f for f in os.listdir(SFX_DIR) if f.endswith('.mp3')]
    total_size = 0
    print(f"\nSFX folder ({len(files)} files):")
    for f in sorted(files):
        path = os.path.join(SFX_DIR, f)
        size = os.path.getsize(path)
        total_size += size
        print(f"  - {f} ({size/1024:.1f} KB)")
    print(f"\nTotal size: {total_size/1024:.1f} KB")
    print("=" * 50)


if __name__ == "__main__":
    main()
