#!/usr/bin/env bash
# Smart Headphone System — Pi Setup Script
# Run once after copying the project to the Pi.
#
#   cd /home/pi/FYP_project/lcd_ui
#   bash setup_pi.sh

set -euo pipefail
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
info() { echo -e "${YELLOW}[..]${NC}    $*"; }

PROJECT="/home/pi/FYP_project"

# ── 1. System packages ────────────────────────────────────────────────────────
info "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3-pip python3-tk python3-dev \
    build-essential gcc g++ \
    espeak-ng espeak-ng-data \
    ffmpeg alsa-utils mpg123 \
    portaudio19-dev libportaudio2 libsndfile1 \
    > /dev/null
ok "System packages ready."

# ── 2. Python packages ────────────────────────────────────────────────────────
info "Installing Python packages (takes 20-40 min on first run due to ARM64 compilation)..."

# Batch 1: fast pure-Python and pre-built packages
pip3 install --break-system-packages --no-cache-dir --timeout 300 \
    flask flask-cors requests \
    SpeechRecognition deep-translator gTTS pygame-ce \
    sounddevice vosk faster-whisper pyttsx3 \
    joblib matplotlib pydrive2 webrtcvad

# numpy/scipy/librosa/soundfile pinned to match the training environment exactly
# (see translate/requirements.txt) and installed BEFORE scikit-learn so it
# compiles against this exact numpy. An unpinned/mismatched audio stack
# produces measurably different feature vectors for the same audio file
# across versions (confirmed: ~30% difference in feature magnitude between
# librosa 0.11.0 and 0.10.2 for an identical file), which changes deepfake
# detection verdicts.
info "Installing pinned numpy/scipy/librosa/soundfile (must precede scikit-learn build)..."
pip3 install --break-system-packages --no-cache-dir --timeout 300 \
    'numpy==2.4.6' 'scipy==1.17.1' 'soundfile==0.13.1' 'librosa==0.11.0'

# scikit-learn MUST be compiled from source on ARM64/Python 3.13:
# PyPI pre-built wheels cause a Bus error due to ABI mismatch with Debian numpy.
# Pinned to match the training environment's scikit-learn version exactly (see
# translate/requirements.txt) — model .pkl files aren't guaranteed to load
# correctly on a scikit-learn version other than the one that trained them.
info "Compiling scikit-learn from source (this takes ~30 min on Pi)..."
pip3 install --break-system-packages --no-cache-dir --no-binary scikit-learn 'scikit-learn==1.8.0'

# Batch 2: argostranslate without stanza (stanza would pull torch/CUDA)
pip3 install --break-system-packages --no-cache-dir --no-deps argostranslate stanza
pip3 install --break-system-packages --no-cache-dir sentencepiece sacremoses

# CatBoost is part of the active deepfake ensemble (see translate/deepfake_checker.py
# _EXCLUDED_MODELS). PyPI doesn't reliably publish aarch64 Linux wheels for every
# release, so this may fall back to a source build (slow, memory-heavy) or fail
# outright — deepfake_checker.py already loads models individually and skips any
# that fail to import/unpickle, so a catboost failure here degrades the ensemble
# to 8 models rather than breaking the deploy. Non-fatal by design.
info "Installing catboost (optional — ensemble degrades gracefully if unavailable)..."
pip3 install --break-system-packages --no-cache-dir --timeout 300 'catboost==1.2.10' \
    || echo -e "${YELLOW}[WARN]${NC} catboost install failed — ensemble will run without it (8/9 models)."

ok "Python packages ready."

# ── 3. Audio: headphone jack output ──────────────────────────────────────────
info "Configuring audio..."
BOOT_CFG="/boot/firmware/config.txt"
[[ ! -f "$BOOT_CFG" ]] && BOOT_CFG="/boot/config.txt"
grep -q "dtparam=audio=on" "$BOOT_CFG" || echo "dtparam=audio=on" | sudo tee -a "$BOOT_CFG" > /dev/null

# Auto-detect the BCM2835 headphone jack card number (varies by Pi model/kernel)
HEADPHONE_CARD=$(aplay -l 2>/dev/null | grep -i 'bcm2835 Headphones\|Headphones' | head -1 | grep -oP 'card \K[0-9]+' || echo "2")
info "Detected headphone card: $HEADPHONE_CARD"

sudo tee /etc/asound.conf > /dev/null << EOF
defaults.pcm.card $HEADPHONE_CARD
defaults.pcm.device 0
defaults.ctl.card $HEADPHONE_CARD
EOF

# Set volume using the PCM control (BCM2835 uses PCM Playback Volume, not Master)
amixer -c "$HEADPHONE_CARD" cset numid=1 85% 2>/dev/null || \
    amixer -c "$HEADPHONE_CARD" sset PCM 85% 2>/dev/null || \
    amixer sset Master 85% unmute 2>/dev/null || true
amixer -c "$HEADPHONE_CARD" cset numid=2 on 2>/dev/null || true
ok "Audio configured (3.5mm headphone jack, card $HEADPHONE_CARD)."

# ── 4. Vosk model (English STT) ───────────────────────────────────────────────
VOSK_DIR="$PROJECT/translate/vosk-model-small-en-us"
if [[ ! -d "$VOSK_DIR" ]]; then
    info "Downloading Vosk English model (~40 MB)..."
    wget -q -O /tmp/vosk.zip \
        "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    unzip -q /tmp/vosk.zip -d "$PROJECT/translate/"
    mv "$PROJECT/translate/vosk-model-small-en-us-"* "$VOSK_DIR" 2>/dev/null || true
    rm -f /tmp/vosk.zip
    ok "Vosk model installed."
else
    ok "Vosk model already present."
fi

# ── 5. Desktop autostart ──────────────────────────────────────────────────────
info "Setting up desktop autostart..."
AUTOSTART_DIR="/home/pi/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/smart-headphone.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Smart Headphone
Comment=Smart Headphone Translation and Deepfake Detection System
Exec=python3 $PROJECT/lcd_ui/app.py
X-GNOME-Autostart-enabled=true
EOF

ok "Autostart configured — app.py will launch on every Pi boot."

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo ""
echo "  To run manually right now (without rebooting):"
echo "    python3 $PROJECT/lcd_ui/app.py"
echo ""
echo "  After rebooting, the app opens automatically."
echo "  Connect your Android app to:"
echo "    http://$(hostname -I | awk '{print $1}'):5000"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
