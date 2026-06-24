"""
Cloud Backup — Smart Headphone
Saves recordings from Raspberry Pi to Google Drive when internet is available.
After a successful upload every local WAV is deleted to free Pi storage.

FIRST-TIME SETUP (run once on any machine with a browser):
  1. Go to https://console.cloud.google.com
     • Create a project → Enable "Google Drive API"
     • Credentials → OAuth 2.0 Client ID (Desktop app)
     • Download JSON → rename to  client_secrets.json
     • Place client_secrets.json in this folder (translate/)
  2. Run:  py cloud_backup.py setup
     • Browser opens once → log in → allow access
     • Saves mycreds.txt  (keep this file — Pi needs it)
  3. Copy both files to the Raspberry Pi:
       client_secrets.json
       mycreds.txt
  From now on, backup runs headlessly — no browser needed.
"""

import os
import socket
import threading
import time
import datetime

_THIS_DIR      = os.path.dirname(os.path.abspath(__file__))
_RECORDINGS    = os.path.join(_THIS_DIR, "recordings")
_CREDS_FILE    = os.path.join(_THIS_DIR, "mycreds.txt")
_SECRETS_FILE  = os.path.join(_THIS_DIR, "client_secrets.json")
_BACKUP_LOG    = os.path.join(_THIS_DIR, "backup_log.txt")

CHECK_INTERVAL = 300   # seconds between internet checks (5 min)


# ── Internet check ────────────────────────────────────────────────────────────

def has_internet():
    try:
        socket.setdefaulttimeout(3)
        socket.create_connection(("8.8.8.8", 53))
        return True
    except OSError:
        return False


# ── Google Drive helpers ──────────────────────────────────────────────────────

def _get_drive():
    """Return an authenticated GoogleDrive instance (headless after first setup)."""
    try:
        from pydrive2.auth import GoogleAuth
        from pydrive2.drive import GoogleDrive
    except ImportError:
        raise RuntimeError(
            "pydrive2 not installed. Run:  py -m pip install pydrive2"
        )

    if not os.path.exists(_SECRETS_FILE):
        raise FileNotFoundError(
            f"client_secrets.json not found in {_THIS_DIR}\n"
            "See setup instructions at the top of cloud_backup.py"
        )

    gauth = GoogleAuth()
    gauth.settings["client_config_file"] = _SECRETS_FILE
    gauth.settings["save_credentials"]         = True
    gauth.settings["save_credentials_backend"] = "file"
    gauth.settings["save_credentials_file"]    = _CREDS_FILE
    gauth.settings["get_refresh_token"]        = True

    if os.path.exists(_CREDS_FILE):
        gauth.LoadCredentialsFile(_CREDS_FILE)

    if gauth.credentials is None:
        gauth.LocalWebserverAuth()          # browser only on first run
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()

    gauth.SaveCredentialsFile(_CREDS_FILE)
    return GoogleDrive(gauth)


def _get_or_create_folder(drive, folder_name="SmartHeadphone_Recordings"):
    """Return the Google Drive folder ID, creating it if needed."""
    query = (f"title='{folder_name}' and "
             f"mimeType='application/vnd.google-apps.folder' and trashed=false")
    results = drive.ListFile({"q": query}).GetList()
    if results:
        return results[0]["id"]
    folder = drive.CreateFile({
        "title": folder_name,
        "mimeType": "application/vnd.google-apps.folder"
    })
    folder.Upload()
    return folder["id"]


def _upload_file(drive, folder_id, file_path):
    """Upload one file to the Drive folder. Returns True on success."""
    try:
        filename = os.path.basename(file_path)
        f = drive.CreateFile({
            "title": filename,
            "parents": [{"id": folder_id}]
        })
        f.SetContentFile(file_path)
        f.Upload()
        return True
    except Exception as e:
        print(f"  [BACKUP] Upload error ({os.path.basename(file_path)}): {e}")
        return False


# ── Main backup function ──────────────────────────────────────────────────────

def backup_recordings(delete_after=True, verbose=True):
    """
    Upload all WAV files from recordings/ to Google Drive.
    Deletes local copies after successful upload when delete_after=True.

    Returns (uploaded_count, failed_count).
    """
    if not has_internet():
        if verbose:
            print("[BACKUP] No internet connection — skipped.")
        return 0, 0

    if not os.path.isdir(_RECORDINGS):
        if verbose:
            print("[BACKUP] No recordings folder found.")
        return 0, 0

    wav_paths = []
    for f in sorted(os.listdir(_RECORDINGS)):
        if f.lower().endswith(".wav") and os.path.isfile(os.path.join(_RECORDINGS, f)):
            wav_paths.append(os.path.join(_RECORDINGS, f))

    if not wav_paths:
        if verbose:
            print("[BACKUP] No recordings to upload.")
        return 0, 0

    if verbose:
        print(f"\n[BACKUP] Uploading {len(wav_paths)} recording(s) to Google Drive...")

    try:
        drive     = _get_drive()
        folder_id = _get_or_create_folder(drive)
    except Exception as e:
        print(f"[BACKUP] Could not connect to Google Drive: {e}")
        return 0, len(wav_paths)

    uploaded = 0
    failed   = 0
    freed_mb = 0.0

    for path in wav_paths:
        filename = os.path.basename(path)
        size = os.path.getsize(path) / (1024 * 1024)

        ok = _upload_file(drive, folder_id, path)
        if ok:
            uploaded += 1
            freed_mb += size
            if verbose:
                print(f"  OK  {filename}  ({size:.2f} MB)")
            if delete_after:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as e:
                        print(f"  [BACKUP] Could not delete {filename}: {e}")
                        print(f"  [BACKUP] File kept locally: {path}")
        else:
            failed += 1
            if verbose:
                print(f"  FAIL  {filename}  -- upload failed, keeping local copy")

    # Write to backup log
    _write_log(uploaded, failed, freed_mb)

    if verbose:
        print(f"\n[BACKUP] Done — Uploaded: {uploaded}  |  Failed: {failed}  "
              f"|  Freed: {freed_mb:.2f} MB")

    return uploaded, failed


def _write_log(uploaded, failed, freed_mb):
    """Append a one-line entry to backup_log.txt."""
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(_BACKUP_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}]  uploaded={uploaded}  failed={failed}  "
                    f"freed={freed_mb:.2f}MB\n")
    except Exception:
        pass


# ── Auto-backup background thread ─────────────────────────────────────────────

class AutoBackup:
    """
    Background thread that wakes up every CHECK_INTERVAL seconds.
    When internet is available AND recordings exist, runs backup automatically.
    """

    def __init__(self, delete_after=True, check_interval=CHECK_INTERVAL):
        self._delete_after    = delete_after
        self._check_interval  = check_interval
        self._running         = False
        self._thread          = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True,
                                         name="AutoBackup")
        self._thread.start()
        print(f"[BACKUP] Auto-backup running "
              f"(checks every {self._check_interval // 60} min)")

    def stop(self):
        self._running = False
        print("[BACKUP] Auto-backup stopped.")

    def _has_pending(self):
        if not os.path.isdir(_RECORDINGS):
            return False
        return any(f.lower().endswith(".wav") and
                   os.path.isfile(os.path.join(_RECORDINGS, f))
                   for f in os.listdir(_RECORDINGS))

    def _loop(self):
        while self._running:
            try:
                if has_internet() and self._has_pending():
                    print("\n[BACKUP] Internet detected — backing up recordings...")
                    backup_recordings(delete_after=self._delete_after, verbose=True)
            except Exception as e:
                print(f"[BACKUP ERROR] {e}")
            time.sleep(self._check_interval)


# ── Storage info helper ───────────────────────────────────────────────────────

def recordings_info():
    """Return (count, total_mb) of pending recordings in the flat recordings/ folder."""
    if not os.path.isdir(_RECORDINGS):
        return 0, 0.0
    paths = [os.path.join(_RECORDINGS, f) for f in os.listdir(_RECORDINGS)
             if f.lower().endswith(".wav") and os.path.isfile(os.path.join(_RECORDINGS, f))]
    total = sum(os.path.getsize(p) for p in paths) / (1024 * 1024)
    return len(paths), total


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        print("\n[SETUP] Opening browser for one-time Google Drive authorization...")
        print("[SETUP] After authorization, mycreds.txt will be saved.")
        print("[SETUP] Copy both client_secrets.json and mycreds.txt to your Pi.\n")
        try:
            _get_drive()
            print("\n[SETUP] Authorization successful! mycreds.txt saved.")
        except Exception as e:
            print(f"\n[SETUP ERROR] {e}")
        sys.exit(0)

    print("\n[BACKUP] Checking for recordings to upload...")
    count, mb = recordings_info()
    print(f"[BACKUP] Found {count} recording(s) — {mb:.2f} MB")

    if count == 0:
        print("[BACKUP] Nothing to upload.")
        sys.exit(0)

    uploaded, failed = backup_recordings(delete_after=True, verbose=True)
    sys.exit(0 if failed == 0 else 1)
