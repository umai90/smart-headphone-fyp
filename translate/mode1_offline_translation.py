"""
MODE 1 - OFFLINE TRANSLATION
Smart Headphone Translation System
------------------------------------------------------------
100% Offline — No internet needed after first setup
Languages : English <-> Urdu
STT       : vosk (English), faster-whisper (Urdu, CPU-only)
Translate : argostranslate (offline neural)
TTS       : espeak-ng (Urdu), pyttsx3 (English)
"""

import sys
import os
import json
import wave
import socket
import tempfile
import subprocess
import queue as _queue
from collections import deque
import numpy as np
import sounddevice as sd

# ─── webrtcvad ───────────────────────────────────────────────────────────────
try:
    import webrtcvad as _webrtcvad
    WEBRTCVAD_AVAILABLE = True
    print("[OK] webrtcvad loaded — VAD auto-stop enabled")
except ImportError:
    WEBRTCVAD_AVAILABLE = False
    print("[WARNING] webrtcvad not installed — fixed-duration recording. Run: pip install webrtcvad")

# Suppress Vosk's verbose LOG lines in the terminal
os.environ.setdefault("VOSK_LOG_LEVEL", "-1")

# Force argostranslate to use its lightweight MINISBD sentence-splitter instead
# of stanza. Deployments that install argostranslate+stanza with --no-deps
# (e.g. lcd_ui/setup_pi.sh, to avoid pulling in torch on ARM64) end up with a
# stanza that can't actually import (it hard-requires torch), which makes
# argostranslate's sentence-boundary-detection silently fail with
# "'NoneType' object has no attribute 'Pipeline'" and fall back to the tiny
# ~65-phrase hardcoded dictionary for every translation. MINISBD is already an
# installed argostranslate dependency and doesn't need stanza/torch at all.
os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")

# Fix Windows console so Urdu characters don't crash the output
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf-8-sig'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── Vosk ────────────────────────────────────────────────────────────────────
try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
    print("[OK] vosk loaded")
except ImportError:
    VOSK_AVAILABLE = False
    print("[WARNING] vosk not installed. Run: py -m pip install vosk")

# ─── Whisper (faster-whisper — CPU-friendly, no torch/CUDA) ──────────────────
try:
    from faster_whisper import WhisperModel as _FasterWhisperModel
    WHISPER_AVAILABLE = True
    print("[OK] faster-whisper loaded")
except ImportError:
    WHISPER_AVAILABLE = False
    print("[WARNING] faster-whisper not installed. Run: pip install faster-whisper")

# ─── Argos Translate ─────────────────────────────────────────────────────────
try:
    import argostranslate.package
    import argostranslate.translate
    ARGOS_AVAILABLE = True
    print("[OK] argostranslate loaded")
except ImportError:
    ARGOS_AVAILABLE = False
    print("[WARNING] argostranslate not installed. Run: py -m pip install argostranslate")

# ─── pyttsx3 ─────────────────────────────────────────────────────────────────
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
    print("[OK] pyttsx3 loaded")
except ImportError:
    PYTTSX3_AVAILABLE = False
    print("[WARNING] pyttsx3 not installed. Run: py -m pip install pyttsx3")

# ─── espeak-ng path ──────────────────────────────────────────────────────────
_ESPEAK_BIN = None
for _candidate in [
    "espeak-ng",
    r"C:\Program Files\eSpeak NG\espeak-ng.exe",
    r"C:\Program Files (x86)\eSpeak NG\espeak-ng.exe",
]:
    try:
        subprocess.run([_candidate, "--version"], capture_output=True, check=True)
        _ESPEAK_BIN = _candidate
        print(f"[OK] espeak-ng found: {_candidate}")
        break
    except (FileNotFoundError, subprocess.CalledProcessError):
        continue

if not _ESPEAK_BIN:
    print("[WARNING] espeak-ng not found. Urdu TTS will use pyttsx3.")

# ─── Fallback Dictionary ─────────────────────────────────────────────────────
EN_TO_UR = {
    "hello": "ہیلو",
    "hi": "ہائے",
    "how are you": "آپ کیسے ہیں",
    "good morning": "صبح بخیر",
    "good night": "شب بخیر",
    "good evening": "شام بخیر",
    "goodbye": "خدا حافظ",
    "thank you": "شکریہ",
    "thank you very much": "بہت بہت شکریہ",
    "yes": "ہاں",
    "no": "نہیں",
    "okay": "ٹھیک ہے",
    "please": "براہ کرم",
    "sorry": "معاف کریں",
    "excuse me": "معاف کیجیے",
    "you are welcome": "کوئی بات نہیں",
    "my name is": "میرا نام ہے",
    "what is your name": "آپ کا نام کیا ہے",
    "i am fine": "میں ٹھیک ہوں",
    "i am good": "میں اچھا ہوں",
    "i am hungry": "مجھے بھوک لگی ہے",
    "i am thirsty": "مجھے پیاس لگی ہے",
    "i am sick": "میں بیمار ہوں",
    "i need help": "مجھے مدد چاہیے",
    "i need water": "مجھے پانی چاہیے",
    "i need a doctor": "مجھے ڈاکٹر چاہیے",
    "i don't understand": "میں سمجھا نہیں",
    "i don't know": "مجھے نہیں معلوم",
    "water": "پانی",
    "food": "کھانا",
    "help": "مدد",
    "where": "کہاں",
    "what": "کیا",
    "when": "کب",
    "how much": "کتنا",
    "stop": "رکو",
    "go": "جاؤ",
    "come": "آؤ",
    "wait": "انتظار کرو",
    "good": "اچھا",
    "bad": "برا",
    "open": "کھولو",
    "close": "بند کرو",
    "left": "بائیں",
    "right": "دائیں",
    "fire": "آگ",
    "police": "پولیس",
    "ambulance": "ایمبولینس",
    "emergency": "ایمرجنسی",
    "danger": "خطرہ",
    "where is the hospital": "ہسپتال کہاں ہے",
    "call the police": "پولیس کو بلاؤ",
    "call a doctor": "ڈاکٹر کو بلاؤ",
    "turn left": "بائیں مڑو",
    "turn right": "دائیں مڑو",
    "go straight": "سیدھے جاؤ",
    "stop here": "یہاں رکو",
    "today": "آج",
    "tomorrow": "کل",
    "now": "ابھی",
    "morning": "صبح",
    "evening": "شام",
    "night": "رات",
}
UR_TO_EN = {v: k for k, v in EN_TO_UR.items()}


# ═════════════════════════════════════════
#  SAFE PRINT (handles Urdu on Windows)
# ═════════════════════════════════════════

def safe_print(msg):
    """Print that never crashes on Windows cp1252 console."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('utf-8', errors='replace').decode('ascii', errors='replace'))


# ═════════════════════════════════════════
#  ARGOS TRANSLATE SETUP
# ═════════════════════════════════════════

_argos_cache = {}

def _argos_installed(from_code, to_code):
    key = (from_code, to_code)
    if key in _argos_cache:
        return _argos_cache[key]
    if not ARGOS_AVAILABLE:
        _argos_cache[key] = False
        return False
    try:
        installed = argostranslate.translate.get_installed_languages()
        from_lang = next((l for l in installed if l.code == from_code), None)
        to_lang   = next((l for l in installed if l.code == to_code),   None)
        if not from_lang or not to_lang:
            _argos_cache[key] = False
            return False
        result = from_lang.get_translation(to_lang) is not None
        _argos_cache[key] = result
        return result
    except Exception:
        _argos_cache[key] = False
        return False


def setup_offline_translation():
    """Download argostranslate en<->ur packages. Needs internet ONCE."""
    if not ARGOS_AVAILABLE:
        print("[SETUP] argostranslate not installed.")
        return False

    success = True
    pairs = [("en", "ur"), ("ur", "en")]
    for from_code, to_code in pairs:
        if _argos_installed(from_code, to_code):
            print(f"[SETUP] {from_code}->{to_code} already installed.")
            continue
        print(f"[SETUP] Downloading {from_code}->{to_code} package...")
        try:
            argostranslate.package.update_package_index()
            available = argostranslate.package.get_available_packages()
            pkg = next(
                (p for p in available if p.from_code == from_code and p.to_code == to_code),
                None
            )
            if not pkg:
                print(f"[SETUP ERROR] Package {from_code}->{to_code} not found.")
                success = False
                continue
            path = pkg.download()
            argostranslate.package.install_from_path(path)
            _argos_cache.clear()
            print(f"[SETUP] {from_code}->{to_code} installed successfully.")
        except Exception as e:
            print(f"[SETUP ERROR] {e}")
            success = False

    # Also download faster-whisper model if not cached (needed for Urdu STT offline)
    if WHISPER_AVAILABLE:
        if not _whisper_model_cached():
            print("[SETUP] Downloading faster-whisper 'small' model (~460 MB, one-time only)...")
            try:
                model = _FasterWhisperModel("small", device="cpu", compute_type="int8")
                _whisper_model_cache["small"] = model
                print("[SETUP] Whisper model downloaded and cached.")
            except Exception as e:
                print(f"[SETUP ERROR] Whisper download failed: {e}")
                success = False
        else:
            print("[SETUP] Whisper model already cached.")
    else:
        print("[SETUP] faster-whisper not installed — skipping Whisper model download.")

    if success:
        print("\n[SETUP DONE] Offline translation ready!")
    else:
        print("\n[SETUP DONE] Completed with some errors — check messages above.")
    return success


def ensure_offline_packages():
    """
    Smart auto-setup for offline translation packages.

    - If packages are already installed  -> returns True instantly (no download).
    - If packages are missing            -> tries to download them (needs internet once).
    - If no internet and packages missing -> warns and returns False.

    Call this at the start of any offline flow so re-runs skip the download entirely.
    """
    if not ARGOS_AVAILABLE:
        print("[OFFLINE] argostranslate not installed. Run: py -m pip install argostranslate")
        return False

    pairs = [("en", "ur"), ("ur", "en")]
    all_ready = all(_argos_installed(f, t) for f, t in pairs)

    if all_ready:
        print("[OFFLINE] Translation packages already installed — skipping download.")
        return True

    # At least one package is missing — need internet to download
    missing = [f"{f}->{t}" for f, t in pairs if not _argos_installed(f, t)]
    print(f"[OFFLINE] Missing packages: {', '.join(missing)}")

    try:
        socket.setdefaulttimeout(3)
        conn = socket.create_connection(("8.8.8.8", 53))
        conn.close()
        has_internet = True
    except OSError:
        has_internet = False
    finally:
        socket.setdefaulttimeout(None)  # restore — otherwise all network calls inherit the 3 s cap

    if not has_internet:
        print("[OFFLINE] No internet — cannot download missing packages.")
        print("[TIP] Connect to the internet once and re-run to download packages.")
        return False

    print("[OFFLINE] First run detected — downloading packages now (one-time only)...")
    return setup_offline_translation()


# ═════════════════════════════════════════
#  TRANSLATION
# ═════════════════════════════════════════

def offline_translate(text, direction="en_to_ur"):
    """Translate using argostranslate, fallback to dictionary."""
    from_code = "en" if direction == "en_to_ur" else "ur"
    to_code   = "ur" if direction == "en_to_ur" else "en"

    # Try argostranslate
    if not ARGOS_AVAILABLE:
        print("[TRANSLATE] argostranslate not installed.")
    elif not _argos_installed(from_code, to_code):
        print(f"[TRANSLATE] Argos pack ({from_code}->{to_code}) not installed.")
        print("[TIP] Run option 6 from main menu to download offline packs.")
    else:
        try:
            result = argostranslate.translate.translate(text, from_code, to_code)
            if result and result.strip():
                return result.strip()
        except Exception as e:
            print(f"[TRANSLATE ERROR] argostranslate: {e}")

    # Fallback to dictionary
    key = text.lower().strip() if direction == "en_to_ur" else text.strip()
    dictionary = EN_TO_UR if direction == "en_to_ur" else UR_TO_EN
    match = dictionary.get(key)
    if match:
        return match
    print(f"[TRANSLATE] No match in dictionary for: {text}")
    return f"[Not translated: {text}]"


# ═════════════════════════════════════════
#  TEXT TO SPEECH
# ═════════════════════════════════════════

def speak_offline(text, lang="en"):
    """
    Fully offline TTS.
    Urdu    -> espeak-ng (writes WAV to temp file, plays with sounddevice)
    English -> pyttsx3
    """
    if not text or text.startswith("[Not"):
        return

    if lang == "ur":
        if _ESPEAK_BIN:
            success = _speak_espeak_wav(text)
            if not success:
                safe_print(f"[TTS] Could not speak Urdu audio. Text: {text}")
        else:
            safe_print(f"[TTS-UR] {text}  (espeak-ng not available for audio)")
    else:
        _speak_pyttsx3(text)


def _speak_espeak_wav(text):
    """
    Generate Urdu speech via espeak-ng into a WAV file, then play it.
    Using a temp file avoids Windows command-line encoding issues.
    """
    tmp_txt  = None
    tmp_wav  = None
    try:
        # Write text to temp UTF-8 file — avoids CLI encoding problems
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', suffix='.txt', delete=False
        ) as f:
            f.write(text)
            tmp_txt = f.name

        # Write speech to WAV file (NamedTemporaryFile avoids mktemp race condition)
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as _f:
            tmp_wav = _f.name
        result = subprocess.run(
            [_ESPEAK_BIN, "-v", "ur", "-s", "130", "-a", "200",
             "-f", tmp_txt, "-w", tmp_wav],
            capture_output=True, timeout=15
        )
        if result.returncode != 0:
            err = result.stderr.decode('utf-8', errors='replace').strip()
            print(f"[ESPEAK ERROR] {err}")
            return False

        if not os.path.exists(tmp_wav) or os.path.getsize(tmp_wav) < 100:
            print("[ESPEAK ERROR] WAV file empty or not created.")
            return False

        # Play the WAV file using sounddevice
        _play_wav(tmp_wav)
        return True

    except subprocess.TimeoutExpired:
        print("[ESPEAK ERROR] Timed out.")
        return False
    except Exception as e:
        print(f"[ESPEAK ERROR] {e}")
        return False
    finally:
        for f in [tmp_txt, tmp_wav]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass


def _play_wav(wav_path):
    """Play a WAV file using sounddevice (no external player needed)."""
    try:
        with wave.open(wav_path, 'rb') as wf:
            samplerate = wf.getframerate()
            channels   = wf.getnchannels()
            sampwidth  = wf.getsampwidth()
            frames     = wf.readframes(wf.getnframes())

        dtype_map = {1: np.uint8, 2: np.int16, 4: np.int32}
        dtype = dtype_map.get(sampwidth, np.int16)
        audio = np.frombuffer(frames, dtype=dtype)
        if channels > 1:
            audio = audio.reshape(-1, channels)

        sd.play(audio, samplerate=samplerate)
        sd.wait()
    except Exception as e:
        print(f"[PLAY ERROR] {e}")


_pyttsx3_engine = None

def _speak_pyttsx3(text):
    """Speak English using pyttsx3 (engine cached across calls)."""
    global _pyttsx3_engine
    if not PYTTSX3_AVAILABLE:
        print(f"[TTS-EN] {text}  (pyttsx3 not available)")
        return
    try:
        if _pyttsx3_engine is None:
            _pyttsx3_engine = pyttsx3.init()
            _pyttsx3_engine.setProperty('rate', 145)
            _pyttsx3_engine.setProperty('volume', 1.0)
            voices = _pyttsx3_engine.getProperty('voices')
            for v in voices:
                if 'english' in v.name.lower():
                    _pyttsx3_engine.setProperty('voice', v.id)
                    break
        _pyttsx3_engine.say(text)
        _pyttsx3_engine.runAndWait()
    except Exception as e:
        print(f"[TTS ERROR] {e}")
        _pyttsx3_engine = None


# ═════════════════════════════════════════
#  AUDIO RECORDING
# ═════════════════════════════════════════

_input_device_rate = None
_mic_device_index  = None


def _get_mic_device_index():
    """
    Explicitly resolve the microphone input device by name rather than
    trusting PipeWire's "default" input at record time — see the matching
    function in mode2_online_translation.py for the full rationale (a
    second line of defense beyond the WirePlumber policy fix, so the
    offline pipeline can never end up recording from a Bluetooth speaker's
    own mic instead of the wired USB microphone). Cached for process life.
    """
    global _mic_device_index
    if _mic_device_index is not None:
        return _mic_device_index
    try:
        devices = sd.query_devices()
        usb_candidates = [
            i for i, d in enumerate(devices)
            if d['max_input_channels'] > 0
            and 'bluez' not in d['name'].lower()
            and 'bluetooth' not in d['name'].lower()
            and 'usb' in d['name'].lower()
        ]
        if usb_candidates:
            _mic_device_index = usb_candidates[0]
            print(f"[MIC] Using USB input device: {devices[_mic_device_index]['name']}", flush=True)
        else:
            non_bt = [
                i for i, d in enumerate(devices)
                if d['max_input_channels'] > 0
                and 'bluez' not in d['name'].lower()
                and 'bluetooth' not in d['name'].lower()
            ]
            _mic_device_index = non_bt[0] if non_bt else None
            print(f"[MIC WARNING] No USB input device found by name — "
                  f"falling back to {'device ' + str(_mic_device_index) if _mic_device_index is not None else 'system default'}.",
                  flush=True)
    except Exception as e:
        print(f"[MIC WARNING] Device lookup failed ({e}) — using system default.", flush=True)
        _mic_device_index = None
    return _mic_device_index


def _get_input_device_rate():
    global _input_device_rate
    if _input_device_rate is None:
        try:
            dev = _get_mic_device_index()
            info = sd.query_devices(dev, kind='input') if dev is not None else sd.query_devices(kind='input')
            _input_device_rate = int(info['default_samplerate'])
        except Exception:
            _input_device_rate = 16000
    return _input_device_rate


def _listen_offline_fixed(duration=6, target_samplerate=16000):
    """
    Fixed-duration microphone recording (fallback when webrtcvad unavailable).
    Records at the device's native rate, then resamples to target_samplerate.
    """
    print(f"\n[MIC] Recording {duration} seconds... Speak now!")
    try:
        native_rate = _get_input_device_rate()

        audio = sd.rec(
            int(duration * native_rate),
            samplerate=native_rate,
            channels=1,
            dtype='int16',
            device=_get_mic_device_index(),
        )
        sd.wait()
        print("[MIC] Done recording.")

        # Resample to target_samplerate if needed (Vosk needs 16 kHz)
        if native_rate != target_samplerate:
            audio = _resample(audio.flatten(), native_rate, target_samplerate)
        else:
            audio = audio.flatten()

        return audio, target_samplerate

    except Exception as e:
        print(f"[MIC ERROR] {e}")
        return None, target_samplerate


def _resample(audio, from_rate, to_rate):
    """Resample int16 audio array from from_rate to to_rate using linear interpolation."""
    if from_rate == to_rate:
        return audio
    duration_samples = len(audio)
    new_length = int(duration_samples * to_rate / from_rate)
    old_indices = np.linspace(0, duration_samples - 1, new_length)
    resampled = np.interp(old_indices, np.arange(duration_samples), audio.astype(np.float32))
    return resampled.astype(np.int16)


def _listen_offline_vad(target_samplerate=16000):
    """
    Stream microphone audio through webrtcvad; auto-stops after 1.5 s of silence.
    Returns (audio_int16, target_samplerate) or (None, target_samplerate).
    """
    FRAME_MS        = 30
    VAD_MODE        = 2
    SILENCE_MS      = 1500
    MIN_SPEECH_MS   = 200
    PRE_ROLL_MS     = 300
    MAX_DURATION_S  = 30

    FRAME_SAMPLES   = int(target_samplerate * FRAME_MS  / 1000)       # 480 @ 16 kHz
    SILENCE_FRAMES  = int(SILENCE_MS  / FRAME_MS)                      # 50
    SPEECH_TRIGGER  = max(1, int(MIN_SPEECH_MS / FRAME_MS))            # 6
    PRE_ROLL_FRAMES = int(PRE_ROLL_MS  / FRAME_MS)                     # 10
    MAX_FRAMES      = int(MAX_DURATION_S * 1000 / FRAME_MS)            # 1000

    vad         = _webrtcvad.Vad(VAD_MODE)
    native_rate = _get_input_device_rate()
    # Request enough native samples per callback to cover one VAD frame after resampling
    blocksize   = max(FRAME_SAMPLES, int(FRAME_SAMPLES * native_rate / target_samplerate))

    audio_q       = _queue.Queue()
    leftover      = np.array([], dtype=np.int16)
    pre_roll      = deque(maxlen=PRE_ROLL_FRAMES)
    collected     = []
    triggered     = False
    silence_count = 0
    speech_streak = 0
    total_frames  = 0

    # Dead-input detection: PipeWire's virtual "default" ALSA device (see
    # setup_pi.sh's Bluetooth-routing change) opens successfully even with no
    # real microphone attached. Real hardware always has some self-noise, so
    # a run of frames that are *exactly* all-zero means there's no physical
    # input behind the stream — fail fast instead of waiting the full
    # MAX_DURATION_S for webrtcvad to never trigger on silence.
    DEAD_INPUT_FRAMES = 20  # ~600ms at FRAME_MS=30
    silent_frame_streak = 0

    def _cb(indata, frames, time_info, status):
        audio_q.put(indata.copy())

    print("\n[MIC] Waiting for speech... (auto-stop on silence)")

    try:
        stream = sd.InputStream(
            samplerate=native_rate, channels=1, dtype='int16',
            blocksize=blocksize, callback=_cb,
            device=_get_mic_device_index(),
        )
    except Exception as e:
        print(f"[MIC] Cannot open stream for VAD: {e}. Falling back to fixed recording.")
        return _listen_offline_fixed(target_samplerate=target_samplerate)

    with stream:
        while total_frames < MAX_FRAMES:
            try:
                chunk = audio_q.get(timeout=0.5)
            except _queue.Empty:
                continue

            flat            = chunk.flatten()
            # Resample this chunk to 16 kHz first, then merge with leftover
            # (leftover is already at target_samplerate — never mix with native-rate audio)
            resampled_chunk = _resample(flat, native_rate, target_samplerate)
            combined        = np.concatenate([leftover, resampled_chunk]) if leftover.size else resampled_chunk

            idx = 0
            while idx + FRAME_SAMPLES <= len(combined):
                frame = combined[idx:idx + FRAME_SAMPLES]

                if np.abs(frame).max() == 0:
                    silent_frame_streak += 1
                    if silent_frame_streak >= DEAD_INPUT_FRAMES:
                        print("[MIC ERROR] No audio detected from input device — "
                              "microphone may not be physically connected.")
                        return None, target_samplerate
                else:
                    silent_frame_streak = 0

                try:
                    is_speech = vad.is_speech(frame.tobytes(), target_samplerate)
                except Exception:
                    is_speech = False

                if not triggered:
                    pre_roll.append(frame)
                    if is_speech:
                        speech_streak += 1
                        if speech_streak >= SPEECH_TRIGGER:
                            triggered     = True
                            silence_count = 0
                            collected.extend(list(pre_roll))
                            pre_roll.clear()
                            print("[MIC] Speech detected — recording...")
                    else:
                        speech_streak = 0
                else:
                    collected.append(frame)
                    total_frames += 1
                    if is_speech:
                        silence_count = 0
                    else:
                        silence_count += 1
                        if silence_count >= SILENCE_FRAMES:
                            print("[MIC] Silence detected — done recording.")
                            if collected:
                                return np.concatenate(collected), target_samplerate
                            return None, target_samplerate

                idx += FRAME_SAMPLES

            leftover = combined[idx:] if idx < len(combined) else np.array([], dtype=np.int16)

    if not collected:
        print("[MIC] No speech detected.")
        return None, target_samplerate

    print("[MIC] Max duration reached — done recording.")
    return np.concatenate(collected), target_samplerate


def listen_offline(duration=6, target_samplerate=16000):
    """
    Record microphone audio. Uses webrtcvad auto-stop when available,
    otherwise falls back to fixed-duration recording.
    The duration param is only used by the fixed fallback.
    """
    if WEBRTCVAD_AVAILABLE:
        return _listen_offline_vad(target_samplerate)
    return _listen_offline_fixed(duration=duration, target_samplerate=target_samplerate)


# ═════════════════════════════════════════
#  SPEECH TO TEXT
# ═════════════════════════════════════════

_VOSK_MODEL_PATH    = os.path.join(_SCRIPT_DIR, "vosk-model-small-en-us")
_vosk_model_cache   = {}
_whisper_model_cache = {}


def _load_vosk_model():
    if "en" in _vosk_model_cache:
        return _vosk_model_cache["en"]
    if not os.path.exists(_VOSK_MODEL_PATH):
        print(f"\n[ERROR] Vosk model not found at: {_VOSK_MODEL_PATH}")
        print("[TIP] Download vosk-model-small-en-us-0.15 from https://alphacephei.com/vosk/models")
        print("      Extract and rename the folder to: vosk-model-small-en-us")
        print(f"      Place it here: {_SCRIPT_DIR}\n")
        return None
    try:
        print("[STT] Loading Vosk model...")
        model = Model(_VOSK_MODEL_PATH)
        _vosk_model_cache["en"] = model
        print("[STT] Vosk model ready.")
        return model
    except Exception as e:
        print(f"[STT ERROR] Could not load Vosk model: {e}")
        return None


def _whisper_model_cached():
    """Return True if the faster-whisper 'small' model is already on disk."""
    model_dir = os.path.join(
        os.path.expanduser("~"), ".cache", "huggingface", "hub",
        "models--Systran--faster-whisper-small"
    )
    return os.path.isdir(model_dir)


def _load_whisper_model():
    if "small" in _whisper_model_cache:
        return _whisper_model_cache["small"]
    print("[STT] Loading faster-whisper model (downloads on first use)...")
    try:
        model = _FasterWhisperModel("small", device="cpu", compute_type="int8")
        _whisper_model_cache["small"] = model
        print("[STT] Whisper model ready.")
        return model
    except Exception as e:
        print(f"[STT ERROR] Could not load Whisper: {e}")
        return None


def _text_fallback_offline(lang):
    """Ask the user to type when mic/STT fails."""
    lang_label = "Urdu" if lang == "ur" else "English"
    print(f"[FALLBACK] STT failed — type your {lang_label} text (Enter to skip):")
    try:
        text = input("  > ").strip()
        return text if text else None
    except (EOFError, KeyboardInterrupt):
        return None


def speech_to_text_offline(lang="en"):
    """
    English -> Vosk  (fully offline)
    Urdu    -> Whisper (offline after first model download)
    Returns (text, audio_data, samplerate).
    """
    if lang == "ur":
        return _stt_whisper()
    return _stt_vosk()


def _stt_vosk():
    """English speech-to-text using Vosk — fully offline.
    Returns (text, audio_data, samplerate).
    audio_data is the raw int16 PCM that was recorded (or None on failure).
    """
    if not VOSK_AVAILABLE:
        print("[ERROR] vosk not installed. Run: py -m pip install vosk")
        return _text_fallback_offline("en"), None, 16000

    model = _load_vosk_model()
    if not model:
        return _text_fallback_offline("en"), None, 16000

    try:
        rec = KaldiRecognizer(model, 16000)
        audio, samplerate = listen_offline(duration=6, target_samplerate=16000)
        if audio is None:
            return _text_fallback_offline("en"), None, 16000

        audio_bytes = audio.tobytes()
        if rec.AcceptWaveform(audio_bytes):
            result = json.loads(rec.Result())
        else:
            result = json.loads(rec.FinalResult())

        text = result.get("text", "").strip()
        if text:
            print(f"[HEARD] {text}")
            return text, audio, samplerate
        else:
            print("[STT] Vosk heard nothing (too quiet or unclear).")
            return _text_fallback_offline("en"), audio, samplerate

    except Exception as e:
        print(f"[STT ERROR] Vosk: {e}")
        return _text_fallback_offline("en"), None, 16000


def _stt_whisper():
    """Urdu speech-to-text using faster-whisper — offline after first model download.
    Returns (text, audio_data, samplerate).
    audio_data is the raw int16 PCM that was recorded (or None on failure).
    """
    if not WHISPER_AVAILABLE:
        print("[ERROR] faster-whisper not installed. Run: pip install faster-whisper")
        return _text_fallback_offline("ur"), None, 16000

    audio, samplerate = listen_offline(duration=6, target_samplerate=16000)
    if audio is None:
        return _text_fallback_offline("ur"), None, 16000

    try:
        model = _load_whisper_model()
        if not model:
            return _text_fallback_offline("ur"), audio, samplerate

        audio_float = audio.astype(np.float32) / 32768.0
        segments, _ = model.transcribe(audio_float, language="ur")
        text = " ".join([s.text for s in segments]).strip()
        if text:
            safe_print(f"[HEARD] {text}")
            return text, audio, samplerate
        else:
            print("[STT] Whisper heard nothing (too quiet or unclear).")
            return _text_fallback_offline("ur"), audio, samplerate

    except Exception as e:
        print(f"[STT ERROR] Whisper: {e}")
        return _text_fallback_offline("ur"), None, 16000


# ═════════════════════════════════════════
#  FULL PIPELINE
# ═════════════════════════════════════════

def full_offline_pipeline(direction="en_to_ur", recorder=None):
    """Listen -> Recognize -> Translate -> Speak"""
    src_lang    = "en" if direction == "en_to_ur" else "ur"
    output_lang = "ur" if direction == "en_to_ur" else "en"
    label       = "English -> Urdu" if direction == "en_to_ur" else "Urdu -> English"

    print("\n" + "="*50)
    print(f"  OFFLINE PIPELINE: {label}")
    print("="*50)

    # ── STEP 1: Speech to Text ───────────────────────────────
    print(f"\n[1/3] Listening ({src_lang.upper()})...")
    text, audio, samplerate = speech_to_text_offline(lang=src_lang)
    if not text:
        # Audio captured but STT returned nothing — save it so it's not lost
        if recorder and audio is not None:
            recorder.log("AUTO", src_lang, '', output_lang, '',
                         audio_data=audio, samplerate=samplerate)
        print("[1/3] SKIPPED — no input received.")
        return None
    safe_print(f"[1/3] OK  Input  : {text}")

    # ── STEP 2: Translate ────────────────────────────────────
    print(f"\n[2/3] Translating {src_lang.upper()} -> {output_lang.upper()}...")
    translated = offline_translate(text, direction)
    safe_print(f"[2/3] OK  Output : {translated}")

    if translated.startswith("[Not translated:"):
        print("[2/3] WARN: Translation not available for this phrase.")
        print("            Use option 6 from the main menu to set up offline packs.")

    # Save the recording as soon as we have a transcript + translation, not
    # after TTS — a slow/failed/interrupted speak_offline() call must not
    # lose audio that was already successfully recognized and translated.
    if recorder:
        recorder.log("AUTO", src_lang, text, output_lang, translated,
                     audio_data=audio, samplerate=samplerate)

    # ── STEP 3: Speak ────────────────────────────────────────
    print(f"\n[3/3] Speaking...")
    safe_print(f"      Original   ({src_lang.upper()}): {text}")
    safe_print(f"      Translated ({output_lang.upper()}): {translated}")
    speak_offline(translated, lang=output_lang)

    print("[3/3] DONE\n")
    return translated


# ═════════════════════════════════════════
#  LIVE MIC LOOP
# ═════════════════════════════════════════

def _warm_up_translation(*directions):
    """
    argostranslate's first call in a process lazily loads its translation
    model (~5-8s, no progress output) — without this warning it looks like
    the pipeline is frozen. Pay that cost once, up front, with a visible
    message, instead of silently during the user's first live translation.
    """
    print("[SETUP] Loading offline translation engine (first use, a few seconds)...")
    for d in directions:
        try:
            offline_translate("hello", direction=d)
        except Exception:
            pass
    print("[SETUP] Ready.")


def live_offline_mode(recorder=None):
    """Continuous loop — Ctrl+C to stop."""
    print("\n" + "="*50)
    print("  OFFLINE LIVE MIC MODE")
    print("="*50)
    if not _argos_installed("en", "ur") or not _argos_installed("ur", "en"):
        print("[WARN] Argostranslate packages not installed — dictionary fallback will be used.")
        print("[TIP]  Connect to internet and run option 6 (Setup) once to install full translation.")
    else:
        print("[OK] Offline translation packages ready.")
    print("  1. English -> Urdu")
    print("  2. Urdu    -> English")
    d = input("\nSelect (1/2): ").strip()
    if d not in ('1', '2'):
        print("[ERROR] Invalid choice.")
        return
    direction = "en_to_ur" if d == "1" else "ur_to_en"
    label     = "English -> Urdu" if direction == "en_to_ur" else "Urdu -> English"
    _warm_up_translation(direction)
    print(f"\n[SET] {label} | Press Ctrl+C to stop.\n")
    while True:
        try:
            full_offline_pipeline(direction=direction, recorder=recorder)
        except KeyboardInterrupt:
            print("\n[OFFLINE] Stopped.")
            break


# ═════════════════════════════════════════
#  DEMO MODE (type to translate)
# ═════════════════════════════════════════

def demo_offline(recorder=None):
    """Type text to translate — no microphone needed."""
    print("\n" + "="*50)
    print("  OFFLINE DEMO MODE (Type to Translate)")
    print("="*50)
    if not _argos_installed("en", "ur") or not _argos_installed("ur", "en"):
        print("[WARN] Argostranslate packages not installed — dictionary fallback will be used.")
        print("[TIP]  Connect to internet and run option 6 (Setup) once to install full translation.")
    else:
        print("[OK] Offline translation packages ready.")
    print("  1. English -> Urdu")
    print("  2. Urdu    -> English")
    d = input("\nSelect (1/2): ").strip()
    if d not in ('1', '2'):
        print("[ERROR] Invalid choice.")
        return
    direction   = "en_to_ur" if d == "1" else "ur_to_en"
    src_lang    = "en" if direction == "en_to_ur" else "ur"
    output_lang = "ur" if direction == "en_to_ur" else "en"
    _warm_up_translation(direction)

    print("\nType text and press Enter. Type 'exit' to quit.\n")
    while True:
        try:
            text = input("Input: ").strip()
            if text.lower() in ("exit", "quit", "q"):
                break
            if not text:
                continue
            translated = offline_translate(text, direction)
            safe_print(f"[ORIGINAL]   {text}")
            safe_print(f"[TRANSLATED] {translated}")
            speak_offline(translated, lang=output_lang)
            if recorder:
                recorder.log("AUTO", src_lang, text, output_lang, translated)
            print("-" * 40)
        except KeyboardInterrupt:
            break
    print("\n[DEMO] Exited.")


# ═════════════════════════════════════════
#  TWO-WAY OFFLINE CONVERSATION
# ═════════════════════════════════════════

def two_way_conversation_offline(recorder=None):
    """
    Continuous offline two-way conversation — English <-> Urdu.
      Person A speaks English -> translated to Urdu   -> spoken to Person B
      Person B speaks Urdu    -> translated to English -> spoken to Person A
      Repeats until Ctrl+C.
    """
    print("\n" + "="*50)
    print("  TWO-WAY OFFLINE CONVERSATION")
    print("  English  <->  Urdu")
    print("="*50)

    if not _argos_installed("en", "ur") or not _argos_installed("ur", "en"):
        print("[WARN] Argostranslate packages not installed — dictionary fallback will be used.")
        print("[TIP]  Connect to internet and run option 6 (Setup) once to install full packs.")
    else:
        print("[OK] Offline translation packages ready.")

    _warm_up_translation("en_to_ur", "ur_to_en")

    print("\n[SET] Person A speaks English  |  Person B speaks Urdu")
    print("Conversation starts now. Press Ctrl+C to stop.\n")

    turn = 'A'
    while True:
        try:
            if turn == 'A':
                print("\n" + "-"*45)
                print("  PERSON A — speak in ENGLISH")
                print("-"*45)
                text, audio, samplerate = speech_to_text_offline(lang="en")
                if text:
                    translated = offline_translate(text, direction="en_to_ur")
                    safe_print(f"[Person A | EN]: {text}")
                    safe_print(f"[-> UR]        : {translated}")
                    if recorder:
                        recorder.log("Person A", "en", text, "ur", translated,
                                     audio_data=audio, samplerate=samplerate)
                    speak_offline(translated, lang="ur")
                elif audio is not None and recorder:
                    recorder.log("Person A", "en", '', "ur", '',
                                 audio_data=audio, samplerate=samplerate)
                turn = 'B'
            else:
                print("\n" + "-"*45)
                print("  PERSON B — speak in URDU")
                print("-"*45)
                text, audio, samplerate = speech_to_text_offline(lang="ur")
                if text:
                    translated = offline_translate(text, direction="ur_to_en")
                    safe_print(f"[Person B | UR]: {text}")
                    safe_print(f"[-> EN]        : {translated}")
                    if recorder:
                        recorder.log("Person B", "ur", text, "en", translated,
                                     audio_data=audio, samplerate=samplerate)
                    speak_offline(translated, lang="en")
                elif audio is not None and recorder:
                    recorder.log("Person B", "ur", '', "en", '',
                                 audio_data=audio, samplerate=samplerate)
                turn = 'A'
        except KeyboardInterrupt:
            print("\n[CONVERSATION] Ended.")
            break


# ═════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  MODE 1 - OFFLINE TRANSLATION")
    print("  Smart Headphone Translation System")
    print("="*50)
    print("  1. Demo mode  (type to translate)")
    print("  2. Live mic   (English -> Urdu)")
    print("  3. Live mic   (Urdu -> English)")
    print("  4. Setup offline translation (internet needed once)")
    print("="*50)
    choice = input("\nChoose (1-4): ").strip()

    if choice == "1":
        demo_offline()
    elif choice == "2":
        full_offline_pipeline(direction="en_to_ur")
    elif choice == "3":
        full_offline_pipeline(direction="ur_to_en")
    elif choice == "4":
        setup_offline_translation()
    else:
        print("Invalid choice.")
