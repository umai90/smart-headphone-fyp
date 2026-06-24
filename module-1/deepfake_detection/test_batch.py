"""
Batch Test Predictor — All Models
Runs every saved classifier on every audio file in a test folder.
Prints a per-file table + ensemble vote + summary.

Usage:
    python test_batch.py                          # uses ../test by default
    python test_batch.py <path_to_test_folder>
"""

import os
import sys
import json
import numpy as np
import joblib
import warnings
warnings.filterwarnings("ignore")

_HERE      = os.path.dirname(os.path.abspath(__file__))
_MODEL_DIR = os.path.join(_HERE, "models")

# ── Test folder ────────────────────────────────────────────────────────────────
if len(sys.argv) > 1:
    TEST_DIR = sys.argv[1]
else:
    TEST_DIR = os.path.join(_HERE, "data", "test")

TEST_DIR = os.path.abspath(TEST_DIR)

AUDIO_EXTS          = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mpeg"}
FAKE_THRESHOLD      = 0.40   # per-model: classify FAKE when fake_prob >= 40%
FAKE_VOTE_THRESHOLD = 2      # ensemble: flag FAKE when >= this many models vote fake

MODEL_FILES = {
    "SVM_RBF":           ["svm_rbf_model.pkl", "svm_model.pkl"],
    "SVM_Linear":        ["svm_linear_model.pkl"],
    "Random_Forest":     ["random_forest_model.pkl"],
    "Grad_Boosting":     ["gradient_boosting_model.pkl"],
    "Extra_Trees":       ["extra_trees_model.pkl"],
    "AdaBoost":          ["adaboost_model.pkl"],
    "Logistic_Reg":      ["logistic_regression_model.pkl"],
    "KNN":               ["knn_model.pkl"],
    "MLP":               ["mlp_model.pkl"],
    "CatBoost":          ["catboost_model.pkl"],
}

# ── Feature extraction — uses preprocess.py (164-dim, matches trained models) ──
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from preprocess import extract_features

# ── Model loader ───────────────────────────────────────────────────────────────
def load_assets():
    scaler_path = os.path.join(_MODEL_DIR, "scaler.pkl")
    if not os.path.exists(scaler_path):
        print(f"[ERROR] scaler.pkl not found in {_MODEL_DIR}")
        print("        Run train_multi_model.py first.")
        sys.exit(1)
    scaler = joblib.load(scaler_path)

    models = {}
    for name, filenames in MODEL_FILES.items():
        for fn in filenames:
            p = os.path.join(_MODEL_DIR, fn)
            if os.path.exists(p):
                try:
                    models[name] = joblib.load(p)
                    break
                except Exception:
                    pass
    return scaler, models

# ── Single model prediction ────────────────────────────────────────────────────
def predict_one(model, scaler, features):
    fs = scaler.transform([features])
    try:
        proba     = model.predict_proba(fs)[0]
        real_prob = float(proba[0] * 100)   # P(Real)
        fake_prob = float(proba[1] * 100)   # P(Fake)
    except Exception:
        try:
            import math
            score     = float(model.decision_function(fs)[0])
            fake_prob = round(100 / (1 + math.exp(-score)), 1)
            real_prob = round(100 - fake_prob, 1)
        except Exception:
            hp = int(model.predict(fs)[0])
            real_prob = 90.0 if hp == 0 else 10.0
            fake_prob = 100.0 - real_prob

    label = "FAKE" if fake_prob >= FAKE_THRESHOLD * 100 else "REAL"
    return label, round(real_prob, 1), round(fake_prob, 1)

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
print("=" * 80)
print("  DEEPFAKE DETECTION — BATCH TEST (All Models)")
print("=" * 80)
print(f"  Test folder : {TEST_DIR}")
print(f"  Model dir   : {_MODEL_DIR}")
print(f"  Per-model threshold : fake_prob >= {FAKE_THRESHOLD*100:.0f}%")
print(f"  Ensemble threshold  : >= {FAKE_VOTE_THRESHOLD} model votes → FAKE")

if not os.path.isdir(TEST_DIR):
    print(f"\n[ERROR] Test folder not found: {TEST_DIR}")
    sys.exit(1)

audio_files = sorted([
    f for f in os.listdir(TEST_DIR)
    if os.path.splitext(f)[1].lower() in AUDIO_EXTS
    and os.path.isfile(os.path.join(TEST_DIR, f))
])

if not audio_files:
    print(f"\n[ERROR] No audio files found in {TEST_DIR}")
    sys.exit(1)

print(f"  Audio files : {len(audio_files)}\n")

scaler, models = load_assets()
model_names = list(models.keys())
print(f"  Loaded {len(models)} model(s): {', '.join(model_names)}\n")

# Column layout
COL = 8   # width per model column
header_models = "".join(f"{n[:COL]:^{COL+1}}" for n in model_names)
print(f"  {'File':<22} {header_models}  {'ENSEMBLE':^10}  {'Real%':>6}  {'Fake%':>6}")
print(f"  {'-'*22} {'  '.join(['-'*COL]*len(model_names))}  {'----------'}  {'------'}  {'------'}")

# Counters
summary = {"REAL": 0, "FAKE": 0, "ERROR": 0}
per_model_fake = {n: 0 for n in model_names}
results_log = []

for fname in audio_files:
    fpath    = os.path.join(TEST_DIR, fname)
    features = extract_features(fpath)

    if features is None:
        print(f"  {fname:<22}  [feature extraction failed]")
        summary["ERROR"] += 1
        continue

    per_model_labels = {}
    real_probs, fake_probs = [], []

    for mname, model in models.items():
        label, rp, fp = predict_one(model, scaler, features)
        per_model_labels[mname] = label
        real_probs.append(rp)
        fake_probs.append(fp)
        if label == "FAKE":
            per_model_fake[mname] += 1

    # Ensemble vote — mirrors deepfake_checker.py FAKE_VOTE_THRESHOLD logic
    votes_fake = sum(1 for l in per_model_labels.values() if l == "FAKE")
    votes_real = len(per_model_labels) - votes_fake
    ensemble   = "FAKE" if votes_fake >= FAKE_VOTE_THRESHOLD else "REAL"
    avg_real   = round(float(np.mean(real_probs)), 1)
    avg_fake   = round(float(np.mean(fake_probs)), 1)
    summary[ensemble] += 1

    # Per-model column icons
    model_cols = "".join(
        f"{'[FAKE]' if per_model_labels.get(n)=='FAKE' else '[real]':^{COL+1}}"
        for n in model_names
    )
    ens_tag = f"[FAKE] {votes_fake}/{len(models)}" if ensemble == "FAKE" else f"[real] {votes_real}/{len(models)}"
    print(f"  {fname:<22} {model_cols}  {ens_tag:<12}  {avg_real:>5.1f}%  {avg_fake:>5.1f}%")

    results_log.append({
        "file": fname, "ensemble": ensemble,
        "votes_fake": votes_fake, "votes_real": votes_real,
        "avg_real_prob": avg_real, "avg_fake_prob": avg_fake,
        "per_model": per_model_labels,
    })

# ── Summary ────────────────────────────────────────────────────────────────────
total = summary["REAL"] + summary["FAKE"]
print(f"\n{'='*80}")
print(f"  SUMMARY — {len(audio_files)} files tested")
print(f"{'='*80}")
print(f"  Ensemble verdict:")
print(f"    REAL  : {summary['REAL']:>3} files  ({summary['REAL']/max(total,1)*100:.1f}%)")
print(f"    FAKE  : {summary['FAKE']:>3} files  ({summary['FAKE']/max(total,1)*100:.1f}%)")
if summary["ERROR"]:
    print(f"    ERROR : {summary['ERROR']:>3} files  (feature extraction failed)")

print(f"\n  Per-model FAKE detections (out of {len(audio_files)} files):")
for mname in model_names:
    cnt  = per_model_fake[mname]
    pct  = cnt / len(audio_files) * 100
    bar  = "#" * int(pct / 5)
    print(f"    {mname:<20} {cnt:>2} fake  ({pct:>5.1f}%)  [{bar:<20}]")

# ── Save JSON log ──────────────────────────────────────────────────────────────
log_path = os.path.join(_HERE, "test_results.json")
with open(log_path, "w") as fh:
    json.dump(results_log, fh, indent=2)
print(f"\n  Detailed results saved to: test_results.json")
print("=" * 80)
