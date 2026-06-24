"""
Generate Urdu TTS fake voice samples for deepfake detection training.

Problem: All current fake data is English (Biden, Musk, Trump clones).
         All current real data is Urdu (_ur.wav recordings).
         Model learned "English = FAKE, Urdu = REAL" instead of actual deepfake artifacts.

Fix: Add AI-generated (TTS) Urdu audio to data/fake/ so the model learns
     that Urdu voices can also be fake.

Output: ~50 Urdu fake .wav files saved to data/fake/urdu_tts_*.wav

Run:
    python generate_urdu_fakes.py
"""

import os
import sys
import io
import time
import wave
import struct
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# Force UTF-8 output so Urdu text doesn't crash on Windows cp1252 console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE     = os.path.dirname(os.path.abspath(__file__))
_FAKE_DIR = os.path.join(_HERE, "data", "fake")
os.makedirs(_FAKE_DIR, exist_ok=True)

# ── Diverse Urdu phrases (translation-domain realistic) ───────────────────────
URDU_PHRASES = [
    # Greetings
    "السلام علیکم",
    "وعلیکم السلام",
    "آپ کا شکریہ",
    "خوش آمدید",
    "خدا حافظ",

    # Questions
    "آپ کیسے ہیں",
    "کیا آپ مجھے سمجھ سکتے ہیں",
    "آپ کا نام کیا ہے",
    "یہ کہاں ہے",
    "یہ کتنے کا ہے",
    "کیا آپ اردو بولتے ہیں",
    "وقت کیا ہوا ہے",
    "کیا یہ صحیح ہے",
    "آپ کہاں رہتے ہیں",

    # Common statements
    "میں ٹھیک ہوں",
    "میں پاکستان سے ہوں",
    "اردو ہماری قومی زبان ہے",
    "میرا نام محمد ہے",
    "آج موسم بہت اچھا ہے",
    "مجھے مدد چاہیے",
    "میں آج بہت خوش ہوں",

    # Translation context
    "براہ کرم انگریزی میں ترجمہ کریں",
    "میں آپ سے بات کرنا چاہتا ہوں",
    "کیا آپ یہ سمجھ سکتے ہیں",
    "یہ ایک بہت اہم بات ہے",
    "پاکستان ایک خوبصورت ملک ہے",

    # Numbers / time
    "ایک دو تین چار پانچ",
    "آج پیر کا دن ہے",
    "چھ سات آٹھ نو دس",

    # Longer natural sentences
    "مجھے ڈاکٹر سے ملنا ہے",
    "کیا آپ مجھے راستہ بتا سکتے ہیں",
    "میں نے کھانا کھا لیا ہے",
    "یہ بازار بہت مہنگا ہے",
    "میرا گھر یہاں سے قریب ہے",
    "آپ نے بہت اچھا کیا",
    "مجھے نہیں معلوم",
    "کوئی بات نہیں",
    "ٹھیک ہے",
    "بہت شکریہ آپ کا",

    # Conversational
    "ہاں بالکل",
    "نہیں میں نہیں مانتا",
    "آپ سے مل کر خوشی ہوئی",
    "پھر ملیں گے",
    "اللہ حافظ",
    "میں سمجھ گیا",
    "کیا آپ دہرا سکتے ہیں",
    "ذرا آہستہ بولیں",
    "مجھے اردو سیکھنی ہے",
    "یہ میرا پہلا دن ہے",
]


def _try_mp3_to_wav(mp3_bytes: bytes, wav_path: str) -> bool:
    """Try to convert MP3 → 16 kHz mono WAV using pydub+ffmpeg. Returns True if successful."""
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
        seg = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        seg.export(wav_path, format="wav")
        return True
    except Exception:
        return False


def generate_gtts(phrases: list[str], out_dir: str) -> int:
    """Generate Urdu TTS using gTTS (Google). Saves as MP3 (preprocess.py supports it).
    Attempts WAV conversion via pydub+ffmpeg if available."""
    try:
        from gtts import gTTS
    except ImportError:
        print("[SKIP] gTTS not installed. Run: pip install gtts")
        return 0

    saved = 0
    print(f"\n[gTTS] Generating {len(phrases)} Urdu TTS samples...")

    for i, phrase in enumerate(phrases, 1):
        # Check if either format already exists
        mp3_path = os.path.join(out_dir, f"urdu_gtts_{i:03d}.mp3")
        wav_path = os.path.join(out_dir, f"urdu_gtts_{i:03d}.wav")
        if os.path.exists(mp3_path) or os.path.exists(wav_path):
            print(f"  [{i:02d}] Already exists, skipping.")
            saved += 1
            continue

        try:
            tts = gTTS(text=phrase, lang="ur", slow=False)
            mp3_buf = io.BytesIO()
            tts.write_to_fp(mp3_buf)
            mp3_bytes = mp3_buf.getvalue()

            # Try WAV conversion (needs ffmpeg). If unavailable, save MP3 directly.
            if _try_mp3_to_wav(mp3_bytes, wav_path):
                print(f"  [{i:02d}/{len(phrases)}] Saved WAV: {os.path.basename(wav_path)}")
            else:
                with open(mp3_path, "wb") as f:
                    f.write(mp3_bytes)
                print(f"  [{i:02d}/{len(phrases)}] Saved MP3: {os.path.basename(mp3_path)}")

            saved += 1
            time.sleep(0.6)   # be polite to Google TTS API

        except Exception as e:
            print(f"  [{i:02d}/{len(phrases)}] FAILED (phrase {i}) -- {e}")
            time.sleep(1.5)

    return saved


def generate_espeak(phrases: list[str], out_dir: str) -> int:
    """Generate Urdu TTS using espeak-ng (offline). Returns count saved."""
    import subprocess
    import shutil

    if not shutil.which("espeak-ng") and not shutil.which("espeak"):
        print("[SKIP] espeak-ng not found. Install from https://espeak.sourceforge.net/")
        return 0

    exe = "espeak-ng" if shutil.which("espeak-ng") else "espeak"
    saved = 0
    print(f"\n[espeak] Generating {len(phrases)} Urdu TTS samples using {exe}...")

    for i, phrase in enumerate(phrases, 1):
        out_path = os.path.join(out_dir, f"urdu_espeak_{i:03d}.wav")
        if os.path.exists(out_path):
            print(f"  [{i:02d}] Already exists, skipping.")
            saved += 1
            continue

        try:
            cmd = [
                exe,
                "-v", "ur",          # Urdu voice
                "-s", "150",          # speed (words per minute)
                "-a", "180",          # amplitude
                "--ipa",
                "-w", out_path,
                phrase,
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            if result.returncode == 0 and os.path.exists(out_path):
                print(f"  [{i:02d}] Saved: {os.path.basename(out_path)}")
                saved += 1
            else:
                print(f"  [{i:02d}] espeak failed: {result.stderr.decode()[:80]}")
        except Exception as e:
            print(f"  [{i:02d}] FAILED -- {e}")

    return saved


def generate_pyttsx3(phrases: list[str], out_dir: str) -> int:
    """Generate Urdu TTS using pyttsx3 (offline). Returns count saved."""
    try:
        import pyttsx3
    except ImportError:
        print("[SKIP] pyttsx3 not installed. Run: pip install pyttsx3")
        return 0

    saved = 0
    print(f"\n[pyttsx3] Generating {len(phrases)} TTS samples...")

    try:
        engine = pyttsx3.init()
        # Try to find an Urdu voice
        voices = engine.getProperty("voices")
        ur_voice = None
        for v in voices:
            if "urdu" in v.name.lower() or "ur" in v.id.lower():
                ur_voice = v.id
                break

        if ur_voice:
            engine.setProperty("voice", ur_voice)
            print(f"  Using Urdu voice: {ur_voice}")
        else:
            print("  No Urdu voice found in pyttsx3 — using default voice (will sound English-accented)")

        engine.setProperty("rate", 150)

        for i, phrase in enumerate(phrases, 1):
            out_path = os.path.join(out_dir, f"urdu_pyttsx3_{i:03d}.wav")
            if os.path.exists(out_path):
                saved += 1
                continue
            try:
                engine.save_to_file(phrase, out_path)
                engine.runAndWait()
                if os.path.exists(out_path):
                    print(f"  [{i:02d}] Saved: {os.path.basename(out_path)}")
                    saved += 1
            except Exception as e:
                print(f"  [{i:02d}] FAILED: {e}")
    except Exception as e:
        print(f"  [pyttsx3 init error] {e}")

    return saved


def verify_output(out_dir: str):
    """Count and report what was generated."""
    urdu_fakes = [
        f for f in os.listdir(out_dir)
        if f.startswith("urdu_") and f.endswith((".wav", ".mp3"))
    ]
    print(f"\n{'='*55}")
    print(f"  Urdu fake files in data/fake/ : {len(urdu_fakes)}")
    all_fakes = [
        f for f in os.listdir(out_dir)
        if f.endswith((".wav", ".mp3", ".flac", ".ogg", ".m4a"))
    ]
    print(f"  Total fake files              : {len(all_fakes)}")
    print(f"{'='*55}")


def main():
    print("=" * 55)
    print("  Urdu Fake Voice Generator")
    print("  Target dir:", _FAKE_DIR)
    print("=" * 55)

    total = 0

    # Method 1: gTTS (best quality, needs internet)
    total += generate_gtts(URDU_PHRASES, _FAKE_DIR)

    # Method 2: espeak-ng (offline, robotic = clearly synthetic = good fake)
    total += generate_espeak(URDU_PHRASES[:20], _FAKE_DIR)

    # Method 3: pyttsx3 (offline fallback)
    if total == 0:
        total += generate_pyttsx3(URDU_PHRASES[:20], _FAKE_DIR)

    verify_output(_FAKE_DIR)

    if total == 0:
        print("\n[ERROR] No files generated.")
        print("  Install gTTS:  pip install gtts pydub")
        print("  Then re-run:   python generate_urdu_fakes.py")
        sys.exit(1)
    else:
        print(f"\n  Done. {total} Urdu fake samples ready.")
        print("  Next step: python retrain_pipeline.py")


if __name__ == "__main__":
    main()
