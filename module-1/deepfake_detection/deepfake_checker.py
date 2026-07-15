"""
Deepfake Checker — ensemble wrapper for deepfake_detection/
Used by realtime_detect.py for live microphone-based detection.

Loads all trained classifiers from model/ (populated by train_multi_model.py),
runs weighted ensemble voting, and applies the two-tier rule fallback.

Improvements over simple majority voting:
  1. Weighted voting   — each model's vote is scaled by its test accuracy
                         (SVM-RBF at 99.98% outweighs AdaBoost at 95.12%)
  2. Prob override     — avg fake probability >= 40% triggers FAKE regardless of votes
  3. High-conf bypass  — avg fake probability >= 75% skips voting entirely (fast path)

Public API (must match what realtime_detect.py expects):
    predict_ensemble(audio_path) -> dict
    available_models()           -> list[str]
"""

import os
import sys
import json
import math
import glob
import numpy as np
import warnings
warnings.filterwarnings("ignore")

_HERE      = os.path.dirname(os.path.abspath(__file__))
_MODEL_DIR = os.path.join(_HERE, "models")

# ── Threshold settings ────────────────────────────────────────────────────────
#
# Thresholds lowered to catch modern high-quality TTS (ChatGPT, ElevenLabs, etc.)
# which score lower fake-probabilities than older voice-conversion fakes.
#
# FAKE_WEIGHT_THRESHOLD: weighted fraction of model accuracy that must vote fake.
#   Lowered 0.20 → 0.12 so even 1–2 high-accuracy models voting FAKE triggers it.
FAKE_WEIGHT_THRESHOLD = 0.12

# FAKE_PROB_THRESHOLD: avg fake probability override (0–100).
#   Lowered 40 → 28 — modern TTS scores 25–35% fake; old threshold missed them.
FAKE_PROB_THRESHOLD = 28.0

# HIGH_CONF_THRESHOLD: fast-path bypass (0–100).
#   Lowered 75 → 60 — clear fakes flagged sooner.
HIGH_CONF_THRESHOLD = 60.0

_cache: dict = {}

# Excluded 2026-07-14, narrowed 2026-07-15 after retraining with diverse
# real mic-captured audio (not just LibriSpeech) — see the matching comment
# in translate/deepfake_checker.py (the production copy) for the full
# analysis. Only AdaBoost still shows elevated fake-probability (38.6% avg)
# on held-out real mic recordings never seen in training; every other
# previously-excluded model (random_forest, extra_trees, gradient_boosting,
# catboost) now generalizes well (2-18% avg fake-prob on the same held-out
# set) and has been re-included. Keep this set in sync with
# translate/deepfake_checker.py.
_EXCLUDED_MODELS: set = {
    "adaboost",
}

# ── Feature extraction (206-dim, same as preprocess.py) ───────────────────────
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from preprocess import extract_features


# ── Model weights from training results ───────────────────────────────────────
def _load_model_weights():
    """Load per-model accuracy weights from model_results.json.

    Returns dict: lowercase model name -> test_accuracy (float 0-1).
    Falls back to uniform weight 1.0 if file is missing.
    """
    if "weights" in _cache:
        return _cache["weights"]
    results_path = os.path.join(_MODEL_DIR, "model_results.json")
    if not os.path.exists(results_path):
        _cache["weights"] = {}
        return {}
    try:
        with open(results_path) as f:
            results = json.load(f)
        # JSON keys like "SVM_RBF" → normalize to "svm_rbf" to match model dict
        weights = {k.lower(): float(v.get("test_accuracy", 1.0))
                   for k, v in results.items()}
        _cache["weights"] = weights
        return weights
    except Exception:
        _cache["weights"] = {}
        return {}


# ── Scaler ─────────────────────────────────────────────────────────────────────
def _load_scaler():
    if "scaler" not in _cache:
        try:
            import joblib
        except ImportError:
            return None
        path = os.path.join(_MODEL_DIR, "scaler.pkl")
        if os.path.exists(path):
            _cache["scaler"] = joblib.load(path)
        else:
            return None
    return _cache["scaler"]


# ── Load all models ────────────────────────────────────────────────────────────
def _load_all_models():
    if "all_models" in _cache:
        return _cache["all_models"]
    try:
        import joblib
    except ImportError:
        return {}
    if not os.path.isdir(_MODEL_DIR):
        return {}
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
    _cache["all_models"] = models
    return models


def available_models() -> list:
    """Return list of loaded model names."""
    return list(_load_all_models().keys())


# ── Two-tier rule fallback ─────────────────────────────────────────────────────
def _extract_rule_signals(audio_path):
    try:
        import librosa
        y, sr = librosa.load(audio_path, mono=True)
        if len(y) == 0:
            return None
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
        pitch_vals  = pitches[magnitudes > np.median(magnitudes)]
        pitch_std   = float(np.std(pitch_vals)) if len(pitch_vals) > 0 else 999.0
        centroid    = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
        rms_std     = float(np.std(librosa.feature.rms(y=y)))
        return pitch_std, centroid, rms_std
    except Exception:
        return None


def _rule_says_fake(pitch_std, centroid, rms_std):
    """Widened to catch modern high-quality TTS (ChatGPT, ElevenLabs).
    Old values: pitch<50, centroid>3000, rms<0.01 — too strict for neural TTS."""
    return pitch_std < 80 and centroid > 2500 and rms_std < 0.02


# ── Core prediction ────────────────────────────────────────────────────────────
def predict_ensemble(audio_path: str) -> dict:
    """
    Run weighted ensemble prediction on a single audio file.

    Decision hierarchy:
      1. High-confidence fast path: avg fake-prob >= 75% → FAKE immediately
      2. Weighted vote: weighted fake fraction >= 20% → FAKE
      3. Probability override: avg fake-prob >= 40% → FAKE
      4. Physics rule fallback: 1+ votes + rule signals → FAKE
      5. Otherwise → REAL

    Returns dict with: label, confidence, real_prob, fake_prob,
                       votes_fake, votes_real, models_used, weighted_fake_frac.
    On failure returns dict with 'error' key.
    """
    scaler  = _load_scaler()
    models  = _load_all_models()
    weights = _load_model_weights()

    if scaler is None:
        return {"error": "scaler.pkl not found. Run train_multi_model.py first."}
    if not models:
        return {"error": "No model .pkl files found. Run train_multi_model.py first."}

    features = extract_features(audio_path)
    if features is None:
        return {"error": "Feature extraction failed — check audio file."}

    try:
        features_scaled = scaler.transform(features.reshape(1, -1))
    except Exception as e:
        return {"error": f"Scaler transform failed: {e}"}

    fake_votes   = 0
    total        = len(models)
    fake_probs   = []
    total_weight = 0.0
    fake_weight  = 0.0

    for name, model in models.items():
        w = weights.get(name, 1.0)   # fallback to uniform weight if not in JSON
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
            print(f"  [WARN] {name} failed: {e}")
            total -= 1

    if total == 0:
        return {"error": "All model predictions failed."}

    avg_fake           = float(np.mean(fake_probs)) * 100 if fake_probs else (fake_votes / total * 100)
    weighted_fake_frac = fake_weight / total_weight if total_weight > 0 else 0.0

    # ── Decision hierarchy ─────────────────────────────────────────────────────
    if avg_fake >= HIGH_CONF_THRESHOLD:
        # Fast path: models are overwhelmingly confident — skip vote counting
        label = "FAKE"
    elif weighted_fake_frac >= FAKE_WEIGHT_THRESHOLD:
        # Weighted vote threshold crossed
        label = "FAKE"
    elif avg_fake >= FAKE_PROB_THRESHOLD:
        # Probability override: ensemble is leaning fake even without enough votes
        label = "FAKE"
    elif fake_votes >= 1:
        # Physics rule fallback for borderline cases
        signals = _extract_rule_signals(audio_path)
        if signals and _rule_says_fake(*signals):
            label    = "FAKE"
            avg_fake = max(avg_fake, 60.0)
        else:
            label = "REAL"
    else:
        label = "REAL"

    real_prob  = round(100.0 - avg_fake, 1)
    fake_prob  = round(avg_fake, 1)
    confidence = fake_prob if label == "FAKE" else real_prob

    return {
        "label":              label,
        "confidence":         round(confidence, 1),
        "real_prob":          real_prob,
        "fake_prob":          fake_prob,
        "votes_fake":         fake_votes,
        "votes_real":         total - fake_votes,
        "models_used":        total,
        "weighted_fake_frac": round(weighted_fake_frac * 100, 1),
    }
