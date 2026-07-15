"""
Deepfake Voice Checker — Multi-Model Ensemble Edition
Smart Headphone Translation System

Loads all trained classifiers from module-1/deepfake_detection/models/
and runs weighted ensemble voting.  A file is marked FAKE when the weighted
fake fraction >= 20%, avg fake probability >= 40%, or high-confidence >= 75%.

Two-tier rule fallback: when 1+ models vote FAKE but thresholds not crossed,
a physics-based rule checks pitch stability + centroid + RMS variance.
If all three conditions fire the file is still flagged FAKE.
"""

import os
import sys
import json
import math
import glob
import threading as _threading
import numpy as np
import warnings
warnings.filterwarnings("ignore")

_THIS_DIR    = os.path.dirname(os.path.abspath(__file__))
_MODEL_DIR      = os.path.join(_THIS_DIR, "..", "module-1", "deepfake_detection", "models")
_RECORD_DIR     = os.path.join(_THIS_DIR, "recordings")
_PREPROCESS_DIR = os.path.join(_THIS_DIR, "..", "module-1", "deepfake_detection")

# FAKE_WEIGHT_THRESHOLD: weighted fraction of total accuracy that must vote fake.
# Lowered from 0.20 → 0.12 to catch modern high-quality TTS (ChatGPT, ElevenLabs)
# that older thresholds missed. Even 1–2 high-accuracy models voting FAKE triggers it.
FAKE_WEIGHT_THRESHOLD = 0.12

# FAKE_PROB_THRESHOLD: avg fake probability override (0–100).
# Lowered from 40 → 28 — modern AI voices score 25–35% fake probability but are
# still synthetic. Lower threshold catches them before they slip through.
FAKE_PROB_THRESHOLD = 28.0

# HIGH_CONF_THRESHOLD: fast-path bypass (0–100).
# Lowered from 75 → 60 — clear fakes now flagged sooner.
HIGH_CONF_THRESHOLD = 60.0

_cache: dict = {}
_cache_lock = _threading.Lock()   # guards _cache under Flask threaded=True


def reload_models():
    """Force a fresh reload of all models and weights (call after retraining)."""
    with _cache_lock:
        _cache.clear()


def _pkl_mtime_max() -> float:
    """Return the newest mtime of any .pkl in MODEL_DIR (0.0 if none found)."""
    if not os.path.isdir(_MODEL_DIR):
        return 0.0
    mtimes = [os.path.getmtime(p) for p in glob.glob(os.path.join(_MODEL_DIR, "*.pkl"))]
    return max(mtimes) if mtimes else 0.0

# Excluded 2026-07-14 after an out-of-distribution accuracy audit: the training
# set's REAL class is 100% LibriSpeech (clean studio audiobook recordings), so
# these 5 tree/boosting models learned "sounds like LibriSpeech" rather than
# genuine acoustic naturalness. On data/test/'s hand-recorded real-audio samples
# (never seen in training) they scored 61-64% avg fake-probability — confidently
# WRONG — while the remaining 5 (margin-based/smooth models) scored 0.5-7.4% on
# the same files and still caught both labeled clone samples at 99%+ confidence.
# Their in-distribution held-out test_accuracy in model_results.json (~99%+) is
# from the SAME narrow LibriSpeech-vs-TTS split and does not reflect this. Only
# re-include after retraining with more diverse real-audio recording conditions
# (device/room/format variety, not just LibriSpeech) or explicit probability
# recalibration (e.g. CalibratedClassifierCV).
_EXCLUDED_MODELS: set = {
    "random_forest", "gradient_boosting", "extra_trees", "adaboost", "catboost",
}


# ── Model weights from training results ───────────────────────────────────────

def _load_model_weights():
    """Load per-model accuracy weights from model_results.json."""
    results_path = os.path.join(_MODEL_DIR, "model_results.json")
    if not os.path.exists(results_path):
        with _cache_lock:
            return _cache.get("weights", {})
    try:
        file_mtime = os.path.getmtime(results_path)
        with _cache_lock:
            if "weights" in _cache and _cache.get("weights_mtime", 0) >= file_mtime:
                return _cache["weights"]
        # File I/O outside lock so other threads aren't blocked
        with open(results_path) as f:
            results = json.load(f)
        weights = {k.lower(): float(v.get("test_accuracy", 1.0))
                   for k, v in results.items()}
        with _cache_lock:
            _cache["weights"] = weights
            _cache["weights_mtime"] = file_mtime
        return weights
    except Exception:
        with _cache_lock:
            return _cache.get("weights", {})


# ── Feature extraction (206-dim via preprocess.py) ────────────────────────────

def _get_extract_features():
    """Lazy-load extract_features from preprocess.py (206-dim)."""
    with _cache_lock:
        if "extract_features" in _cache:
            return _cache["extract_features"]
    # Import outside lock — module import can be slow
    if _PREPROCESS_DIR not in sys.path:
        sys.path.insert(0, _PREPROCESS_DIR)
    try:
        from preprocess import extract_features
        fn = extract_features
    except Exception as e:
        print(f"  [ERROR] Cannot import preprocess.extract_features: {e}")
        fn = None
    with _cache_lock:
        _cache["extract_features"] = fn
    return fn


def _extract_features(file_path):
    extract_fn = _get_extract_features()
    if extract_fn is None:
        return None
    return extract_fn(file_path)


# ── Scaler ────────────────────────────────────────────────────────────────────

def _load_scaler():
    try:
        import joblib
    except ImportError:
        print("  [ERROR] joblib not installed.")
        return None
    path = os.path.join(_MODEL_DIR, "scaler.pkl")
    if not os.path.exists(path):
        print(f"  [ERROR] scaler.pkl not found in:\n    {_MODEL_DIR}")
        return None
    current_mtime = _pkl_mtime_max()
    with _cache_lock:
        if "scaler" in _cache and _cache.get("models_mtime", 0) >= current_mtime:
            return _cache["scaler"]
    scaler = joblib.load(path)   # joblib.load outside lock — can be slow
    with _cache_lock:
        _cache["scaler"] = scaler
    return scaler


# ── Load all models ───────────────────────────────────────────────────────────

def _load_all_models():
    """Load every *.pkl except scaler.pkl from model dir. Returns dict name→model.
    Automatically reloads when any .pkl is newer than the cached copy."""
    try:
        import joblib
    except ImportError:
        print("  [ERROR] joblib not installed.")
        return {}

    if not os.path.isdir(_MODEL_DIR):
        print(f"  [ERROR] model directory not found:\n    {_MODEL_DIR}")
        print("  Run train_multi_model.py first.")
        return {}

    current_mtime = _pkl_mtime_max()
    with _cache_lock:
        if "all_models" in _cache and _cache.get("models_mtime", 0) >= current_mtime:
            return _cache["all_models"]

    # Load all pkl files outside the lock — joblib.load can take seconds
    models = {}
    for pkl in sorted(glob.glob(os.path.join(_MODEL_DIR, "*.pkl"))):
        fname = os.path.basename(pkl)
        if fname in ("scaler.pkl", "svm_model.pkl"):
            # svm_model.pkl is a backward-compat copy of svm_rbf_model.pkl;
            # loading both gives SVM two votes in the ensemble.
            continue
        name = fname.replace("_model.pkl", "").replace(".pkl", "")
        if name in _EXCLUDED_MODELS:
            continue
        try:
            models[name] = joblib.load(pkl)
        except Exception as e:
            print(f"  [WARN] Could not load {fname}: {e}")

    if not models:
        print(f"  [ERROR] No model .pkl files found in:\n    {_MODEL_DIR}")
        print("  Run train_multi_model.py first.")

    with _cache_lock:
        _cache["all_models"] = models
        _cache["models_mtime"] = current_mtime
    return models


# ── Two-tier rule fallback ─────────────────────────────────────────────────────

def _extract_rule_signals(audio_path):
    """Extract pitch_std, spectral_centroid_mean, rms_std for rule check."""
    try:
        import librosa
        y, sr = librosa.load(audio_path, mono=True)
        if len(y) == 0:
            return None

        pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
        pitch_vals = pitches[magnitudes > np.median(magnitudes)]
        pitch_std  = float(np.std(pitch_vals)) if len(pitch_vals) > 0 else 999.0

        centroid_mean = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))

        rms = librosa.feature.rms(y=y)
        rms_std = float(np.std(rms))

        return pitch_std, centroid_mean, rms_std
    except Exception:
        return None


def _rule_says_fake(pitch_std, centroid, rms_std):
    """AI voices: unnaturally stable pitch + high centroid energy + flat RMS.
    Thresholds widened to catch modern high-quality TTS (ChatGPT, ElevenLabs)
    which have more natural-sounding pitch but still show flat RMS + high centroid."""
    return pitch_std < 80 and centroid > 2500 and rms_std < 0.02


# ── Core prediction ────────────────────────────────────────────────────────────

def _predict_raw(audio_path: str):
    """
    Internal: run ensemble and return full details.
    Returns (label, confidence, real_prob, fake_prob, votes_fake, votes_real, total)
    or None on failure.
    """
    scaler = _load_scaler()
    models = _load_all_models()

    if scaler is None or not models:
        return None

    features = _extract_features(audio_path)
    if features is None:
        return None

    try:
        features_scaled = scaler.transform(features.reshape(1, -1))
    except Exception as e:
        print(f"  [ERROR] Scaler transform failed: {e}")
        return None

    weights      = _load_model_weights()
    fake_votes   = 0
    total        = len(models)
    fake_probs   = []
    total_weight = 0.0
    fake_weight  = 0.0

    for name, model in models.items():
        w = weights.get(name, 1.0)
        try:
            pred        = int(model.predict(features_scaled)[0])
            fake_votes += pred
            total_weight += w
            if pred == 1:
                fake_weight += w

            if hasattr(model, "predict_proba"):
                proba    = model.predict_proba(features_scaled)[0]
                classes  = list(model.classes_)
                fake_idx = classes.index(1) if 1 in classes else 1
                fake_probs.append(float(proba[fake_idx]))
            else:
                try:
                    df = float(model.decision_function(features_scaled)[0])
                    fake_probs.append(1.0 / (1.0 + math.exp(-df)))
                except Exception:
                    fake_probs.append(float(pred))
        except Exception as e:
            print(f"  [WARN] Model {name} prediction failed: {e}")
            total -= 1

    if total == 0:
        return None

    avg_fake_prob      = float(np.mean(fake_probs)) * 100 if fake_probs else (fake_votes / total * 100)
    weighted_fake_frac = fake_weight / total_weight if total_weight > 0 else 0.0

    # ── Decision hierarchy ─────────────────────────────────────────────────────
    if avg_fake_prob >= HIGH_CONF_THRESHOLD:
        # Fast path: overwhelming confidence — skip vote counting
        label = "FAKE"
    elif weighted_fake_frac >= FAKE_WEIGHT_THRESHOLD:
        label = "FAKE"
    elif avg_fake_prob >= FAKE_PROB_THRESHOLD:
        # Probability override: models leaning fake without enough weighted votes
        label = "FAKE"
    elif fake_votes >= 1:
        # Physics rule fallback for borderline cases
        signals = _extract_rule_signals(audio_path)
        if signals and _rule_says_fake(*signals):
            label         = "FAKE"
            avg_fake_prob = max(avg_fake_prob, 60.0)
        else:
            label = "REAL"
    else:
        label = "REAL"

    real_prob   = round(100.0 - avg_fake_prob, 1)
    fake_prob   = round(avg_fake_prob, 1)
    confidence  = fake_prob if label == "FAKE" else real_prob
    votes_real  = total - fake_votes
    return label, round(confidence, 1), real_prob, fake_prob, fake_votes, votes_real, total, round(weighted_fake_frac * 100, 1)


def predict_file(audio_path: str):
    """
    Ensemble prediction on a single audio file.

    Returns (label, confidence, real_prob, fake_prob) or None on failure.
    Labels: 'REAL' (class 0) or 'FAKE' (class 1).
    """
    raw = _predict_raw(audio_path)
    if raw is None:
        return None
    return raw[0], raw[1], raw[2], raw[3]   # label, confidence, real_prob, fake_prob


def predict_ensemble(audio_path: str) -> dict:
    """Flask endpoint entry point — delegates to ensemble predict_file."""
    raw = _predict_raw(audio_path)
    if raw is None:
        return {"error": "prediction failed — check model/scaler files or run train_multi_model.py"}
    label, conf, rp, fp, votes_fake, votes_real, total, wfrac = raw
    return {
        "label":              label,
        "confidence":         conf,
        "real_prob":          rp,
        "fake_prob":          fp,
        "votes_fake":         votes_fake,
        "votes_real":         votes_real,
        "models_used":        total,
        "weighted_fake_frac": wfrac,
    }


def available_models() -> list:
    """Return list of loaded model names (for realtime_detect.py)."""
    return list(_load_all_models().keys())


# ── Audio file listing ─────────────────────────────────────────────────────────

_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}


def _list_recorded():
    """Return filenames from the flat recordings/ root directory."""
    results = []
    if not os.path.isdir(_RECORD_DIR):
        return results
    for f in os.listdir(_RECORD_DIR):
        if (os.path.splitext(f)[1].lower() in _AUDIO_EXTS
                and os.path.isfile(os.path.join(_RECORD_DIR, f))):
            results.append(f)
    return sorted(results)


# ── Interactive menu ───────────────────────────────────────────────────────────

def run_deepfake_checker():
    print("\n" + "=" * 60)
    print("  DEEPFAKE VOICE CHECKER  (Multi-Model Ensemble)")
    print("=" * 60)

    wavs = _list_recorded()
    if not wavs:
        print(f"\n  [INFO] No audio files found in:\n         {_RECORD_DIR}")
        print("  Record a conversation first, then come back.\n")
        return

    models = _load_all_models()
    if not models:
        print(f"\n  [ERROR] No models found in:\n         {_MODEL_DIR}")
        print("  Run train_multi_model.py first.\n")
        return

    print(f"\n  Models loaded : {len(models)}  ({', '.join(models.keys())})")
    print(f"  Fake threshold: prob>={FAKE_PROB_THRESHOLD}% or weight>={FAKE_WEIGHT_THRESHOLD*100:.0f}%")
    print(f"\n  Audio files ({len(wavs)}):")
    for i, fname in enumerate(wavs, 1):
        print(f"    {i:2}. {fname}")
    print(f"     A. ALL files")

    try:
        choice = input("\n  Select file (number / A / 0=back): ").strip().upper()
    except (EOFError, KeyboardInterrupt):
        return

    if choice == "0":
        return

    files_to_test = []
    if choice == "A":
        files_to_test = [os.path.join(_RECORD_DIR, f) for f in wavs]
    elif choice.isdigit() and 1 <= int(choice) <= len(wavs):
        files_to_test = [os.path.join(_RECORD_DIR, wavs[int(choice) - 1])]
    else:
        print("  [ERROR] Invalid choice.")
        return

    print("\n" + "-" * 60)
    for path in files_to_test:
        result = predict_ensemble(path)
        if 'error' not in result:
            label  = result['label']
            conf   = result['confidence']
            rp     = result['real_prob']
            fp     = result['fake_prob']
            vf     = result['votes_fake']
            vr     = result['votes_real']
            total  = result['models_used']
            marker = "[+]" if label == "REAL" else "[!]"
            print(f"\n  File      : {os.path.basename(path)}")
            print(f"  Result    : {marker} {label}  ({conf:.1f}% confidence)")
            print(f"  Real prob : {rp:.1f}%   |   Fake prob : {fp:.1f}%")
            print(f"  Votes     : {vf} FAKE  /  {vr} REAL  (of {total} models)")
        else:
            print(f"\n  [!] Could not analyse: {os.path.basename(path)}")
    print("-" * 60 + "\n")


def check_file(audio_path: str):
    """Run ensemble prediction on a single file and print the result."""
    models = _load_all_models()
    if not models:
        print(f"  [ERROR] No models found in: {_MODEL_DIR}")
        return
    result = predict_file(audio_path)
    fname  = os.path.basename(audio_path)
    print("\n" + "-" * 50)
    if result:
        label, conf, rp, fp = result
        marker = "[+]" if label == "REAL" else "[!]"
        print(f"  Ensemble Result : {marker} {label}  ({conf:.1f}% confidence)")
        print(f"  File            : {fname}")
        print(f"  Real prob       : {rp:.1f}%   |   Fake prob : {fp:.1f}%")
    else:
        print(f"  [!] Ensemble could not analyse: {fname}")
    print("-" * 50 + "\n")


def check_test_folder():
    """Run ensemble prediction on every audio file in the recordings folder."""
    print("\n" + "=" * 60)
    print("  ENSEMBLE DEEPFAKE SCAN — recordings/")
    print("=" * 60)

    wavs = _list_recorded()
    if not wavs:
        print(f"\n  [INFO] No audio files found in:\n         {_RECORD_DIR}\n")
        return

    models = _load_all_models()
    if not models:
        print(f"\n  [ERROR] No models found in: {_MODEL_DIR}\n")
        return

    print(f"\n  Models: {len(models)}  |  Fake threshold: prob>={FAKE_PROB_THRESHOLD}% or weight>={FAKE_WEIGHT_THRESHOLD*100:.0f}%")
    print(f"  Scanning {len(wavs)} file(s)...\n")
    real_count = fake_count = error_count = 0

    for fname in wavs:
        path   = os.path.join(_RECORD_DIR, fname)
        result = predict_ensemble(path)
        if 'error' not in result:
            label  = result['label']
            conf   = result['confidence']
            vf     = result['votes_fake']
            total  = result['models_used']
            marker = "[+]" if label == "REAL" else "[!]"
            print(f"  {marker} {label:4s}  ({conf:5.1f}%)  votes:{vf}/{total}  {fname}")
            if label == "REAL":
                real_count += 1
            else:
                fake_count += 1
        else:
            print(f"  [?] ERROR          {fname}")
            error_count += 1

    print(f"\n  Summary : {real_count} REAL  |  {fake_count} FAKE  |  {error_count} error(s)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    check_test_folder()
