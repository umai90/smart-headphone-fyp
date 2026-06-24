#!/usr/bin/env python3
"""
Smart Headphone System — LCD Touchscreen Controller
Raspberry Pi 4B + 3.5"/5" SPI TFT Touchscreen (Waveshare / MHS / ILI9486)

Talks to the Flask API (localhost:5000) via HTTP.
Touch events reach pygame as mouse events (tslib → SDL).

Screens:
  Home → Translate Setup → Active Session
       → Deepfake Detection
       → Recordings Manager
       → Settings
"""

import os
import sys
import time
import threading
import subprocess
import socket
import json
from typing import Optional, Dict, Any, List, Tuple

# ── Framebuffer / SDL config — must happen before pygame import ───────────────
_ON_PI = os.path.exists('/dev/fb1') or (
    sys.platform.startswith('linux') and os.path.exists('/proc/device-tree/model')
)

if _ON_PI:
    os.environ.setdefault('SDL_FBDEV',     '/dev/fb1')
    os.environ.setdefault('SDL_VIDEODRIVER', 'fbcon')
    # tslib maps touch events to SDL mouse events — no extra config needed
    if os.path.exists('/dev/input/touchscreen'):
        os.environ.setdefault('TSLIB_TSDEVICE', '/dev/input/touchscreen')
        os.environ.setdefault('SDL_MOUSEDRV',   'TSLIB')
        os.environ.setdefault('SDL_MOUSEDEV',   '/dev/input/touchscreen')

import pygame
from pygame.locals import (QUIT, KEYDOWN, K_ESCAPE,
                            MOUSEBUTTONDOWN, MOUSEBUTTONUP,
                            FINGERDOWN, FINGERUP, FULLSCREEN, NOFRAME)

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
    print("[WARNING] 'requests' not installed. Run: pip3 install requests")

# ── Display geometry ─────────────────────────────────────────────────────────
# Change to 800x480 if you have a 5" display
W, H = 480, 320

# ── Flask API ─────────────────────────────────────────────────────────────────
API          = 'http://127.0.0.1:5000'
API_TIMEOUT  = 4    # seconds per HTTP call
POLL_INTERVAL = 1.5  # seconds between /status polls

# ── Color palette (matches Flutter app theme) ─────────────────────────────────
BG      = (  6,  13,  31)
HEADER  = ( 14,  26,  52)
CARD    = ( 20,  37,  61)
CARD2   = ( 28,  48,  80)
ACCENT  = (  0, 194, 255)   # #00C2FF
GREEN   = (  0, 229, 160)   # #00E5A0
RED     = (255,  82,  82)
AMBER   = (255, 180,   0)
WHITE   = (255, 255, 255)
GRAY    = (120, 140, 170)
DARK    = ( 10,  20,  45)
DIMRED  = ( 80,   0,   0)

# ── Language table (matches Flutter supported_languages.dart) ─────────────────
LANGUAGES: List[Tuple[str, str]] = [
    ('en', 'English'),   ('ur', 'Urdu'),      ('ar', 'Arabic'),
    ('zh', 'Chinese'),   ('fr', 'French'),    ('de', 'German'),
    ('es', 'Spanish'),   ('it', 'Italian'),   ('ja', 'Japanese'),
    ('ko', 'Korean'),    ('pt', 'Portuguese'),('ru', 'Russian'),
    ('hi', 'Hindi'),     ('tr', 'Turkish'),   ('nl', 'Dutch'),
    ('pl', 'Polish'),    ('sv', 'Swedish'),   ('id', 'Indonesian'),
    ('ms', 'Malay'),     ('th', 'Thai'),      ('vi', 'Vietnamese'),
    ('el', 'Greek'),     ('cs', 'Czech'),     ('hu', 'Hungarian'),
    ('ro', 'Romanian'),  ('uk', 'Ukrainian'), ('he', 'Hebrew'),
    ('bn', 'Bengali'),   ('fa', 'Persian'),   ('sw', 'Swahili'),
]

# ─────────────────────────────────────────────────────────────────────────────
#  Drawing helpers
# ─────────────────────────────────────────────────────────────────────────────

def rr(surface, color, rect, radius=10, border=0, bc=None):
    """Filled rounded rect, optional 1-px border."""
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    if border and bc:
        pygame.draw.rect(surface, bc, rect, border, border_radius=radius)


def blit_text(surface, text, font, color, rect, align='center', valign='center'):
    """Render text centered/aligned within rect (clips to rect)."""
    surf = font.render(str(text), True, color)
    tw, th = surf.get_size()
    rx, ry, rw, rh = rect
    x = rx + (rw - tw) // 2 if align == 'center' else (rx + 8 if align == 'left' else rx + rw - tw - 8)
    y = ry + (rh - th) // 2 if valign == 'center' else (ry + 4 if valign == 'top' else ry + rh - th - 4)
    old_clip = surface.get_clip()
    surface.set_clip(rect)
    surface.blit(surf, (x, y))
    surface.set_clip(old_clip)


def wrap_text(font, text: str, max_w: int) -> List[str]:
    """Word-wrap text to list of lines that fit within max_w pixels."""
    if not text:
        return ['']
    words = text.split()
    lines, line = [], ''
    for word in words:
        candidate = (line + ' ' + word).strip()
        if font.size(candidate)[0] <= max_w:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines or ['']


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


# ─────────────────────────────────────────────────────────────────────────────
#  Button widget
# ─────────────────────────────────────────────────────────────────────────────

class Btn:
    def __init__(self, rect, text='', color=CARD2, fg=WHITE, bc=None, r=10):
        self.rect    = pygame.Rect(rect)
        self.text    = text
        self.color   = color
        self.fg      = fg
        self.bc      = bc
        self.r       = r
        self.pressed = False
        self.font: Optional[pygame.font.Font] = None

    def draw(self, surf):
        c = tuple(max(0, v - 25) for v in self.color) if self.pressed else self.color
        rr(surf, c, self.rect, self.r, border=1 if self.bc else 0, bc=self.bc)
        if self.font and self.text:
            blit_text(surf, self.text, self.font, self.fg,
                      (self.rect.x, self.rect.y, self.rect.w, self.rect.h))

    def hit(self, pos) -> bool:
        return self.rect.collidepoint(pos)


# ─────────────────────────────────────────────────────────────────────────────
#  App-wide state + Flask API wrapper
# ─────────────────────────────────────────────────────────────────────────────

class AppState:
    def __init__(self):
        self.local_ip  = get_local_ip()
        self._flask_ok = False
        self._status: Dict[str, Any] = {}
        self._lock     = threading.Lock()
        self._stopper  = threading.Event()

    def start(self):
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()

    def stop(self):
        self._stopper.set()

    def _poll_loop(self):
        while not self._stopper.is_set():
            try:
                r = _requests.get(f'{API}/status', timeout=API_TIMEOUT)
                ok = r.status_code == 200
                data = r.json() if ok else {}
            except Exception:
                ok, data = False, {}
            with self._lock:
                self._flask_ok = ok
                if ok:
                    self._status = data
            self._stopper.wait(POLL_INTERVAL)

    def snapshot(self) -> Tuple[bool, Dict[str, Any]]:
        with self._lock:
            return self._flask_ok, dict(self._status)

    # ── HTTP helpers (called from background threads) ─────────────────────────

    def get(self, path: str) -> Tuple[bool, Any]:
        if not _HAS_REQUESTS:
            return False, {}
        try:
            r = _requests.get(f'{API}{path}', timeout=API_TIMEOUT)
            return r.status_code == 200, (r.json() if r.content else {})
        except Exception as e:
            return False, {'error': str(e)}

    def post(self, path: str, data=None) -> Tuple[bool, Any]:
        if not _HAS_REQUESTS:
            return False, {}
        try:
            r = _requests.post(f'{API}{path}', json=data, timeout=API_TIMEOUT)
            return r.status_code == 200, (r.json() if r.content else {})
        except Exception as e:
            return False, {'error': str(e)}

    def delete(self, path: str) -> Tuple[bool, Any]:
        if not _HAS_REQUESTS:
            return False, {}
        try:
            r = _requests.delete(f'{API}{path}', timeout=API_TIMEOUT)
            return r.status_code == 200, (r.json() if r.content else {})
        except Exception as e:
            return False, {'error': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
#  Base Screen
# ─────────────────────────────────────────────────────────────────────────────

class Screen:
    def __init__(self, app: 'App'):
        self.app = app

    def on_enter(self, **kw):  pass
    def on_exit(self):          pass
    def touch_down(self, pos):  pass
    def touch_up(self, pos):    pass
    def render(self, surf):     pass

    # ── Shared header: title bar + back chevron + API dot ────────────────────
    def _header(self, surf, title: str, back=True) -> Optional[pygame.Rect]:
        pygame.draw.rect(surf, HEADER, (0, 0, W, 44))
        pygame.draw.line(surf, ACCENT,  (0, 44), (W, 44), 1)
        ok, _ = self.app.state.snapshot()
        pygame.draw.circle(surf, GREEN if ok else RED, (W - 15, 22), 7)
        f = self.app.fonts
        dot_lbl = f['xs'].render('ON' if ok else 'OFF', True, DARK if ok else WHITE)
        surf.blit(dot_lbl, (W - 15 - dot_lbl.get_width() // 2,
                             22 - dot_lbl.get_height() // 2))
        t = f['md'].render(title, True, WHITE)
        surf.blit(t, (W // 2 - t.get_width() // 2, 12))
        if back:
            back_s = f['sm'].render('< Back', True, ACCENT)
            surf.blit(back_s, (10, 14))
            return pygame.Rect(0, 0, 85, 44)
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  HOME SCREEN
# ─────────────────────────────────────────────────────────────────────────────

class HomeScreen(Screen):
    _MENU = [
        ('TRANSLATE',  ACCENT, 'Translation\nSessions'),
        ('DEEPFAKE',   RED,    'Deepfake\nDetection'),
        ('RECORDINGS', GREEN,  'Recordings\nManager'),
        ('SETTINGS',   GRAY,   'System\nSettings'),
    ]

    def on_enter(self, **_):
        pad, bw, bh = 10, (W - 30) // 2, 110
        self._btns: List[Tuple[Btn, str]] = []
        targets = ['translate', 'deepfake', 'recordings', 'settings']
        for i, (label, color, _) in enumerate(self._MENU):
            col = i % 2
            row = i // 2
            x = pad + col * (bw + pad)
            y = 54 + row * (bh + pad)
            b = Btn((x, y, bw, bh), label, CARD2, WHITE, color, r=14)
            b.font = self.app.fonts['md']
            self._btns.append((b, targets[i]))

    def touch_down(self, pos):
        for b, _ in self._btns:
            b.pressed = b.hit(pos)

    def touch_up(self, pos):
        for b, target in self._btns:
            if b.pressed and b.hit(pos):
                self.app.go(target)
            b.pressed = False

    def render(self, surf):
        surf.fill(BG)
        # Title bar
        pygame.draw.rect(surf, HEADER, (0, 0, W, 46))
        pygame.draw.line(surf, ACCENT, (0, 46), (W, 46), 1)
        f = self.app.fonts
        t1 = f['lg'].render('Smart Headphone', True, ACCENT)
        t2 = f['xs'].render('Translation + Deepfake Detection System', True, GRAY)
        surf.blit(t1, (W // 2 - t1.get_width() // 2, 4))
        surf.blit(t2, (W // 2 - t2.get_width() // 2, 30))

        ok, status = self.app.state.snapshot()
        # API dot (right of header)
        pygame.draw.circle(surf, GREEN if ok else RED, (W - 15, 16), 7)
        dot_l = f['xs'].render('API', True, DARK if ok else WHITE)
        surf.blit(dot_l, (W - 15 - dot_l.get_width() // 2, 16 - dot_l.get_height() // 2))

        for i, ((b, _), (_, color, subtitle)) in enumerate(zip(self._btns, self._MENU)):
            rr(surf, CARD2, b.rect, 14, border=2, bc=color)
            # Sub-label (two lines inside button)
            for li, line in enumerate(subtitle.split('\n')):
                ls = f['xs'].render(line, True, color)
                surf.blit(ls, (b.rect.centerx - ls.get_width() // 2,
                                b.rect.y + 18 + li * 18))
            lbl = f['md'].render(b.text, True, WHITE)
            surf.blit(lbl, (b.rect.centerx - lbl.get_width() // 2,
                             b.rect.y + 62))

        # Footer
        ip_s  = f['xs'].render(f"IP: {self.app.state.local_ip}:5000", True, GRAY)
        cnt   = status.get('translation_count', 0)
        cnt_s = f['xs'].render(f"Translations: {cnt}", True, GRAY)
        surf.blit(ip_s,  (10, H - 20))
        surf.blit(cnt_s, (W - cnt_s.get_width() - 10, H - 20))


# ─────────────────────────────────────────────────────────────────────────────
#  TRANSLATE SETUP SCREEN
# ─────────────────────────────────────────────────────────────────────────────

class TranslateScreen(Screen):
    def on_enter(self, **_):
        self._mode      = 'online'
        self._direction = '1way'
        self._from_idx  = 0
        self._to_idx    = 1
        self._error     = ''
        self._busy      = False
        f = self.app.fonts
        # Mode
        self._b_online  = Btn((120, 64, 100, 34), 'ONLINE',  r=9)
        self._b_offline = Btn((232, 64, 100, 34), 'OFFLINE', r=9)
        # Direction
        self._b_1way    = Btn((120, 110, 100, 34), '1-WAY',   r=9)
        self._b_2way    = Btn((232, 110, 100, 34), '2-WAY',   r=9)
        # From lang arrows
        self._b_fl      = Btn(( 10, 162,  32, 34), '<', CARD, ACCENT, r=8)
        self._b_fr      = Btn((185, 162,  32, 34), '>', CARD, ACCENT, r=8)
        # To lang arrows
        self._b_tl      = Btn((248, 162,  32, 34), '<', CARD, ACCENT, r=8)
        self._b_tr      = Btn((423, 162,  32, 34), '>', CARD, ACCENT, r=8)
        # Start
        self._b_start   = Btn((130, 218, 220, 54), '> START', GREEN, DARK, r=16)
        for b in [self._b_online, self._b_offline, self._b_1way, self._b_2way,
                  self._b_fl, self._b_fr, self._b_tl, self._b_tr, self._b_start]:
            b.font = f['sm']
        self._b_start.font = f['md']

    def _all(self):
        return [self._b_online, self._b_offline, self._b_1way, self._b_2way,
                self._b_fl, self._b_fr, self._b_tl, self._b_tr, self._b_start]

    def touch_down(self, pos):
        for b in self._all():
            b.pressed = b.hit(pos)

    def touch_up(self, pos):
        for b in self._all():
            b.pressed = False
        back = self._header.__func__  # check back area
        if pygame.Rect(0, 0, 85, 44).collidepoint(pos):
            self.app.go('home'); return
        if self._b_online.hit(pos):   self._mode = 'online';   self._error = ''
        elif self._b_offline.hit(pos):self._mode = 'offline';  self._error = ''
        elif self._b_1way.hit(pos):   self._direction = '1way'
        elif self._b_2way.hit(pos):   self._direction = '2way'
        elif self._b_fl.hit(pos):     self._from_idx = (self._from_idx - 1) % len(LANGUAGES)
        elif self._b_fr.hit(pos):     self._from_idx = (self._from_idx + 1) % len(LANGUAGES)
        elif self._b_tl.hit(pos):     self._to_idx   = (self._to_idx   - 1) % len(LANGUAGES)
        elif self._b_tr.hit(pos):     self._to_idx   = (self._to_idx   + 1) % len(LANGUAGES)
        elif self._b_start.hit(pos) and not self._busy:
            self._busy = True
            threading.Thread(target=self._start, daemon=True).start()

    def _start(self):
        ok, _ = self.app.state.post('/pi/start', {
            'direction': self._direction,
            'mode':      self._mode,
            'from_lang': LANGUAGES[self._from_idx][0],
            'to_lang':   LANGUAGES[self._to_idx][0],
        })
        self._busy = False
        if ok:
            self.app.go('session',
                        direction  = self._direction,
                        mode       = self._mode,
                        from_name  = LANGUAGES[self._from_idx][1],
                        to_name    = LANGUAGES[self._to_idx][1])
        else:
            self._error = 'Cannot reach Flask API — is it running?'

    def render(self, surf):
        surf.fill(BG)
        self._header(surf, 'Translation Setup')
        f = self.app.fonts

        # Mode buttons
        lbl = f['sm'].render('Mode:', True, GRAY)
        surf.blit(lbl, (10, 76))
        for b, active in [(self._b_online,  self._mode == 'online'),
                          (self._b_offline, self._mode == 'offline')]:
            b.color = ACCENT if active else CARD2
            b.fg    = DARK   if active else WHITE
            b.bc    = ACCENT if active else None
            b.draw(surf)

        # Direction buttons
        lbl2 = f['sm'].render('Direction:', True, GRAY)
        surf.blit(lbl2, (10, 122))
        for b, active in [(self._b_1way, self._direction == '1way'),
                          (self._b_2way, self._direction == '2way')]:
            b.color = GREEN if active else CARD2
            b.fg    = DARK  if active else WHITE
            b.bc    = GREEN if active else None
            b.draw(surf)

        # Language pickers
        fn = LANGUAGES[self._from_idx][1]
        tn = LANGUAGES[self._to_idx][1]
        lbl3 = f['sm'].render('From:', True, GRAY)
        surf.blit(lbl3, (10, 174))

        # From box
        rr(surf, CARD2, (44, 162, 139, 34), 8, border=1, bc=ACCENT)
        blit_text(surf, fn[:10], f['sm'], WHITE, (44, 162, 139, 34))
        self._b_fl.draw(surf); self._b_fr.draw(surf)

        # Arrow
        arr = f['md'].render('=>', True, ACCENT)
        surf.blit(arr, (216, 170))

        # To box
        rr(surf, CARD2, (282, 162, 139, 34), 8, border=1, bc=GREEN)
        blit_text(surf, tn[:10], f['sm'], WHITE, (282, 162, 139, 34))
        self._b_tl.draw(surf); self._b_tr.draw(surf)

        # Start
        if self._busy:
            self._b_start.color = GRAY
            self._b_start.text  = 'Starting...'
        else:
            self._b_start.color = GREEN
            self._b_start.text  = '> START'
        self._b_start.draw(surf)

        if self._error:
            e = f['xs'].render(self._error, True, RED)
            surf.blit(e, (W // 2 - e.get_width() // 2, 284))


# ─────────────────────────────────────────────────────────────────────────────
#  ACTIVE SESSION SCREEN
# ─────────────────────────────────────────────────────────────────────────────

_STATE_LABELS = {
    'idle':        ('IDLE',          GRAY),
    'listening':   ('LISTENING...',  GREEN),
    'recording':   ('RECORDING...',  ACCENT),
    'translating': ('TRANSLATING...', AMBER),
    'speaking':    ('SPEAKING...',   ACCENT),
    'done':        ('DONE',          GREEN),
    'error':       ('ERROR',         RED),
    'unknown':     ('WAITING...',    GRAY),
}


class SessionScreen(Screen):
    def on_enter(self, direction='1way', mode='online',
                 from_name='English', to_name='Urdu', **_):
        self._dir    = direction
        self._mode   = mode
        self._from   = from_name
        self._to     = to_name
        bw = 180
        self._b_stop = Btn((W // 2 - bw // 2, H - 58, bw, 46),
                           '  STOP SESSION', RED, WHITE, r=14)
        self._b_stop.font = self.app.fonts['md']

    def touch_down(self, pos):
        self._b_stop.pressed = self._b_stop.hit(pos)

    def touch_up(self, pos):
        self._b_stop.pressed = False
        if self._b_stop.hit(pos):
            threading.Thread(
                target=lambda: self.app.state.post('/pi/stop'), daemon=True
            ).start()
            self.app.go('translate')

    def render(self, surf):
        surf.fill(BG)
        ok, status = self.app.state.snapshot()
        f = self.app.fonts

        # Header row
        pygame.draw.rect(surf, HEADER, (0, 0, W, 44))
        pygame.draw.line(surf, ACCENT, (0, 44), (W, 44), 1)
        dir_s  = '1-WAY' if self._dir == '1way' else '2-WAY'
        mode_s = 'ONLINE' if self._mode == 'online' else 'OFFLINE'
        hdr = f['sm'].render(
            f"{dir_s} | {mode_s} | {self._from[:3].upper()} -> {self._to[:3].upper()}", True, GRAY)
        surf.blit(hdr, (10, 14))

        raw_state = status.get('state', 'unknown')
        slabel, scolor = _STATE_LABELS.get(raw_state, (raw_state.upper(), GRAY))
        pygame.draw.circle(surf, scolor, (W - 90, 22), 5)
        sl = f['sm'].render(slabel, True, scolor)
        surf.blit(sl, (W - 82, 14))

        # Original text box
        rr(surf, CARD, (8, 52, W - 16, 82), 10, border=1, bc=GRAY)
        from_lbl = f['xs'].render(f"[ {self._from} — original ]", True, ACCENT)
        surf.blit(from_lbl, (16, 56))
        orig = status.get('last_original', '')
        lines = wrap_text(f['sm'], orig or 'Waiting for speech...', W - 36)
        for i, ln in enumerate(lines[:3]):
            c = WHITE if orig else GRAY
            surf.blit(f['sm'].render(ln, True, c), (16, 74 + i * 20))

        # Middle divider
        arrow_s = f['xs'].render('-' * 22 + '  translated  ' + '-' * 22, True, GRAY)
        surf.blit(arrow_s, (W // 2 - arrow_s.get_width() // 2, 138))

        # Translated text box
        rr(surf, CARD, (8, 155, W - 16, 82), 10, border=1, bc=GREEN)
        to_lbl = f['xs'].render(f"[ {self._to} — translation ]", True, GREEN)
        surf.blit(to_lbl, (16, 159))
        transl = status.get('last_translated', '')
        lines2 = wrap_text(f['sm'], transl or '...', W - 36)
        for i, ln in enumerate(lines2[:3]):
            c = WHITE if transl else GRAY
            surf.blit(f['sm'].render(ln, True, c), (16, 177 + i * 20))

        # Count
        cnt = status.get('translation_count', 0)
        cnt_s = f['xs'].render(f"Session translations: {cnt}", True, GRAY)
        surf.blit(cnt_s, (10, H - 68))

        if not ok:
            warn = f['xs'].render('! API offline — session may have ended', True, RED)
            surf.blit(warn, (10, H - 80))

        self._b_stop.draw(surf)


# ─────────────────────────────────────────────────────────────────────────────
#  DEEPFAKE DETECTION SCREEN
# ─────────────────────────────────────────────────────────────────────────────

class DeepfakeScreen(Screen):
    _ROW_H   = 48
    _VISIBLE = 5

    def on_enter(self, **_):
        self._recs: List[Dict]    = []
        self._results: Dict[str, Dict] = {}
        self._testing: Optional[str]   = None
        self._scroll  = 0
        self._loading = True
        self._error   = ''
        self._b_refresh = Btn((W - 94, 10, 82, 26), 'Refresh', CARD2, ACCENT, ACCENT, r=8)
        self._b_refresh.font = self.app.fonts['sm']
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        self._loading = True
        ok, data = self.app.state.get('/recordings?source=pi')
        if ok:
            self._recs = data.get('recordings', [])
            self._error = ''
        else:
            self._error = 'Cannot load recordings. Is Flask running?'
        self._loading = False

    def _test_row_rect(self, vis_i: int) -> pygame.Rect:
        y = 52 + vis_i * self._ROW_H
        return pygame.Rect(W - 74, y + 10, 66, 28)

    def _do_test(self, name: str):
        self._testing = name
        ok, data = self.app.state.post(f'/detect_recording/{name}')
        self._results[name] = data if ok else {'error': 'Failed'}
        self._testing = None

    def touch_down(self, pos): pass

    def touch_up(self, pos):
        if pygame.Rect(0, 0, 85, 44).collidepoint(pos):
            self.app.go('home'); return
        if self._b_refresh.hit(pos):
            threading.Thread(target=self._load, daemon=True).start(); return

        if self._loading or self._testing:
            return
        for vis_i, abs_i in enumerate(range(self._scroll,
                                             min(self._scroll + self._VISIBLE, len(self._recs)))):
            name = self._recs[abs_i]['name']
            if name not in self._results and self._test_row_rect(vis_i).collidepoint(pos):
                threading.Thread(target=self._do_test, args=(name,), daemon=True).start()
                return
        # Scroll arrows (last col)
        if pygame.Rect(W - 30, 52, 24, 44).collidepoint(pos):
            self._scroll = max(0, self._scroll - 1)
        elif pygame.Rect(W - 30, H - 70, 24, 44).collidepoint(pos):
            self._scroll = min(max(0, len(self._recs) - self._VISIBLE), self._scroll + 1)

    def render(self, surf):
        surf.fill(BG)
        self._header(surf, 'Deepfake Detection')
        self._b_refresh.draw(surf)
        f = self.app.fonts

        if self._loading:
            m = f['md'].render('Loading recordings...', True, GRAY)
            surf.blit(m, (W // 2 - m.get_width() // 2, H // 2 - 10)); return

        if self._error:
            m = f['sm'].render(self._error, True, RED)
            surf.blit(m, (10, 80)); return

        if not self._recs:
            m = f['sm'].render('No recordings found on Pi', True, GRAY)
            surf.blit(m, (W // 2 - m.get_width() // 2, H // 2 - 10)); return

        row_w = W - 86
        for vis_i, abs_i in enumerate(range(self._scroll,
                                             min(self._scroll + self._VISIBLE, len(self._recs)))):
            rec  = self._recs[abs_i]
            name = rec['name']
            y    = 52 + vis_i * self._ROW_H
            rr(surf, CARD, (8, y, row_w, self._ROW_H - 4), 8)
            nm = f['sm'].render(name[:26], True, WHITE)
            surf.blit(nm, (14, y + 4))
            sz = f['xs'].render(f"{rec.get('size_mb', 0):.1f}MB", True, GRAY)
            surf.blit(sz, (14, y + 26))

            res = self._results.get(name)
            if self._testing == name:
                tst = f['xs'].render('Testing...', True, AMBER)
                surf.blit(tst, (row_w - tst.get_width() + 4, y + 18))
            elif res:
                if 'verdict' in res:
                    verdict = res['verdict']
                    conf    = int(res.get('confidence', 0) * 100)
                    color   = RED if verdict == 'FAKE' else GREEN
                    vs = f['sm'].render(f"{verdict} {conf}%", True, color)
                    surf.blit(vs, (row_w - vs.get_width() + 4, y + 14))
                else:
                    es = f['xs'].render('Error', True, RED)
                    surf.blit(es, (row_w - es.get_width() + 4, y + 18))
            else:
                tr = self._test_row_rect(vis_i)
                rr(surf, CARD2, tr, 6, border=1, bc=ACCENT)
                tt = f['xs'].render('TEST', True, ACCENT)
                surf.blit(tt, (tr.centerx - tt.get_width() // 2,
                                tr.centery - tt.get_height() // 2))

        # Scroll indicators
        if self._scroll > 0:
            u = f['sm'].render('^', True, ACCENT)
            surf.blit(u, (W - 24, 56))
        if self._scroll + self._VISIBLE < len(self._recs):
            d = f['sm'].render('v', True, ACCENT)
            surf.blit(d, (W - 24, H - 64))

        cnt = f['xs'].render(
            f"{len(self._recs)} recordings  |  {len(self._results)} tested", True, GRAY)
        surf.blit(cnt, (10, H - 20))


# ─────────────────────────────────────────────────────────────────────────────
#  RECORDINGS MANAGER SCREEN
# ─────────────────────────────────────────────────────────────────────────────

class RecordingsScreen(Screen):
    _ROW_H   = 44
    _VISIBLE = 5

    def on_enter(self, **_):
        self._recs: List[Dict] = []
        self._loading = True
        self._scroll  = 0
        self._error   = ''
        self._busy    = False
        self._msg     = ''
        self._msg_t   = 0
        self._msg_c   = GRAY
        f = self.app.fonts
        self._b_refresh = Btn((W - 94, 10, 82, 26), 'Refresh', CARD2, ACCENT, ACCENT, r=8)
        self._b_backup  = Btn((W - 94, H - 40, 82, 30), 'Backup', CARD2, GREEN, GREEN, r=8)
        for b in [self._b_refresh, self._b_backup]:
            b.font = f['sm']
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        self._loading = True
        ok, data = self.app.state.get('/recordings?source=all')
        self._recs  = data.get('recordings', []) if ok else []
        self._error = '' if ok else 'Cannot reach server'
        self._loading = False

    def _delete(self, name: str):
        self._busy = True
        ok, _ = self.app.state.delete(f'/recordings/{name}')
        self._msg   = f"Deleted {name}" if ok else f"Delete failed"
        self._msg_c = GREEN if ok else RED
        self._msg_t = time.time()
        self._busy  = False
        threading.Thread(target=self._load, daemon=True).start()

    def _backup(self):
        self._busy = True
        ok, _ = self.app.state.post('/recordings/backup')
        self._msg   = 'Backup started — uploading to Google Drive' if ok else 'Backup failed'
        self._msg_c = GREEN if ok else RED
        self._msg_t = time.time()
        self._busy  = False

    def _del_rect(self, vis_i: int) -> pygame.Rect:
        y = 52 + vis_i * self._ROW_H
        return pygame.Rect(W - 78, y + 8, 70, 28)

    def touch_down(self, pos): pass

    def touch_up(self, pos):
        if pygame.Rect(0, 0, 85, 44).collidepoint(pos):
            self.app.go('home'); return
        if self._b_refresh.hit(pos):
            threading.Thread(target=self._load, daemon=True).start(); return
        if self._b_backup.hit(pos) and not self._busy:
            threading.Thread(target=self._backup, daemon=True).start(); return
        if self._busy or self._loading:
            return
        for vis_i, abs_i in enumerate(range(self._scroll,
                                             min(self._scroll + self._VISIBLE, len(self._recs)))):
            rec = self._recs[abs_i]
            if not rec.get('source', 'pi') == 'cloud':  # only delete pi files
                if self._del_rect(vis_i).collidepoint(pos):
                    name = rec['name']
                    threading.Thread(target=self._delete, args=(name,), daemon=True).start()
                    return
        # Scroll
        if pygame.Rect(W - 28, 52, 22, 44).collidepoint(pos):
            self._scroll = max(0, self._scroll - 1)
        elif pygame.Rect(W - 28, H - 80, 22, 44).collidepoint(pos):
            self._scroll = min(max(0, len(self._recs) - self._VISIBLE), self._scroll + 1)

    def render(self, surf):
        surf.fill(BG)
        self._header(surf, 'Recordings')
        self._b_refresh.draw(surf)
        self._b_backup.draw(surf)
        f = self.app.fonts

        if self._loading:
            m = f['md'].render('Loading...', True, GRAY)
            surf.blit(m, (W // 2 - m.get_width() // 2, H // 2)); return

        if self._error:
            m = f['sm'].render(self._error, True, RED)
            surf.blit(m, (10, 60)); return

        if not self._recs:
            m = f['sm'].render('No recordings on Pi', True, GRAY)
            surf.blit(m, (W // 2 - m.get_width() // 2, H // 2)); return

        row_w = W - 90
        for vis_i, abs_i in enumerate(range(self._scroll,
                                             min(self._scroll + self._VISIBLE, len(self._recs)))):
            rec    = self._recs[abs_i]
            name   = rec.get('name', '')
            is_cld = rec.get('source', 'pi') == 'cloud'
            y = 52 + vis_i * self._ROW_H
            border_c = GREEN if is_cld else ACCENT
            rr(surf, CARD, (8, y, row_w, self._ROW_H - 4), 8, border=1, bc=border_c)
            nm = f['sm'].render(name[:26], True, WHITE)
            surf.blit(nm, (14, y + 4))
            meta = f"{'Cloud' if is_cld else 'Pi'}  {rec.get('size_mb', 0):.1f}MB  {rec.get('date','')[:10]}"
            ms = f['xs'].render(meta, True, border_c)
            surf.blit(ms, (14, y + 24))
            if not is_cld:
                dr = self._del_rect(vis_i)
                rr(surf, DIMRED, dr, 6, border=1, bc=RED)
                dt = f['xs'].render('DEL', True, RED)
                surf.blit(dt, (dr.centerx - dt.get_width() // 2,
                                dr.centery - dt.get_height() // 2))

        if self._scroll > 0:
            surf.blit(f['sm'].render('^', True, ACCENT), (W - 22, 56))
        if self._scroll + self._VISIBLE < len(self._recs):
            surf.blit(f['sm'].render('v', True, ACCENT), (W - 22, H - 90))

        # Message toast
        if self._msg and time.time() - self._msg_t < 4:
            ms = f['xs'].render(self._msg, True, self._msg_c)
            surf.blit(ms, (10, H - 52))

        cnt = f['xs'].render(f"{len(self._recs)} files", True, GRAY)
        surf.blit(cnt, (10, H - 20))


# ─────────────────────────────────────────────────────────────────────────────
#  SETTINGS SCREEN
# ─────────────────────────────────────────────────────────────────────────────

class SettingsScreen(Screen):
    def on_enter(self, **_):
        f = self.app.fonts
        self._b_restart = Btn((10,  72, W - 20, 46), 'Restart Flask API', CARD2, ACCENT, ACCENT, r=12)
        self._b_reboot  = Btn((10, 130, W - 20, 46), 'Reboot Pi',         CARD2, AMBER,  AMBER,  r=12)
        self._b_shutdown= Btn((10, 188, W - 20, 46), 'Shutdown Pi',       DIMRED, RED,   RED,    r=12)
        for b in [self._b_restart, self._b_reboot, self._b_shutdown]:
            b.font = f['md']
        self._msg   = ''
        self._msg_c = GRAY
        self._msg_t = 0

    def _run_cmd(self, cmd: List[str], msg_ok: str, msg_fail: str):
        try:
            subprocess.run(cmd, check=True, timeout=5)
            self._msg = msg_ok; self._msg_c = GREEN
        except Exception as e:
            self._msg = msg_fail; self._msg_c = RED
        self._msg_t = time.time()

    def touch_down(self, pos): pass

    def touch_up(self, pos):
        if pygame.Rect(0, 0, 85, 44).collidepoint(pos):
            self.app.go('home'); return
        if self._b_restart.hit(pos):
            threading.Thread(
                target=self._run_cmd,
                args=(['sudo', 'systemctl', 'restart', 'smart-headphone-api'],
                      'API restarting...', 'Restart failed'),
                daemon=True
            ).start()
        elif self._b_reboot.hit(pos):
            self._msg   = 'Rebooting in 3 seconds...'
            self._msg_c = AMBER
            self._msg_t = time.time()
            threading.Thread(
                target=lambda: (time.sleep(3),
                                subprocess.run(['sudo', 'reboot'], check=False)),
                daemon=True
            ).start()
        elif self._b_shutdown.hit(pos):
            self._msg   = 'Shutting down in 3 seconds...'
            self._msg_c = RED
            self._msg_t = time.time()
            threading.Thread(
                target=lambda: (time.sleep(3),
                                subprocess.run(['sudo', 'shutdown', '-h', 'now'], check=False)),
                daemon=True
            ).start()

    def touch_down(self, pos): pass

    def render(self, surf):
        surf.fill(BG)
        self._header(surf, 'Settings')
        f = self.app.fonts
        self._b_restart.draw(surf)
        self._b_reboot.draw(surf)
        self._b_shutdown.draw(surf)

        # Info rows
        info = [
            ('Pi IP Address',   self.app.state.local_ip),
            ('Flask API URL',   f'{self.app.state.local_ip}:5000'),
            ('Display Size',    f'{W} x {H}'),
            ('Version',         '1.0.0'),
        ]
        y = 248
        for label, val in info:
            lbl = f['xs'].render(f'{label}:', True, GRAY)
            vs  = f['xs'].render(val, True, ACCENT)
            surf.blit(lbl, (14, y))
            surf.blit(vs,  (W - vs.get_width() - 14, y))
            y += 18

        if self._msg and time.time() - self._msg_t < 5:
            ms = f['sm'].render(self._msg, True, self._msg_c)
            surf.blit(ms, (W // 2 - ms.get_width() // 2, 54))


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN APPLICATION
# ─────────────────────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        pygame.init()
        pygame.mouse.set_visible(False)

        flags = (FULLSCREEN | NOFRAME) if _ON_PI else 0
        self.display = pygame.display.set_mode((W, H), flags)
        pygame.display.set_caption('Smart Headphone')

        # Fonts — freesans exists on Raspberry Pi OS; falls back to default
        try:
            font_name = 'freesans'
            pygame.font.SysFont(font_name, 10)  # test availability
        except Exception:
            font_name = None
        self.fonts = {
            'xs': pygame.font.SysFont(font_name, 13),
            'sm': pygame.font.SysFont(font_name, 16),
            'md': pygame.font.SysFont(font_name, 20),
            'lg': pygame.font.SysFont(font_name, 24),
        }

        self.state = AppState()
        self.state.start()

        self._screens: Dict[str, Screen] = {
            'home':        HomeScreen(self),
            'translate':   TranslateScreen(self),
            'session':     SessionScreen(self),
            'deepfake':    DeepfakeScreen(self),
            'recordings':  RecordingsScreen(self),
            'settings':    SettingsScreen(self),
        }
        self._cur = 'home'
        self._screens['home'].on_enter()
        self._clock = pygame.time.Clock()

    def go(self, name: str, **kw):
        if name not in self._screens:
            return
        self._screens[self._cur].on_exit()
        self._cur = name
        self._screens[name].on_enter(**kw)

    def run(self):
        running = True
        while running:
            for ev in pygame.event.get():
                if ev.type == QUIT:
                    running = False
                elif ev.type == KEYDOWN and ev.key == K_ESCAPE:
                    running = False
                elif ev.type == MOUSEBUTTONDOWN:
                    self._screens[self._cur].touch_down(ev.pos)
                elif ev.type == MOUSEBUTTONUP:
                    self._screens[self._cur].touch_up(ev.pos)
                elif ev.type == FINGERDOWN:
                    pos = (int(ev.x * W), int(ev.y * H))
                    self._screens[self._cur].touch_down(pos)
                elif ev.type == FINGERUP:
                    pos = (int(ev.x * W), int(ev.y * H))
                    self._screens[self._cur].touch_up(pos)

            self._screens[self._cur].render(self.display)
            pygame.display.flip()
            self._clock.tick(30)  # 30 FPS — easy on Pi CPU

        self.state.stop()
        pygame.quit()


if __name__ == '__main__':
    App().run()
