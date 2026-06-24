"""
Model Analyzer — Deepfake Voice Detection
Loads (or trains) all 9 classifiers, produces a comprehensive accuracy report,
confusion matrices, ROC/PR curves, and a ranked summary.

Run:   python model_analyzer.py
Output directory:  deepfake_detection/analysis/
"""

import os
import sys
import json
import time
import numpy as np
import joblib
import warnings
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.svm import SVC
from sklearn.ensemble import (RandomForestClassifier, GradientBoostingClassifier,
                               ExtraTreesClassifier, AdaBoostClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                              roc_auc_score, roc_curve, precision_recall_curve,
                              average_precision_score, f1_score)

try:
    from catboost import CatBoostClassifier
    _CATBOOST_AVAILABLE = True
except ImportError:
    _CATBOOST_AVAILABLE = False

_HERE         = os.path.dirname(os.path.abspath(__file__))
_MODEL_DIR    = os.path.join(_HERE, "models")
_ANALYSIS_DIR = os.path.join(_HERE, "analysis")
os.makedirs(_MODEL_DIR, exist_ok=True)
os.makedirs(_ANALYSIS_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# 1. Load features
# ──────────────────────────────────────────────────────────────────────────────
_X_PATH = os.path.join(_HERE, "X_features.npy")
_Y_PATH = os.path.join(_HERE, "y_labels.npy")

print("=" * 70)
print("  DEEPFAKE VOICE DETECTION — MODEL ANALYZER")
print("=" * 70)

if not os.path.exists(_X_PATH):
    print("[INFO] Feature file not found — running preprocess.py …")
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import preprocess
    X, y, _ = preprocess.load_dataset()
    np.save(_X_PATH, X)
    np.save(_Y_PATH, y)
else:
    X = np.load(_X_PATH)
    y = np.load(_Y_PATH)

print(f"[DATA] {len(y)} samples  |  Real: {np.sum(y==0)}  |  Fake: {np.sum(y==1)}")
print(f"[DATA] Feature dimensions: {X.shape[1]}")

# ──────────────────────────────────────────────────────────────────────────────
# 2. Scale & split
# ──────────────────────────────────────────────────────────────────────────────
scaler_path = os.path.join(_MODEL_DIR, "scaler.pkl")
if os.path.exists(scaler_path):
    scaler  = joblib.load(scaler_path)
    X_scaled = scaler.transform(X)
else:
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    joblib.dump(scaler, scaler_path)

min_class = int(np.bincount(y).min())
test_size  = max(0.2, min(0.4, 1 / len(y) * min_class * 2))
X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=test_size, stratify=y, random_state=42
)
n_splits = min(5, min_class)
cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

print(f"[SPLIT] Train: {len(y_train)}  |  Test: {len(y_test)}  |  CV folds: {n_splits}")

# Dataset-size-aware hyperparameters
knn_k       = max(1, min(7, len(X_train) - 1))
gb_subsample = 0.8 if len(X_train) > 10 else 1.0
mlp_early   = len(X_train) >= 10
print(f"[INFO]  KNN k={knn_k}  GradBoost subsample={gb_subsample}  MLP early_stopping={mlp_early}")

# ──────────────────────────────────────────────────────────────────────────────
# 3. Model registry  (filename → estimator definition)
# ──────────────────────────────────────────────────────────────────────────────
MODEL_REGISTRY = {
    "SVM_RBF": (
        ["svm_rbf_model.pkl", "svm_model.pkl"],
        SVC(kernel="rbf", C=10, gamma="scale",
            probability=True, random_state=42, class_weight="balanced"),
    ),
    "SVM_Linear": (
        ["svm_linear_model.pkl"],
        SVC(kernel="linear", C=1,
            probability=True, random_state=42, class_weight="balanced"),
    ),
    "Random_Forest": (
        ["random_forest_model.pkl"],
        RandomForestClassifier(n_estimators=200, class_weight="balanced",
                               random_state=42, n_jobs=-1),
    ),
    "Gradient_Boosting": (
        ["gradient_boosting_model.pkl"],
        GradientBoostingClassifier(n_estimators=200, learning_rate=0.1,
                                    max_depth=3, subsample=gb_subsample, random_state=42),
    ),
    "Extra_Trees": (
        ["extra_trees_model.pkl"],
        ExtraTreesClassifier(n_estimators=200, class_weight="balanced",
                              random_state=42, n_jobs=-1),
    ),
    "AdaBoost": (
        ["adaboost_model.pkl"],
        AdaBoostClassifier(n_estimators=100, learning_rate=0.5,
                            random_state=42),
    ),
    "Logistic_Regression": (
        ["logistic_regression_model.pkl"],
        LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced",
                            random_state=42, solver="lbfgs"),
    ),
    "KNN": (
        ["knn_model.pkl"],
        KNeighborsClassifier(n_neighbors=knn_k, weights="distance",
                              metric="euclidean", n_jobs=-1),
    ),
    "MLP": (
        ["mlp_model.pkl"],
        MLPClassifier(hidden_layer_sizes=(256, 128, 64), activation="relu",
                       max_iter=500, random_state=42, early_stopping=mlp_early,
                       validation_fraction=0.1, alpha=0.001),
    ),
}

if _CATBOOST_AVAILABLE:
    MODEL_REGISTRY["CatBoost"] = (
        ["catboost_model.pkl"],
        CatBoostClassifier(
            iterations=944, learning_rate=0.28180829608089975,
            depth=10, l2_leaf_reg=7.173375161810935,
            random_seed=42, verbose=0,
        ),
    )

# ──────────────────────────────────────────────────────────────────────────────
# 4. Load from disk or train fresh
# ──────────────────────────────────────────────────────────────────────────────
print("\n[LOAD] Loading / training models …")
loaded_models  = {}
was_trained    = {}

for name, (filenames, fallback) in MODEL_REGISTRY.items():
    model = None
    for fn in filenames:
        path = os.path.join(_MODEL_DIR, fn)
        if os.path.exists(path):
            try:
                model = joblib.load(path)
                break
            except Exception:
                pass
    if model is not None:
        print(f"  [OK]   Loaded  : {name}")
        was_trained[name] = False
    else:
        print(f"  [NEW]  Training: {name} …", end="", flush=True)
        t0 = time.time()
        fallback.fit(X_train, y_train)
        elapsed = time.time() - t0
        model = fallback
        save_path = os.path.join(_MODEL_DIR, filenames[0])
        joblib.dump(model, save_path)
        if name == "SVM_RBF":
            joblib.dump(model, os.path.join(_MODEL_DIR, "svm_model.pkl"))
        print(f" done ({elapsed:.1f}s)")
        was_trained[name] = True
    loaded_models[name] = model

# ──────────────────────────────────────────────────────────────────────────────
# 5. Evaluate every model
# ──────────────────────────────────────────────────────────────────────────────
print("\n[EVAL] Evaluating all models (CV + test set) …")
results = {}

for name, model in loaded_models.items():
    t0 = time.time()
    cv_scores = cross_val_score(model, X_scaled, y, cv=cv, scoring="accuracy")
    cv_time   = time.time() - t0

    y_pred   = model.predict(X_test)
    test_acc = accuracy_score(y_test, y_pred)
    cm       = confusion_matrix(y_test, y_pred)
    report   = classification_report(y_test, y_pred, output_dict=True,
                                      target_names=["Real", "Fake"])

    # Probabilities for ROC / PR
    try:
        if hasattr(model, "predict_proba"):
            y_prob = model.predict_proba(X_test)[:, 1]
        elif hasattr(model, "decision_function"):
            df     = model.decision_function(X_test)
            y_prob = 1 / (1 + np.exp(-df))
        else:
            y_prob = y_pred.astype(float)
        auc      = roc_auc_score(y_test, y_prob)
        fpr, tpr, _ = roc_curve(y_test, y_prob)
        prec_c, rec_c, _ = precision_recall_curve(y_test, y_prob)
        avg_prec = average_precision_score(y_test, y_prob)
    except Exception:
        y_prob   = y_pred.astype(float)
        auc      = 0.0
        fpr, tpr = np.array([0.0, 1.0]), np.array([0.0, 1.0])
        prec_c   = np.array([1.0, 0.0])
        rec_c    = np.array([0.0, 1.0])
        avg_prec = 0.0

    fake_report = report.get("Fake", {"f1-score": 0, "precision": 0, "recall": 0})
    results[name] = {
        "cv_mean":         float(cv_scores.mean()),
        "cv_std":          float(cv_scores.std()),
        "cv_scores":       cv_scores.tolist(),
        "test_accuracy":   float(test_acc),
        "f1_weighted":     float(report["weighted avg"]["f1-score"]),
        "f1_fake":         float(fake_report["f1-score"]),
        "precision_fake":  float(fake_report["precision"]),
        "recall_fake":     float(fake_report["recall"]),
        "f1_real":         float(report.get("Real", {}).get("f1-score", 0)),
        "auc":             float(auc),
        "avg_precision":   float(avg_prec),
        "confusion_matrix": cm,
        "report":          report,
        # curve data (numpy arrays — removed before JSON serialisation)
        "_y_prob": y_prob,
        "_fpr":    fpr,
        "_tpr":    tpr,
        "_prec":   prec_c,
        "_rec":    rec_c,
    }
    print(f"  {name:<22}  CV={cv_scores.mean():.2%}  Test={test_acc:.2%}  AUC={auc:.4f}")

# ──────────────────────────────────────────────────────────────────────────────
# 6. Console report — clear percentages + fake-detection leaderboard
# ──────────────────────────────────────────────────────────────────────────────

def _bar(value: float, width: int = 20) -> str:
    """Text progress bar from 0-1."""
    filled = int(round(value * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"

def _verdict(acc: float) -> str:
    if acc >= 0.95: return "Excellent"
    if acc >= 0.85: return "Good     "
    if acc >= 0.75: return "Fair     "
    return                  "Weak     "

sorted_results = sorted(results.items(),
                         key=lambda x: x[1]["test_accuracy"], reverse=True)
sorted_fake    = sorted(results.items(),
                         key=lambda x: x[1]["recall_fake"],   reverse=True)
ranks      = {name: rank for rank, (name, _) in enumerate(sorted_results, 1)}
ranks_fake = {name: rank for rank, (name, _) in enumerate(sorted_fake,    1)}

D = "=" * 110

# ── Table 1: overall accuracy ─────────────────────────────────────────────────
print(f"\n{D}")
print(f"  RANKING BY OVERALL ACCURACY")
print(D)
print(f"  {'#':<3} {'Model':<22} {'Test Accuracy':>14} {'CV Accuracy':>13} "
      f"{'AUC-ROC':>9} {'Fake F1':>8} {'Verdict'}")
print(f"  {'-'*105}")

for rank, (name, r) in enumerate(sorted_results, 1):
    acc  = r["test_accuracy"]
    star = " <-- BEST" if rank == 1 else (" <-- 2nd" if rank == 2 else "")
    print(f"  {rank:<3} {name:<22} "
          f"{acc:>7.2%}  {_bar(acc)}  "
          f"{r['cv_mean']:>7.2%} ±{r['cv_std']:>5.2%}  "
          f"{r['auc']:>8.4f}  "
          f"{r['f1_fake']:>7.4f}  "
          f"{_verdict(acc)}{star}")

print(D)

# ── Table 2: FAKE DETECTION performance ───────────────────────────────────────
print(f"\n{D}")
print(f"  RANKING BY FAKE VOICE DETECTION  (most important for security)")
print(f"  Fake Recall = % of real fake voices the model successfully caught")
print(D)
print(f"  {'#':<3} {'Model':<22} {'Fake Recall':>12} {'Fake Precision':>15} "
      f"{'Fake F1':>8} {'Missed Fakes':>13} {'False Alarms':>13}")
print(f"  {'-'*105}")

for rank, (name, r) in enumerate(sorted_fake, 1):
    cm_   = r["confusion_matrix"]
    fn_   = int(cm_[1, 0])   # Fake predicted as Real (missed!)
    fp_   = int(cm_[0, 1])   # Real predicted as Fake (false alarm)
    star  = " <-- BEST" if rank == 1 else (" <-- 2nd" if rank == 2 else "")
    print(f"  {rank:<3} {name:<22} "
          f"{r['recall_fake']:>7.2%}  {_bar(r['recall_fake'])}  "
          f"{r['precision_fake']:>9.2%}         "
          f"{r['f1_fake']:>7.4f}  "
          f"{fn_:>6} fakes missed  "
          f"{fp_:>6} false alarms{star}")

print(D)

# ── Winner summary ─────────────────────────────────────────────────────────────
best_name,  best_r  = sorted_results[0]
bfake_name, bfake_r = sorted_fake[0]

print(f"\n  OVERALL WINNER   : {best_name}")
print(f"    Test Accuracy  : {best_r['test_accuracy']:.2%}")
print(f"    CV  Accuracy   : {best_r['cv_mean']:.2%} ± {best_r['cv_std']:.2%}")
print(f"    AUC-ROC        : {best_r['auc']:.4f}")
print(f"    Fake Detection : catches {best_r['recall_fake']:.2%} of fake voices")
cm_ = best_r["confusion_matrix"]
tn_, fp_, fn_, tp_ = cm_[0,0], cm_[0,1], cm_[1,0], cm_[1,1]
print(f"    Confusion      : TN={tn_} FP={fp_} / FN={fn_} TP={tp_}")

if bfake_name != best_name:
    print(f"\n  BEST FAKE-CATCHER: {bfake_name}")
    print(f"    Fake Recall    : {bfake_r['recall_fake']:.2%}  "
          f"(catches more AI-generated voices)")
    print(f"    Fake Precision : {bfake_r['precision_fake']:.2%}")
    cm2 = bfake_r["confusion_matrix"]
    print(f"    Confusion      : TN={cm2[0,0]} FP={cm2[0,1]} / "
          f"FN={cm2[1,0]} TP={cm2[1,1]}")
    print(f"\n  TIP: If AI voices are slipping through as REAL,")
    print(f"       use {bfake_name} or lower the fake_threshold in deepfake_checker.py")
    print(f"       Current threshold in checker: 25% (FAKE_THRESHOLD = 0.25)")

print()

# ──────────────────────────────────────────────────────────────────────────────
# 7. Plot 1 — Bar chart: 4 key metrics
# ──────────────────────────────────────────────────────────────────────────────
names  = list(results.keys())
names_short = [n.replace("_", "\n") for n in names]
CMAP   = plt.cm.viridis(np.linspace(0.15, 0.85, len(names)))

fig, axes = plt.subplots(2, 2, figsize=(18, 12))
fig.suptitle("Deepfake Voice Detection — Model Comparison", fontsize=17,
             fontweight="bold", y=0.99)

metric_plot = [
    ("test_accuracy", "Test Accuracy",          axes[0, 0]),
    ("cv_mean",       "Cross-Val Accuracy",      axes[0, 1]),
    ("auc",           "AUC-ROC Score",           axes[1, 0]),
    ("f1_fake",       "F1-Score (Fake class)",   axes[1, 1]),
]

for key, title, ax in metric_plot:
    vals = [results[n][key] for n in names]
    bars = ax.bar(names_short, vals, color=CMAP, edgecolor="black", linewidth=0.4)
    ax.set_title(title, fontsize=12, fontweight="bold")
    lo = max(0, min(vals) - 0.05)
    ax.set_ylim(lo, 1.0)
    ax.set_ylabel("Score", fontsize=10)
    ax.tick_params(axis="x", labelsize=7)
    ax.grid(axis="y", alpha=0.3)
    best_idx = int(np.argmax(vals))
    for bi, (bar, val) in enumerate(zip(bars, vals)):
        edge_w  = 2.5 if bi == best_idx else 0.4
        edge_c  = "red" if bi == best_idx else "black"
        bar.set_edgecolor(edge_c)
        bar.set_linewidth(edge_w)
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.003,
                f"{val:.3f}", ha="center", va="bottom",
                fontsize=7, fontweight="bold")

plt.tight_layout()
p1 = os.path.join(_ANALYSIS_DIR, "01_model_comparison.png")
plt.savefig(p1, dpi=150, bbox_inches="tight")
plt.close()
print(f"[PLOT] Saved: analysis/01_model_comparison.png")

# ──────────────────────────────────────────────────────────────────────────────
# 8. Plot 2 — ROC & Precision-Recall curves
# ──────────────────────────────────────────────────────────────────────────────
CMAP_ROC = plt.cm.tab10(np.linspace(0, 1, len(names)))
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(17, 7))
fig.suptitle("ROC and Precision-Recall Curves", fontsize=15, fontweight="bold")

for i, name in enumerate(names):
    r = results[name]
    ax1.plot(r["_fpr"], r["_tpr"], lw=2, color=CMAP_ROC[i],
             label=f"{name}  (AUC={r['auc']:.3f})")
ax1.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.5, label="Random (AUC=0.500)")
ax1.set_title("ROC Curves — All Models", fontsize=13, fontweight="bold")
ax1.set_xlabel("False Positive Rate", fontsize=11)
ax1.set_ylabel("True Positive Rate",  fontsize=11)
ax1.legend(fontsize=8, loc="lower right")
ax1.grid(alpha=0.25)

for i, name in enumerate(names):
    r = results[name]
    ax2.plot(r["_rec"], r["_prec"], lw=2, color=CMAP_ROC[i],
             label=f"{name}  (AP={r['avg_precision']:.3f})")
ax2.set_title("Precision-Recall Curves — All Models", fontsize=13, fontweight="bold")
ax2.set_xlabel("Recall",    fontsize=11)
ax2.set_ylabel("Precision", fontsize=11)
ax2.legend(fontsize=8, loc="lower left")
ax2.grid(alpha=0.25)

plt.tight_layout()
p2 = os.path.join(_ANALYSIS_DIR, "02_roc_pr_curves.png")
plt.savefig(p2, dpi=150, bbox_inches="tight")
plt.close()
print(f"[PLOT] Saved: analysis/02_roc_pr_curves.png")

# ──────────────────────────────────────────────────────────────────────────────
# 9. Plot 3 — Confusion matrices (one per model)
# ──────────────────────────────────────────────────────────────────────────────
n_models = len(names)
ncols = 3
nrows = (n_models + ncols - 1) // ncols
fig, axes_grid = plt.subplots(nrows, ncols, figsize=(5.5 * ncols, 4.5 * nrows))
fig.suptitle("Confusion Matrices — All Models", fontsize=16, fontweight="bold")
flat = axes_grid.flatten() if nrows * ncols > 1 else [axes_grid]

for i, name in enumerate(names):
    r  = results[name]
    cm = r["confusion_matrix"]
    ax = flat[i]
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
    ax.set_xticklabels(["Real", "Fake"])
    ax.set_yticklabels(["Real", "Fake"])
    ax.set_xlabel("Predicted");  ax.set_ylabel("Actual")
    rank_tag = f" (#{ranks[name]})" if ranks[name] <= 3 else ""
    ax.set_title(f"{name}{rank_tag}\nAcc={r['test_accuracy']:.2%}  AUC={r['auc']:.4f}",
                  fontsize=10, fontweight="bold")
    thresh = cm.max() / 2
    for ii in range(2):
        for jj in range(2):
            ax.text(jj, ii, cm[ii, jj], ha="center", va="center", fontsize=18,
                    color="white" if cm[ii, jj] > thresh else "black")
    plt.colorbar(im, ax=ax, fraction=0.046)

for i in range(n_models, len(flat)):
    flat[i].set_visible(False)

plt.tight_layout()
p3 = os.path.join(_ANALYSIS_DIR, "03_confusion_matrices.png")
plt.savefig(p3, dpi=150, bbox_inches="tight")
plt.close()
print(f"[PLOT] Saved: analysis/03_confusion_matrices.png")

# ──────────────────────────────────────────────────────────────────────────────
# 10. Plot 4 — Multi-metric grouped bar chart
# ──────────────────────────────────────────────────────────────────────────────
metric_keys   = ["test_accuracy", "cv_mean", "auc", "f1_weighted", "f1_fake", "recall_fake"]
metric_labels = ["Test Acc", "CV Acc", "AUC-ROC", "F1 Weighted", "F1 Fake", "Recall Fake"]
x     = np.arange(len(metric_labels))
width = 0.08
CMAP2 = plt.cm.Set2(np.linspace(0, 1, len(names)))

fig, ax = plt.subplots(figsize=(15, 7))
for i, name in enumerate(names):
    r      = results[name]
    vals   = [r[k] for k in metric_keys]
    offset = (i - len(names) / 2) * width + width / 2
    ax.bar(x + offset, vals, width, label=name, color=CMAP2[i], alpha=0.88)

ax.set_xticks(x)
ax.set_xticklabels(metric_labels, fontsize=11)
ax.set_ylim(0, 1.08)
ax.set_ylabel("Score", fontsize=12)
ax.set_title("All Models — Multi-Metric Summary", fontsize=14, fontweight="bold")
ax.axhline(0.9,  color="red",    linestyle="--", alpha=0.35, linewidth=1.2, label="90% line")
ax.axhline(0.75, color="orange", linestyle="--", alpha=0.35, linewidth=1.2, label="75% line")
ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left", fontsize=8)
ax.grid(axis="y", alpha=0.25)

plt.tight_layout()
p4 = os.path.join(_ANALYSIS_DIR, "04_summary_chart.png")
plt.savefig(p4, dpi=150, bbox_inches="tight")
plt.close()
print(f"[PLOT] Saved: analysis/04_summary_chart.png")

# ──────────────────────────────────────────────────────────────────────────────
# 11. Plot 5 — Accuracy vs AUC scatter
# ──────────────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 7))
for i, name in enumerate(names):
    r = results[name]
    ax.scatter(r["test_accuracy"], r["auc"], s=200, color=CMAP_ROC[i],
               zorder=3, edgecolors="black", linewidths=0.8)
    ax.annotate(name, (r["test_accuracy"], r["auc"]),
                textcoords="offset points", xytext=(6, 4), fontsize=8)
ax.set_xlabel("Test Accuracy", fontsize=12)
ax.set_ylabel("AUC-ROC",       fontsize=12)
ax.set_title("Test Accuracy vs AUC-ROC — All Models", fontsize=13, fontweight="bold")
ax.grid(alpha=0.3)
ax.axhline(0.9, color="red",    linestyle="--", alpha=0.3)
ax.axvline(0.9, color="red",    linestyle="--", alpha=0.3)
plt.tight_layout()
p5 = os.path.join(_ANALYSIS_DIR, "05_accuracy_vs_auc.png")
plt.savefig(p5, dpi=150, bbox_inches="tight")
plt.close()
print(f"[PLOT] Saved: analysis/05_accuracy_vs_auc.png")

# ──────────────────────────────────────────────────────────────────────────────
# 12. Text report
# ──────────────────────────────────────────────────────────────────────────────
report_path = os.path.join(_ANALYSIS_DIR, "analysis_report.txt")
with open(report_path, "w", encoding="utf-8") as fh:
    fh.write("DEEPFAKE VOICE DETECTION — MODEL ANALYSIS REPORT\n")
    fh.write("=" * 80 + "\n\n")
    fh.write(f"Dataset      : {len(y)} samples\n")
    fh.write(f"Real samples : {np.sum(y==0)}\n")
    fh.write(f"Fake samples : {np.sum(y==1)}\n")
    fh.write(f"Features     : {X.shape[1]} dimensions\n")
    fh.write(f"Train split  : {len(y_train)} samples\n")
    fh.write(f"Test split   : {len(y_test)} samples\n")
    fh.write(f"CV strategy  : {n_splits}-fold Stratified K-Fold\n\n")

    fh.write("RANKING BY OVERALL ACCURACY\n")
    fh.write("-" * 90 + "\n")
    fh.write(f"{'#':<4} {'Model':<22} {'CV Acc':>9} {'±Std':>7} "
             f"{'Test Acc':>10} {'AUC':>9} {'F1-Fake':>9} "
             f"{'Recall%':>9} {'Precision%':>11} {'Verdict'}\n")
    fh.write("-" * 90 + "\n")
    for rank, (name, r) in enumerate(sorted_results, 1):
        fh.write(f"#{rank:<3} {name:<22} {r['cv_mean']:>8.2%}  {r['cv_std']:>6.2%}  "
                 f"{r['test_accuracy']:>9.2%}  {r['auc']:>8.4f}  "
                 f"{r['f1_fake']:>8.4f}  {r['recall_fake']:>8.2%}  "
                 f"{r['precision_fake']:>10.2%}  {_verdict(r['test_accuracy'])}\n")
    fh.write("\n")

    fh.write("RANKING BY FAKE DETECTION (Recall on Fake class)\n")
    fh.write("-" * 90 + "\n")
    fh.write(f"{'#':<4} {'Model':<22} {'Fake Recall%':>13} {'Fake Prec%':>11} "
             f"{'Fake F1':>8} {'Missed Fakes':>13} {'False Alarms':>13}\n")
    fh.write("-" * 90 + "\n")
    for rank, (name, r) in enumerate(sorted_fake, 1):
        cm_  = r["confusion_matrix"]
        fn_  = int(cm_[1, 0])
        fp__ = int(cm_[0, 1])
        fh.write(f"#{rank:<3} {name:<22} {r['recall_fake']:>12.2%}  "
                 f"{r['precision_fake']:>10.2%}  {r['f1_fake']:>7.4f}  "
                 f"{fn_:>12}  {fp__:>12}\n")
    fh.write("\n")

    fh.write("DETAILED PER-MODEL RESULTS\n")
    fh.write("=" * 80 + "\n\n")
    for name, r in results.items():
        cm_t = r["confusion_matrix"]
        tn2, fp2, fn2, tp2 = cm_t[0,0], cm_t[0,1], cm_t[1,0], cm_t[1,1]
        fh.write(f"MODEL: {name}  (Overall Rank #{ranks[name]}  |  Fake-Detection Rank #{ranks_fake[name]})\n")
        fh.write("-" * 50 + "\n")
        fh.write(f"  CV Accuracy      : {r['cv_mean']:.2%} ± {r['cv_std']:.2%}\n")
        fh.write(f"  CV Fold Scores   : {[f'{s:.2%}' for s in r['cv_scores']]}\n")
        fh.write(f"  Test Accuracy    : {r['test_accuracy']:.2%}\n")
        fh.write(f"  AUC-ROC          : {r['auc']:.4f}\n")
        fh.write(f"  Avg Precision    : {r['avg_precision']:.4f}\n")
        fh.write(f"  F1 (weighted)    : {r['f1_weighted']:.4f}\n")
        fh.write(f"  F1 (Fake class)  : {r['f1_fake']:.4f}\n")
        fh.write(f"  F1 (Real class)  : {r['f1_real']:.4f}\n")
        fh.write(f"  Recall  (Fake)   : {r['recall_fake']:.2%}  "
                 f"← catches this % of AI-generated voices\n")
        fh.write(f"  Precision(Fake)  : {r['precision_fake']:.2%}\n")
        fh.write(f"  Confusion Matrix :\n")
        fh.write(f"    TN (Real→Real) : {tn2:>4}  (correctly flagged as real)\n")
        fh.write(f"    FP (Real→Fake) : {fp2:>4}  ← false alarms\n")
        fh.write(f"    FN (Fake→Real) : {fn2:>4}  ← MISSED FAKES (dangerous!)\n")
        fh.write(f"    TP (Fake→Fake) : {tp2:>4}  (correctly caught)\n\n")

    fh.write("BEST MODEL RECOMMENDATION\n")
    fh.write("=" * 80 + "\n")
    fh.write(f"  Best Overall    : {best_name}  ({best_r['test_accuracy']:.2%} accuracy)\n")
    fh.write(f"  Best Fake Catcher: {bfake_name}  "
             f"({bfake_r['recall_fake']:.2%} fake recall)\n")
    fh.write(f"  AUC-ROC         : {best_r['auc']:.4f}\n")
    fh.write(f"  NOTE: If AI voices slip through as REAL, lower\n")
    fh.write(f"        FAKE_THRESHOLD in deepfake_checker.py (currently 0.25 = 25%)\n\n")

    fh.write("OUTPUT FILES\n")
    fh.write("-" * 40 + "\n")
    fh.write("  analysis/01_model_comparison.png  — accuracy/AUC bar charts\n")
    fh.write("  analysis/02_roc_pr_curves.png      — ROC and PR curves\n")
    fh.write("  analysis/03_confusion_matrices.png — all confusion matrices\n")
    fh.write("  analysis/04_summary_chart.png      — multi-metric grouped bars\n")
    fh.write("  analysis/05_accuracy_vs_auc.png    — scatter accuracy vs AUC\n")
    fh.write("  analysis/analysis_report.txt       — this report\n")
    fh.write("  model/model_results.json           — machine-readable results\n")

print(f"[REPORT] Saved: analysis/analysis_report.txt")

# ──────────────────────────────────────────────────────────────────────────────
# 13. JSON results (no numpy arrays)
# ──────────────────────────────────────────────────────────────────────────────
json_out = {}
for name, r in results.items():
    json_out[name] = {
        "rank":             ranks[name],
        "rank_fake":        ranks_fake[name],
        "cv_mean":          r["cv_mean"],
        "cv_std":           r["cv_std"],
        "cv_scores":        r["cv_scores"],
        "test_accuracy":    r["test_accuracy"],
        "f1_weighted":      r["f1_weighted"],
        "f1_fake":          r["f1_fake"],
        "precision_fake":   r["precision_fake"],
        "recall_fake":      r["recall_fake"],
        "auc":              r["auc"],
        "avg_precision":    r["avg_precision"],
        "confusion_matrix": r["confusion_matrix"].tolist(),
    }

json_path = os.path.join(_MODEL_DIR, "model_results.json")
with open(json_path, "w") as fh:
    json.dump(json_out, fh, indent=2)
print(f"[JSON]   Saved: model/model_results.json")

print(f"\n{'='*70}")
print(f"  Analysis complete!")
print(f"  Output directory  : {_ANALYSIS_DIR}")
print(f"  Best overall      : {best_name}  ({best_r['test_accuracy']:.2%} accuracy)")
print(f"  Best fake-catcher : {bfake_name}  ({bfake_r['recall_fake']:.2%} fake recall)")
print(f"{'='*70}\n")
