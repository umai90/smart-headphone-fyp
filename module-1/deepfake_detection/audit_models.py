"""
Post-retrain audit: for each trained model, test individually against
held-out real mic recordings (never seen in training) + data/test/ files
+ a sample of known-fake files, to see which models actually generalize
to real-world mic-captured audio vs which still only recognise
"clean studio audio == real".
"""
import os
import sys
import glob
import json
import joblib
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from preprocess import extract_features

MODEL_DIR = os.path.join(_HERE, "models")

HOLDOUT_REAL_DIR = os.path.join(_HERE, "..", "..", "translate", "recordings")
HOLDOUT_REAL_FILES = [
    "20260421_035535_001_Pi-1Way_ur.wav",
    "20260421_035535_002_Pi-1Way_ur.wav",
    "20260421_035535_009_Pi-1Way_ur.wav",
    "20260421_035535_011_Pi-1Way_ur.wav",
    "20260421_035535_012_Pi-1Way_ur.wav",
    "20260421_035535_015_Pi-1Way_ur.wav",
    "20260510_193316_001_AUTO_ur.wav",
    "20260510_212043_001_AUTO_ur.wav",
    "20260523_075145_001_AUTO_ur.wav",
    "20260603_062137_015_Pi-1Way_ur.wav",
    "20260613_111257_003_AUTO_en.wav",
    "20260715_045315_001_AUTO_en.wav",
]

TEST_DIR = os.path.join(_HERE, "data", "test")
KNOWN_FAKE_SAMPLE = [
    "Ali.wav", "Aurther.wav", "Connor.wav", "David.wav", "Davis.wav",
    "biden-to-Trump.wav", "biden-to-musk.wav",
]
FAKE_DIR = os.path.join(_HERE, "data", "fake")


def load_models():
    scaler = joblib.load(os.path.join(MODEL_DIR, "scaler.pkl"))
    models = {}
    for pkl in sorted(glob.glob(os.path.join(MODEL_DIR, "*.pkl"))):
        fname = os.path.basename(pkl)
        if fname in ("scaler.pkl", "svm_model.pkl", "best_model.pth"):
            continue
        name = fname.replace("_model.pkl", "").replace(".pkl", "")
        try:
            models[name] = joblib.load(pkl)
        except Exception as e:
            print(f"  [WARN] could not load {fname}: {e}")
    return scaler, models


def predict_one(model, scaler, path):
    feats = extract_features(path)
    if feats is None:
        return None
    fs = scaler.transform(feats.reshape(1, -1))
    pred = int(model.predict(fs)[0])
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(fs)[0]
        classes = list(model.classes_)
        fake_idx = classes.index(1) if 1 in classes else 1
        fake_prob = float(proba[fake_idx]) * 100
    else:
        fake_prob = float(pred) * 100
    return pred, fake_prob


def main():
    scaler, models = load_models()
    print(f"Loaded {len(models)} models: {', '.join(models.keys())}\n")

    real_files = [os.path.join(HOLDOUT_REAL_DIR, f) for f in HOLDOUT_REAL_FILES]
    real_files.append(os.path.join(TEST_DIR, "Test(Urdu Real Audio).wav"))
    fake_files = [os.path.join(FAKE_DIR, f) for f in KNOWN_FAKE_SAMPLE]
    fake_files.append(os.path.join(TEST_DIR, "Test(Urdu Clone).wav"))

    print(f"Held-out REAL (mic-captured, never trained on): {len(real_files)} files")
    print(f"Known FAKE sample: {len(fake_files)} files\n")

    results = {}
    for name, model in models.items():
        real_correct = real_probs = 0
        real_fake_probs = []
        for f in real_files:
            r = predict_one(model, scaler, f)
            if r is None:
                continue
            pred, fake_prob = r
            real_fake_probs.append(fake_prob)
            if pred == 0:
                real_correct += 1

        fake_correct = 0
        fake_fake_probs = []
        for f in fake_files:
            r = predict_one(model, scaler, f)
            if r is None:
                continue
            pred, fake_prob = r
            fake_fake_probs.append(fake_prob)
            if pred == 1:
                fake_correct += 1

        real_acc = real_correct / len(real_files) * 100
        fake_acc = fake_correct / len(fake_files) * 100
        avg_real_fakeprob = np.mean(real_fake_probs)
        avg_fake_fakeprob = np.mean(fake_fake_probs)

        results[name] = {
            "real_acc": real_acc,
            "fake_acc": fake_acc,
            "avg_fake_prob_on_real": avg_real_fakeprob,
            "avg_fake_prob_on_fake": avg_fake_fakeprob,
        }
        print(f"{name:22s}  held-out-REAL acc: {real_acc:6.1f}%  "
              f"(avg fake_prob {avg_real_fakeprob:5.1f}%)   "
              f"FAKE acc: {fake_acc:6.1f}%  (avg fake_prob {avg_fake_fakeprob:5.1f}%)")

    with open(os.path.join(_HERE, "audit_results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved: audit_results.json")


if __name__ == "__main__":
    main()
