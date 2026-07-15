#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Smart Headphone System — Raspberry Pi 4B Setup Script
# Run once after a fresh Raspberry Pi OS (Bookworm / Bullseye) install.
#
# Usage:
#   chmod +x install.sh
#   sudo bash install.sh
#
# What it does:
#   1. Installs all Python + system dependencies
#   2. Configures the 3.5" / 5" SPI TFT display (dtoverlay)
#   3. Sets up audio (headphones out + USB mic or built-in mic)
#   4. Installs and enables systemd services (Flask API + LCD UI)
#   5. Calibrates the touchscreen
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && error "Run as root: sudo bash install.sh"

PROJECT_DIR="/home/pi/FYP_project"
LCD_DIR="$PROJECT_DIR/lcd_ui"
TRANSLATE_DIR="$PROJECT_DIR/translate"

# ─────────────────────────── 1. System packages ───────────────────────────────
info "Updating package lists..."
apt-get update -qq

info "Installing system dependencies..."
apt-get install -y --no-install-recommends \
    python3-pip python3-pygame python3-requests \
    python3-numpy python3-scipy \
    libportaudio2 libsndfile1 \
    espeak-ng espeak-ng-data \
    ffmpeg sox \
    alsa-utils pulseaudio pulseaudio-utils \
    libts-dev tslib evtest \
    git build-essential \
    fontconfig \
    > /dev/null 2>&1
info "System packages installed."

# ─────────────────────────── 2. Python pip packages ──────────────────────────
info "Installing Python packages (this may take a few minutes)..."
pip3 install --break-system-packages --quiet \
    flask flask-cors \
    requests \
    SpeechRecognition \
    deep-translator \
    gTTS \
    pygame-ce \
    sounddevice \
    vosk \
    faster-whisper \
    argostranslate \
    pyttsx3 \
    joblib \
    matplotlib \
    pydrive2 \
    webrtcvad \
    evdev \
    2>&1 | grep -v "^$" || true

# numpy/scipy/librosa/soundfile pinned to match the training environment exactly
# (see translate/requirements.txt), installed before scikit-learn so it builds
# against this exact numpy. NOTE: this script also apt-installs python3-numpy /
# python3-scipy above (system packages) which can shadow these pinned pip
# versions — setup_pi.sh (the actually-used deploy path) does not do this.
info "Installing pinned numpy/scipy/librosa/soundfile (must precede scikit-learn build)..."
pip3 install --break-system-packages --no-cache-dir --timeout 300 \
    'numpy==2.4.6' 'scipy==1.17.1' 'soundfile==0.13.1' 'librosa==0.11.0'

# scikit-learn MUST be compiled from source on ARM64/Python 3.13 and pinned to
# match the training environment: PyPI pre-built wheels cause a Bus error from
# ABI mismatch with the numpy build on this platform, and an unpinned/mismatched
# version risks failing to unpickle models trained with a different scikit-learn.
# Keep this version in sync with translate/requirements.txt (the training-side pin).
info "Compiling scikit-learn from source (this takes ~30 min on Pi)..."
pip3 install --break-system-packages --no-cache-dir --no-binary scikit-learn 'scikit-learn==1.8.0'
info "Python packages installed."

# ─────────────────────────── 3. SPI TFT Display ──────────────────────────────
info "Configuring SPI TFT display..."
echo ""
echo "  Common 3.5\" SPI display models:"
echo "  [1] Waveshare 3.5\" Type A  (ILI9486) — most common"
echo "  [2] Waveshare 3.5\" Type B  (ILI9486)"
echo "  [3] Waveshare 3.5\" Type C  (ILI9488)"
echo "  [4] MHS / KeDei 3.5\"       (ILI9486)"
echo "  [5] Generic 3.5\" ILI9341   (320x240)"
echo "  [6] 5\" Waveshare           (800x480, ILI9488)"
echo "  [7] Skip display setup     (already configured)"
echo ""
read -rp "  Enter your display type [1-7]: " DISP_CHOICE

BOOT_CONFIG="/boot/firmware/config.txt"
[[ ! -f "$BOOT_CONFIG" ]] && BOOT_CONFIG="/boot/config.txt"

# Remove any previous TFT overlay lines
sed -i '/dtoverlay=waveshare/d;/dtoverlay=piscreen/d;/dtoverlay=ili/d;/dtoverlay=fbtft/d' "$BOOT_CONFIG"

case "$DISP_CHOICE" in
  1) OVERLAY="dtoverlay=waveshare35a,rotate=270" ;;
  2) OVERLAY="dtoverlay=waveshare35b,rotate=270" ;;
  3) OVERLAY="dtoverlay=waveshare35c,rotate=270" ;;
  4) OVERLAY="dtoverlay=piscreen,speed=16000000,rotate=90" ;;
  5) OVERLAY="dtoverlay=ili9341,speed=42000000,rotate=90,bgr=1" ;;
  6)
    OVERLAY="dtoverlay=waveshare5,rotate=270"
    # Patch lcd_controller.py for 800x480
    sed -i 's/^W, H = 480, 320/W, H = 800, 480/' "$LCD_DIR/lcd_controller.py"
    info "LCD controller resolution updated to 800x480."
    ;;
  7) OVERLAY="" ; warn "Skipping display config — assuming it's already set up." ;;
  *) error "Invalid choice." ;;
esac

if [[ -n "$OVERLAY" ]]; then
    # Ensure SPI is enabled
    if ! grep -q "^dtparam=spi=on" "$BOOT_CONFIG"; then
        echo "dtparam=spi=on" >> "$BOOT_CONFIG"
    fi
    echo "$OVERLAY" >> "$BOOT_CONFIG"
    info "Display overlay '$OVERLAY' added to $BOOT_CONFIG"
fi

# ─────────────────────────── 4. Touch calibration (tslib) ────────────────────
info "Setting up touchscreen (tslib)..."

TSLIB_CONF="/etc/ts.conf"
cat > "$TSLIB_CONF" << 'EOF'
module_raw input
module pthres pmin=1
module dejitter delta=100
module linear
EOF

# udev rule so /dev/input/touchscreen symlink is always correct
cat > /etc/udev/rules.d/95-touchscreen.rules << 'EOF'
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="ADS7846*", SYMLINK+="input/touchscreen"
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="*Touchscreen*", SYMLINK+="input/touchscreen"
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="*touchscreen*", SYMLINK+="input/touchscreen"
EOF
udevadm control --reload-rules 2>/dev/null || true
info "Touch udev rules created."

# ─────────────────────────── 5. Audio configuration ──────────────────────────
info "Configuring audio..."

# Disable HDMI audio, use 3.5mm headphone jack
if ! grep -q "^dtparam=audio=on" "$BOOT_CONFIG"; then
    echo "dtparam=audio=on" >> "$BOOT_CONFIG"
fi

# ALSA: set headphone jack as default output
ALSA_CONF="/etc/asound.conf"
cat > "$ALSA_CONF" << 'EOF'
# Default to headphone jack (card 0, device 0)
defaults.pcm.card 0
defaults.pcm.device 0
defaults.ctl.card 0
EOF

# Check for USB audio device (microphone in USB headset)
if aplay -l 2>/dev/null | grep -qi "USB Audio"; then
    info "USB audio device detected — setting as default capture (microphone)."
    USB_CARD=$(aplay -l 2>/dev/null | grep -i "USB Audio" | head -1 | sed 's/card \([0-9]*\).*/\1/')
    cat >> "$ALSA_CONF" << EOF

# USB microphone input
pcm.usb_mic {
    type hw
    card $USB_CARD
}
pcm.!default {
    type asym
    playback.pcm "hw:0,0"
    capture.pcm  "hw:$USB_CARD,0"
}
EOF
    info "USB mic configured on card $USB_CARD."
else
    warn "No USB audio found. If your headphone has a built-in mic, plug it in before rebooting."
fi

# Set headphone volume to 85%
amixer sset Master 85% unmute 2>/dev/null || true
amixer sset PCM    85% unmute 2>/dev/null || true
info "Audio configured."

# ─────────────────────────── 6. Systemd services ─────────────────────────────
info "Installing systemd services..."

SERVICE_DIR="$LCD_DIR/services"
cp "$SERVICE_DIR/smart-headphone-api.service" /etc/systemd/system/
cp "$SERVICE_DIR/smart-headphone-lcd.service" /etc/systemd/system/

# Verify paths match actual project location
sed -i "s|/home/pi/FYP_project|$PROJECT_DIR|g" \
    /etc/systemd/system/smart-headphone-api.service \
    /etc/systemd/system/smart-headphone-lcd.service

systemctl daemon-reload
systemctl enable smart-headphone-api.service
systemctl enable smart-headphone-lcd.service
info "Services enabled — will start on next boot."

# ─────────────────────────── 7. pi user permissions ──────────────────────────
info "Granting pi user access to audio, video, input, SPI..."
for GRP in audio video input spi gpio dialout; do
    usermod -aG "$GRP" pi 2>/dev/null || true
done

# ─────────────────────────── 8. Vosk model ───────────────────────────────────
VOSK_MODEL="$TRANSLATE_DIR/vosk-model-small-en-us"
if [[ ! -d "$VOSK_MODEL" ]]; then
    info "Downloading Vosk English model (~40 MB)..."
    VOSK_URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    wget -q -O /tmp/vosk_model.zip "$VOSK_URL"
    unzip -q /tmp/vosk_model.zip -d "$TRANSLATE_DIR/"
    # Rename to expected folder name
    mv "$TRANSLATE_DIR"/vosk-model-small-en-us-* "$VOSK_MODEL" 2>/dev/null || true
    rm -f /tmp/vosk_model.zip
    info "Vosk model installed."
else
    info "Vosk model already present."
fi

# ─────────────────────────── 9. Touch calibration reminder ───────────────────
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Installation complete!${NC}"
echo ""
echo "  NEXT STEPS:"
echo ""
echo "  1. Reboot now:"
echo "       sudo reboot"
echo ""
echo "  2. After reboot, the LCD should show the display."
echo "     If the image is upside-down or sideways, edit:"
echo "       sudo nano $BOOT_CONFIG"
echo "     Change 'rotate=270' to 0, 90, 180, or 270."
echo ""
echo "  3. Calibrate the touchscreen (run ONCE after first boot):"
echo "       sudo TSLIB_TSDEVICE=/dev/input/touchscreen ts_calibrate"
echo ""
echo "  4. Check service status:"
echo "       sudo systemctl status smart-headphone-api"
echo "       sudo systemctl status smart-headphone-lcd"
echo ""
echo "  5. View logs:"
echo "       tail -f /var/log/smart-headphone-api.log"
echo "       tail -f /var/log/smart-headphone-lcd.log"
echo ""
echo "  6. Connect Android app: open Settings → enter Pi IP:"
echo "       http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
