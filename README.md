# Smart Headphone: Real-Time Translation & Deepfake Voice Detection

Final Year Project — a wearable headphone system that performs **real-time multilingual speech translation** and **AI-generated (deepfake) voice detection** using a Raspberry Pi backend and a Flutter mobile app.

---

## System Architecture

```
Flutter App (Android / iOS)
        ↕  HTTP REST API
Raspberry Pi — Python / Flask  (port 5000)
    ├── Speech-to-Text    (online: Google Speech  |  offline: Vosk / Whisper)
    ├── Translation       (online: GoogleTranslator  |  offline: argostranslate)
    ├── Text-to-Speech    (online: gTTS + pygame  |  offline: espeak-ng / pyttsx3)
    ├── Voice Recorder    (saves timestamped WAV files)
    ├── Deepfake Detector (9-model ML ensemble)
    └── Cloud Backup      (Google Drive via pydrive2)
```

---

## Features

- **34 languages** supported (English, Urdu, Arabic, French, German, Chinese, Hindi, Spanish, and 26 more)
- **Online & offline modes** — works without internet via Vosk + Whisper + argostranslate
- **1-Way and 2-Way Pi translation sessions** controlled from the mobile app
- **Deepfake voice detection** — 206-dimension acoustic feature extraction + 9-classifier ensemble (SVM, Random Forest, Gradient Boosting, Extra Trees, AdaBoost, Logistic Regression, KNN, MLP, CatBoost)
- **Real-time detection** — 2 s window, 1 s stride, temporal smoothing
- **Google Drive backup** of session recordings (automatic, background thread)
- **LCD display** support on Raspberry Pi

---

## Repository Structure

```
FYP_project/
├── Application/
│   └── frontend/smart_headphone_app/   Flutter mobile app
│       └── lib/
│           ├── main.dart
│           ├── providers/              State management (Provider)
│           ├── screens/                5 app screens
│           ├── services/               HTTP service layer
│           └── utils/                  Theme + language list
│
├── translate/                          Python Flask backend (runs on Pi)
│   ├── run_flask.py                    Entry point — starts the API server
│   ├── main_controller.py              CLI menu
│   ├── mode2_online_translation.py     Flask API + online STT/TTS
│   ├── mode1_offline_translation.py    Fully offline pipeline
│   ├── deepfake_checker.py             Production ensemble detector
│   ├── conversation_recorder.py        WAV recording per speaker turn
│   ├── cloud_backup.py                 Google Drive upload
│   └── requirements.txt
│
├── module-1/deepfake_detection/        ML training pipeline
│   ├── preprocess.py                   Feature extraction (librosa, 206-dim)
│   ├── train_multi_model.py            Train 9 sklearn classifiers
│   ├── realtime_detect.py              Live mic detection loop
│   ├── retrain_pipeline.py             Orchestrate Urdu fake gen + retrain
│   ├── generate_urdu_fakes.py          Generate Urdu fake audio samples
│   ├── balance_dataset.py              Undersample to 1:1 real:fake
│   └── batch_predict.py               Batch file prediction
│
├── lcd_ui/                             Raspberry Pi LCD display interface
│   ├── app.py                          Main LCD app
│   ├── lcd_controller.py              Display controller
│   └── services/                       Backend service connectors
│
└── docs/
    ├── SmartHeadphone_Research_Paper.pdf   Published research paper
    └── SmartHeadphone_Research_Paper.tex   LaTeX source
```

---

## Setup

### Backend (Raspberry Pi)

**Requirements:** Python 3.10+, pip

```bash
cd translate
pip install -r requirements.txt
python run_flask.py          # starts Flask API on port 5000
```

**Offline mode** additionally requires:
- [Vosk small English model](https://alphacephei.com/vosk/models) — extract to `translate/vosk-model-small-en-us/`
- OpenAI Whisper: `pip install openai-whisper`
- argostranslate: `pip install argostranslate`
- espeak-ng: `sudo apt install espeak-ng`

### Flutter Mobile App

**Requirements:** Flutter 3.x, Dart 3.x

```bash
cd Application/frontend/smart_headphone_app
flutter pub get
flutter run
```

Set the server URL in the app's **Settings** screen to your Raspberry Pi's local IP, e.g. `http://192.168.1.X:5000`.

### ML Training Pipeline

**Requirements:** Python 3.10+, librosa, scikit-learn

```bash
cd module-1/deepfake_detection
pip install librosa scikit-learn catboost imbalanced-learn
```

1. Download [ASVspoof 2019 LA dataset](https://datashare.ed.ac.uk/handle/10283/3336) and place FLAC files in `data/`
2. Run `python preprocess.py` to extract features
3. Run `python train_multi_model.py` to train all 9 models → saved to `models/`

---

## Deepfake Detection — Feature Set (206 dimensions)

| Feature | Dimensions | Why it catches AI voices |
|---------|-----------|--------------------------|
| MFCC (mean, std, max × 40) | 120 | Timbral texture |
| Delta MFCC mean × 40 | 40 | AI voices have unnaturally smooth transitions |
| Chroma STFT mean | 12 | Harmonic content |
| Tonnetz mean | 6 | Tonal centroid |
| Spectral contrast mean | 7 | Spectral dynamics |
| IMFCC (inverse mel) | 13 | High-frequency artefacts |
| Jitter + shimmer | 2 | AI voices have near-zero jitter, flat amplitude |
| ZCR, RMS, rolloff, pitch, bandwidth | 6 | Prosodic naturalness |

**Ensemble voting** (9 classifiers): majority weighted vote with physics-based fallback rules for low-confidence cases.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/translate` | Translate text |
| GET | `/status` | Pi session state |
| POST | `/pi/start` | Start autonomous translate loop |
| POST | `/pi/stop` | Stop session |
| GET | `/recordings` | List saved WAV files |
| GET | `/recordings/<name>` | Stream a recording |
| DELETE | `/recordings/<name>` | Delete a recording |
| POST | `/recordings/backup` | Trigger Google Drive backup |
| POST | `/detect` | Upload audio for deepfake detection |
| POST | `/detect_recording/<name>` | Detect saved recording |
| GET | `/health` | Server health + feature list |
| GET | `/languages` | Supported language list |

---

## Research

The full research paper is available in `docs/SmartHeadphone_Research_Paper.pdf`.

The deepfake detection module is trained on the [ASVspoof 2019](https://www.asvspoof.org/) dataset (Logical Access partition) supplemented with locally generated Urdu synthetic speech.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Mobile App | Flutter, Dart, Provider |
| Backend | Python, Flask, SpeechRecognition |
| Online STT | Google Speech API |
| Offline STT | Vosk (English), OpenAI Whisper (Urdu) |
| Translation | deep-translator / argostranslate |
| TTS | gTTS + pygame / espeak-ng / pyttsx3 |
| ML / Features | librosa, scikit-learn, CatBoost |
| Cloud Backup | Google Drive (pydrive2) |
| Hardware | Raspberry Pi 4, USB microphone, speaker, LCD |
