"""
Fix TTS Test - edge-tts with proper error handling
"""
import asyncio
import edge_tts
import os

# Suara yang PASTI valid
VOICE = "id-ID-GadisNeural" 
# VOICE = "id-ID-ArdiNeural"

TEXT = "Halo, ini adalah tes suara untuk aplikasi Global Viral Clipper. Apakah terdengar dengan jelas?"
OUTPUT_FILE = "test_output/test_audio.mp3"

async def main():
    print(f"Edge-TTS Version Check...")
    print(f"Mencoba generate suara menggunakan: {VOICE}")
    print(f"Text: {TEXT}")
    print()
    
    try:
        communicate = edge_tts.Communicate(TEXT, VOICE)
        await communicate.save(OUTPUT_FILE)
        
        if os.path.isfile(OUTPUT_FILE):
            size = os.path.getsize(OUTPUT_FILE) / 1024
            print(f"✅ BERHASIL! Audio tersimpan di: {OUTPUT_FILE} ({size:.1f} KB)")
        else:
            print("❌ File tidak dibuat")
            
    except edge_tts.exceptions.NoAudioReceived:
        print("❌ ERROR: No Audio Received.")
        print("Kemungkinan penyebab:")
        print("1. Nama Voice ID salah/tidak tersedia.")
        print("2. Teks yang dikirim kosong.")
    except Exception as e:
        print(f"❌ Error Lain: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
