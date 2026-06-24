"""
Batch predictor — runs SVM on every audio file in the Fake/ and Real/ folders.
Usage:  python batch_predict.py
        python batch_predict.py <folder_path>   # custom folder
"""

import os
import sys
import joblib
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from preprocess import extract_features

_MODEL_DIR     = os.path.join(_HERE, "models")
FAKE_THRESHOLD = 40.0   # classify FAKE when fake_prob >= 40% (ASVspoof security-first EER point)
AUDIO_EXTS     = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mpeg"}

try:
    svm    = joblib.load(os.path.join(_MODEL_DIR, "svm_model.pkl"))
    scaler = joblib.load(os.path.join(_MODEL_DIR, "scaler.pkl"))
except FileNotFoundError as e:
    print(f"[ERROR] Model file not found: {e}")
    print("Run train_multi_model.py first.")
    sys.exit(1)

# Default: scan both Fake/ and Real/ folders side-by-side
_ROOT = os.path.join(_HERE, "..")
SCAN_FOLDERS = [
    (os.path.join(_ROOT, "Fake"), "FAKE"),
    (os.path.join(_ROOT, "Real"), "REAL"),
]
if len(sys.argv) > 1:
    SCAN_FOLDERS = [(sys.argv[1], "?")]

print(f"\n{'File':<42} {'True':>6} {'Pred':>6} {'Real%':>8} {'Fake%':>8}  Status")
print("-" * 85)

correct = total = 0

for folder_path, true_label in SCAN_FOLDERS:
    if not os.path.isdir(folder_path):
        continue
    for fname in sorted(os.listdir(folder_path)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in AUDIO_EXTS:
            continue
        fpath    = os.path.join(folder_path, fname)
        features = extract_features(fpath)
        if features is None:
            print(f"  {fname:<40}  ERROR")
            continue

        scaled   = scaler.transform([features])
        proba    = svm.predict_proba(scaled)[0]

        # sklearn classes_ = [0=REAL, 1=FAKE]
        real_pct = float(proba[0] * 100)
        fake_pct = float(proba[1] * 100)
        label    = "FAKE" if fake_pct >= FAKE_THRESHOLD else "REAL"

        total += 1
        hit    = (label == true_label) or true_label == "?"
        if hit:
            correct += 1
        status = "OK" if label == true_label else ("MISS" if true_label != "?" else "")

        display = f"{os.path.basename(folder_path)}/{fname}"
        print(f"  {display:<40}  {true_label:>4}  {label:>4}  "
              f"{real_pct:>6.1f}%  {fake_pct:>6.1f}%  {status}")

if total > 0 and SCAN_FOLDERS[0][1] != "?":
    print(f"\n  Accuracy: {correct}/{total} = {correct/total:.1%}")
print()
