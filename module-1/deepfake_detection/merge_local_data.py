"""
Merge local data/real + data/fake into the existing balanced ASVspoof dataset.
Extracts features from local files, appends to X_features.npy, rebalances 1:1.
"""
import os, sys, numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

X_PATH = os.path.join(_HERE, "X_features.npy")
Y_PATH = os.path.join(_HERE, "y_labels.npy")

print("\n[MERGE] Loading existing balanced dataset (ASVspoof)...")
X_asv = np.load(X_PATH)
y_asv = np.load(Y_PATH)
print(f"  ASVspoof Real : {int((y_asv==0).sum())}")
print(f"  ASVspoof Fake : {int((y_asv==1).sum())}")

print("\n[MERGE] Extracting features from local data/real + data/fake...")
from preprocess import load_dataset
X_local, y_local, names = load_dataset()
if len(y_local) == 0:
    print("[ERROR] No local files found. Check data/real/ and data/fake/ folders.")
    sys.exit(1)
print(f"  Local Real (with aug): {int((y_local==0).sum())}")
print(f"  Local Fake (with aug): {int((y_local==1).sum())}")

print("\n[MERGE] Combining datasets...")
X_combined = np.concatenate([X_asv, X_local], axis=0)
y_combined = np.concatenate([y_asv, y_local], axis=0)
print(f"  Combined Real : {int((y_combined==0).sum())}")
print(f"  Combined Fake : {int((y_combined==1).sum())}")

print("\n[MERGE] Rebalancing to 1:1...")
real_idx = np.where(y_combined == 0)[0]
fake_idx = np.where(y_combined == 1)[0]
n_min    = min(len(real_idx), len(fake_idx))

rng          = np.random.default_rng(seed=42)
chosen_real  = rng.choice(real_idx, size=n_min, replace=False)
chosen_fake  = rng.choice(fake_idx, size=n_min, replace=False)
balanced_idx = np.concatenate([chosen_real, chosen_fake])
rng.shuffle(balanced_idx)

X_bal = X_combined[balanced_idx]
y_bal = y_combined[balanced_idx]

np.save(X_PATH, X_bal)
np.save(Y_PATH, y_bal)

print(f"\n[MERGE] Saved balanced dataset:")
print(f"  Real : {int((y_bal==0).sum())}")
print(f"  Fake : {int((y_bal==1).sum())}")
print(f"  Total: {len(y_bal)}")
print(f"\n[MERGE] Done. Run train_multi_model.py --cv to retrain.")
