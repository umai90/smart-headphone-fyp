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
    python3-pip python3-tk \
    espeak-ng espeak-ng-data \
    ffmpeg alsa-utils mpg123 \
    portaudio19-dev libportaudio2 libsndfile1 \
    > /dev/null
ok "System packages ready."

# ── 2. Python packages ────────────────────────────────────────────────────────
info "Installing Python packages (takes a few minutes on first run)..."
pip3 install --break-system-packages -q \
    flask flask-cors requests \
    SpeechRecognition deep-translator gTTS pygame-ce \
    sounddevice vosk openai-whisper argostranslate pyttsx3 \
    librosa scikit-learn joblib matplotlib pydrive2 webrtcvad
ok "Python packages ready."

# ── 3. Audio: headphone jack output ──────────────────────────────────────────
info "Configuring audio..."
BOOT_CFG="/boot/firmware/config.txt"
[[ ! -f "$BOOT_CFG" ]] && BOOT_CFG="/boot/config.txt"
grep -q "dtparam=audio=on" "$BOOT_CFG" || echo "dtparam=audio=on" | sudo tee -a "$BOOT_CFG" > /dev/null

# Default output to 3.5mm headphone jack (device 0 = built-in)
sudo tee /etc/asound.conf > /dev/null << 'EOF'
defaults.pcm.card 0
defaults.pcm.device 0
defaults.ctl.card 0
EOF

# Set volume to 85%
amixer sset Master 85% unmute 2>/dev/null || true
ok "Audio configured (3.5mm headphone jack)."

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
