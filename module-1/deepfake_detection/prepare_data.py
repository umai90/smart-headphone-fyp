#!/usr/bin/env python3
"""
prepare_data.py  —  Download & generate balanced training data for deepfake detection.

Steps
-----
1. Downloads LibriSpeech test-clean (~346 MB, 40 English speakers)  → data/real/
2. Generates fake English TTS via edge-tts (20 neural voices)        → data/fake/
3. Generates fake Urdu TTS via edge-tts (Urdu neural voices)         → data/fake/
4. Reports final balance and optionally retrains all models

Datasets used
-------------
• Real English  : LibriSpeech test-clean — openslr.org/12
  License: CC BY 4.0  |  40 speakers  |  ~2620 utterances  |  346 MB
• Real Urdu     : your existing recordings (data/real/*.wav)
• Fake English  : edge-tts neural voices (Microsoft Azure, free CLI)
• Fake Urdu     : edge-tts ur-PK-AsadNeural / ur-PK-UzmaNeural

Usage
-----
    python prepare_data.py                          # default: 150 real-EN, 100 fake-EN, 20 fake-UR
    python prepare_data.py --real-en 200            # more real English clips
    python prepare_data.py --skip-download          # only generate TTS fakes (no LibriSpeech)
    python prepare_data.py --retrain                # retrain after downloading
    python prepare_data.py --skip-download --retrain
"""

import argparse
import asyncio
import os
import random
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

_HERE     = Path(__file__).parent.resolve()
_DATA_DIR = _HERE / "data"
_REAL_DIR = _DATA_DIR / "real"
_FAKE_DIR = _DATA_DIR / "fake"
_TMP_DIR  = _HERE / "_librispeech_tmp"

LIBRISPEECH_URL      = "https://www.openslr.org/resources/12/test-clean.tar.gz"
LIBRISPEECH_TGZ      = _TMP_DIR / "test-clean.tar.gz"
LIBRISPEECH_EXT      = _TMP_DIR / "LibriSpeech"
LIBRISPEECH_MIN_SIZE = 300 * 1024 * 1024   # 300 MB — incomplete if smaller


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _count_audio(folder: Path, min_bytes: int = 1024) -> int:
    exts = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
    return sum(
        1 for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in exts and f.stat().st_size >= min_bytes
    )


_last_progress_t = 0.0

def _progress_cb(block_num: int, block_size: int, total_size: int):
    global _last_progress_t
    now = time.time()
    if now - _last_progress_t < 0.5 and block_num * block_size < total_size:
        return
    _last_progress_t = now
    downloaded = block_num * block_size
    pct = min(100.0, 100.0 * downloaded / total_size) if total_size > 0 else 0.0
    mb  = downloaded / 1_048_576
    tot = total_size / 1_048_576
    bar_len = 30
    filled  = int(bar_len * pct / 100)
    bar     = "#" * filled + "-" * (bar_len - filled)
    print(f"\r  [{bar}] {pct:5.1f}%  {mb:.1f}/{tot:.1f} MB", end="", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# Step 1: LibriSpeech real English
# ──────────────────────────────────────────────────────────────────────────────

def download_and_extract_librispeech(n_clips: int) -> int:
    """Download LibriSpeech test-clean and copy n_clips FLAC files to data/real/.

    Returns number of newly added clips.
    """
    _TMP_DIR.mkdir(exist_ok=True)
    _REAL_DIR.mkdir(parents=True, exist_ok=True)

    # ── Check how many libri clips already exist ──────────────────────────────
    existing = [f for f in _REAL_DIR.glob("libri_en_*.flac") if f.stat().st_size >= 1024]
    if len(existing) >= n_clips:
        print(f"\n[LIBRISPEECH] Already have {len(existing)} clips in data/real/ — skipping.")
        return 0

    already = len(existing)
    still_need = n_clips - already

    # ── Download (with size validation + re-download if incomplete) ───────────
    need_download = True
    if LIBRISPEECH_TGZ.exists():
        actual_size = LIBRISPEECH_TGZ.stat().st_size
        if actual_size >= LIBRISPEECH_MIN_SIZE:
            print(f"\n[LIBRISPEECH] Archive already present ({actual_size/1e6:.0f} MB): {LIBRISPEECH_TGZ}")
            need_download = False
        else:
            print(f"\n[LIBRISPEECH] Incomplete archive ({actual_size/1e6:.0f} MB) — re-downloading …")
            LIBRISPEECH_TGZ.unlink()

    if need_download:
        print(f"\n[LIBRISPEECH] Downloading test-clean (~330 MB) …")
        print(f"  Source : {LIBRISPEECH_URL}")
        try:
            urllib.request.urlretrieve(LIBRISPEECH_URL, LIBRISPEECH_TGZ, _progress_cb)
            print()
            actual_size = LIBRISPEECH_TGZ.stat().st_size
            if actual_size < LIBRISPEECH_MIN_SIZE:
                print(f"[ERROR] Downloaded file too small ({actual_size/1e6:.0f} MB). Download may be incomplete.")
                LIBRISPEECH_TGZ.unlink()
                return 0
            print(f"  Saved  : {LIBRISPEECH_TGZ}  ({actual_size/1e6:.0f} MB)")
        except Exception as exc:
            print(f"\n[ERROR] Download failed: {exc}")
            print("  Check your internet connection and try again.")
            if LIBRISPEECH_TGZ.exists():
                LIBRISPEECH_TGZ.unlink()
            return 0

    # ── Extract (first time only; verify by checking if FLAC files exist) ─────
    ext_ok = LIBRISPEECH_EXT.exists() and any(LIBRISPEECH_EXT.rglob("*.flac"))
    if not ext_ok:
        if LIBRISPEECH_EXT.exists():
            shutil.rmtree(LIBRISPEECH_EXT)   # remove empty/corrupt dir
        print("[LIBRISPEECH] Extracting archive — this may take 1-3 minutes …")
        try:
            with tarfile.open(LIBRISPEECH_TGZ, "r:gz") as tar:
                tar.extractall(path=_TMP_DIR)
            print(f"  Extracted to: {LIBRISPEECH_EXT}")
        except Exception as exc:
            print(f"[ERROR] Extraction failed: {exc}")
            print("  The archive may be corrupt. Deleting it so next run re-downloads.")
            LIBRISPEECH_TGZ.unlink(missing_ok=True)
            return 0
    else:
        print(f"[LIBRISPEECH] Already extracted: {LIBRISPEECH_EXT}")

    # ── Sample FLAC files ─────────────────────────────────────────────────────
    all_flac = sorted(LIBRISPEECH_EXT.rglob("*.flac"))
    if not all_flac:
        print("[ERROR] No FLAC files found after extraction.")
        return 0

    print(f"[LIBRISPEECH] Found {len(all_flac)} utterances — sampling {still_need} …")
    rng = random.Random(42)
    rng.shuffle(all_flac)
    to_copy = all_flac[:still_need]

    n_copied = 0
    for i, src in enumerate(to_copy, already + 1):
        dst = _REAL_DIR / f"libri_en_{i:04d}.flac"
        if dst.exists():
            continue
        try:
            shutil.copy2(src, dst)
            n_copied += 1
        except Exception as exc:
            print(f"  [WARN] Copy failed for {src.name}: {exc}")

        if n_copied % 25 == 0 or i == len(to_copy) + already:
            print(f"\r  Copied {n_copied}/{still_need} clips …", end="", flush=True)

    print(f"\n[LIBRISPEECH] Added {n_copied} real English clips to data/real/")
    return n_copied


# ──────────────────────────────────────────────────────────────────────────────
# Step 2 & 3: edge-tts fake voices
# ──────────────────────────────────────────────────────────────────────────────

# 20 English neural voices — diverse accents (US, UK, AU, IN, CA, IE, NZ)
ENGLISH_VOICES = [
    "en-US-AriaNeural",     "en-US-GuyNeural",      "en-US-JennyNeural",
    "en-US-EricNeural",     "en-US-MichelleNeural", "en-US-RogerNeural",
    "en-US-SteffanNeural",  "en-US-AnaNeural",
    "en-GB-SoniaNeural",    "en-GB-RyanNeural",
    "en-GB-LibbyNeural",    "en-GB-ThomasNeural",
    "en-AU-NatashaNeural",  "en-AU-WilliamNeural",
    "en-IN-NeerjaNeural",   "en-IN-PrabhatNeural",
    "en-CA-ClaraNeural",    "en-CA-LiamNeural",
    "en-IE-EmilyNeural",    "en-NZ-MollyNeural",
]

ENGLISH_TEXTS = [
    "The quick brown fox jumps over the lazy dog near the riverbank every morning at dawn.",
    "Scientists have discovered a new species of bird in the Amazon rainforest that can mimic human speech.",
    "The annual conference on artificial intelligence will be held next month with over five thousand attendees.",
    "Climate change continues to affect weather patterns causing unprecedented flooding and droughts worldwide.",
    "Machine learning algorithms can now detect subtle audio patterns that are imperceptible to the human ear.",
    "The patient was admitted after experiencing severe chest pain and difficulty breathing for several hours.",
    "Financial markets reacted positively to the central bank decision to hold interest rates steady.",
    "Researchers worked for three years before publishing their groundbreaking findings in a peer-reviewed journal.",
    "Modern smartphones have revolutionized the way people communicate and access information across the globe.",
    "The documentary explores lives of ordinary people who made extraordinary contributions to their communities.",
    "Artificial intelligence is transforming healthcare transportation and finance in ways never imagined before.",
    "The new education policy aims to improve literacy and provide equal opportunities for all students.",
    "Renewable energy sources such as solar and wind power are becoming increasingly affordable worldwide.",
    "Space exploration missions have uncovered fascinating details about the formation of our solar system.",
    "The global pandemic permanently accelerated adoption of remote work and digital communication technologies.",
]

URDU_VOICES = ["ur-PK-AsadNeural", "ur-PK-UzmaNeural"]

URDU_TEXTS = [
    "آج کا موسم بہت خوشگوار ہے اور آسمان پر بادل چھائے ہوئے ہیں۔ ہمیں اللہ کا شکر ادا کرنا چاہیے۔",
    "پاکستان میں تعلیم کے شعبے میں بہت بڑی تبدیلیاں آ رہی ہیں اور نوجوان نسل کو بہت فائدہ ہوگا۔",
    "ٹیکنالوجی نے ہماری زندگی کو مکمل طور پر بدل دیا ہے اور مستقبل میں مزید تبدیلیاں آئیں گی۔",
    "خاندان ایک معاشرے کی بنیادی اکائی ہوتی ہے جو ہمیں مضبوطی اور سکون دیتی ہے ہر وقت۔",
    "نوجوان نسل کو ملک کی ترقی کے لیے محنت اور لگن سے کام کرنا چاہیے تاکہ پاکستان ترقی کرے۔",
    "صحت ایک بہت بڑی نعمت ہے اور ہمیں اپنی صحت کا خیال رکھنا چاہیے ورنہ پچھتانا پڑتا ہے۔",
    "پانی زندگی کی بنیادی ضرورت ہے اور ہمیں اسے ضائع نہیں کرنا چاہیے کیونکہ یہ بہت قیمتی ہے۔",
    "کتابیں انسان کی بہترین دوست ہوتی ہیں اور علم حاصل کرنا ہر مسلمان پر فرض کیا گیا ہے۔",
    "دوستی ایک مقدس رشتہ ہے جسے ہمیں ہمیشہ عزت اور محبت کے ساتھ نبھانا اور سنبھالنا چاہیے۔",
    "قوموں کی ترقی کا راز تعلیم اور محنت میں ہے نہ کہ سستی اور کاہلی اور لاپرواہی میں ہے۔",
]


async def _tts_clip(voice: str, text: str, out_path: Path, retries: int = 3) -> bool:
    """Generate one TTS MP3 with retries. Returns True on success."""
    import edge_tts
    for attempt in range(1, retries + 1):
        try:
            tmp = out_path.with_suffix(".tmp.mp3")
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(tmp))
            if tmp.exists() and tmp.stat().st_size > 1024:
                tmp.rename(out_path)
                return True
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        except Exception as exc:
            if attempt < retries:
                await asyncio.sleep(2 ** attempt)   # exponential backoff
            else:
                print(f"\n  [WARN] edge-tts failed ({voice}) after {retries} attempts: {exc}")
    return False


async def generate_tts_fakes(n_english: int, n_urdu: int) -> tuple[int, int]:
    """Generate fake TTS voices and save to data/fake/."""
    _FAKE_DIR.mkdir(parents=True, exist_ok=True)

    # Build pair list: (voice, text_idx) — shuffle so every run picks diverse combos
    en_pairs = [(v, j) for v in ENGLISH_VOICES for j in range(len(ENGLISH_TEXTS))]
    random.Random(42).shuffle(en_pairs)
    en_pairs = en_pairs[:n_english]

    ur_pairs = [(v, j) for v in URDU_VOICES for j in range(len(URDU_TEXTS))]
    ur_pairs = ur_pairs[:n_urdu]

    # ── English TTS ───────────────────────────────────────────────────────────
    print(f"\n[TTS-EN] Generating up to {len(en_pairs)} fake English clips …")
    n_en_ok = 0
    for i, (voice, j) in enumerate(en_pairs, 1):
        tag  = voice.replace("Neural", "").replace("-", "_")
        fname = f"tts_en_{tag}_{j:02d}.mp3"
        out_path = _FAKE_DIR / fname
        if out_path.exists() and out_path.stat().st_size > 1024:
            n_en_ok += 1
            print(f"\r  {i:>3}/{len(en_pairs)}  [skip] {fname:<55}", end="", flush=True)
            continue
        if out_path.exists():   # stale zero-byte from previous failed run
            out_path.unlink(missing_ok=True)
        ok = await _tts_clip(voice, ENGLISH_TEXTS[j], out_path)
        if ok:
            n_en_ok += 1
        print(f"\r  {i:>3}/{len(en_pairs)}  {'[OK]  ' if ok else '[FAIL]'} {fname:<55}", end="", flush=True)
        await asyncio.sleep(0.3)

    print(f"\n[TTS-EN] Done: {n_en_ok}/{len(en_pairs)} generated")

    # ── Urdu TTS ──────────────────────────────────────────────────────────────
    print(f"\n[TTS-UR] Generating up to {len(ur_pairs)} fake Urdu clips …")
    n_ur_ok = 0
    for i, (voice, j) in enumerate(ur_pairs, 1):
        tag   = voice.replace("Neural", "").replace("-", "_")
        fname = f"tts_ur_{tag}_{j:02d}.mp3"
        out_path = _FAKE_DIR / fname
        if out_path.exists() and out_path.stat().st_size > 1024:
            n_ur_ok += 1
            print(f"\r  {i:>3}/{len(ur_pairs)}  [skip] {fname:<55}", end="", flush=True)
            continue
        if out_path.exists():
            out_path.unlink(missing_ok=True)
        ok = await _tts_clip(voice, URDU_TEXTS[j], out_path)
        if ok:
            n_ur_ok += 1
        print(f"\r  {i:>3}/{len(ur_pairs)}  {'[OK]  ' if ok else '[FAIL]'} {fname:<55}", end="", flush=True)
        await asyncio.sleep(0.3)

    print(f"\n[TTS-UR] Done: {n_ur_ok}/{len(ur_pairs)} generated")
    return n_en_ok, n_ur_ok


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

async def async_main(args):
    print("\n" + "=" * 65)
    print("  Deepfake Detection — Data Preparation Script")
    print("=" * 65)

    real_before = _count_audio(_REAL_DIR) if _REAL_DIR.exists() else 0
    fake_before = _count_audio(_FAKE_DIR) if _FAKE_DIR.exists() else 0
    print(f"\nCurrent data/real/ : {real_before} audio files")
    print(f"Current data/fake/ : {fake_before} audio files")

    # Step 1 — LibriSpeech real English
    if not args.skip_download:
        download_and_extract_librispeech(args.real_en)
    else:
        print("\n[SKIP] LibriSpeech download skipped (--skip-download)")

    # Steps 2 & 3 — TTS fake voices
    if not args.skip_tts:
        await generate_tts_fakes(args.fake_en, args.fake_ur)
    else:
        print("\n[SKIP] TTS generation skipped (--skip-tts)")

    # Summary
    real_after = _count_audio(_REAL_DIR) if _REAL_DIR.exists() else 0
    fake_after = _count_audio(_FAKE_DIR) if _FAKE_DIR.exists() else 0
    ratio = fake_after / max(1, real_after)

    print("\n" + "=" * 65)
    print("  FINAL DATASET SUMMARY")
    print("=" * 65)
    print(f"  data/real/  :  {real_after:>4}  files  (+{real_after - real_before} new)")
    print(f"  data/fake/  :  {fake_after:>4}  files  (+{fake_after - fake_before} new)")
    print(f"  Real : Fake =   1 : {ratio:.1f}")
    print()
    aug_real = real_after * 4
    aug_fake = fake_after * 4
    print(f"  With 3× augmentation (preprocess.py):")
    print(f"    Augmented real  : {aug_real}")
    print(f"    Augmented fake  : {aug_fake}")
    print(f"  SMOTE in train_multi_model.py will balance the training set.")
    print("=" * 65)

    if args.retrain:
        print("\n[RETRAIN] Starting train_multi_model.py …\n")
        result = subprocess.run(
            [sys.executable, str(_HERE / "train_multi_model.py")],
            cwd=str(_HERE),
        )
        sys.exit(result.returncode)
    else:
        print("\nNext steps:")
        print("  1.  python prepare_data.py   (already done)")
        print("  2.  python train_multi_model.py")
        print()
        print("Or run both at once:")
        print("  python prepare_data.py --retrain")


def main():
    ap = argparse.ArgumentParser(
        description="Download real voices and generate TTS fakes for deepfake detection training",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--real-en", type=int, default=150, metavar="N",
                    help="Real English clips to sample from LibriSpeech (default: 150)")
    ap.add_argument("--fake-en", type=int, default=100, metavar="N",
                    help="Fake English TTS clips to generate via edge-tts (default: 100)")
    ap.add_argument("--fake-ur", type=int, default=20, metavar="N",
                    help="Fake Urdu TTS clips to generate via edge-tts (default: 20)")
    ap.add_argument("--skip-download", action="store_true",
                    help="Skip LibriSpeech download (keep existing real clips)")
    ap.add_argument("--skip-tts", action="store_true",
                    help="Skip TTS generation (keep existing fake clips)")
    ap.add_argument("--retrain", action="store_true",
                    help="Run train_multi_model.py after data preparation")
    args = ap.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
