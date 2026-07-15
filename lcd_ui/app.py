#!/usr/bin/env python3
"""
Smart Headphone System — Desktop GUI
Raspberry Pi 4B + HDMI/DSI touchscreen (acts as normal monitor).
Touch events = mouse events — works out of the box, no drivers needed.

Auto-starts Flask API when launched.
Connect the Android app to: http://<pi-ip>:5000
"""

import os
import sys
import socket
import threading
import subprocess
import tkinter as tk
from tkinter import ttk

try:
    import requests
    _HAS_REQ = True
except ImportError:
    _HAS_REQ = False

# ── Flask API ──────────────────────────────────────────────────────────────────
API     = 'http://127.0.0.1:5000'
TIMEOUT = 4

# ── Colors (matches Flutter app) ───────────────────────────────────────────────
BG    = '#060D1F'
CARD  = '#0E1E3C'
CARD2 = '#1C3050'
BLUE  = '#00C2FF'
GREEN = '#00E5A0'
RED   = '#FF5252'
AMBER = '#FFB400'
WHITE = '#FFFFFF'
GRAY  = '#7890A0'
DARK  = '#040810'

# ── Languages ──────────────────────────────────────────────────────────────────
LANGUAGES = [
    ('en','English'), ('ur','Urdu'),    ('ar','Arabic'),  ('zh','Chinese'),
    ('fr','French'),  ('de','German'),  ('es','Spanish'), ('it','Italian'),
    ('ja','Japanese'),('ko','Korean'),  ('pt','Portuguese'),('ru','Russian'),
    ('hi','Hindi'),   ('tr','Turkish'), ('nl','Dutch'),   ('pl','Polish'),
    ('sv','Swedish'), ('id','Indonesian'),('ms','Malay'), ('th','Thai'),
    ('vi','Vietnamese'),('el','Greek'), ('cs','Czech'),   ('hu','Hungarian'),
    ('ro','Romanian'),('uk','Ukrainian'),('he','Hebrew'), ('bn','Bengali'),
    ('fa','Persian'), ('sw','Swahili'),
]
LANG_CODES = [c for c, _ in LANGUAGES]

# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _get(path):
    if not _HAS_REQ:
        return False, {}
    try:
        r = requests.get(f'{API}{path}', timeout=TIMEOUT)
        return r.status_code == 200, (r.json() if r.content else {})
    except Exception:
        return False, {}

def _post(path, data=None):
    if not _HAS_REQ:
        return False, {}
    try:
        r = requests.post(f'{API}{path}', json=data, timeout=TIMEOUT)
        return r.status_code == 200, (r.json() if r.content else {})
    except Exception:
        return False, {}

def _delete(path):
    if not _HAS_REQ:
        return False, {}
    try:
        r = requests.delete(f'{API}{path}', timeout=TIMEOUT)
        return r.status_code == 200, (r.json() if r.content else {})
    except Exception:
        return False, {}

def _local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN APP
# ──────────────────────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Smart Headphone System')
        self.root.configure(bg=BG)
        self.root.attributes('-fullscreen', True)
        # Esc exits fullscreen (for debugging); F11 re-enters it
        self.root.bind('<Escape>', lambda e: self.root.attributes('-fullscreen', False))
        self.root.bind('<F11>',    lambda e: self.root.attributes('-fullscreen', True))

        self._session   = False
        self._poll_stop = threading.Event()
        self._flask_proc = None

        # Live state variables
        self.v_from  = tk.StringVar(value='en')
        self.v_to    = tk.StringVar(value='ur')
        self.v_api   = tk.StringVar(value='● Connecting...')
        self.v_state = tk.StringVar(value='Ready')
        self.v_orig  = tk.StringVar(value='')
        self.v_trans = tk.StringVar(value='')
        self.v_count = tk.StringVar(value='0')

        self._start_flask()
        self._build()
        self._start_poll()

    # ── Flask startup ──────────────────────────────────────────────────────────

    def _start_flask(self):
        """Start Flask API if not already running."""
        if not _HAS_REQ:
            return
        try:
            requests.get(f'{API}/health', timeout=2)
            return  # already up
        except Exception:
            pass
        # run_flask.py does: from mode2_online_translation import start_flask_api; start_flask_api()
        script = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'translate', 'run_flask.py'))
        if os.path.exists(script):
            self._flask_proc = subprocess.Popen(
                [sys.executable, script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ── Background status poll ─────────────────────────────────────────────────

    def _start_poll(self):
        _MAP = {
            'idle': 'Ready', 'listening': 'Listening...',
            'recording': 'Recording...', 'translating': 'Translating...',
            'speaking': 'Speaking...', 'done': 'Done', 'error': 'Error',
        }
        def _loop():
            while not self._poll_stop.is_set():
                ok, d = _get('/status')
                if ok:
                    self.v_api.set('● Online')
                    self.v_state.set(_MAP.get(d.get('state', ''), 'Ready'))
                    self.v_orig.set(d.get('last_original', ''))
                    self.v_trans.set(d.get('last_translated', ''))
                    self.v_count.set(str(d.get('translation_count', 0)))
                else:
                    self.v_api.set('● Offline')
                color = GREEN if ok else RED
                self.root.after(0, lambda c=color: self._lbl_api.configure(fg=c))
                self._poll_stop.wait(1.5)
        threading.Thread(target=_loop, daemon=True).start()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build(self):
        # ── Top bar ──────────────────────────────────────────────────────────
        bar = tk.Frame(self.root, bg=CARD, height=50)
        bar.pack(fill='x')
        bar.pack_propagate(False)

        tk.Label(bar, text='Smart Headphone System', bg=CARD, fg=BLUE,
                 font=('Arial', 17, 'bold')).pack(side='left', padx=18, pady=10)
        self._lbl_api = tk.Label(bar, textvariable=self.v_api, bg=CARD,
                                  fg=GREEN, font=('Arial', 12))
        self._lbl_api.pack(side='right', padx=14)
        tk.Label(bar, text=f'IP: {_local_ip()}:5000', bg=CARD,
                 fg=GRAY, font=('Arial', 11)).pack(side='right', padx=4)

        # ── Language selector ─────────────────────────────────────────────────
        lang_bar = tk.Frame(self.root, bg=BG)
        lang_bar.pack(fill='x', padx=20, pady=(10, 4))

        tk.Label(lang_bar, text='Translate From:', bg=BG, fg=GRAY,
                 font=('Arial', 13)).pack(side='left')

        # Style comboboxes to match dark theme
        st = ttk.Style()
        st.theme_use('clam')
        st.configure('Dark.TCombobox',
                     fieldbackground=CARD2, background=CARD2,
                     foreground=WHITE, selectbackground=BLUE,
                     selectforeground=WHITE, arrowcolor=BLUE)

        ttk.Combobox(lang_bar, textvariable=self.v_from, values=LANG_CODES,
                     width=10, font=('Arial', 13),
                     style='Dark.TCombobox').pack(side='left', padx=(6, 12))

        tk.Label(lang_bar, text='=>', bg=BG, fg=BLUE,
                 font=('Arial', 15, 'bold')).pack(side='left')

        tk.Label(lang_bar, text='To:', bg=BG, fg=GRAY,
                 font=('Arial', 13)).pack(side='left', padx=(12, 0))

        ttk.Combobox(lang_bar, textvariable=self.v_to, values=LANG_CODES,
                     width=10, font=('Arial', 13),
                     style='Dark.TCombobox').pack(side='left', padx=6)

        tk.Label(lang_bar,
                 text='(codes: en=English  ur=Urdu  fr=French  de=German  zh=Chinese  ar=Arabic ...)',
                 bg=BG, fg=GRAY, font=('Arial', 10)).pack(side='left', padx=16)

        # ── Mode buttons grid ─────────────────────────────────────────────────
        grid = tk.Frame(self.root, bg=BG)
        grid.pack(expand=True, fill='both', padx=20, pady=6)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_rowconfigure(0, weight=1)
        grid.grid_rowconfigure(1, weight=1)
        grid.grid_rowconfigure(2, weight=1)

        F  = ('Arial', 15, 'bold')
        BH = 4

        def btn(text, fg, bg, cmd, row, col, span=1):
            b = tk.Button(grid, text=text, command=cmd,
                         font=F, fg=fg, bg=bg,
                         activeforeground=DARK, activebackground=fg,
                         relief='flat', cursor='hand2',
                         height=BH, wraplength=320)
            b.grid(row=row, column=col, columnspan=span,
                   padx=8, pady=6, sticky='nsew')
            return b

        self._b_1w_on  = btn('1-WAY  ONLINE\nListen → Translate → Speak',
                              BLUE,   '#081828', lambda: self._start('1way','online'),  0, 0)
        self._b_1w_off = btn('1-WAY  OFFLINE\nNo internet needed',
                              '#5599DD','#071020', lambda: self._start('1way','offline'), 0, 1)
        self._b_2w_on  = btn('2-WAY  ONLINE\nBoth sides translate live',
                              GREEN,  '#081A12', lambda: self._start('2way','online'),  1, 0)
        self._b_2w_off = btn('2-WAY  OFFLINE\nBoth sides, no internet',
                              '#22BB88','#06120C', lambda: self._start('2way','offline'), 1, 1)
        self._b_deep   = btn('DEEPFAKE  DETECTION\nTest audio files for AI-generated voices',
                              RED,    '#180010', self._open_deepfake,                   2, 0, span=2)

        self._mode_btns = [self._b_1w_on, self._b_1w_off,
                           self._b_2w_on, self._b_2w_off, self._b_deep]
        # Store original colors to restore after stop
        self._btn_colors = [(b.cget('fg'), b.cget('bg')) for b in self._mode_btns]

        # ── Status bar ────────────────────────────────────────────────────────
        sb = tk.Frame(self.root, bg=DARK, height=78)
        sb.pack(fill='x', side='bottom')
        sb.pack_propagate(False)

        # STOP button — hidden until session starts
        self._btn_stop = tk.Button(
            sb, text='■  STOP SESSION',
            command=self._stop,
            font=('Arial', 14, 'bold'), bg=RED, fg=WHITE,
            relief='flat', cursor='hand2', padx=22, pady=6)

        left = tk.Frame(sb, bg=DARK)
        left.pack(side='left', fill='both', expand=True, padx=14, pady=6)

        row1 = tk.Frame(left, bg=DARK)
        row1.pack(fill='x')
        tk.Label(row1, textvariable=self.v_state,
                 bg=DARK, fg=GREEN, font=('Arial', 13, 'bold')).pack(side='left')
        tk.Label(row1, text='  |  translations: ',
                 bg=DARK, fg=GRAY, font=('Arial', 11)).pack(side='left')
        tk.Label(row1, textvariable=self.v_count,
                 bg=DARK, fg=BLUE, font=('Arial', 11, 'bold')).pack(side='left')

        row2 = tk.Frame(left, bg=DARK)
        row2.pack(fill='x', pady=(3, 0))
        self._lbl_orig = tk.Label(row2, textvariable=self.v_orig,
                                   bg=DARK, fg=GRAY, font=('Arial', 11),
                                   anchor='w', wraplength=380, justify='left')
        self._lbl_orig.pack(side='left')
        tk.Label(row2, text='  =>  ', bg=DARK, fg=BLUE,
                 font=('Arial', 11, 'bold')).pack(side='left')
        self._lbl_trans = tk.Label(row2, textvariable=self.v_trans,
                                    bg=DARK, fg=WHITE, font=('Arial', 11, 'bold'),
                                    anchor='w', wraplength=380, justify='left')
        self._lbl_trans.pack(side='left')

    # ── Session control ────────────────────────────────────────────────────────

    def _start(self, direction, mode):
        if self._session:
            return
        def _do():
            ok, _ = _post('/pi/start', {
                'direction': direction,
                'mode':      mode,
                'from_lang': self.v_from.get(),
                'to_lang':   self.v_to.get(),
            })
            if ok:
                self._session = True
                self.root.after(0, self._on_started)
            else:
                self.root.after(0, lambda: self.v_state.set('Failed — is Flask API running?'))
        threading.Thread(target=_do, daemon=True).start()

    def _stop(self):
        def _do():
            _post('/pi/stop')
            self._session = False
            self.root.after(0, self._on_stopped)
        threading.Thread(target=_do, daemon=True).start()

    def _on_started(self):
        for b in self._mode_btns:
            b.configure(state='disabled', fg='#333344', bg='#080810')
        self._btn_stop.pack(side='right', padx=18, pady=18)

    def _on_stopped(self):
        for b, (fg, bg) in zip(self._mode_btns, self._btn_colors):
            b.configure(state='normal', fg=fg, bg=bg)
        self._btn_stop.pack_forget()
        self.v_state.set('Session stopped')
        self.v_orig.set('')
        self.v_trans.set('')

    def _open_deepfake(self):
        DeepfakeWindow(self.root)

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self._poll_stop.set()
            if self._flask_proc:
                self._flask_proc.terminate()


# ──────────────────────────────────────────────────────────────────────────────
#  DEEPFAKE DETECTION WINDOW (popup)
# ──────────────────────────────────────────────────────────────────────────────

class DeepfakeWindow:
    def __init__(self, parent):
        self.win = tk.Toplevel(parent)
        self.win.title('Deepfake Detection')
        self.win.configure(bg=BG)
        self.win.geometry('700x500')
        self.win.resizable(False, False)
        self.win.grab_set()  # modal — blocks main window while open
        self._recs = []

        # Header
        tk.Label(self.win, text='Deepfake Voice Detection',
                 bg=BG, fg=RED, font=('Arial', 16, 'bold')).pack(pady=(14, 2))
        tk.Label(self.win,
                 text='Select a recording from the list, then tap TEST.',
                 bg=BG, fg=GRAY, font=('Arial', 11)).pack()

        # Result display
        self._v_result = tk.StringVar(value='')
        self._lbl_result = tk.Label(self.win, textvariable=self._v_result,
                                     bg=BG, font=('Arial', 14, 'bold'),
                                     wraplength=660)
        self._lbl_result.pack(pady=8)

        # Recordings list
        list_frame = tk.Frame(self.win, bg=BG)
        list_frame.pack(expand=True, fill='both', padx=20, pady=(0, 8))

        self._lb = tk.Listbox(list_frame, bg=CARD2, fg=WHITE,
                               font=('Arial', 13), selectbackground=RED,
                               selectforeground=WHITE, relief='flat',
                               activestyle='none', height=10, borderwidth=0)
        self._lb.pack(side='left', fill='both', expand=True)
        scr = tk.Scrollbar(list_frame, command=self._lb.yview, bg=CARD)
        scr.pack(side='right', fill='y')
        self._lb.configure(yscrollcommand=scr.set)

        # Buttons
        btn_row = tk.Frame(self.win, bg=BG)
        btn_row.pack(fill='x', padx=20, pady=(0, 14))

        def _abtn(text, fg, bg, cmd):
            return tk.Button(btn_row, text=text, command=cmd,
                            font=('Arial', 13, 'bold'), fg=fg, bg=bg,
                            relief='flat', cursor='hand2', padx=20, pady=8)

        _abtn('TEST',    WHITE, RED,   self._test).pack(side='left')
        _abtn('Refresh', GRAY,  CARD2, self._load).pack(side='left', padx=10)
        _abtn('Close',   GRAY,  CARD2, self.win.destroy).pack(side='right')

        self._load()

    def _load(self):
        self._v_result.set('Loading recordings...')
        self._lbl_result.configure(fg=GRAY)
        def _do():
            ok, data = _get('/recordings?source=pi')
            recs = data.get('recordings', []) if ok else []
            self.win.after(0, lambda: self._populate(recs))
        threading.Thread(target=_do, daemon=True).start()

    def _populate(self, recs):
        self._recs = recs
        self._lb.delete(0, 'end')
        if recs:
            for r in recs:
                self._lb.insert(
                    'end',
                    f"  {r['name']}   {r.get('size_mb', 0):.2f} MB   {r.get('date','')[:10]}")
            self._v_result.set(f'{len(recs)} recordings on Pi')
            self._lbl_result.configure(fg=GRAY)
        else:
            self._v_result.set('No recordings found. Run a translation session first.')
            self._lbl_result.configure(fg=AMBER)

    def _test(self):
        sel = self._lb.curselection()
        if not sel:
            self._v_result.set('Tap a recording in the list first.')
            self._lbl_result.configure(fg=AMBER)
            return
        name = self._recs[sel[0]]['name']
        self._v_result.set(f'Testing  {name} ...')
        self._lbl_result.configure(fg=GRAY)
        def _do():
            ok, data = _post(f'/detect_recording/{name}')
            if ok and 'label' in data:
                verdict = data['label']
                conf    = int(data.get('confidence', 0))
                real_p  = int(data.get('real_prob',  0))
                fake_p  = int(data.get('fake_prob',  0))
                msg   = f"{verdict}   {conf}% confidence   (Real {real_p}%  /  Fake {fake_p}%)"
                color = RED if verdict == 'FAKE' else GREEN
            else:
                msg   = 'Test failed — check that Flask API is running and models are trained.'
                color = AMBER
            self.win.after(0, lambda: self._v_result.set(msg))
            self.win.after(0, lambda: self._lbl_result.configure(fg=color))
        threading.Thread(target=_do, daemon=True).start()


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    App().run()
