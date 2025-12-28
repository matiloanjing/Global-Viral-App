"""
Kilat Code Clipper - Auto Build Installer
============================================
This script automates the entire build process:
1. Creates required directories
2. Downloads FFmpeg automatically
3. Installs all Python dependencies
4. Compiles the application to .exe using PyInstaller

Just run: python build_installer.py
"""

import os
import sys
import subprocess
import zipfile
import shutil
import urllib.request
from pathlib import Path


# ============================================================================
# CONFIGURATION
# ============================================================================
APP_NAME = "KilatCodeClipper"
MAIN_SCRIPT = "main.py"
BIN_FOLDER = "bin"
DIST_FOLDER = "dist"

# FFmpeg download URL (Gyan.dev essentials build - smaller size)
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_ZIP = "ffmpeg-release-essentials.zip"

# Required Python packages
REQUIRED_PACKAGES = [
    "pyinstaller",
    "customtkinter",
    "yt-dlp",
    "groq",
    "google-generativeai",
    "deep-translator",
    "edge-tts",
    "ffmpeg-python",
    "pillow",
    "requests"
]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
def print_header(text: str):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_step(step: int, text: str):
    """Print a step indicator"""
    print(f"\n[Step {step}] {text}")
    print("-" * 40)


def run_command(cmd: list, description: str = "") -> bool:
    """Run a command and return success status"""
    if description:
        print(f"  → {description}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"  ✗ Command failed: {' '.join(cmd)}")
            if result.stderr:
                print(f"  Error: {result.stderr[:500]}")
            return False
        return True
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False


def download_file(url: str, destination: str) -> bool:
    """Download a file with progress indicator"""
    print(f"  → Downloading from: {url}")
    print(f"  → Saving to: {destination}")
    
    try:
        def progress_hook(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = min(100, (downloaded / total_size) * 100)
                mb_downloaded = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r  → Progress: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)", end="", flush=True)
        
        urllib.request.urlretrieve(url, destination, progress_hook)
        print()  # New line after progress
        return True
    except Exception as e:
        print(f"\n  ✗ Download failed: {e}")
        return False


# ============================================================================
# BUILD STEPS
# ============================================================================
def step_1_create_directories():
    """Create required directories"""
    print_step(1, "Creating Directories")
    
    # Create bin folder
    bin_path = Path(BIN_FOLDER)
    if not bin_path.exists():
        bin_path.mkdir(parents=True)
        print(f"  ✓ Created: {BIN_FOLDER}/")
    else:
        print(f"  ✓ Already exists: {BIN_FOLDER}/")
    
    return True


def step_2_download_ffmpeg():
    """Download and extract FFmpeg"""
    print_step(2, "Downloading FFmpeg")
    
    ffmpeg_exe = Path(BIN_FOLDER) / "ffmpeg.exe"
    ffprobe_exe = Path(BIN_FOLDER) / "ffprobe.exe"
    
    # Check if already exists
    if ffmpeg_exe.exists() and ffprobe_exe.exists():
        print(f"  ✓ FFmpeg already exists in {BIN_FOLDER}/")
        print(f"    - ffmpeg.exe: {ffmpeg_exe.stat().st_size / (1024*1024):.1f} MB")
        print(f"    - ffprobe.exe: {ffprobe_exe.stat().st_size / (1024*1024):.1f} MB")
        return True
    
    # Download FFmpeg
    zip_path = Path(FFMPEG_ZIP)
    if not zip_path.exists():
        if not download_file(FFMPEG_URL, str(zip_path)):
            print("  ✗ Failed to download FFmpeg")
            print("  → Please download manually from: https://www.gyan.dev/ffmpeg/builds/")
            return False
    
    print("  → Extracting FFmpeg...")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Find the bin folder inside the zip
            # Structure is usually: ffmpeg-X.X-essentials_build/bin/
            bin_files = []
            for name in zf.namelist():
                if name.endswith('bin/ffmpeg.exe') or name.endswith('bin/ffprobe.exe'):
                    bin_files.append(name)
            
            if not bin_files:
                print("  ✗ Could not find ffmpeg.exe in archive")
                return False
            
            # Extract the files
            for file_path in bin_files:
                filename = os.path.basename(file_path)
                with zf.open(file_path) as src:
                    dest_path = Path(BIN_FOLDER) / filename
                    with open(dest_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    print(f"  ✓ Extracted: {filename}")
        
        # Cleanup zip file
        zip_path.unlink()
        print(f"  ✓ Cleaned up: {FFMPEG_ZIP}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Extraction failed: {e}")
        return False


def step_3_install_dependencies():
    """Install required Python packages"""
    print_step(3, "Installing Python Dependencies")
    
    # Upgrade pip first
    print("  → Upgrading pip...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        capture_output=True
    )
    
    # Install packages
    packages_str = " ".join(REQUIRED_PACKAGES)
    print(f"  → Installing: {packages_str}")
    
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install"] + REQUIRED_PACKAGES,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print("  ⚠ Some packages may have issues, but continuing...")
        if result.stderr:
            # Only show relevant errors
            for line in result.stderr.split('\n'):
                if 'error' in line.lower():
                    print(f"    {line}")
    else:
        print("  ✓ All packages installed successfully!")
    
    return True


def step_4_compile_exe():
    """Compile to EXE using PyInstaller"""
    print_step(4, "Compiling to EXE")
    
    # Check if main.py exists
    if not Path(MAIN_SCRIPT).exists():
        print(f"  ✗ {MAIN_SCRIPT} not found in current directory!")
        return False
    
    # Find customtkinter location for bundling
    print("  → Finding customtkinter location...")
    try:
        import customtkinter
        ctk_path = Path(customtkinter.__file__).parent
        print(f"  ✓ Found customtkinter at: {ctk_path}")
    except ImportError:
        print("  ✗ customtkinter not installed!")
        return False
    
    # Build PyInstaller command
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        f"--name={APP_NAME}",
        f"--add-data={BIN_FOLDER};{BIN_FOLDER}",
        f"--add-data=sfx;sfx",  # Bundle SFX audio files
        f"--add-data=animator_v2.py;.",  # Bundle animator module
        f"--add-data=character_edit.py;.",  # Bundle character edit module
        f"--add-data={ctk_path};customtkinter",
    ]
    
    # Try to add face_recognition_models for face detection support
    try:
        import face_recognition_models
        fr_models_path = Path(face_recognition_models.__file__).parent
        pyinstaller_cmd.append(f"--add-data={fr_models_path};face_recognition_models")
        print(f"  ✓ Found face_recognition_models at: {fr_models_path}")
    except ImportError:
        print("  → face_recognition_models not found (face detection will be unavailable)")
    
    # Try to add dlib for face detection
    try:
        import dlib
        dlib_path = Path(dlib.__file__).parent
        pyinstaller_cmd.append(f"--hidden-import=dlib")
        print(f"  ✓ Found dlib")
    except ImportError:
        print("  → dlib not found")
    
    # Add hidden imports for face detection
    pyinstaller_cmd.append("--hidden-import=face_recognition")
    pyinstaller_cmd.append("--hidden-import=numpy")
    
    # Add icon if exists
    icon_path = Path("icon.ico")
    if icon_path.exists():
        pyinstaller_cmd.append(f"--icon={icon_path}")
        print(f"  ✓ Using icon: {icon_path}")
    else:
        print("  → No icon.ico found (optional)")
    
    # Add the main script
    pyinstaller_cmd.append(MAIN_SCRIPT)
    
    print("\n  → Running PyInstaller...")
    print(f"  → Command: {' '.join(pyinstaller_cmd)}")
    print("\n  This may take a few minutes...\n")
    
    # Run PyInstaller
    result = subprocess.run(
        pyinstaller_cmd,
        text=True
    )
    
    if result.returncode != 0:
        print("  ✗ PyInstaller failed!")
        return False
    
    # Check output
    exe_path = Path(DIST_FOLDER) / APP_NAME / f"{APP_NAME}.exe"
    if exe_path.exists():
        print(f"\n  ✓ SUCCESS! EXE created at:")
        print(f"    {exe_path.absolute()}")
        print(f"    Size: {exe_path.stat().st_size / (1024*1024):.1f} MB")
        return True
    else:
        print("  ✗ EXE not found after build!")
        return False


def step_5_cleanup():
    """Clean up build artifacts"""
    print_step(5, "Cleanup")
    
    # Remove build folder
    build_path = Path("build")
    if build_path.exists():
        shutil.rmtree(build_path)
        print("  ✓ Removed: build/")
    
    # Remove spec file
    spec_file = Path(f"{APP_NAME}.spec")
    if spec_file.exists():
        spec_file.unlink()
        print(f"  ✓ Removed: {spec_file}")
    
    print("  ✓ Cleanup complete!")
    return True


# ============================================================================
# MAIN
# ============================================================================
def main():
    print_header("Kilat Code Clipper - Auto Build Installer")
    print(f"\nWorking directory: {os.getcwd()}")
    print(f"Python version: {sys.version}")
    
    # Run all steps
    steps = [
        ("Create Directories", step_1_create_directories),
        ("Download FFmpeg", step_2_download_ffmpeg),
        ("Install Dependencies", step_3_install_dependencies),
        ("Compile to EXE", step_4_compile_exe),
        ("Cleanup", step_5_cleanup),
    ]
    
    for name, func in steps:
        if not func():
            print(f"\n❌ BUILD FAILED at step: {name}")
            print("Please check the errors above and try again.")
            sys.exit(1)
    
    # Success summary
    print_header("BUILD COMPLETE!")
    print(f"""
    Your application has been compiled successfully!
    
    📁 Output Location:
       {Path(DIST_FOLDER).absolute() / APP_NAME}
    
    📦 Contents:
       - {APP_NAME}.exe (main executable)
       - bin/ffmpeg.exe (bundled)
       - bin/ffprobe.exe (bundled)
       - _internal/ (runtime files)
    
    🚀 To run the app:
       Double-click {APP_NAME}.exe
    
    📋 To distribute:
       Copy the entire '{APP_NAME}' folder
    
    ⚠️ Remember:
       Users need to enter their own API keys:
       - Groq API Key (for transcription)
       - Gemini API Key (for AI analysis)
    """)


if __name__ == "__main__":
    main()
