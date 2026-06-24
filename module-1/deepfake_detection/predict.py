import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_TRANSLATE_DIR = os.path.normpath(os.path.join(_HERE, '..', '..', 'translate'))
if _TRANSLATE_DIR not in sys.path:
    sys.path.insert(0, _TRANSLATE_DIR)

from deepfake_checker import predict_ensemble


def predict(audio_path):
    result = predict_ensemble(audio_path)
    if 'error' in result:
        print(f"[ERROR] {result['error']}")
        return

    label      = result['label']
    confidence = result['confidence']
    real_prob  = result['real_prob']
    fake_prob  = result['fake_prob']
    vf         = result['votes_fake']
    vr         = result['votes_real']
    total      = result['models_used']
    marker     = "[!] FAKE" if label == "FAKE" else "[+] REAL"

    print(f"\nFile      : {audio_path}")
    print(f"Result    : {marker}  ({confidence:.2f}% confidence)")
    print(f"  Real probability : {real_prob:.2f}%")
    print(f"  Fake probability : {fake_prob:.2f}%")
    print(f"  Votes            : {vf} FAKE / {vr} REAL ({total} models)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python predict.py <path_to_audio_file>")
        print("Example: python predict.py recordings/my_voice.wav")
    else:
        predict(sys.argv[1])
