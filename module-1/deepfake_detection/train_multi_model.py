"""
Multi-Model Training for Deepfake Voice Detection
Trains 9 classifiers, saves each to models/ directory, prints a comparison table.

ASVspoof 2019 LA usage
----------------------
    # Quick pipeline test on ~500 files (a few minutes on CPU):
    python train_multi_model.py --subset ^
        --train-audio D:/LA/LA/ASVspoof2019_LA_train/flac ^
        --labels D:/LA/LA/ASVspoof2019_LA_cm_protocols/ASVspoof2019.LA.cm.train.trn.txt

    # Full training (feature extraction cached after the first run):
    python train_multi_model.py ^
        --train-audio D:/LA/LA/ASVspoof2019_LA_train/flac ^
        --labels D:/LA/LA/ASVspoof2019_LA_cm_protocols/ASVspoof2019.LA.cm.train.trn.txt

    # Re-extract all features from scratch:
    python train_multi_model.py --no-cache --train-audio ... --labels ...

    # Force cross-validation (slow on large datasets, auto-runs for <=2000 samples):
    python train_multi_model.py --cv --train-audio ... --labels ...

Legacy usage (data/fake + data/real folders)
--------------------------------------------
    python train_multi_model.py

Output
------
    models/          — all .pkl models + scaler
    models/best_model.pth — copy of best-performing model
    models/model_results.json
    feature_cache/   — per-file .npy feature cache (fast reload on subsequent runs)
"""

import argparse
import os
import sys
import json
import time
import random
import numpy as np
import joblib
import warnings
warnings.filterwarnings("ignore")

from sklearn.svm import SVC
from sklearn.ensemble import (RandomForestClassifier, GradientBoostingClassifier,
                               ExtraTreesClassifier, AdaBoostClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.metrics import (accuracy_score, classification_report,
                              confusion_matrix, roc_auc_score)

try:
    from catboost import CatBoostClassifier
    _CATBOOST_AVAILABLE = True
except ImportError:
    _CATBOOST_AVAILABLE = False
    print("[WARN] catboost not installed — CatBoost skipped. Run: pip install catboost")

try:
    from imblearn.over_sampling import SMOTE
    _SMOTE_AVAILABLE = True
except ImportError:
    _SMOTE_AVAILABLE = False
    print("[WARN] imbalanced-learn not installed — SMOTE skipped. Run: pip install imbalanced-learn")

_HERE      = os.path.dirname(os.path.abspath(__file__))
_MODEL_DIR = os.path.join(_HERE, "models")
_CACHE_DIR = os.path.join(_HERE, "feature_cache")
os.makedirs(_MODEL_DIR, exist_ok=True)
os.makedirs(_CACHE_DIR, exist_ok=True)


# ── ASVspoof 2019 LA helpers ───────────────────────────────────────────────────

def _parse_protocol(label_file):
    """Parse ASVspoof 2019 LA CM protocol file.

    Format (space-separated):
        SPEAKER_ID  FILENAME  ENVIRONMENT  ATTACK_TYPE  LABEL
        LA_0079     LA_T_1271820  -  A09  spoof

    Returns dict: filename_stem -> 0 (bonafide/real) or 1 (spoof/fake)
    """
    mapping = {}
    with open(label_file, "r") as fh:
        for line in fh:
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            stem      = parts[1]   # e.g. LA_T_1271820
            label_str = parts[-1]  # bonafide | spoof
            mapping[stem] = 0 if label_str == "bonafide" else 1
    return mapping


def _load_or_extract(audio_path, stem, force=False):
    """Return 206-dim feature vector, using per-file disk cache when available."""
    cache_path = os.path.join(_CACHE_DIR, f"{stem}.npy")
    if not force and os.path.exists(cache_path):
        try:
            return np.load(cache_path), True   # (features, was_cached)
        except Exception:
            pass  # corrupt cache entry — fall through to re-extract

    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    from preprocess import extract_features

    feats = extract_features(audio_path)
    if feats is not None:
        np.save(cache_path, feats)
    return feats, False


def load_asvspoof_dataset(audio_dir, label_file, subset=False,
                          subset_n=500, force=False):
    """Load ASVspoof 2019 LA, extracting and caching per-file features.

    Parameters
    ----------
    audio_dir  : folder containing .flac files
    label_file : ASVspoof 2019 LA CM protocol .txt file
    subset     : if True, limit to subset_n files (balanced bonafide/spoof)
    subset_n   : total files when subset=True (default 500)
    force      : ignore existing cache, re-extract everything

    Returns
    -------
    X : np.ndarray  shape (N, 206)
    y : np.ndarray  shape (N,)   0=real / 1=fake
    """
    print(f"[DATA] Parsing protocol : {label_file}")
    file_label = _parse_protocol(label_file)
    print(f"[DATA] Protocol entries : {len(file_label)}")

    bonafide_stems = [s for s, l in file_label.items() if l == 0]
    spoof_stems    = [s for s, l in file_label.items() if l == 1]
    print(f"[DATA]   bonafide : {len(bonafide_stems)}")
    print(f"[DATA]   spoof    : {len(spoof_stems)}")

    if subset:
        half = subset_n // 2
        random.seed(42)
        bonafide_stems = random.sample(bonafide_stems, min(half, len(bonafide_stems)))
        spoof_stems    = random.sample(spoof_stems,    min(half, len(spoof_stems)))
        print(f"[DATA] --subset mode : {len(bonafide_stems)} bonafide + "
              f"{len(spoof_stems)} spoof = {len(bonafide_stems)+len(spoof_stems)} total")

    all_stems  = bonafide_stems + spoof_stems
    all_labels = [0] * len(bonafide_stems) + [1] * len(spoof_stems)
    total      = len(all_stems)

    X, y = [], []
    n_cached = n_extracted = n_skipped = 0

    print(f"[DATA] Loading features for {total} files …")
    print(f"       (Cached files load in <1 ms; uncached files take ~1-3 s each)")
    t_start = time.time()

    for i, (stem, label) in enumerate(zip(all_stems, all_labels), 1):
        audio_path = os.path.join(audio_dir, f"{stem}.flac")
        if not os.path.exists(audio_path):
            n_skipped += 1
            continue

        feats, was_cached = _load_or_extract(audio_path, stem, force=force)
        if feats is None:
            n_skipped += 1
            continue

        X.append(feats)
        y.append(label)
        if was_cached:
            n_cached += 1
        else:
            n_extracted += 1

        if i % 100 == 0 or i == total:
            elapsed = time.time() - t_start
            rate    = i / elapsed if elapsed > 0 else 0
            eta     = (total - i) / rate if rate > 0 else 0
            print(f"  {i:>5}/{total}  ({100*i/total:5.1f}%)  "
                  f"cached={n_cached}  extracted={n_extracted}  "
                  f"skipped={n_skipped}  ETA={eta:.0f}s")

    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.int64)

    print(f"[DATA] Final dataset : {len(y)} samples — "
          f"Real={np.sum(y==0)}  Fake={np.sum(y==1)}")
    if n_skipped:
        print(f"[WARN] Skipped {n_skipped} files "
              f"(audio missing or extraction error)")
    return X, y


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Train deepfake voice detection models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--train-audio", default=None,
        help="Path to ASVspoof 2019 LA train .flac folder")
    parser.add_argument(
        "--labels", default=None,
        help="Path to ASVspoof 2019 LA CM protocol .txt file")
    parser.add_argument(
        "--subset", action="store_true",
        help="Use ~500 files only — quick end-to-end pipeline test")
    parser.add_argument(
        "--subset-n", type=int, default=500,
        help="Number of files in --subset mode (default: 500)")
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Ignore on-disk feature cache and re-extract everything")
    parser.add_argument(
        "--cv", action="store_true",
        help="Force cross-validation even on large datasets (very slow)")
    args = parser.parse_args()

    _X_PATH = os.path.join(_HERE, "X_features.npy")
    _Y_PATH = os.path.join(_HERE, "y_labels.npy")

    # ── Load / extract features ────────────────────────────────────────────────
    if args.train_audio and args.labels:
        # ASVspoof 2019 LA path
        X, y = load_asvspoof_dataset(
            audio_dir  = args.train_audio,
            label_file = args.labels,
            subset     = args.subset,
            subset_n   = args.subset_n,
            force      = args.no_cache,
        )
        # Keep X_features.npy / y_labels.npy in sync for model_analyzer.py
        np.save(_X_PATH, X)
        np.save(_Y_PATH, y)

    elif os.path.exists(_X_PATH):
        # Reuse pre-built feature matrix (legacy or previous ASVspoof run)
        print(f"[DATA] Loading existing feature matrix: {_X_PATH}")
        X = np.load(_X_PATH)
        y = np.load(_Y_PATH)

    else:
        # Legacy flat-folder fallback (data/fake/ + data/real/)
        print("[DATA] --train-audio not given and X_features.npy not found.")
        print("[DATA] Falling back to legacy preprocess.py (data/fake + data/real) …")
        if _HERE not in sys.path:
            sys.path.insert(0, _HERE)
        import preprocess
        X, y, _ = preprocess.load_dataset()
        np.save(_X_PATH, X)
        np.save(_Y_PATH, y)

    if len(y) == 0:
        print("[ERROR] No samples loaded. "
              "Check --train-audio / --labels paths, or your data/ folders.")
        sys.exit(1)

    print(f"\nDataset : {len(y)} samples  |  Real: {np.sum(y==0)}  |  Fake: {np.sum(y==1)}")
    print(f"Features: {X.shape[1]} dimensions  (expected 206: MFCC×3 + chroma + ZCR/RMS/rolloff + pitch + bandwidth + tonnetz + contrast + IMFCC + delta-MFCC + jitter/shimmer)")

    # ── Scale ──────────────────────────────────────────────────────────────────
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    joblib.dump(scaler, os.path.join(_MODEL_DIR, "scaler.pkl"))
    print("Scaler saved.")

    # ── Train / test split ─────────────────────────────────────────────────────
    min_class = int(np.bincount(y).min())
    test_size  = max(0.2, min(0.4, 1 / len(y) * min_class * 2))
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=test_size, stratify=y, random_state=42
    )

    # Cross-validation: run automatically only when dataset is small enough
    # (large datasets make CV prohibitively slow on CPU).
    run_cv  = args.cv or (len(y) <= 2000)
    n_splits = min(5, min_class)
    cv       = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

    if not run_cv:
        print(f"[INFO] CV skipped (dataset has {len(y)} samples — use --cv to force it)")

    print(f"Train: {len(y_train)}  |  Test: {len(y_test)}  |  CV folds: {n_splits if run_cv else 'OFF'}")

    # ── SMOTE oversampling (training set only) ─────────────────────────────────
    if _SMOTE_AVAILABLE:
        min_train_class = int(np.bincount(y_train.astype(int)).min())
        if min_train_class >= 2:
            k_neighbors = min(5, min_train_class - 1)
            smote        = SMOTE(random_state=42, k_neighbors=k_neighbors)
            X_train, y_train = smote.fit_resample(X_train, y_train)
            print(f"SMOTE resampled -> {len(y_train)} samples  "
                  f"|  Real: {int(np.sum(y_train==0))}  |  Fake: {int(np.sum(y_train==1))}")
        else:
            print("[WARN] SMOTE skipped — training class too small for resampling")
    print()

    # ── Dataset-size-aware hyperparameters ─────────────────────────────────────
    knn_k        = max(1, min(7, len(X_train) - 1))
    gb_subsample = 0.8 if len(X_train) > 10 else 1.0
    mlp_early    = len(X_train) >= 10

    # ── Model registry ─────────────────────────────────────────────────────────
    MODELS = {
        "SVM_RBF": (
            "svm_rbf_model.pkl",
            SVC(kernel="rbf", C=10, gamma="scale",
                probability=True, random_state=42, class_weight="balanced"),
        ),
        "SVM_Linear": (
            "svm_linear_model.pkl",
            SVC(kernel="linear", C=1,
                probability=True, random_state=42, class_weight="balanced"),
        ),
        "Random_Forest": (
            "random_forest_model.pkl",
            RandomForestClassifier(
                n_estimators=200, class_weight="balanced",
                random_state=42, n_jobs=-1),
        ),
        "Gradient_Boosting": (
            "gradient_boosting_model.pkl",
            GradientBoostingClassifier(
                n_estimators=200, learning_rate=0.1,
                max_depth=3, subsample=gb_subsample, random_state=42),
        ),
        "Extra_Trees": (
            "extra_trees_model.pkl",
            ExtraTreesClassifier(
                n_estimators=200, class_weight="balanced",
                random_state=42, n_jobs=-1),
        ),
        "AdaBoost": (
            "adaboost_model.pkl",
            AdaBoostClassifier(
                n_estimators=100, learning_rate=0.5,
                random_state=42),
        ),
        "Logistic_Regression": (
            "logistic_regression_model.pkl",
            LogisticRegression(
                C=1.0, max_iter=1000, class_weight="balanced",
                random_state=42, solver="lbfgs"),
        ),
        "KNN": (
            "knn_model.pkl",
            KNeighborsClassifier(
                n_neighbors=knn_k, weights="distance",
                metric="euclidean", n_jobs=-1),
        ),
        "MLP": (
            "mlp_model.pkl",
            MLPClassifier(
                hidden_layer_sizes=(256, 128, 64), activation="relu",
                max_iter=500, random_state=42, early_stopping=mlp_early,
                validation_fraction=0.1, alpha=0.001),
        ),
    }

    if _CATBOOST_AVAILABLE:
        MODELS["CatBoost"] = (
            "catboost_model.pkl",
            CatBoostClassifier(
                iterations=200, learning_rate=0.1,
                depth=6, random_seed=42, verbose=0),
        )

    print(f"KNN neighbors : {knn_k}  (capped to training set size)")
    print(f"Total models  : {len(MODELS)}")

    # ── Train & evaluate ───────────────────────────────────────────────────────
    print("=" * 75)
    print(f"{'Model':<22} {'CV Acc ± Std':>16} {'Test Acc':>9} {'F1':>7} {'AUC':>7} {'Time':>7}")
    print("=" * 75)

    all_results = {}

    for name, (filename, model) in MODELS.items():
        t0 = time.time()

        if run_cv:
            try:
                cv_scores = cross_val_score(model, X_scaled, y,
                                            cv=cv, scoring="accuracy")
            except Exception:
                cv_scores = np.array([0.0])
        else:
            cv_scores = np.array([0.0])

        model.fit(X_train, y_train)
        elapsed = time.time() - t0

        y_pred   = model.predict(X_test)
        test_acc = accuracy_score(y_test, y_pred)
        report   = classification_report(y_test, y_pred, output_dict=True,
                                          target_names=["Real", "Fake"])
        f1 = report["weighted avg"]["f1-score"]

        try:
            if hasattr(model, "predict_proba"):
                y_prob = model.predict_proba(X_test)[:, 1]
            else:
                df     = model.decision_function(X_test)
                y_prob = 1 / (1 + np.exp(-df))
            auc = roc_auc_score(y_test, y_prob)
        except Exception:
            auc = 0.0

        cv_str = f"{cv_scores.mean():.2%} ±{cv_scores.std():.2%}" if run_cv else "skipped"
        print(f"{name:<22} {cv_str:>16}  {test_acc:>8.2%}  {f1:>6.4f}  {auc:>6.4f}  {elapsed:>5.1f}s")

        all_results[name] = {
            "cv_mean":       float(cv_scores.mean()),
            "cv_std":        float(cv_scores.std()),
            "cv_scores":     cv_scores.tolist(),
            "test_accuracy": float(test_acc),
            "f1_score":      float(f1),
            "auc_score":     float(auc),
            "train_time":    float(elapsed),
            "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
            "classification_report": {
                k: v for k, v in report.items() if k != "accuracy"
            },
        }

        save_path = os.path.join(_MODEL_DIR, filename)
        joblib.dump(model, save_path)
        if name == "SVM_RBF":
            joblib.dump(model, os.path.join(_MODEL_DIR, "svm_model.pkl"))

    print("=" * 75)

    # ── Best model ─────────────────────────────────────────────────────────────
    best      = max(all_results, key=lambda k: all_results[k]["test_accuracy"])
    best_acc  = all_results[best]["test_accuracy"]
    best_file = MODELS[best][0]

    print(f"\nBest model : {best}  ({best_acc:.2%} test accuracy)")

    best_pth = os.path.join(_MODEL_DIR, "best_model.pth")
    joblib.dump(joblib.load(os.path.join(_MODEL_DIR, best_file)), best_pth)
    print(f"Saved as   : {best_pth}  (load with joblib.load)")

    # ── Persist JSON ───────────────────────────────────────────────────────────
    results_path = os.path.join(_MODEL_DIR, "model_results.json")
    with open(results_path, "w") as fh:
        json.dump(all_results, fh, indent=2)

    print(f"\nAll models saved to   : {_MODEL_DIR}/")
    print(f"Results JSON saved to : {results_path}")


if __name__ == "__main__":
    main()
