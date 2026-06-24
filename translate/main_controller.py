"""
Main Controller - Smart Headphone Translation System
"""

import sys
import socket


def check_internet():
    try:
        socket.setdefaulttimeout(3)
        conn = socket.create_connection(("8.8.8.8", 53))
        conn.close()
        return True
    except OSError:
        return False


def print_banner():
    print("\n" + "="*55)
    print("   SMART HEADPHONE TRANSLATION SYSTEM")
    print("   Version 1.0.0")
    print("="*55 + "\n")


def main():
    print_banner()

    print("[SYSTEM] Checking internet connection...")
    internet = check_internet()

    if internet:
        print("[SYSTEM] Internet AVAILABLE - Mode 2 (Online) activated\n")
        mode = "online"
    else:
        print("[SYSTEM] No Internet - Mode 1 (Offline) activated\n")
        mode = "offline"

    # Start auto-backup in background (uploads recordings when internet appears)
    auto_backup = _start_auto_backup()

    while True:
        count, mb = _backup_info()
        print("\n" + "="*45)
        print("  MAIN MENU")
        print("="*45)
        print("  1. Auto Mode (recommended)")
        print("  2. Force Offline Mode")
        print("  3. Force Online Mode")
        print("  4. Start Flask API Server")
        print("  5. Demo Mode (no mic needed)")
        print("  6. Setup Offline Packages (run once)")
        print("  7. Test Recorded Voices (Deepfake Detection)")
        print("  8. Backup Recordings to Cloud Now")
        print("  9. Exit")
        print("="*45)
        print(f"  [Internet: {'ON' if internet else 'OFF'} | Mode: {mode.upper()} | "
              f"Saved recordings: {count} ({mb:.1f} MB)]")

        choice = input("\nEnter choice (1-9): ").strip()

        if choice == '1':
            # Re-check internet at the moment of use
            internet = check_internet()
            mode = "online" if internet else "offline"
            if mode == "online":
                run_online_auto()
            else:
                run_offline_auto()
        elif choice == '2':
            run_offline_auto()
        elif choice == '3':
            internet = check_internet()
            if not internet:
                print("[WARNING] No internet detected. Online mode may fail.")
            run_online_auto()
        elif choice == '4':
            internet = check_internet()
            if not internet:
                print("[WARNING] No internet detected. Flask API requires internet for translation.")
            start_api()
        elif choice == '5':
            internet = check_internet()
            run_demo(internet)
        elif choice == '6':
            setup_offline()
        elif choice == '7':
            run_deepfake_check()
        elif choice == '8':
            run_cloud_backup()
        elif choice == '9':
            if auto_backup:
                auto_backup.stop()
            print("\n[EXIT] Goodbye!\n")
            sys.exit(0)
        else:
            print("[ERROR] Invalid choice. Enter 1-9.")


def _ask_recording():
    """Ask whether to enable voice recording for this session."""
    try:
        ans = input("\nEnable voice recording? (y/n, default=y): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if ans == 'n':
        print("[RECORD] Recording DISABLED for this session.")
        return False
    print("[RECORD] Recording ENABLED — voices will be saved as WAV files.")
    return True


def _make_recorder(enabled, label):
    """Create and start a recorder if enabled, else return None."""
    if not enabled:
        return None
    from conversation_recorder import ConversationRecorder
    rec = ConversationRecorder()
    rec.start(label)
    return rec


def _stop_recorder(rec):
    """Stop recorder if it exists and is active."""
    if rec:
        rec.stop()


def run_demo(internet=True):
    """Route demo to online or offline depending on connectivity."""
    record = _ask_recording()
    rec = _make_recorder(record, "Online Demo" if internet else "Offline Demo")
    try:
        if internet:
            try:
                from mode2_online_translation import demo_mode
                demo_mode(recorder=rec)
            except ImportError as e:
                print(f"[ERROR] Could not load online demo: {e}")
                print("[FALLBACK] Trying offline demo...")
                _run_offline_demo(recorder=rec)
        else:
            print("[INFO] No internet — launching Offline Demo.")
            _run_offline_demo(recorder=rec)
    finally:
        _stop_recorder(rec)


def _run_offline_demo(recorder=None):
    try:
        from mode1_offline_translation import demo_offline
        demo_offline(recorder=recorder)
    except ImportError as e:
        print(f"[ERROR] Could not load offline module: {e}")


def run_online_auto():
    try:
        from mode2_online_translation import live_mic_mode, two_way_conversation_mode
    except ImportError as e:
        print(f"[ERROR] Could not load online module: {e}")
        return

    print("\n  1. Single person  (live mic, Ctrl+C to stop)")
    print("  2. Two-way conversation  (Person A <-> Person B)")
    choice = input("\nSelect (1/2): ").strip()
    if choice not in ('1', '2'):
        print("[ERROR] Invalid choice.")
        return

    record = _ask_recording()
    labels = {'1': "Online Live Mic", '2': "Online Two-Way Conversation"}
    rec = _make_recorder(record, labels[choice])
    try:
        if choice == '1':
            live_mic_mode(recorder=rec)
        else:
            two_way_conversation_mode(recorder=rec)
    finally:
        _stop_recorder(rec)


def run_offline_auto():
    try:
        from mode1_offline_translation import (live_offline_mode, demo_offline,
                                                two_way_conversation_offline)
    except ImportError as e:
        print(f"[ERROR] Could not load offline module: {e}")
        return

    print("\n  1. Live mic — single person  (English <-> Urdu, Ctrl+C to stop)")
    print("  2. Two-way conversation      (Person A: English | Person B: Urdu)")
    print("  3. Demo                      (no mic — type to translate)")
    d = input("\nSelect (1/2/3): ").strip()
    if d not in ('1', '2', '3'):
        print("[ERROR] Invalid choice.")
        return

    record = _ask_recording()
    labels = {'1': "Offline Live Mic", '2': "Offline Two-Way Conversation",
              '3': "Offline Demo"}
    rec = _make_recorder(record, labels[d])
    try:
        if d == '1':
            live_offline_mode(recorder=rec)
        elif d == '2':
            two_way_conversation_offline(recorder=rec)
        else:
            demo_offline(recorder=rec)
    finally:
        _stop_recorder(rec)


def run_deepfake_check():
    try:
        from deepfake_checker import run_deepfake_checker
        run_deepfake_checker()
    except ImportError as e:
        print(f"[ERROR] Could not load deepfake checker: {e}")


def setup_offline():
    """Download and install argostranslate en<->ur packages (needs internet once)."""
    print("\n[SETUP] Checking internet for one-time package download...")
    if not check_internet():
        print("[ERROR] No internet connection. Setup requires internet once to download packages.")
        return
    try:
        from mode1_offline_translation import setup_offline_translation
        ok = setup_offline_translation()
        if ok:
            print("\n[SETUP] Offline translation packages ready. You can now use Offline Mode without internet.")
        else:
            print("\n[SETUP] Setup finished with some errors. Check messages above.")
    except ImportError as e:
        print(f"[ERROR] Could not load offline module: {e}")


def start_api():
    try:
        from mode2_online_translation import start_flask_api
        start_flask_api()
    except ImportError as e:
        print(f"[ERROR] {e}")


def _start_auto_backup():
    """Start background auto-backup thread. Returns the instance (or None on error)."""
    try:
        from cloud_backup import AutoBackup
        ab = AutoBackup(delete_after=True)
        ab.start()
        return ab
    except Exception as e:
        print(f"[BACKUP] Auto-backup unavailable: {e}")
        return None


def _backup_info():
    """Return (count, mb) of pending recordings."""
    try:
        from cloud_backup import recordings_info
        return recordings_info()
    except Exception:
        return 0, 0.0


def run_cloud_backup():
    """Manual backup trigger from the menu."""
    try:
        from cloud_backup import backup_recordings, recordings_info
        count, mb = recordings_info()
        if count == 0:
            print("\n[BACKUP] No recordings to upload.")
            return
        print(f"\n[BACKUP] {count} recording(s) found ({mb:.1f} MB)")
        confirm = input("Upload to Google Drive and delete local copies? (y/n): ").strip().lower()
        if confirm == 'y':
            backup_recordings(delete_after=True, verbose=True)
        else:
            print("[BACKUP] Cancelled.")
    except Exception as e:
        print(f"[BACKUP ERROR] {e}")


if __name__ == "__main__":
    # Auto-start Flask API when launched with --flask flag (used by systemd service)
    if len(sys.argv) > 1 and sys.argv[1] == '--flask':
        print("[AUTOSTART] Starting Flask API server...")
        _start_auto_backup()
        start_api()
    else:
        main()
