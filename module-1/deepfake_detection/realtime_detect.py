"""
Real-Time Fake Voice Detector  +  Firebase Logging
----------------------------------------------------
Listens to your microphone continuously.
Every 2 seconds it analyses the captured audio,
prints whether the voice is REAL or FAKE,
and saves the result to Firebase Firestore.

Improvements applied (research-based):
  - 50% overlapping windows: records 1 s strides over a 2 s buffer,
    so fake speech spanning a window boundary is still caught.
  - Temporal smoothing: requires 2 of the last 3 chunks to be FAKE
    before triggering an alarm — prevents single noisy-chunk false alarms.
  - Weighted ensemble: votes weighted by each model's training accuracy
    (handled inside deepfake_checker.py).

SETUP (one-time):
  1. Go to https://console.firebase.google.com
  2. Create a project  e.g. "FakeVoiceDetector"
  3. Go to Project Settings > Service Accounts > Generate new private key
  4. Save the downloaded JSON file as:
       module-1/deepfake_detection/serviceAccountKey.json
  5. In Firebase Console enable Firestore Database (start in test mode)

Press Ctrl+C to stop.
"""

import numpy as np
import sounddevice as sd
import warnings
import datetime
import os
from collections import deque
warnings.filterwarnings("ignore")

# ── Firebase Setup ────────────────────────────────────────────────────────────
FIREBASE_ENABLED = False
db = None

SERVICE_ACCOUNT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "serviceAccountKey.json"
)

if os.path.exists(SERVICE_ACCOUNT_PATH):
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        FIREBASE_ENABLED = True
        print("   Firebase connected successfully.")
    except Exception as e:
        print(f"   Firebase connection failed: {e}")
        print("   Running without Firebase logging.")
else:
    print("   serviceAccountKey.json not found.")
    print("   Running without Firebase logging.")
    print("   (See setup instructions at the top of this file)\n")

# ── Config ────────────────────────────────────────────────────────────────────
SAMPLE_RATE    = 16000   # Hz (must match training)
CHUNK_SECONDS  = 2       # analysis window length (research optimum for MFCC-based detection)
STRIDE_SECONDS = 1       # 50% overlap: new audio added per cycle (research: catches boundary fakes)

# Temporal smoothing: require this many of the last SMOOTH_WINDOW chunks to
# be FAKE before reporting an alarm (reduces single-chunk false alarms).
SMOOTH_WINDOW        = 3
SMOOTH_FAKE_REQUIRED = 2

# ── Load ensemble (all available models via deepfake_checker) ─────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
import sys as _sys
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)
try:
    from deepfake_checker import predict_ensemble, available_models
    _avail = available_models()
    if not _avail:
        raise FileNotFoundError("No trained model .pkl files found in models/")
    print(f"   Ensemble loaded: {len(_avail)} models — {', '.join(_avail)}")
except Exception as e:
    print(f"   [ERROR] Could not load models: {e}")
    print("   Run train_multi_model.py first.")
    import sys; sys.exit(1)

# ── Prediction history for temporal smoothing ─────────────────────────────────
_pred_history  = deque(maxlen=SMOOTH_WINDOW)   # stores "REAL" / "FAKE" strings
_prev_smoothed = "REAL"                         # last reported smoothed label

# ── Save to Firebase ──────────────────────────────────────────────────────────
def log_to_firebase(label: str, confidence: float, real_pct: float, fake_pct: float):
    if not FIREBASE_ENABLED:
        return
    try:
        db.collection("predictions").add({
            "timestamp":   datetime.datetime.utcnow().isoformat(),
            "prediction":  label,
            "confidence":  round(confidence, 2),
            "real_prob":   round(real_pct, 2),
            "fake_prob":   round(fake_pct, 2),
            "chunk_secs":  CHUNK_SECONDS,
        })
    except Exception as e:
        print(f"   [Firebase error] {e}")

# ── Prediction ────────────────────────────────────────────────────────────────
def predict_chunk(audio: np.ndarray):
    global _prev_smoothed
    import tempfile, wave as _wave

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            tmp_path = f.name
        arr = (audio * 32767).astype(np.int16)
        with _wave.open(tmp_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(arr.tobytes())

        ens = predict_ensemble(tmp_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except Exception: pass

    if 'error' in ens:
        print(f"  [ERROR] {ens['error']}")
        return

    raw_label  = ens['label']
    real_pct   = ens['real_prob']
    fake_pct   = ens['fake_prob']
    confidence = ens['confidence']
    votes_r    = ens['votes_real']
    votes_f    = ens['votes_fake']
    n_models   = ens['models_used']
    wfrac      = ens.get('weighted_fake_frac', 0.0)

    # ── Temporal smoothing ────────────────────────────────────────────────────
    _pred_history.append(raw_label)
    fake_in_window = _pred_history.count("FAKE")
    smoothed_label = "FAKE" if fake_in_window >= SMOOTH_FAKE_REQUIRED else "REAL"

    # Only log to Firebase when smoothed label changes (avoids duplicate entries)
    if smoothed_label != _prev_smoothed:
        log_to_firebase(smoothed_label, confidence, real_pct, fake_pct)
        _prev_smoothed = smoothed_label

    # ── Display ───────────────────────────────────────────────────────────────
    color  = "\033[92m" if smoothed_label == "REAL" else "\033[91m"
    reset  = "\033[0m"
    bar_r  = int(real_pct / 5) * "|"
    bar_f  = int(fake_pct / 5) * "|"
    ts     = datetime.datetime.now().strftime("%H:%M:%S")

    smooth_note = ""
    if raw_label != smoothed_label:
        smooth_note = f"  [raw={raw_label}, smoothed over {len(_pred_history)} chunks]"

    print(f"\n{color}{'='*60}")
    print(f"  [{ts}]  ENSEMBLE : {smoothed_label}  ({confidence:.1f}% confident)")
    print(f"  Votes  Real={votes_r}  Fake={votes_f}  WeightedFake={wfrac:.1f}%  (of {n_models} models)")
    print(f"  Real  [{bar_r:<20}] {real_pct:.1f}%")
    print(f"  Fake  [{bar_f:<20}] {fake_pct:.1f}%")
    if smooth_note:
        print(f"  {smooth_note.strip()}")
    if FIREBASE_ENABLED and smoothed_label != raw_label:
        print(f"  Saved to Firebase Firestore")
    print(f"{'='*60}{reset}")

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    window_size = SAMPLE_RATE * CHUNK_SECONDS    # 2 s = 32,000 samples
    stride_size = SAMPLE_RATE * STRIDE_SECONDS   # 1 s = 16,000 samples

    # Rolling audio buffer — always holds the last CHUNK_SECONDS of audio
    audio_buffer = np.zeros(window_size, dtype=np.float32)

    print("\n  Real-Time Fake Voice Detector")
    print(f"  Window: {CHUNK_SECONDS} s  |  Stride: {STRIDE_SECONDS} s (50% overlap)  |  SR: {SAMPLE_RATE} Hz")
    print(f"  Smoothing: {SMOOTH_FAKE_REQUIRED}/{SMOOTH_WINDOW} consecutive FAKE chunks -> alarm")
    if FIREBASE_ENABLED:
        print("  Logging to: Firebase Firestore > 'predictions' collection")
    print("  Press Ctrl+C to stop.\n")

    try:
        devices = sd.query_devices()
        default_input = sd.default.device[0]
        print(f"  Microphone: {devices[default_input]['name']}\n")
    except Exception:
        pass

    print("  Listening...")

    try:
        while True:
            # Record one stride (1 s) of new audio
            new_audio = sd.rec(
                frames=stride_size,
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocking=True
            ).flatten()

            # Slide buffer: drop oldest stride, append new audio
            audio_buffer = np.roll(audio_buffer, -stride_size)
            audio_buffer[-stride_size:] = new_audio

            # Skip silence — check the full 2 s window
            if np.max(np.abs(audio_buffer)) < 0.005:
                print("  [silence — skipping]")
                continue

            predict_chunk(audio_buffer)

    except KeyboardInterrupt:
        print("\n\n  Stopped. Goodbye!")

if __name__ == "__main__":
    main()
