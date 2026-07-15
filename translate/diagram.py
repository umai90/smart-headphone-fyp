"""
diagram.py  —  Architecture & Data-Flow Diagram Generator
Smart Headphone Translation System
Run: py diagram.py
Outputs: system_diagram.txt  +  system_diagram.png
"""

import os
import sys

# The ASCII diagram below is full of box-drawing/arrow characters outside
# cp1252 (Windows' default console codepage), which crashes plain print()
# with UnicodeEncodeError. Force UTF-8 stdout so this runs on any console.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_DIR = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────────────────────────────────────────────────────────
#  ASCII DIAGRAM
# ─────────────────────────────────────────────────────────────────────────────

ASCII = r"""
╔══════════════════════════════════════════════════════════════════════════════════════╗
║        SMART HEADPHONE TRANSLATION SYSTEM — COMPLETE ARCHITECTURE                  ║
║        Version 1.0.0                                                               ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

                     ┌──────────────────────────────────────────┐
                     │           main_controller.py              │
                     │   ┌──────────────────────────────────┐    │
                     │   │            MAIN MENU              │    │
                     │   │  1. Auto Mode (recommended)       │    │
                     │   │  2. Force Offline Mode            │    │
                     │   │  3. Force Online Mode             │    │
                     │   │  4. Flask API Server              │    │
                     │   │  5. Demo Mode (no mic)            │    │
                     │   │  6. Setup Offline Packages        │    │
                     │   │  7. Test Recorded Voices (Deepfake│    │
                     │   │  8. Exit                          │    │
                     │   └──────────────┬───────────────────┘    │
                     │            ┌─────▼──────┐                 │
                     │            │  Internet  │                 │
                     │            │  Check?    │                 │
                     │            └──┬──────┬──┘                 │
                     └──────────────┼──────┼────────────────────┘
                              YES ──┘      └── NO
                              │                    │
         ┌────────────────────▼──┐     ┌───────────▼──────────────────┐
         │     ONLINE MODE        │     │        OFFLINE MODE           │
         │  mode2_online_        │     │    mode1_offline_             │
         │  translation.py       │     │    translation.py             │
         └──────────┬─────────────┘     └────────────┬─────────────────┘
                    │                                 │
   ┌────────────────▼──────────────┐  ┌──────────────▼──────────────────┐
   │       ONLINE PIPELINE          │  │        OFFLINE PIPELINE          │
   │                                │  │                                  │
   │  [1/3] SPEECH TO TEXT          │  │  [1/3] SPEECH TO TEXT            │
   │  ┌────────────────────────┐    │  │  ┌───────────────────────────┐   │
   │  │ sounddevice records    │    │  │  │ sounddevice records mic   │   │
   │  │ SpeechRecognition +    │    │  │  │ English → Vosk (offline)  │   │
   │  │ Google Speech API      │    │  │  │ Urdu    → Whisper (local) │   │
   │  │ Fallback: type text    │    │  │  │ Fallback: type text       │   │
   │  └────────────┬───────────┘    │  │  └──────────────┬────────────┘   │
   │               │ returns        │  │                 │ returns        │
   │               │ (text,audio,sr)│  │                 │ (text,audio,sr)│
   │               │                │  │                 │                │
   │  [2/3] TRANSLATE               │  │  [2/3] TRANSLATE                 │
   │  ┌────────────────────────┐    │  │  ┌───────────────────────────┐   │
   │  │ deep-translator        │    │  │  │ argostranslate (offline   │   │
   │  │ (Google Translate API) │    │  │  │ neural model)             │   │
   │  │ 10 languages supported │    │  │  │ Fallback: phrase dict     │   │
   │  └────────────┬───────────┘    │  │  │ EN ↔ UR only             │   │
   │               │                │  │  └──────────────┬────────────┘   │
   │  [3/3] TEXT TO SPEECH          │  │  [3/3] TEXT TO SPEECH            │
   │  ┌────────────────────────┐    │  │  ┌───────────────────────────┐   │
   │  │ gTTS → MP3 → play      │    │  │  │ Urdu  → espeak-ng (WAV)  │   │
   │  │ pyttsx3 fallback       │    │  │  │ English → pyttsx3         │   │
   │  └────────────┬───────────┘    │  │  └──────────────┬────────────┘   │
   └───────────────┼────────────────┘  └─────────────────┼────────────────┘
                   │                                      │
                   └──────────────────┬───────────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │   conversation_recorder.py│
                         │   recorder.log(speaker,   │
                         │     src_lang, src_text,   │
                         │     tgt_lang, tgt_text,   │
                         │     audio_data, samplerate)│
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼──────────────────────────┐
                         │  recordings/  (flat — no subfolders)  │
                         │  ├── 20260418_143022_001_Person_A_en.wav │
                         │  ├── 20260418_143022_002_Person_B_ur.wav │
                         │  └── YYYYMMDD_HHMMSS_NNN_SPEAKER_lang.wav│
                         └───────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    MODES OF OPERATION — DATA FLOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌─────────────────────────────────────────────────────────────────────┐
  │  A) SINGLE PERSON — Live Mic or Demo                                │
  │                                                                     │
  │  [MIC/TYPE] ──► STT (voice→text) ──► TRANSLATE ──► TTS (speak)     │
  │                     │                                               │
  │                     └──► audio + text ──► RECORDER                 │
  │                            saves: entry_NNN_AUTO_en.wav + log.txt  │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │  B) TWO PERSON — Conversation Mode                                  │
  │                                                                     │
  │  PERSON A                              PERSON B                     │
  │  speaks English                        speaks Urdu                  │
  │      │                                     │                        │
  │      ▼                                     ▼                        │
  │  STT (Vosk/Google EN)               STT (Whisper/Google UR)        │
  │      │                                     │                        │
  │      ▼                                     ▼                        │
  │  Translate EN → UR                  Translate UR → EN              │
  │      │                                     │                        │
  │      ▼                                     ▼                        │
  │  TTS speaks UR          ◄──────►   TTS speaks EN                   │
  │  Person B hears                     Person A hears                  │
  │      │                                     │                        │
  │      ▼                                     ▼                        │
  │  entry_NNN_Person_A_en.wav         entry_NNN_Person_B_ur.wav       │
  │  (Person A's real voice saved)     (Person B's real voice saved)   │
  └─────────────────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    RECORDING OUTPUT EXAMPLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  recordings/   (flat — all files in one folder, no subfolders)
  ├── 20260418_143022_001_Person_A_en.wav  ← Person A English voice
  ├── 20260418_143022_002_Person_B_ur.wav  ← Person B Urdu voice
  ├── 20260418_150500_001_Person_A_en.wav  ← next session
  └── ...
  Filename format: YYYYMMDD_HHMMSS_NNN_Speaker_lang.wav
    YYYYMMDD_HHMMSS = session start time (groups entries from same session)
    NNN             = entry number within session
    Speaker         = Person_A / Person_B / AUTO
    lang            = en / ur / ar / ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    MODULE DEPENDENCY MAP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  main_controller.py
  ├── mode1_offline_translation.py
  │   ├── vosk              ← English STT (fully offline)
  │   ├── openai-whisper    ← Urdu STT (model cached after 1st download)
  │   ├── argostranslate    ← EN↔UR translation (fully offline)
  │   ├── pyttsx3           ← English TTS
  │   ├── espeak-ng         ← Urdu TTS (system binary)
  │   ├── sounddevice       ← mic recording + WAV playback
  │   └── numpy             ← audio resampling (native rate → 16kHz)
  │
  ├── mode2_online_translation.py
  │   ├── SpeechRecognition + Google Speech API  ← STT (needs internet)
  │   ├── deep-translator + Google Translate     ← 10-language translation
  │   ├── gTTS                                   ← online TTS (MP3)
  │   ├── pyttsx3                                ← TTS fallback
  │   ├── flask + flask-cors                     ← REST API for Android
  │   ├── sounddevice + wave                     ← mic recording
  │   └── numpy + tempfile                       ← audio handling
  │
  └── conversation_recorder.py
      ├── wave      ← write PCM audio to .wav files
      ├── numpy     ← int16 array → bytes conversion
      ├── os        ← session folder management
      └── datetime  ← timestamps

  FLASK REST API  (Mode 2 — Android App endpoint):
  ┌─────────────────────────────────────────────────────────────────┐
  │  POST /translate  { text, source, target } → { translated }    │
  │  GET  /languages  → { 1:English, 2:Urdu, 3:Arabic, ... }      │
  │  GET  /health     → { status: ok, mode: online }               │
  │  Host: 0.0.0.0:5000                                            │
  └─────────────────────────────────────────────────────────────────┘
"""


def save_ascii():
    path = os.path.join(_DIR, "system_diagram.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(ASCII)
    print(f"[SAVED] ASCII diagram  →  {path}")


# ─────────────────────────────────────────────────────────────────────────────
#  PNG DIAGRAM  (requires matplotlib)
# ─────────────────────────────────────────────────────────────────────────────

# Colour palette
C_HEADER   = "#1a1a2e"   # dark navy
C_CTRL     = "#16213e"   # dark blue
C_ONLINE   = "#0f3460"   # medium blue
C_OFFLINE  = "#533483"   # purple
C_STT      = "#e94560"   # red-pink
C_TRANS    = "#f5a623"   # amber
C_TTS      = "#27ae60"   # green
C_REC      = "#2980b9"   # teal-blue
C_STORE    = "#1abc9c"   # mint
C_ARROW    = "#555555"
C_DIAMOND  = "#c0392b"
C_PERSON   = "#7f8c8d"


def _box(ax, x, y, w, h, lines, fc, ec="#222", fs=7.8, tc="white",
         bold=False, alpha=1.0, radius=0.3):
    from matplotlib.patches import FancyBboxPatch
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad={radius}",
        facecolor=fc, edgecolor=ec, linewidth=1.3,
        zorder=3, alpha=alpha
    )
    ax.add_patch(patch)
    if isinstance(lines, str):
        lines = [lines]
    n = len(lines)
    for i, line in enumerate(lines):
        yy = y + h - (i + 1) * h / (n + 1) + h / (n + 1) / 2
        # adjust to vertically centre the block
        yy = y + h / 2 + (n / 2 - i - 0.5) * (h / (n + 1.2))
        ax.text(x + w / 2, yy, line,
                ha="center", va="center",
                fontsize=fs, color=tc,
                fontweight="bold" if (bold or i == 0) else "normal",
                zorder=4)


def _diamond(ax, cx, cy, hw, hh, label, fc, tc="white", fs=8):
    import matplotlib.patches as mpatches
    from matplotlib.patches import Polygon
    pts = [(cx, cy + hh), (cx + hw, cy), (cx, cy - hh), (cx - hw, cy)]
    diamond = Polygon(pts, closed=True, facecolor=fc, edgecolor="#222",
                      linewidth=1.3, zorder=3)
    ax.add_patch(diamond)
    ax.text(cx, cy, label, ha="center", va="center",
            fontsize=fs, color=tc, fontweight="bold", zorder=4)


def _arrow(ax, x1, y1, x2, y2, label="", color=C_ARROW, lw=1.5):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="->", color=color,
                        lw=lw, connectionstyle="arc3,rad=0.0"),
        zorder=5
    )
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + 0.15, my, label, fontsize=6.5, color=color, zorder=6)


def _curved_arrow(ax, x1, y1, x2, y2, rad=0.25, color=C_ARROW, lw=1.5):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="->", color=color, lw=lw,
                        connectionstyle=f"arc3,rad={rad}"),
        zorder=5
    )


def _line(ax, x1, y1, x2, y2, color=C_ARROW, lw=1.2, ls="-"):
    ax.plot([x1, x2], [y1, y2], color=color, lw=lw, linestyle=ls, zorder=2)


def generate_png():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    FW, FH = 22, 26
    fig = plt.figure(figsize=(FW, FH), facecolor="#f0f4f8")
    ax  = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, FW)
    ax.set_ylim(0, FH)
    ax.axis("off")
    ax.set_facecolor("#f0f4f8")

    # ── Title ────────────────────────────────────────────────────────────────
    _box(ax, 0.3, 24.5, FW - 0.6, 1.3,
         ["SMART HEADPHONE TRANSLATION SYSTEM — ARCHITECTURE & DATA FLOW",
          "Version 1.0.0"],
         C_HEADER, fs=9.5, bold=True, radius=0.2)

    # ── Main Controller ───────────────────────────────────────────────────────
    _box(ax, 7, 21.8, 8, 2.4,
         ["main_controller.py",
          "MAIN MENU: 1.Auto  2.Offline  3.Online",
          "4.Flask API  5.Demo  6.Setup  7.Deepfake  8.Exit",
          "ConversationRecorder started / stopped here"],
         C_CTRL, fs=8.2, radius=0.3)

    _arrow(ax, 11, 21.8, 11, 21.1)

    # ── Internet diamond ─────────────────────────────────────────────────────
    _diamond(ax, 11, 20.4, 1.5, 0.65, "Internet?", C_DIAMOND, fs=8)

    # YES → right branch  /  NO → left branch
    _arrow(ax, 12.5, 20.4, 17.5, 20.4, "YES →", color="#27ae60", lw=2)
    _arrow(ax, 9.5,  20.4,  4.5, 20.4, "← NO",  color="#e74c3c", lw=2)

    # ── ONLINE MODE box ───────────────────────────────────────────────────────
    _box(ax, 14.5, 18.8, 7, 1.35,
         ["MODE 2 — ONLINE", "mode2_online_translation.py"],
         C_ONLINE, fs=8.5, radius=0.3)
    _arrow(ax, 18, 20.4, 18, 20.15)

    # ── OFFLINE MODE box ──────────────────────────────────────────────────────
    _box(ax, 0.5, 18.8, 7, 1.35,
         ["MODE 1 — OFFLINE", "mode1_offline_translation.py"],
         C_OFFLINE, fs=8.5, radius=0.3)
    _arrow(ax, 4, 20.4, 4, 20.15)

    # ═════════════════════════════════════════════════════════════════════════
    #  PIPELINE COLUMNS
    # ═════════════════════════════════════════════════════════════════════════

    # ── [OFFLINE] STEP 1 ─────────────────────────────────────────────────────
    _arrow(ax, 4, 18.8, 4, 18.3)
    _box(ax, 0.5, 16.5, 7, 1.65,
         ["[1/3] SPEECH TO TEXT  (Offline)",
          "sounddevice  →  mic recording (16 kHz)",
          "English  →  Vosk  (fully offline)",
          "Urdu     →  Whisper  (local cache)",
          "returns: (text, audio_pcm, samplerate)"],
         C_STT, fs=7.5, radius=0.25)

    _arrow(ax, 4, 16.5, 4, 15.95)

    # ── [OFFLINE] STEP 2 ─────────────────────────────────────────────────────
    _box(ax, 0.5, 14.3, 7, 1.5,
         ["[2/3] TRANSLATE  (Offline)",
          "argostranslate  (offline neural model)",
          "EN ↔ UR  only",
          "Fallback: built-in phrase dictionary"],
         C_TRANS, fs=7.5, radius=0.25)

    _arrow(ax, 4, 14.3, 4, 13.75)

    # ── [OFFLINE] STEP 3 ─────────────────────────────────────────────────────
    _box(ax, 0.5, 12.1, 7, 1.5,
         ["[3/3] TEXT TO SPEECH  (Offline)",
          "Urdu    →  espeak-ng  →  WAV  →  sounddevice",
          "English →  pyttsx3  (SAPI voice)",
          "Fully offline — no internet needed"],
         C_TTS, fs=7.5, radius=0.25)

    # ── [ONLINE] STEP 1 ──────────────────────────────────────────────────────
    _arrow(ax, 18, 18.8, 18, 18.3)
    _box(ax, 14.5, 16.5, 7, 1.65,
         ["[1/3] SPEECH TO TEXT  (Online)",
          "sounddevice  →  mic recording (16 kHz)",
          "SpeechRecognition  +  Google Speech API",
          "10 languages  (en, ur, ar, fr, de, hi, ...)",
          "returns: (text, audio_pcm, samplerate)"],
         C_STT, fs=7.5, radius=0.25)

    _arrow(ax, 18, 16.5, 18, 15.95)

    # ── [ONLINE] STEP 2 ──────────────────────────────────────────────────────
    _box(ax, 14.5, 14.3, 7, 1.5,
         ["[2/3] TRANSLATE  (Online)",
          "deep-translator  →  Google Translate API",
          "10 languages  (any ↔ any)",
          "Auto language detection supported"],
         C_TRANS, fs=7.5, radius=0.25)

    _arrow(ax, 18, 14.3, 18, 13.75)

    # ── [ONLINE] STEP 3 ──────────────────────────────────────────────────────
    _box(ax, 14.5, 12.1, 7, 1.5,
         ["[3/3] TEXT TO SPEECH  (Online)",
          "gTTS  →  MP3  →  Windows default player",
          "pyttsx3 fallback (if gTTS fails)",
          "Supports all 10 output languages"],
         C_TTS, fs=7.5, radius=0.25)

    # ── Arrows into recorder ─────────────────────────────────────────────────
    _arrow(ax,  4,  12.1,  8,  11.3)
    _arrow(ax, 18,  12.1, 14,  11.3)

    # ── ConversationRecorder ─────────────────────────────────────────────────
    _box(ax, 6.5, 9.9, 9, 1.25,
         ["conversation_recorder.py",
          "recorder.log(speaker, src_lang, src_text, tgt_lang, tgt_text, audio_data, samplerate)"],
         C_REC, fs=8, radius=0.3)

    _arrow(ax, 11, 9.9, 11, 9.35)

    # ── Session folder ───────────────────────────────────────────────────────
    _box(ax, 5.5, 7.8, 11, 1.4,
         ["recordings/  (flat — no subfolders)",
          "YYYYMMDD_HHMMSS_001_Person_A_en.wav  +  _002_Person_B_ur.wav  + ..."],
         C_STORE, fs=8, radius=0.3)

    # ═════════════════════════════════════════════════════════════════════════
    #  TWO-PERSON FLOW  (lower half)
    # ═════════════════════════════════════════════════════════════════════════

    # Section label
    ax.text(11, 7.3, "— TWO-PERSON CONVERSATION FLOW —",
            ha="center", va="center", fontsize=9.5,
            color=C_CTRL, fontweight="bold", zorder=4)

    # Person A
    _box(ax, 0.5, 5.4, 4.5, 1.0,
         ["PERSON A", "speaks English"],
         C_PERSON, fs=8.5, radius=0.3)

    # Person B
    _box(ax, 17, 5.4, 4.5, 1.0,
         ["PERSON B", "speaks Urdu"],
         C_PERSON, fs=8.5, radius=0.3)

    # STT blocks
    _arrow(ax, 2.75, 5.4, 2.75, 4.8)
    _box(ax, 0.5, 3.8, 4.5, 0.9,
         ["STT (English)", "Vosk / Google Speech"],
         C_STT, fs=7.8, radius=0.25)

    _arrow(ax, 19.25, 5.4, 19.25, 4.8)
    _box(ax, 17, 3.8, 4.5, 0.9,
         ["STT (Urdu)", "Whisper / Google Speech"],
         C_STT, fs=7.8, radius=0.25)

    # Translate blocks
    _arrow(ax, 2.75, 3.8, 2.75, 3.2)
    _box(ax, 0.5, 2.2, 4.5, 0.9,
         ["Translate EN → UR", "argostranslate / deep-translator"],
         C_TRANS, fs=7.8, radius=0.25)

    _arrow(ax, 19.25, 3.8, 19.25, 3.2)
    _box(ax, 17, 2.2, 4.5, 0.9,
         ["Translate UR → EN", "argostranslate / deep-translator"],
         C_TRANS, fs=7.8, radius=0.25)

    # TTS blocks + who hears
    _arrow(ax, 2.75, 2.2, 2.75, 1.6)
    _box(ax, 0.5, 0.7, 4.5, 0.8,
         ["TTS speaks UR  →  Person B hears",
          "voice clip saved: PersonA_en.wav"],
         C_TTS, fs=7.2, radius=0.25)

    _arrow(ax, 19.25, 2.2, 19.25, 1.6)
    _box(ax, 17, 0.7, 4.5, 0.8,
         ["TTS speaks EN  →  Person A hears",
          "voice clip saved: PersonB_ur.wav"],
         C_TTS, fs=7.2, radius=0.25)

    # Cross-arrows (A's output heard by B and vice versa)
    _curved_arrow(ax, 5.0,  1.1, 17.0, 1.1, rad=-0.4,
                  color="#27ae60", lw=1.8)
    _curved_arrow(ax, 17.0, 0.8,  5.0, 0.8, rad=-0.4,
                  color="#e74c3c", lw=1.8)

    # Recorder arrows from Person A and B flows
    _arrow(ax,  2.75, 0.7,  8.5,  7.9)
    _arrow(ax, 19.25, 0.7, 13.5,  7.9)

    # ── Single-person flow note ───────────────────────────────────────────────
    _box(ax, 7.5, 5.4, 7, 1.7,
         ["SINGLE PERSON FLOW",
          "Speak (mic) or Type (demo)",
          "   ↓",
          "STT → Translate → TTS → Recorder",
          "entry_NNN_AUTO_lang.wav + log.txt"],
         C_CTRL, fs=7.8, tc="#ecf0f1", radius=0.3)

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(color=C_STT,    label="Speech-to-Text (STT)"),
        mpatches.Patch(color=C_TRANS,  label="Translation Engine"),
        mpatches.Patch(color=C_TTS,    label="Text-to-Speech (TTS)"),
        mpatches.Patch(color=C_REC,    label="Conversation Recorder"),
        mpatches.Patch(color=C_STORE,  label="Session Folder / WAV Files"),
        mpatches.Patch(color=C_ONLINE, label="Online Mode (internet)"),
        mpatches.Patch(color=C_OFFLINE,label="Offline Mode (no internet)"),
    ]
    ax.legend(handles=legend_items, loc="lower right",
              fontsize=8, framealpha=0.9,
              bbox_to_anchor=(0.99, 0.01))

    out = os.path.join(_DIR, "system_diagram.png")
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"[SAVED] PNG  diagram  →  {out}")


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def _safe_print(text):
    """Print text safely on any Windows console encoding."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Encode to UTF-8 bytes and write directly to the binary stream
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    # Reconfigure stdout to UTF-8 if possible (Python 3.7+)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    _safe_print(ASCII)
    save_ascii()

    try:
        generate_png()
        print("\n[DONE] Open system_diagram.png for the full visual diagram.")
    except ImportError:
        print("\n[INFO] matplotlib not found — only ASCII saved.")
        print("       Install with: py -m pip install matplotlib")
    except Exception as e:
        print(f"\n[PNG ERROR] {e}")
