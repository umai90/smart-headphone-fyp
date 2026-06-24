"""
Conversation Recorder
Smart Headphone Translation System
Saves the original voice audio for every translation exchange.
"""

import os
import wave
import datetime
import numpy as np


class ConversationRecorder:
    """
    Records a translation session — saves each speaker's raw voice as a WAV file.

    Usage:
        rec = ConversationRecorder()
        rec.start()
        rec.log("Person A", "en", "Hello", "ur", "ہیلو", audio_data=audio, samplerate=16000)
        rec.stop()
    """

    def __init__(self):
        self._active      = False
        self._session_dir = None
        self._session_ts  = None
        self._entry_count = 0

    # ── Public API ────────────────────────────────────────────────

    def start(self, label="Conversation"):
        """Prepare the recordings folder and begin recording."""
        try:
            self._session_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "recordings"
            )
            os.makedirs(self._session_dir, exist_ok=True)
            self._session_ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self._active      = True
            self._entry_count = 0
            print(f"\n[RECORD] Session STARTED  ->  {self._session_dir}/")
        except Exception as e:
            print(f"[RECORD ERROR] Could not start recording: {e}")

    def stop(self):
        """Finalise the session."""
        if not self._active:
            return
        self._active = False
        print(f"[RECORD] Session SAVED      ->  {self._session_dir}/")
        print(f"[RECORD] Total voices saved : {self._entry_count}")

    def log(self, speaker, src_lang, src_text, tgt_lang, tgt_text,
            audio_data=None, samplerate=16000):
        """
        Save the speaker's voice clip for one exchange.

        Parameters
        ----------
        speaker    : str          e.g. "Person A", "Person B", "AUTO"
        src_lang   : str          e.g. "en"
        src_text   : str          original text  (not saved — voices only)
        tgt_lang   : str          e.g. "ur"       (not saved — voices only)
        tgt_text   : str          translated text (not saved — voices only)
        audio_data : np.ndarray   raw int16 PCM audio of the speaker (or None)
        samplerate : int          sample rate of audio_data (default 16000)
        """
        if not self._active or not self._session_dir:
            return
        if audio_data is None:
            return  # nothing to save (typed fallback input)
        try:
            self._entry_count += 1
            safe_speaker = (speaker.replace(" ", "_")
                                    .replace("(", "").replace(")", ""))
            filename = (f"{self._session_ts}_"
                        f"{self._entry_count:03d}_{safe_speaker}_{src_lang}.wav")
            save_path = os.path.join(self._session_dir, filename)
            self._save_wav(save_path, audio_data, samplerate)
        except Exception as e:
            print(f"[RECORD ERROR] Could not save voice: {e}")

    # ── Internal helpers ──────────────────────────────────────────

    def _save_wav(self, path, audio_data, samplerate):
        """Write a numpy int16 array to a WAV file."""
        try:
            arr = np.array(audio_data, dtype=np.int16).flatten()
            with wave.open(path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)          # 16-bit = 2 bytes
                wf.setframerate(samplerate)
                wf.writeframes(arr.tobytes())
            print(f"[RECORD] Voice saved  ->  {os.path.basename(path)}")
        except Exception as e:
            print(f"[RECORD ERROR] Could not save audio: {e}")

    # ── Properties ────────────────────────────────────────────────

    @property
    def active(self):
        return self._active

    @property
    def session_dir(self):
        return self._session_dir
