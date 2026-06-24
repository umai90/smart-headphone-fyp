import os
import sys
import hashlib
import numpy as np
import librosa
import warnings
from scipy.fft import dct
from joblib import Parallel, delayed
warnings.filterwarnings("ignore")

_HERE     = os.path.dirname(os.path.abspath(__file__))
_FAKE_DIR = os.path.join(_HERE, "data", "fake")
_REAL_DIR = os.path.join(_HERE, "data", "real")

SR     = 16000
N_MFCC = 40

FAKE_AUGMENT_COUNT = 7
REAL_AUGMENT_COUNT = 3


# ── Augmentation helpers ───────────────────────────────────────────────────────

def _add_noise(y, snr_db=15):
    rms_signal = np.sqrt(np.mean(y ** 2))
    if rms_signal == 0:
        return y
    rms_noise = rms_signal / (10 ** (snr_db / 20))
    noise = np.random.randn(len(y)) * rms_noise
    return (y + noise).astype(np.float32)


def _pitch_shift(y, sr, n_steps):
    try:
        return librosa.effects.pitch_shift(y, sr=sr, n_steps=n_steps)
    except Exception:
        return y


def _time_stretch(y, rate):
    try:
        stretched = librosa.effects.time_stretch(y, rate=rate)
        if len(stretched) > len(y):
            return stretched[:len(y)]
        return np.pad(stretched, (0, max(0, len(y) - len(stretched))))
    except Exception:
        return y


def _mic_simulation(y, sr):
    y_noisy = _add_noise(y, snr_db=25)
    delay_samples = int(sr * 0.015)
    if delay_samples < len(y_noisy):
        echo = np.zeros_like(y_noisy)
        echo[delay_samples:] = y_noisy[:-delay_samples] * 0.08
        y_noisy = np.clip(y_noisy + echo, -1.0, 1.0)
    return y_noisy.astype(np.float32)


def get_augmented_variants(y, sr, label):
    variants = []
    if label == 1:
        augments = [
            lambda a: _add_noise(a, snr_db=20),
            lambda a: _add_noise(a, snr_db=12),
            lambda a: _pitch_shift(a, sr, n_steps=1.5),
            lambda a: _pitch_shift(a, sr, n_steps=-1.5),
            lambda a: _time_stretch(a, rate=0.88),
            lambda a: _time_stretch(a, rate=1.12),
            lambda a: _mic_simulation(a, sr),
        ]
        for fn in augments[:FAKE_AUGMENT_COUNT]:
            try:
                aug = fn(y)
                if aug is not None and len(aug) > 0:
                    variants.append(aug)
            except Exception:
                pass
    else:
        for _ in range(REAL_AUGMENT_COUNT):
            try:
                variants.append(_mic_simulation(y, sr))
            except Exception:
                pass
    return variants


# ── Feature extraction ─────────────────────────────────────────────────────────

def extract_features(file_path_or_array, sr_in=None):
    try:
        if isinstance(file_path_or_array, np.ndarray):
            y  = file_path_or_array.astype(np.float32)
            sr = sr_in if sr_in else SR
        else:
            y, sr = librosa.load(file_path_or_array, sr=SR, mono=True)

        if len(y) == 0:
            return None

        mfcc        = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=N_MFCC)
        mfcc_mean   = np.mean(mfcc, axis=1)
        mfcc_std    = np.std(mfcc,  axis=1)
        mfcc_max    = np.max(mfcc,  axis=1)

        chroma      = librosa.feature.chroma_stft(y=y, sr=sr)
        chroma_mean = np.mean(chroma, axis=1)

        zcr_mean     = np.mean(librosa.feature.zero_crossing_rate(y))
        _rms         = librosa.feature.rms(y=y)
        rms_mean     = float(np.mean(_rms))
        rolloff_mean = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))

        pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
        pitch_vals = pitches[magnitudes > np.median(magnitudes)]
        pitch_mean = float(np.mean(pitch_vals)) if len(pitch_vals) > 0 else 0.0
        pitch_std  = float(np.std(pitch_vals))  if len(pitch_vals) > 0 else 0.0

        bandwidth_mean = float(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr)))

        tonnetz      = librosa.feature.tonnetz(y=librosa.effects.harmonic(y), sr=sr)
        tonnetz_mean = np.mean(tonnetz, axis=1)

        contrast      = librosa.feature.spectral_contrast(y=y, sr=sr)
        contrast_mean = np.mean(contrast, axis=1)

        _n_fft        = 2048
        mel_basis     = librosa.filters.mel(sr=sr, n_fft=_n_fft, n_mels=128)
        mel_basis_inv = mel_basis[::-1, :]
        S             = np.abs(librosa.stft(y, n_fft=_n_fft))
        mel_spec      = np.dot(mel_basis_inv, S)
        log_mel       = np.log(mel_spec + 1e-9)
        imfccs        = dct(log_mel, axis=0, norm="ortho")[:13]
        imfcc_mean    = np.mean(imfccs, axis=1)

        # Delta MFCC — rate of change of spectral shape over time.
        # AI voices have unnaturally smooth frame-to-frame transitions.
        try:
            _mfcc_delta    = librosa.feature.delta(mfcc)
            mfcc_delta_mean = np.mean(_mfcc_delta, axis=1)
        except Exception:
            mfcc_delta_mean = np.zeros(N_MFCC)

        # Jitter — mean absolute F0 period-to-period variation.
        # AI/TTS voices tend to have near-zero jitter (unnaturally stable pitch).
        jitter = (float(np.mean(np.abs(np.diff(pitch_vals))))
                  if len(pitch_vals) > 1 else 0.0)

        # Shimmer — mean absolute frame-to-frame RMS amplitude variation.
        # AI voices tend to have too-flat amplitude envelopes.
        shimmer = (float(np.mean(np.abs(np.diff(_rms[0]))))
                   if _rms.shape[1] > 1 else 0.0)

        return np.concatenate([
            mfcc_mean, mfcc_std, mfcc_max,       # 120
            chroma_mean,                           # 12
            [zcr_mean, rms_mean, rolloff_mean],   # 3
            [pitch_mean, pitch_std],               # 2
            [bandwidth_mean],                      # 1
            tonnetz_mean,                          # 6
            contrast_mean,                         # 7
            imfcc_mean,                            # 13
            mfcc_delta_mean,                       # 40  ← new
            [jitter, shimmer],                     # 2   ← new
        ])
        # Total: 206 dimensions

    except Exception as e:
        print(f"  [ERROR] Feature extraction failed: {e}")
        return None


# ── Parallel worker (one file → list of (feats, label, name)) ─────────────────

def _process_file_parallel(file_path, label, tag):
    results = []
    try:
        audio, sr = librosa.load(file_path, sr=SR, mono=True)
    except Exception as e:
        print(f"  [SKIP] {os.path.basename(file_path)}: {e}")
        return results

    if len(audio) == 0:
        return results

    feats = extract_features(audio, sr)
    if feats is not None:
        results.append((feats, label, tag))
        lbl = "REAL" if label == 0 else "FAKE"
        print(f"  [{lbl}] {os.path.basename(file_path)}", flush=True)

    for i, aug_audio in enumerate(get_augmented_variants(audio, sr, label)):
        feats = extract_features(aug_audio, sr)
        if feats is not None:
            results.append((feats, label, f"{tag}_aug{i+1}"))

    return results


# Legacy single-file helper kept for backward compatibility with train_multi_model.py
def _process_file(file_path, label, tag, X, y_list, file_names):
    for feats, lbl, name in _process_file_parallel(file_path, label, tag):
        X.append(feats)
        y_list.append(lbl)
        file_names.append(name)


# ── Dataset loader (parallel) ──────────────────────────────────────────────────

def load_dataset():
    """
    Loads audio from two flat folders in parallel across all CPU cores:
        deepfake_detection/data/fake/  → label 1 (FAKE)
        deepfake_detection/data/real/  → label 0 (REAL)
    """
    AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mpeg"}

    # Build full file list
    tasks = []
    for folder_path, label, tag_prefix in [
        (_FAKE_DIR, 1, "Fake"),
        (_REAL_DIR, 0, "Real"),
    ]:
        if not os.path.isdir(folder_path):
            print(f"  [WARN] Folder not found: {folder_path}")
            continue

        seen_hashes = set()
        for file in sorted(os.listdir(folder_path)):
            ext = os.path.splitext(file)[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                continue
            fp  = os.path.join(folder_path, file)
            try:
                md5 = hashlib.md5(open(fp, "rb").read(65536)).hexdigest()
            except Exception:
                continue
            if md5 in seen_hashes:
                print(f"  [SKIP duplicate] {file}")
                continue
            seen_hashes.add(md5)
            tasks.append((fp, label, f"{tag_prefix}/{file}"))

    n_cores = os.cpu_count() or 1
    print(f"  Processing {len(tasks)} files using {n_cores} CPU cores in parallel …")

    # Run all files in parallel
    all_results = Parallel(n_jobs=-1, backend="loky", verbose=0)(
        delayed(_process_file_parallel)(fp, label, tag)
        for fp, label, tag in tasks
    )

    # Flatten
    X, y_list, file_names = [], [], []
    for file_results in all_results:
        for feats, label, name in file_results:
            X.append(feats)
            y_list.append(label)
            file_names.append(name)

    return np.array(X), np.array(y_list), file_names


if __name__ == "__main__":
    import time
    print(f"Extracting features from all datasets using all CPU cores …\n")
    t0 = time.time()
    X, y, names = load_dataset()

    if len(y) == 0:
        print("\n[ERROR] No audio files found. Check your folder paths.")
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"\n{'='*50}")
    print(f"Total samples : {len(y)}")
    print(f"Real  (0)     : {int(np.sum(y == 0))}")
    print(f"Fake  (1)     : {int(np.sum(y == 1))}")
    print(f"Feature dims  : {X.shape[1]}")
    print(f"Time taken    : {elapsed/60:.1f} minutes")
    print(f"{'='*50}")

    np.save(os.path.join(_HERE, "X_features.npy"), X)
    np.save(os.path.join(_HERE, "y_labels.npy"),   y)
    print(f"\nSaved -> X_features.npy  |  y_labels.npy")
