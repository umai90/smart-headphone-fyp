"""
Balance Dataset — undersample fake to match real count (1:1 ratio).
Reads X_features.npy + y_labels.npy, writes balanced versions.
Original files are backed up as X_features_original.npy / y_labels_original.npy.
"""

import numpy as np
import os

_HERE = os.path.dirname(os.path.abspath(__file__))

X_PATH      = os.path.join(_HERE, "X_features.npy")
Y_PATH      = os.path.join(_HERE, "y_labels.npy")
X_BAK_PATH  = os.path.join(_HERE, "X_features_original.npy")
Y_BAK_PATH  = os.path.join(_HERE, "y_labels_original.npy")


def balance():
    if not os.path.exists(X_PATH) or not os.path.exists(Y_PATH):
        print("[ERROR] X_features.npy or y_labels.npy not found.")
        print("        Run train_multi_model.py --train-audio ... first.")
        return False

    X = np.load(X_PATH)
    y = np.load(Y_PATH)

    real_idx = np.where(y == 0)[0]
    fake_idx = np.where(y == 1)[0]
    n_real   = len(real_idx)
    n_fake   = len(fake_idx)

    print(f"\n[BALANCE] Current dataset:")
    print(f"  Real (label=0) : {n_real}")
    print(f"  Fake (label=1) : {n_fake}")
    print(f"  Ratio          : 1 : {n_fake / n_real:.1f}")

    if n_real == n_fake:
        print("[BALANCE] Already balanced — nothing to do.")
        return True

    # Back up originals (only once)
    if not os.path.exists(X_BAK_PATH):
        np.save(X_BAK_PATH, X)
        np.save(Y_BAK_PATH, y)
        print(f"\n[BALANCE] Originals backed up:")
        print(f"  {X_BAK_PATH}")
        print(f"  {Y_BAK_PATH}")
    else:
        print("\n[BALANCE] Backup already exists — skipping backup.")

    # Undersample fake to match real count (reproducible random seed)
    rng          = np.random.default_rng(seed=42)
    chosen_fake  = rng.choice(fake_idx, size=n_real, replace=False)

    balanced_idx = np.concatenate([real_idx, chosen_fake])
    rng.shuffle(balanced_idx)

    X_bal = X[balanced_idx]
    y_bal = y[balanced_idx]

    np.save(X_PATH, X_bal)
    np.save(Y_PATH, y_bal)

    print(f"\n[BALANCE] Balanced dataset saved:")
    print(f"  Real (label=0) : {int((y_bal == 0).sum())}")
    print(f"  Fake (label=1) : {int((y_bal == 1).sum())}")
    print(f"  Total          : {len(y_bal)}")
    print(f"  Ratio          : 1 : 1  (balanced)")
    print(f"\n[BALANCE] Ready — run train_multi_model.py to retrain all models.")
    return True


if __name__ == "__main__":
    balance()
