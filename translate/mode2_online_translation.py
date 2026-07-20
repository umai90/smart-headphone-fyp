"""
MODE 2 - ONLINE TRANSLATION
Smart Headphone Translation System
Uses: deep-translator + gTTS + sounddevice (NO pyaudio needed)
"""

import sys
import os
import subprocess
import threading as _threading

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
import time
import tempfile
import wave
import numpy as np
import sounddevice as sd

# Pi translation control
_pi_ctrl = {
    'stop':   _threading.Event(),
    'thread': None,
    'lock':   _threading.Lock(),
}

_pi_status_lock        = _threading.Lock()
_translator_cache_lock = _threading.Lock()
_backup_status_lock    = _threading.Lock()
_backup_status         = {'running': False, 'uploaded': 0, 'failed': 0, 'error': ''}

# Fix Windows console so Urdu/Arabic characters don't crash output
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf-8-sig'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def safe_print(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('utf-8', errors='replace').decode('ascii', errors='replace'))

# ─── Translation ───────────────────────────────────────────────────────────────
try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
    print("[WARNING] deep-translator not installed. Run: py -m pip install deep-translator")

# ─── Text-to-Speech ────────────────────────────────────────────────────────────
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    print("[WARNING] gTTS not available. Using pyttsx3 fallback.")

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

try:
    import pygame
    pygame.mixer.init()
    PYGAME_AVAILABLE = True
except Exception:
    PYGAME_AVAILABLE = False

try:
    import webrtcvad as _webrtcvad
    WEBRTCVAD_AVAILABLE = True
except ImportError:
    WEBRTCVAD_AVAILABLE = False

# ─── Speech Recognition ────────────────────────────────────────────────────────
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    print("[WARNING] SpeechRecognition not available. Run: py -m pip install SpeechRecognition")

# ──────────────────────────────────────────────────────────────────────────────
# SUPPORTED LANGUAGES
# ──────────────────────────────────────────────────────────────────────────────
SUPPORTED_LANGUAGES = {
    '1':  ('en',    'English'),
    '2':  ('ur',    'Urdu'),
    '3':  ('ar',    'Arabic'),
    '4':  ('fr',    'French'),
    '5':  ('de',    'German'),
    '6':  ('zh-CN', 'Chinese'),
    '7':  ('hi',    'Hindi'),
    '8':  ('es',    'Spanish'),
    '9':  ('tr',    'Turkish'),
    '10': ('ru',    'Russian'),
    '11': ('it',    'Italian'),
    '12': ('ja',    'Japanese'),
    '13': ('ko',    'Korean'),
    '14': ('pt',    'Portuguese'),
    '15': ('nl',    'Dutch'),
    '16': ('pl',    'Polish'),
    '17': ('sv',    'Swedish'),
    '18': ('da',    'Danish'),
    '19': ('fi',    'Finnish'),
    '20': ('no',    'Norwegian'),
    '21': ('id',    'Indonesian'),
    '22': ('ms',    'Malay'),
    '23': ('th',    'Thai'),
    '24': ('vi',    'Vietnamese'),
    '25': ('el',    'Greek'),
    '26': ('cs',    'Czech'),
    '27': ('hu',    'Hungarian'),
    '28': ('ro',    'Romanian'),
    '29': ('uk',    'Ukrainian'),
    '30': ('he',    'Hebrew'),
    '31': ('bn',    'Bengali'),
    '32': ('fa',    'Persian'),
    '33': ('sw',    'Swahili'),
    '34': ('tl',    'Filipino'),
}

# Maps 2-letter Flutter codes to Google Translate codes (where different)
_FLUTTER_TO_GTRANSLATE = {
    'zh': 'zh-CN',   # Flutter sends 'zh', Google Translate needs 'zh-CN'
    'no': 'no',
}

def _normalize_lang_code(code):
    """Convert Flutter app language codes to Google Translate codes."""
    return _FLUTTER_TO_GTRANSLATE.get(code, code)

TARGET_LANGUAGE = 'ur'  # Default: everything -> Urdu

_translator_cache  = {}
try:
    _sr_recognizer = sr.Recognizer() if SR_AVAILABLE else None
except Exception:
    _sr_recognizer = None
_pyttsx3_engine    = None
_input_device_rate = None
_mic_device_index  = None


def _get_mic_device_index():
    """
    Explicitly resolve the microphone input device by name rather than
    trusting PipeWire's "default" input at record time. WirePlumber's
    default source has been observed to silently switch to a connected
    Bluetooth speaker's own (low-quality) mic on reconnect even with the
    autoswitch-to-headset-profile policy disabled at the system level —
    this is a code-level second line of defense so a stray default-source
    change can never route the mic path to a Bluetooth (or any non-USB)
    device. Input must always be the wired USB microphone; result is
    cached for the life of the process since the mic isn't hot-swapped
    mid-session.
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


# ──────────────────────────────────────────────────────────────────────────────
# CORE FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def _detect_lang(text):
    """
    Lightweight script-based language detection — no extra dependencies.
    Checks Unicode ranges: Arabic/Urdu (U+0600-U+06FF) -> 'ur', else 'en'.
    """
    for ch in text:
        if '\u0600' <= ch <= '\u06FF':
            return 'ur'
    return 'en'


def translate_text(text, source='auto', target=None):
    """Translate text using deep-translator (translator instances cached per language pair)."""
    if target is None:
        target = TARGET_LANGUAGE
    if not TRANSLATOR_AVAILABLE:
        return f"[Translator unavailable] {text}"
    # Normalize codes (e.g. 'zh' -> 'zh-CN') for Google Translate compatibility
    norm_source = _normalize_lang_code(source)
    norm_target = _normalize_lang_code(target)
    key = (norm_source, norm_target)
    try:
        with _translator_cache_lock:
            if key not in _translator_cache:
                _translator_cache[key] = GoogleTranslator(source=norm_source, target=norm_target)
            translator = _translator_cache[key]
        result = translator.translate(text)
        return result if result else text
    except Exception as e:
        with _translator_cache_lock:
            _translator_cache.pop(key, None)
        return f"[Translation error: {e}]"


def speak_text(text, lang=None):
    """Speak text using gTTS+pygame (online) or pyttsx3 (fallback)."""
    global _pyttsx3_engine
    if lang is None:
        lang = TARGET_LANGUAGE

    if GTTS_AVAILABLE:
        tmp_path = None
        try:
            tts = gTTS(text=text, lang=lang, slow=False)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
                tmp_path = f.name
            tts.save(tmp_path)
            if PYGAME_AVAILABLE:
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            else:
                word_count = len(text.split())
                sleep_sec  = max(4, round(word_count / 130 * 60) + 2)
                if os.name == 'nt':
                    os.system(f'start /min "" "{tmp_path}"')
                    time.sleep(sleep_sec)
                else:
                    subprocess.run(['mpg123', '-q', tmp_path], check=False)
            return
        except Exception as e:
            print(f"[gTTS error: {e}] Trying pyttsx3...")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    try:
        if _pyttsx3_engine is None:
            if not PYTTSX3_AVAILABLE:
                print(f"[SPEAK - no audio engine] {text}")
                return
            _pyttsx3_engine = pyttsx3.init()
            _pyttsx3_engine.setProperty('rate', 150)
        _pyttsx3_engine.say(text)
        _pyttsx3_engine.runAndWait()
    except Exception as e:
        print(f"[pyttsx3 error: {e}]")
        _pyttsx3_engine = None


def _resample_audio(audio, from_rate, to_rate):
    """Resample int16 audio from from_rate to to_rate using linear interpolation."""
    if from_rate == to_rate:
        return audio
    new_length = int(len(audio) * to_rate / from_rate)
    old_indices = np.linspace(0, len(audio) - 1, new_length)
    resampled = np.interp(old_indices, np.arange(len(audio)), audio.astype(np.float32))
    return resampled.astype(np.int16)


# Maps app language codes to BCP-47 codes for Google Speech API
_LANG_MAP = {
    'en': 'en-US',  'ur': 'ur-PK',  'ar': 'ar-SA',
    'fr': 'fr-FR',  'de': 'de-DE',  'hi': 'hi-IN',
    'es': 'es-ES',  'tr': 'tr-TR',  'ru': 'ru-RU',
    'zh-CN': 'zh-CN', 'zh': 'zh-CN',
    'it': 'it-IT',  'ja': 'ja-JP',  'ko': 'ko-KR',
    'pt': 'pt-PT',  'nl': 'nl-NL',  'pl': 'pl-PL',
    'sv': 'sv-SE',  'da': 'da-DK',  'fi': 'fi-FI',
    'no': 'nb-NO',  'id': 'id-ID',  'ms': 'ms-MY',
    'th': 'th-TH',  'vi': 'vi-VN',  'el': 'el-GR',
    'cs': 'cs-CZ',  'hu': 'hu-HU',  'ro': 'ro-RO',
    'uk': 'uk-UA',  'he': 'iw-IL',  'bn': 'bn-IN',
    'fa': 'fa-IR',  'sw': 'sw-TZ',  'tl': 'fil-PH',
}


def _send_to_stt(audio, sr_lang, source_lang, fallback_to_text):
    """Send int16 PCM at 16 kHz to Google Speech API. Returns (text, audio, 16000)."""
    TARGET_RATE = 16000
    if not SR_AVAILABLE or _sr_recognizer is None:
        if fallback_to_text:
            return _text_fallback(source_lang), audio, TARGET_RATE
        return None, audio, TARGET_RATE

    tmp_wav = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as f:
            tmp_wav = f.name
        with wave.open(tmp_wav, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(TARGET_RATE)
            wf.writeframes(audio.tobytes())
        with sr.AudioFile(tmp_wav) as source:
            audio_data = _sr_recognizer.record(source)
        text = _sr_recognizer.recognize_google(audio_data, language=sr_lang)
        print(f"[MIC] Heard: {text}")
        return text, audio, TARGET_RATE
    except sr.UnknownValueError:
        print("[MIC] Google could not understand the audio.")
        if fallback_to_text:
            return _text_fallback(source_lang), audio, TARGET_RATE
        return None, audio, TARGET_RATE
    except sr.RequestError as e:
        print(f"[MIC] Google Speech API error: {e}")
        if fallback_to_text:
            return _text_fallback(source_lang), audio, TARGET_RATE
        return None, audio, TARGET_RATE
    except Exception as e:
        print(f"[STT ERROR] {e}")
        if fallback_to_text:
            return _text_fallback(source_lang), audio, TARGET_RATE
        return None, audio, TARGET_RATE
    finally:
        if tmp_wav and os.path.exists(tmp_wav):
            try:
                os.remove(tmp_wav)
            except Exception:
                pass


def _listen_fixed(source_lang='en', fallback_to_text=True):
    """Fallback: record a fixed 7 seconds then send to Google Speech API."""
    TARGET_RATE = 16000
    DURATION    = 7

    if not SR_AVAILABLE or _sr_recognizer is None:
        print("[ERROR] SpeechRecognition not available. Run: pip install SpeechRecognition")
        if fallback_to_text:
            return _text_fallback(source_lang), None, TARGET_RATE
        return None, None, TARGET_RATE

    sr_lang     = _LANG_MAP.get(source_lang, 'en-US')
    native_rate = _get_input_device_rate()
    recording   = None
    print(f"\n[MIC] Recording {DURATION}s (fixed)... Speak now in {source_lang.upper()}!")
    try:
        recording = sd.rec(
            int(DURATION * native_rate),
            samplerate=native_rate,
            channels=1,
            dtype='int16',
            device=_get_mic_device_index(),
        )
        sd.wait()
        print("[MIC] Done. Sending to Google Speech API...")
        audio = recording.flatten()
        if native_rate != TARGET_RATE:
            audio = _resample_audio(audio, native_rate, TARGET_RATE)
        return _send_to_stt(audio, sr_lang, source_lang, fallback_to_text)
    except Exception as e:
        global _mic_device_index
        _mic_device_index = None  # re-resolve device on next attempt
        print(f"[MIC ERROR] {e}")
        try:
            rec_audio = (_resample_audio(recording.flatten(), native_rate, TARGET_RATE)
                         if recording is not None else None)
        except Exception:
            rec_audio = None
        if fallback_to_text:
            return _text_fallback(source_lang), rec_audio, TARGET_RATE
        return None, rec_audio, TARGET_RATE


def _listen_vad(source_lang='en', fallback_to_text=True):
    """
    VAD-based recording via webrtcvad.
    Waits silently until speech is detected, records until 1.5 s of silence,
    then submits to Google Speech API.  Hard-caps at 30 s.
    Falls back to _listen_fixed() if the audio stream cannot be opened.

    Returns (text, audio_int16_16khz, 16000).
    """
    import queue as _queue
    from collections import deque

    TARGET_RATE = 16000
    FRAME_MS    = 30                              # webrtcvad only accepts 10/20/30 ms
    FRAME_SAMP  = TARGET_RATE * FRAME_MS // 1000  # 480 samples per frame

    # Tuning knobs
    VAD_MODE          = 2     # 0=permissive … 3=strict; 2 works well for most mics
    SILENCE_MS        = 1500  # continuous silence (ms) after speech → stop
    MIN_SPEECH_MS     = 200   # minimum speech (ms) before we start accumulating
    PRE_ROLL_MS       = 300   # ms of audio kept before speech trigger (avoids clipping)
    MAX_DURATION_SEC  = 30    # hard cap

    silence_frames_req = SILENCE_MS       // FRAME_MS   # 50
    min_speech_frames  = MIN_SPEECH_MS    // FRAME_MS   # 7
    pre_roll_capacity  = PRE_ROLL_MS      // FRAME_MS   # 10
    max_total_frames   = MAX_DURATION_SEC * 1000 // FRAME_MS

    vad         = _webrtcvad.Vad(VAD_MODE)
    q           = _queue.Queue()
    native_rate = _get_input_device_rate()

    def _cb(indata, frames, t, status):
        q.put(bytes(indata))

    print(f"\n[MIC-VAD] Waiting for speech in {source_lang.upper()} "
          f"(stops after {SILENCE_MS} ms silence)...")

    pre_roll      = deque(maxlen=pre_roll_capacity)
    accumulated   = []
    speech_streak = 0
    silence_streak= 0
    triggered     = False

    # Dead-input detection: PipeWire's virtual "default" ALSA device (see
    # setup_pi.sh's Bluetooth-routing change) always opens successfully even
    # when no real microphone is attached — unlike the old hardcoded-ALSA
    # setup, which raised an immediate exception here. Real hardware always
    # has some self-noise, so a run of frames that are *exactly* all-zero
    # means there's no physical input device behind the stream. Fail fast
    # instead of waiting the full MAX_DURATION_SEC for webrtcvad to never
    # trigger on silence that will never end.
    DEAD_INPUT_FRAMES = 20  # ~600ms at FRAME_MS=30
    silent_frame_streak = 0

    try:
        with sd.InputStream(
            samplerate=native_rate,
            channels=1,
            dtype='int16',
            blocksize=int(native_rate * FRAME_MS / 1000),
            callback=_cb,
            device=_get_mic_device_index(),
        ):
            while True:
                try:
                    raw = q.get(timeout=MAX_DURATION_SEC + 2)
                except _queue.Empty:
                    break

                # Resample chunk to 16 kHz for webrtcvad
                chunk = np.frombuffer(raw, dtype=np.int16)
                if native_rate != TARGET_RATE:
                    chunk = _resample_audio(chunk, native_rate, TARGET_RATE)

                # Exact frame size required by webrtcvad
                if len(chunk) < FRAME_SAMP:
                    chunk = np.pad(chunk, (0, FRAME_SAMP - len(chunk)))
                else:
                    chunk = chunk[:FRAME_SAMP]

                if np.abs(chunk).max() == 0:
                    silent_frame_streak += 1
                    if silent_frame_streak >= DEAD_INPUT_FRAMES:
                        print("[MIC ERROR] No audio detected from input device — "
                              "microphone may not be physically connected.")
                        return (_text_fallback(source_lang) if fallback_to_text else None,
                                None, TARGET_RATE)
                else:
                    silent_frame_streak = 0

                try:
                    is_speech = vad.is_speech(chunk.tobytes(), TARGET_RATE)
                except Exception:
                    is_speech = False

                if not triggered:
                    # Pre-trigger: fill ring buffer, count speech frames
                    pre_roll.append(chunk)
                    speech_streak = (speech_streak + 1) if is_speech else max(0, speech_streak - 1)
                    if speech_streak >= min_speech_frames:
                        triggered      = True
                        silence_streak = 0
                        # Include the pre-roll so the first syllable isn't clipped
                        accumulated.extend(pre_roll)
                        accumulated.append(chunk)
                        print("[MIC-VAD] Speech detected — recording")
                else:
                    # Post-trigger: accumulate and watch for silence
                    accumulated.append(chunk)
                    if is_speech:
                        silence_streak = 0
                    else:
                        silence_streak += 1
                        if silence_streak >= silence_frames_req:
                            dur = len(accumulated) * FRAME_MS / 1000
                            print(f"[MIC-VAD] Silence — stopping  ({dur:.1f} s captured)")
                            break

                    if len(accumulated) >= max_total_frames:
                        print("[MIC-VAD] Max duration reached")
                        break

    except Exception as e:
        # Some budget USB audio adapters intermittently drop their input
        # channel (observed live: device briefly reports 0 input channels,
        # then recovers on its own) - clear the cached device index so the
        # next attempt re-resolves it fresh instead of retrying the same
        # now-stale index forever.
        global _mic_device_index
        _mic_device_index = None
        print(f"[MIC-VAD] Stream error: {e}  -> falling back to fixed recording")
        return _listen_fixed(source_lang, fallback_to_text)

    if not accumulated:
        print("[MIC-VAD] No speech detected")
        if fallback_to_text:
            return _text_fallback(source_lang), None, TARGET_RATE
        return None, None, TARGET_RATE

    audio   = np.concatenate(accumulated)
    sr_lang = _LANG_MAP.get(source_lang, 'en-US')
    return _send_to_stt(audio, sr_lang, source_lang, fallback_to_text)


def listen_microphone(source_lang='en', fallback_to_text=True):
    """
    Record microphone audio and recognise with Google Speech API.
    Uses webrtcvad (auto start/stop on silence) when available.
    Falls back to a fixed 7-second recording when webrtcvad is not installed.

    Returns (text, audio_int16, 16000).
    """
    if WEBRTCVAD_AVAILABLE:
        return _listen_vad(source_lang, fallback_to_text)
    return _listen_fixed(source_lang, fallback_to_text)


def _text_fallback(lang):
    """Ask the user to type text when mic/STT fails."""
    print(f"[FALLBACK] Type your text in {lang.upper()} (or press Enter to skip):")
    try:
        text = input("  > ").strip()
        return text if text else None
    except (EOFError, KeyboardInterrupt):
        return None


def full_pipeline(source_lang='en', target_lang=None, recorder=None):
    """Listen -> Translate -> Speak"""
    if target_lang is None:
        target_lang = TARGET_LANGUAGE

    print(f"\n[PIPELINE] {source_lang.upper()} -> {target_lang.upper()}")
    text, audio, samplerate = listen_microphone(source_lang)
    if not text:
        if recorder and audio is not None:
            recorder.log("AUTO", source_lang, '', target_lang, '',
                         audio_data=audio, samplerate=samplerate)
        return

    translated = translate_text(text, source=source_lang, target=target_lang)
    safe_print(f"[RESULT] Original  : {text}")
    safe_print(f"[RESULT] Translated: {translated}")
    speak_text(translated, lang=target_lang)

    if recorder:
        recorder.log("AUTO", source_lang, text, target_lang, translated,
                     audio_data=audio, samplerate=samplerate)


# ──────────────────────────────────────────────────────────────────────────────
# FLASK API — REST endpoint for Android App
# ──────────────────────────────────────────────────────────────────────────────

_RECORDINGS_DIR = os.path.join(_THIS_DIR, "recordings")
_LANG_CFG_FILE  = os.path.join(_THIS_DIR, "lang_config.json")

# Ensure deepfake_checker is importable from this directory
import sys as _sys
if _THIS_DIR not in _sys.path:
    _sys.path.insert(0, _THIS_DIR)

import time as _time
_pi_status = {
    'state':             'idle',
    'from_lang':         'en',
    'to_lang':           'ur',
    'last_original':     '',
    'last_translated':   '',
    'translation_count': 0,
    'started_at':        _time.time(),
    'direction':         '1way',
}


def _pi_set(**kwargs):
    with _pi_status_lock:
        _pi_status.update(kwargs)


def _pi_inc_count():
    with _pi_status_lock:
        _pi_status['translation_count'] += 1


def _pi_snap():
    with _pi_status_lock:
        return dict(_pi_status)


def _load_lang_config():
    """Load saved language preference (set by app via /language endpoint)."""
    if os.path.exists(_LANG_CFG_FILE):
        try:
            import json
            with open(_LANG_CFG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {'from_code': 'en', 'to_code': 'ur'}


def _save_lang_config(from_code, to_code):
    try:
        import json
        with open(_LANG_CFG_FILE, 'w') as f:
            json.dump({'from_code': from_code, 'to_code': to_code}, f)
    except Exception:
        pass


def _count_local_recordings():
    if not os.path.isdir(_RECORDINGS_DIR):
        return 0
    return sum(1 for f in os.listdir(_RECORDINGS_DIR)
               if f.lower().endswith('.wav') and
               os.path.isfile(os.path.join(_RECORDINGS_DIR, f)))


def _find_recording(filename):
    """Search flat recordings/ root for a file by name.
    Strips any directory component to prevent path-traversal attacks."""
    safe_name = os.path.basename(filename)
    if not safe_name or safe_name != filename:
        return None, None
    path = os.path.join(_RECORDINGS_DIR, safe_name)
    if os.path.exists(path):
        return path, ''
    return None, None


def _list_local_recordings():
    import datetime
    files = []
    if not os.path.isdir(_RECORDINGS_DIR):
        return files
    for name in sorted(os.listdir(_RECORDINGS_DIR), reverse=True):
        if not name.lower().endswith('.wav'):
            continue
        path = os.path.join(_RECORDINGS_DIR, name)
        if not os.path.isfile(path):
            continue
        size_mb = round(os.path.getsize(path) / (1024 * 1024), 2)
        mtime   = os.path.getmtime(path)
        date    = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        files.append({'name': name, 'size_mb': size_mb, 'date': date, 'source': 'pi'})
    return files


def _list_cloud_recordings():
    """List WAV files backed up to Google Drive.
    Runs with a hard timeout so it never blocks the Flask thread for long."""
    import concurrent.futures
    def _fetch():
        from cloud_backup import _get_drive, _get_or_create_folder
        drive     = _get_drive()
        folder_id = _get_or_create_folder(drive)
        query = (f"'{folder_id}' in parents and trashed=false and "
                 f"title contains '.wav'")
        items = drive.ListFile({'q': query}).GetList()
        result = []
        for item in sorted(items, key=lambda x: x.get('createdDate', ''), reverse=True):
            size_mb = round(int(item.get('fileSize', 0)) / (1024 * 1024), 2)
            date    = item.get('createdDate', '')[:16].replace('T', ' ')
            result.append({
                'name': item['title'], 'size_mb': size_mb,
                'date': date, 'source': 'cloud', 'drive_id': item['id']
            })
        return result
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_fetch)
            return future.result(timeout=5)   # max 5 s — within Flutter's 6 s client timeout
    except Exception:
        return []


def start_flask_api():
    try:
        from flask import Flask, request, jsonify, send_from_directory
        from flask_cors import CORS

        app = Flask(__name__)
        CORS(app)

        # ── Translation ──────────────────────────────────────────────────────

        @app.route('/translate', methods=['POST'])
        def api_translate():
            data   = request.get_json(silent=True) or {}
            text   = data.get('text', '')
            source = _normalize_lang_code(data.get('source', 'auto'))
            target = _normalize_lang_code(data.get('target', 'ur'))
            mode   = data.get('mode', 'online')
            if not text:
                return jsonify({'error': 'No text provided'}), 400

            _pi_set(state='translating', from_lang=source, to_lang=target)

            if mode == 'offline':
                try:
                    import sys as _sys
                    _sys.path.insert(0, _THIS_DIR)
                    from mode1_offline_translation import offline_translate
                    direction = ('en_to_ur' if (source in ('en', 'auto') and target == 'ur')
                                 else 'ur_to_en' if (source == 'ur' and target in ('en', 'auto'))
                                 else 'en_to_ur')
                    result = offline_translate(text, direction=direction)
                except Exception as e:
                    result = f'[Offline error: {e}]'
            else:
                result = translate_text(text, source=source, target=target)

            _pi_inc_count()
            _pi_set(state='idle', last_original=text, last_translated=result)

            return jsonify({'original': text, 'translated': result,
                            'source': source, 'target': target, 'mode': mode})

        # ── Monitor ──────────────────────────────────────────────────────────

        @app.route('/status', methods=['GET'])
        def api_status():
            import time
            snap = _pi_snap()
            return jsonify({
                **snap,
                'uptime_sec':        int(time.time() - snap['started_at']),
                'recordings_local':  _count_local_recordings(),
            })

        @app.route('/language', methods=['POST'])
        def api_language():
            data      = request.get_json(silent=True) or {}
            from_code = data.get('from_code', 'en')
            to_code   = data.get('to_code',   'ur')
            _pi_set(from_lang=from_code, to_lang=to_code)
            _save_lang_config(from_code, to_code)
            return jsonify({'success': True, 'from_code': from_code, 'to_code': to_code})

        # ── Recordings ───────────────────────────────────────────────────────

        @app.route('/recordings', methods=['GET'])
        def api_recordings_list():
            source = request.args.get('source', 'pi')   # 'pi', 'cloud', or 'all'
            files  = []
            if source in ('pi', 'all'):
                files += _list_local_recordings()
            if source in ('cloud', 'all'):
                files += _list_cloud_recordings()
            return jsonify({'recordings': files, 'count': len(files)})

        @app.route('/recordings/<string:filename>', methods=['GET'])
        def api_serve_recording(filename):
            path, _ = _find_recording(filename)
            if path is None:
                return jsonify({'error': 'File not found'}), 404
            return send_from_directory(_RECORDINGS_DIR, filename, mimetype='audio/wav')

        @app.route('/recordings/<string:filename>', methods=['DELETE'])
        def api_delete_recording(filename):
            path, _ = _find_recording(filename)
            if path is None:
                return jsonify({'error': 'File not found'}), 404
            try:
                os.remove(path)
                return jsonify({'success': True, 'deleted': filename})
            except FileNotFoundError:
                return jsonify({'error': 'File not found'}), 404
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @app.route('/recordings/backup', methods=['POST'])
        def api_backup_now():
            """Trigger cloud backup in a background thread — returns immediately."""
            with _backup_status_lock:
                if _backup_status['running']:
                    return jsonify({'status': 'already_running'}), 200
                # Set running=True inside the same lock as the check — atomic
                _backup_status['running'] = True

            def _run():
                try:
                    import sys as _sys
                    _sys.path.insert(0, _THIS_DIR)
                    from cloud_backup import backup_recordings
                    up, fail = backup_recordings(delete_after=True, verbose=False)
                    with _backup_status_lock:
                        _backup_status.update({'uploaded': up, 'failed': fail, 'error': ''})
                except Exception as e:
                    with _backup_status_lock:
                        _backup_status.update({'error': str(e)})
                finally:
                    with _backup_status_lock:
                        _backup_status['running'] = False

            _threading.Thread(target=_run, daemon=True, name='cloud-backup').start()
            return jsonify({'status': 'started', 'message': 'Backup running in background'})

        @app.route('/recordings/backup/status', methods=['GET'])
        def api_backup_status():
            with _backup_status_lock:
                return jsonify(dict(_backup_status))

        # ── Misc ─────────────────────────────────────────────────────────────

        @app.route('/languages', methods=['GET'])
        def api_languages():
            return jsonify(SUPPORTED_LANGUAGES)

        @app.route('/health', methods=['GET'])
        def health():
            return jsonify({
                'status': 'ok',
                'mode': 'online',
                'features': ['translate', 'detect', 'monitor', 'recordings', 'pi_control'],
                'endpoints': [
                    'POST /translate', 'GET /status', 'POST /language',
                    'GET /recordings', 'GET /recordings/<name>',
                    'DELETE /recordings/<name>', 'POST /recordings/backup',
                    'GET /recordings/backup/status',
                    'POST /detect', 'POST /detect_recording/<name>',
                    'POST /pi/start', 'POST /pi/stop',
                    'GET /languages', 'GET /health',
                ],
            })

        # ── Pi Mic/Speaker Control ────────────────────────────────────────────

        def _offline_translate_pair(text, src, tgt):
            import sys as _s
            _s.path.insert(0, _THIS_DIR)
            from mode1_offline_translation import offline_translate
            if src in ('en', 'auto') and tgt == 'ur':
                d = 'en_to_ur'
            elif src == 'ur' and tgt in ('en', 'auto'):
                d = 'ur_to_en'
            else:
                d = 'en_to_ur'
            return offline_translate(text, direction=d)

        def _run_1way(mode, from_lang, to_lang, stop_ev):
            """Pi listens with mic, translates, speaks through speaker — 1 person."""
            import sys as _s
            _s.path.insert(0, _THIS_DIR)
            from conversation_recorder import ConversationRecorder
            recorder = ConversationRecorder()
            recorder.start(f'Pi-1Way-{from_lang}-{to_lang}')
            if mode == 'offline':
                # argostranslate's first call in a process lazily loads its
                # translation model (~5-8s) — pay that cost once now instead
                # of during the first real listen/translate cycle.
                from mode1_offline_translation import _warm_up_translation
                d = 'en_to_ur' if (from_lang == 'en' or to_lang == 'ur') else 'ur_to_en'
                _warm_up_translation(d)
            _pi_set(state='listening')
            try:
                while not stop_ev.is_set():
                    try:
                        if mode == 'offline':
                            from mode1_offline_translation import speech_to_text_offline
                            text, audio, samplerate = speech_to_text_offline(from_lang)
                        else:
                            text, audio, samplerate = listen_microphone(from_lang, fallback_to_text=False)
                        if stop_ev.is_set():
                            break
                        if not text:
                            # Audio was captured but STT returned nothing — save it anyway
                            if audio is not None:
                                recorder.log('Pi-1Way', from_lang, '', to_lang, '',
                                             audio_data=audio, samplerate=samplerate)
                            continue
                        _pi_set(state='translating')
                        if mode == 'offline':
                            try:
                                result = _offline_translate_pair(text, from_lang, to_lang)
                            except Exception as e:
                                result = f'[Offline error: {e}]'
                        else:
                            result = translate_text(text, source=from_lang, target=to_lang)
                        _pi_inc_count()
                        _pi_set(last_original=text, last_translated=result)
                        recorder.log('Pi-1Way', from_lang, text, to_lang, result,
                                     audio_data=audio, samplerate=samplerate)
                        speak_text(result, to_lang)
                        _pi_set(state='listening')
                    except Exception as _exc:
                        if stop_ev.is_set():
                            break
                        print(f"[Pi-1Way] loop error (continuing): {_exc}", flush=True)
            finally:
                recorder.stop()
                _pi_set(state='idle')

        def _run_2way(mode, lang_a, lang_b, stop_ev):
            """Pi listens with mic, translates both ways, speaks — 2 persons."""
            import sys as _s
            _s.path.insert(0, _THIS_DIR)
            from conversation_recorder import ConversationRecorder
            recorder = ConversationRecorder()
            recorder.start(f'Pi-2Way-{lang_a}-{lang_b}')
            if mode == 'offline':
                from mode1_offline_translation import _warm_up_translation
                _warm_up_translation('en_to_ur', 'ur_to_en')
            turn = 'A'
            _pi_set(state='listening')
            try:
                while not stop_ev.is_set():
                    try:
                        src = lang_a if turn == 'A' else lang_b
                        tgt = lang_b if turn == 'A' else lang_a
                        speaker = f'Person-{turn}'
                        if mode == 'offline':
                            from mode1_offline_translation import speech_to_text_offline
                            text, audio, samplerate = speech_to_text_offline(src)
                        else:
                            text, audio, samplerate = listen_microphone(src, fallback_to_text=False)
                        if stop_ev.is_set():
                            break
                        if not text:
                            # Save the captured audio even when STT returned nothing
                            if audio is not None:
                                recorder.log(speaker, src, '', tgt, '',
                                             audio_data=audio, samplerate=samplerate)
                            turn = 'B' if turn == 'A' else 'A'
                            continue
                        _pi_set(state='translating')
                        if mode == 'offline':
                            try:
                                result = _offline_translate_pair(text, src, tgt)
                            except Exception as e:
                                result = f'[Offline error: {e}]'
                        else:
                            result = translate_text(text, source=src, target=tgt)
                        _pi_inc_count()
                        _pi_set(last_original=text, last_translated=result)
                        recorder.log(speaker, src, text, tgt, result,
                                     audio_data=audio, samplerate=samplerate)
                        speak_text(result, tgt)
                        turn = 'B' if turn == 'A' else 'A'
                        _pi_set(state='listening')
                    except Exception as _exc:
                        if stop_ev.is_set():
                            break
                        print(f"[Pi-2Way] loop error (continuing): {_exc}", flush=True)
            finally:
                recorder.stop()
                _pi_set(state='idle')

        @app.route('/pi/start', methods=['POST'])
        def api_pi_start():
            data      = request.get_json(silent=True) or {}
            direction = data.get('direction', '1way')
            mode      = data.get('mode',      'online')
            from_lang = data.get('from_lang', 'en')
            to_lang   = data.get('to_lang',   'ur')

            with _pi_ctrl['lock']:
                _pi_ctrl['stop'].set()
                t = _pi_ctrl['thread']
                if t and t.is_alive():
                    t.join(timeout=3)

                stop_ev = _threading.Event()
                _pi_ctrl['stop'] = stop_ev
                _pi_set(from_lang=from_lang, to_lang=to_lang, direction=direction,
                        started_at=_time.time(), translation_count=0, state='idle')

                target = _run_2way if direction == '2way' else _run_1way
                new_thread = _threading.Thread(
                    target=target,
                    args=(mode, from_lang, to_lang, stop_ev),
                    daemon=True,
                    name=f'pi-{direction}',
                )
                _pi_ctrl['thread'] = new_thread
                new_thread.start()

            return jsonify({'success': True, 'direction': direction,
                            'mode': mode, 'from_lang': from_lang, 'to_lang': to_lang})

        @app.route('/pi/stop', methods=['POST'])
        def api_pi_stop():
            with _pi_ctrl['lock']:
                _pi_ctrl['stop'].set()
            _pi_set(state='idle')
            return jsonify({'success': True})

        @app.route('/detect', methods=['POST'])
        def api_detect():
            if 'audio' not in request.files:
                return jsonify({'error': 'No audio file provided'}), 400
            audio_file = request.files['audio']
            import tempfile
            suffix   = os.path.splitext(audio_file.filename or 'audio.wav')[1] or '.wav'
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                    tmp_path = f.name
                    audio_file.save(tmp_path)
                from deepfake_checker import predict_ensemble
                ens = predict_ensemble(tmp_path)
                if 'error' in ens:
                    return jsonify({'error': ens['error']}), 500
                return jsonify({
                    'label':      ens['label'],
                    'confidence': round(ens['confidence'], 1),
                    'real_prob':  round(ens['real_prob'], 1),
                    'fake_prob':  round(ens['fake_prob'], 1),
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except Exception: pass

        @app.route('/detect_recording/<string:filename>', methods=['POST'])
        def api_detect_recording(filename):
            """Detect deepfake on an already-saved recording using ensemble vote."""
            path, _ = _find_recording(filename)
            if path is None:
                return jsonify({'error': f'Recording not found: {filename}'}), 404
            try:
                from deepfake_checker import predict_ensemble
                ens = predict_ensemble(path)
                if 'error' in ens:
                    return jsonify({'error': ens['error']}), 500
                return jsonify({
                    'label':      ens['label'],
                    'confidence': round(ens['confidence'], 1),
                    'real_prob':  round(ens['real_prob'], 1),
                    'fake_prob':  round(ens['fake_prob'], 1),
                    'filename':   filename,
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        print("\n[API] Flask server starting on http://0.0.0.0:5000")
        print("[API] Endpoints:")
        print("      POST   /translate           - translate text (online/offline)")
        print("      GET    /status              - Pi monitor status")
        print("      POST   /language            - set language from app")
        print("      GET    /recordings          - list recordings (?source=pi|cloud|all)")
        print("      GET    /recordings/<name>   - stream WAV file")
        print("      DELETE /recordings/<name>   - delete recording")
        print("      POST   /recordings/backup   - trigger cloud backup now")
        print("      POST   /detect              - deepfake voice detection (upload file)")
        print("      POST   /detect_recording/<name> - deepfake detect saved recording")
        print("      GET    /health              - server status")
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

    except ImportError:
        print("[ERROR] Flask not installed. Run: py -m pip install flask flask-cors")


# ──────────────────────────────────────────────────────────────────────────────
# DEMO MODE — no mic needed
# ──────────────────────────────────────────────────────────────────────────────

def demo_mode(recorder=None):
    """Type text -> translate -> speak. No microphone needed."""
    global TARGET_LANGUAGE

    print("\n" + "="*50)
    print("  DEMO MODE - Type to Translate")
    print("="*50)

    print("\nSelect TARGET language:")
    for k, (code, name) in SUPPORTED_LANGUAGES.items():
        print(f"  {k:>2}. {name} ({code})")

    choice = input("\nEnter number (default = 2 for Urdu): ").strip()
    if choice in SUPPORTED_LANGUAGES:
        TARGET_LANGUAGE = SUPPORTED_LANGUAGES[choice][0]
        lang_name = SUPPORTED_LANGUAGES[choice][1]
    else:
        TARGET_LANGUAGE = 'ur'
        lang_name = 'Urdu'

    print(f"\n[SET] Translating everything TO: {lang_name}")
    print("Type text and press Enter. Type 'exit' to quit.\n")

    while True:
        try:
            text = input("Input: ").strip()
            if text.lower() in ('exit', 'quit', 'q'):
                break
            if not text:
                continue
            src_lang   = _detect_lang(text)
            translated = translate_text(text, source='auto', target=TARGET_LANGUAGE)
            safe_print(f"[ORIGINAL]   {text}")
            safe_print(f"[TRANSLATED] {translated}")
            speak_text(translated, lang=TARGET_LANGUAGE)
            if recorder:
                recorder.log("AUTO", src_lang, text, TARGET_LANGUAGE, translated)
            print("-" * 40)
        except KeyboardInterrupt:
            break

    print("\n[DEMO] Exited.")


# ──────────────────────────────────────────────────────────────────────────────
# LIVE MIC MODE
# ──────────────────────────────────────────────────────────────────────────────

def live_mic_mode(recorder=None):
    """Continuous: mic listen -> translate -> speak"""
    global TARGET_LANGUAGE

    print("\n" + "="*50)
    print("  LIVE MIC MODE")
    print("="*50)

    print("\nSelect SOURCE language (you will speak this):")
    for k, (code, name) in SUPPORTED_LANGUAGES.items():
        print(f"  {k:>2}. {name} ({code})")
    src_choice  = input("\nEnter number (default = 1 for English): ").strip()
    src_lang    = SUPPORTED_LANGUAGES.get(src_choice, ('en', 'English'))[0]

    print("\nSelect TARGET language (translate TO):")
    tgt_choice  = input("Enter number (default = 2 for Urdu): ").strip()
    TARGET_LANGUAGE = SUPPORTED_LANGUAGES.get(tgt_choice, ('ur', 'Urdu'))[0]

    print(f"\n[SET] {src_lang.upper()} -> {TARGET_LANGUAGE.upper()}")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            full_pipeline(source_lang=src_lang, target_lang=TARGET_LANGUAGE, recorder=recorder)
        except KeyboardInterrupt:
            print("\n[MIC] Stopped.")
            break


# ──────────────────────────────────────────────────────────────────────────────
# TWO-WAY CONVERSATION MODE
# ──────────────────────────────────────────────────────────────────────────────

def two_way_conversation_mode(recorder=None):
    """
    Continuous two-way conversation:
      Person A speaks Lang A -> translated to Lang B -> spoken to Person B
      Person B speaks Lang B -> translated to Lang A -> spoken to Person A
      Repeats until Ctrl+C.
    """
    print("\n" + "="*50)
    print("  TWO-WAY CONVERSATION MODE")
    print("="*50)

    print("\nSelect Person A's language:")
    for k, (code, name) in SUPPORTED_LANGUAGES.items():
        print(f"  {k:>2}. {name} ({code})")
    a_choice = input("\nPerson A language (default = 1 English): ").strip()
    lang_a_code, lang_a_name = SUPPORTED_LANGUAGES.get(a_choice, ('en', 'English'))

    print("\nSelect Person B's language:")
    for k, (code, name) in SUPPORTED_LANGUAGES.items():
        print(f"  {k:>2}. {name} ({code})")
    b_choice = input("\nPerson B language (default = 2 Urdu): ").strip()
    lang_b_code, lang_b_name = SUPPORTED_LANGUAGES.get(b_choice, ('ur', 'Urdu'))

    print(f"\n[SET] Person A: {lang_a_name}  |  Person B: {lang_b_name}")
    print("Conversation starts now. Press Ctrl+C to stop.\n")

    turn = 'A'
    while True:
        try:
            if turn == 'A':
                print("\n" + "-"*45)
                print(f"  PERSON A — speak in {lang_a_name.upper()}")
                print("-"*45)
                text, audio, samplerate = listen_microphone(source_lang=lang_a_code)
                if text:
                    translated = translate_text(text, source=lang_a_code, target=lang_b_code)
                    safe_print(f"[Person A | {lang_a_name}]: {text}")
                    safe_print(f"[-> {lang_b_name}]          : {translated}")
                    speak_text(translated, lang=lang_b_code)
                    if recorder:
                        recorder.log(f"Person A ({lang_a_name})", lang_a_code, text, lang_b_code, translated,
                                     audio_data=audio, samplerate=samplerate)
                elif audio is not None and recorder:
                    recorder.log(f"Person A ({lang_a_name})", lang_a_code, '', lang_b_code, '',
                                 audio_data=audio, samplerate=samplerate)
                turn = 'B'
            else:
                print("\n" + "-"*45)
                print(f"  PERSON B — speak in {lang_b_name.upper()}")
                print("-"*45)
                text, audio, samplerate = listen_microphone(source_lang=lang_b_code)
                if text:
                    translated = translate_text(text, source=lang_b_code, target=lang_a_code)
                    safe_print(f"[Person B | {lang_b_name}]: {text}")
                    safe_print(f"[-> {lang_a_name}]          : {translated}")
                    speak_text(translated, lang=lang_a_code)
                    if recorder:
                        recorder.log(f"Person B ({lang_b_name})", lang_b_code, text, lang_a_code, translated,
                                     audio_data=audio, samplerate=samplerate)
                elif audio is not None and recorder:
                    recorder.log(f"Person B ({lang_b_name})", lang_b_code, '', lang_a_code, '',
                                 audio_data=audio, samplerate=samplerate)
                turn = 'A'
        except KeyboardInterrupt:
            print("\n[CONVERSATION] Ended.")
            break


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    live_mic_mode()
