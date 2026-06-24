#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Manual startup — use this when NOT using systemd (e.g., during development
# or first-time testing over SSH).
#
# Run from the Pi terminal (or SSH):
#   cd /home/pi/FYP_project
#   bash lcd_ui/start_manual.sh
# ─────────────────────────────────────────────────────────────────────────────

PROJECT="/home/pi/FYP_project"
TRANSLATE="$PROJECT/translate"
LCD="$PROJECT/lcd_ui"

echo "[1/2] Starting Flask API in background..."
cd "$TRANSLATE"
nohup python3 run_flask.py > /tmp/flask.log 2>&1 &
FLASK_PID=$!
echo "      Flask PID: $FLASK_PID  (logs: /tmp/flask.log)"

echo "      Waiting 4 s for Flask to be ready..."
sleep 4

# Quick health check
if curl -s http://127.0.0.1:5000/health > /dev/null 2>&1; then
    echo "      Flask is UP."
else
    echo "[WARN] Flask didn't respond. LCD will retry automatically."
fi

echo "[2/2] Starting LCD app..."
cd "$LCD"
export DISPLAY=:0

python3 app.py

# When app exits, also kill Flask
kill $FLASK_PID 2>/dev/null || true
echo "System stopped."
