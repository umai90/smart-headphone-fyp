"""
Full Retrain Pipeline - Urdu-aware Deepfake Detection
======================================================

Steps:
  1. Generate Urdu TTS fake voices  (generate_urdu_fakes.py)
  2. Clear stale feature cache      (X_features.npy, feature_cache/)
  3. Retrain all 9 models           (train_multi_model.py)
  4. Show before/after accuracy     (compare old vs new model_results.json)

Run:
    python retrain_pipeline.py

Requirements:
    pip install gtts pydub
    (pydub needs ffmpeg — install from https://ffmpeg.org/download.html)
"""

import os
import sys
import json
import shutil
import subprocess
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE      = os.path.dirname(os.path.abspath(__file__))
_MODEL_DIR = os.path.join(_HERE, "models")
_CACHE_DIR = os.path.join(_HERE, "feature_cache")
_X_PATH    = os.path.join(_HERE, "X_features.npy")
_Y_PATH    = os.path.join(_HERE, "y_labels.npy")
_RESULTS   = os.path.join(_MODEL_DIR, "model_results.json")
_FAKE_DIR  = os.path.join(_HERE, "data", "fake")
_REAL_DIR  = os.path.join(_HERE, "data", "real")


def _header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def step1_check_data():
    _header("STEP 1 — Data check")

    fake_files = [f for f in os.listdir(_FAKE_DIR)
                  if f.endswith((".wav", ".mp3", ".flac", ".ogg", ".m4a"))]
    real_files = [f for f in os.listdir(_REAL_DIR)
                  if f.endswith((".wav", ".mp3", ".flac", ".ogg", ".m4a"))]

    urdu_fakes = [f for f in fake_files if f.startswith("urdu_")]
    eng_fakes  = [f for f in fake_files if not f.startswith("urdu_")]

    print(f"  Real files          : {len(real_files)}")
    print(f"  Fake files (total)  : {len(fake_files)}")
    print(f"    |-- English fakes   : {len(eng_fakes)}")
    print(f"    |-- Urdu fakes      : {len(urdu_fakes)}")

    if len(urdu_fakes) == 0:
        print("\n  [WARN] No Urdu fake files found.")
        print("  Running generate_urdu_fakes.py first...")
        return False
    elif len(urdu_fakes) < 10:
        print(f"\n  [WARN] Only {len(urdu_fakes)} Urdu fakes — recommended >= 30.")
        print("  Consider running generate_urdu_fakes.py again.")

    print(f"\n  Dataset looks good. Proceeding with retraining.")
    return True


def step2_generate_urdu_fakes():
    _header("STEP 2 — Generate Urdu TTS fakes")

    script = os.path.join(_HERE, "generate_urdu_fakes.py")
    if not os.path.exists(script):
        print(f"  [ERROR] generate_urdu_fakes.py not found at {script}")
        sys.exit(1)

    print("  Running generate_urdu_fakes.py ...")
    result = subprocess.run(
        [sys.executable, script],
        cwd=_HERE
    )
    if result.returncode != 0:
        print("  [ERROR] generate_urdu_fakes.py failed.")
        sys.exit(1)


def step3_clear_cache():
    _header("STEP 3 — Clear stale feature cache")

    # Delete X_features.npy and y_labels.npy — forces fresh feature extraction
    for path, label in [(_X_PATH, "X_features.npy"), (_Y_PATH, "y_labels.npy")]:
        if os.path.exists(path):
            os.remove(path)
            print(f"  Deleted: {label}")
        else:
            print(f"  Not found (ok): {label}")

    # Delete feature_cache/ directory — per-file .npy cache
    if os.path.isdir(_CACHE_DIR):
        shutil.rmtree(_CACHE_DIR)
        print(f"  Deleted: feature_cache/ ({_CACHE_DIR})")
    else:
        print("  feature_cache/ not found (ok)")

    print("  Cache cleared. Training will extract fresh features.")


def step4_load_old_results() -> dict:
    """Load existing model results before retraining (for before/after comparison)."""
    if not os.path.exists(_RESULTS):
        return {}
    with open(_RESULTS) as f:
        return json.load(f)


def step5_retrain():
    _header("STEP 4 — Retrain all models")

    script = os.path.join(_HERE, "train_multi_model.py")
    if not os.path.exists(script):
        print(f"  [ERROR] train_multi_model.py not found at {script}")
        sys.exit(1)

    print("  Running train_multi_model.py (legacy flat-folder mode) ...")
    print("  This will take 5-15 minutes on CPU.\n")

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, script],
        cwd=_HERE
    )
    elapsed = time.time() - t0

    if result.returncode != 0:
        print("  [ERROR] Training failed. Check output above.")
        sys.exit(1)

    print(f"\n  Training completed in {elapsed/60:.1f} minutes.")


def step6_compare(old_results: dict):
    _header("STEP 5 — Before vs After comparison")

    if not os.path.exists(_RESULTS):
        print("  model_results.json not found after training.")
        return

    with open(_RESULTS) as f:
        new_results = json.load(f)

    if not old_results:
        print("  No old results to compare (first-time training).")
        _print_results_table(new_results, label="NEW")
        return

    print(f"\n  {'Model':<22} {'OLD Acc':>9} {'NEW Acc':>9} {'Change':>8}")
    print(f"  {'-'*52}")

    for name, new_data in new_results.items():
        new_acc = new_data["test_accuracy"]
        old_acc = old_results.get(name, {}).get("test_accuracy", None)

        if old_acc is not None:
            delta = new_acc - old_acc
            sign  = "+" if delta >= 0 else ""
            print(f"  {name:<22} {old_acc:>8.2%}  {new_acc:>8.2%}  {sign}{delta:>+.2%}")
        else:
            print(f"  {name:<22} {'N/A':>9}  {new_acc:>8.2%}  {'(new)':>8}")

    best     = max(new_results, key=lambda k: new_results[k]["test_accuracy"])
    best_acc = new_results[best]["test_accuracy"]
    print(f"\n  Best model: {best}  ({best_acc:.2%})")


def _print_results_table(results: dict, label: str = ""):
    print(f"\n  {'Model':<22} {'Accuracy':>10} {'F1':>8} {'AUC':>8}")
    print(f"  {'-'*52}")
    for name, data in sorted(results.items(),
                              key=lambda x: x[1]["test_accuracy"], reverse=True):
        print(f"  {name:<22} {data['test_accuracy']:>9.2%}  "
              f"{data['f1_score']:>7.4f}  {data['auc_score']:>7.4f}")


def step7_verify_fake_dir():
    _header("STEP 6 — Final data summary")

    fake_files = [f for f in os.listdir(_FAKE_DIR)
                  if f.endswith((".wav", ".mp3", ".flac", ".ogg", ".m4a"))]
    real_files = [f for f in os.listdir(_REAL_DIR)
                  if f.endswith((".wav", ".mp3", ".flac", ".ogg", ".m4a"))]
    urdu_fakes = [f for f in fake_files if f.startswith("urdu_")]

    print(f"  Real files        : {len(real_files)}")
    print(f"  Fake files total  : {len(fake_files)}")
    print(f"    |-- Urdu fakes    : {len(urdu_fakes)}")
    print(f"    |-- English fakes : {len(fake_files) - len(urdu_fakes)}")
    print()
    print("  Models saved to   :", _MODEL_DIR)
    print("  Results JSON      :", _RESULTS)
    print()
    print("  Run realtime detection:")
    print("    python realtime_detect.py")
    print()
    print("  The model now knows:")
    print("    FAKE = AI-generated voice (English OR Urdu)")
    print("    REAL = Natural human voice (English OR Urdu)")


def main():
    print("\n" + "=" * 60)
    print("  Urdu-Aware Deepfake Retrain Pipeline")
    print("=" * 60)

    # Check if Urdu fakes already exist
    urdu_fakes_exist = any(
        f.startswith("urdu_")
        for f in os.listdir(_FAKE_DIR)
        if f.endswith((".wav", ".mp3"))
    ) if os.path.isdir(_FAKE_DIR) else False

    if not urdu_fakes_exist:
        step2_generate_urdu_fakes()
    else:
        data_ok = step1_check_data()
        if not data_ok:
            step2_generate_urdu_fakes()

    step1_check_data()

    # Save old results before wiping cache
    old_results = step4_load_old_results()

    step3_clear_cache()
    step5_retrain()
    step6_compare(old_results)
    step7_verify_fake_dir()

    print("\n  Pipeline complete.")


if __name__ == "__main__":
    main()
