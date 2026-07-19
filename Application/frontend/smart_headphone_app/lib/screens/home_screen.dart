import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../providers/translation_provider.dart';
import '../services/pi_service.dart';
import '../utils/app_theme.dart';
import '../utils/supported_languages.dart';

/// This screen is intentionally Pi-only: the Pi is the single device that
/// listens (its own microphone) and speaks (its own/Bluetooth speaker) —
/// the phone here is a remote control and monitor, not an alternate
/// input/output path. There is deliberately no phone-mic or on-screen
/// keyboard translate flow.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  // Server connectivity — polled quietly every 12 s
  bool _serverOnline = false;
  bool _pollBusy = false;
  Timer? _pollTimer;

  // Pi session state
  bool _piRunning = false;
  bool _piLoading = false;
  String _activeDirection = '';  // '1way' | '2way'
  int _recordingCount = 0;       // count utterances recorded this session
  Timer? _recordingTimer;

  // Live monitor — what the Pi last heard/translated, from /status polling
  String _lastOriginal = '';
  String _lastTranslated = '';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _pollServer();
      _pollTimer =
          Timer.periodic(const Duration(seconds: 12), (_) => _pollServer());
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _recordingTimer?.cancel();
    super.dispose();
  }

  Future<void> _pollServer() async {
    if (_pollBusy || !mounted) return;
    _pollBusy = true;
    final p = context.read<TranslationProvider>();
    final url = p.serverUrl;
    final alive = url.isNotEmpty && await PiService(url).checkHealth();
    if (!mounted) { _pollBusy = false; return; }
    if (alive != _serverOnline) setState(() => _serverOnline = alive);

    // Recover Pi session state if app was restarted while a session was running
    if (alive && !_piRunning) {
      final status = await PiService(url).getStatus();
      if (mounted && status != null && status.state != 'idle') {
        setState(() {
          _piRunning = true;
          _recordingCount = status.recordingsLocal;
          _activeDirection = status.direction;
          _lastOriginal = status.lastOriginal;
          _lastTranslated = status.lastTranslated;
        });
        _startRecordingPoll(url);
      }
    }
    _pollBusy = false;
  }

  void _startRecordingPoll(String url) {
    _recordingTimer?.cancel();
    _recordingTimer = Timer.periodic(const Duration(seconds: 3), (_) async {
      if (!_piRunning || !mounted) { _recordingTimer?.cancel(); return; }
      final status = await PiService(url).getStatus();
      if (mounted && status != null) {
        setState(() {
          _recordingCount = status.recordingsLocal;
          _lastOriginal = status.lastOriginal;
          _lastTranslated = status.lastTranslated;
        });
      }
    });
  }

  Future<void> _startPiSession(String direction) async {
    final consented = await _confirmRecordingConsent(direction);
    if (!mounted || !consented) return;

    setState(() => _piLoading = true);
    final p = context.read<TranslationProvider>();
    final ok = await PiService(p.serverUrl).startTranslation(
      direction: direction,
      mode: p.mode == TranslationMode.online ? 'online' : 'offline',
      fromLang: p.fromLang.code,
      toLang: p.toLang.code,
    );
    if (!mounted) return;
    if (ok) {
      setState(() {
        _piRunning = true;
        _piLoading = false;
        _activeDirection = direction;
        _recordingCount = 0;
        _lastOriginal = '';
        _lastTranslated = '';
      });
      _startRecordingPoll(p.serverUrl);
    } else {
      setState(() => _piLoading = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: const Text('Could not start Pi. Check server connection.'),
          backgroundColor: Colors.redAccent.withValues(alpha: 0.9),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          margin: const EdgeInsets.all(16),
        ));
      }
    }
  }

  Future<void> _stopPiSession() async {
    _recordingTimer?.cancel();
    final p = context.read<TranslationProvider>();
    await PiService(p.serverUrl).stopTranslation();
    if (!mounted) return;
    setState(() {
      _piRunning = false;
      _piLoading = false;
      _activeDirection = '';
    });
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(
        'Session ended — $_recordingCount recording(s) saved',
        style: const TextStyle(color: Colors.white),
      ),
      backgroundColor: AppTheme.accentGreen.withValues(alpha: 0.9),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      margin: const EdgeInsets.all(16),
      duration: const Duration(seconds: 4),
    ));
  }

  /// Asks the user to explicitly consent before the Pi's microphone starts
  /// listening — this session records ambient conversation (potentially
  /// involving people other than the phone's owner), so a clear opt-in
  /// gate before recording begins is a deliberate privacy choice, not just
  /// a confirmation dialog.
  Future<bool> _confirmRecordingConsent(String direction) async {
    final label = direction == '2way' ? '2-Way conversation' : '1-Way';
    final result = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF0E1E3C),
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(18),
            side: BorderSide(color: AppTheme.accent.withValues(alpha: 0.25))),
        icon: const Icon(Icons.mic_rounded, color: AppTheme.accent, size: 32),
        title: const Text('Allow voice recording?',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
        content: Text(
          'Starting $label will make the Pi listen through its own '
          'microphone and save each voice as a recording. Make sure '
          'everyone nearby is okay with being recorded before continuing.',
          style: const TextStyle(color: Colors.white70, height: 1.4),
        ),
        actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel', style: TextStyle(color: Colors.white38)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.accent,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10)),
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Allow & Start',
                style: TextStyle(color: Colors.black, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
    return result ?? false;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF060D1F), Color(0xFF0E1E3C), Color(0xFF162D4A)],
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              _AppBar(serverOnline: _serverOnline),
              // ── STOP SESSION BAR — always visible when Pi is running ──────
              if (_piRunning)
                _StopSessionBar(
                  direction: _activeDirection,
                  recordingCount: _recordingCount,
                  onStop: _stopPiSession,
                ),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
                  child: Column(
                    children: [
                      const _ModeToggle(),
                      const SizedBox(height: 14),
                      _LanguageBar(
                        onPickFrom: () =>
                            _pickLanguage(context, isFrom: true),
                        onPickTo: () =>
                            _pickLanguage(context, isFrom: false),
                      ),
                      const SizedBox(height: 14),
                      if (!_piRunning)
                        _PiControlSection(
                          serverOnline: _serverOnline,
                          loading: _piLoading,
                          onStart: _startPiSession,
                        )
                      else
                        _LiveMonitorSection(
                          fromLang: context.watch<TranslationProvider>().fromLang,
                          toLang: context.watch<TranslationProvider>().toLang,
                          lastOriginal: _lastOriginal,
                          lastTranslated: _lastTranslated,
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _pickLanguage(BuildContext context, {required bool isFrom}) {
    final p = context.read<TranslationProvider>();
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF0E1E3C),
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(26))),
      builder: (_) => _LanguagePicker(
        selected: isFrom ? p.fromLang : p.toLang,
        onSelect: (lang) {
          isFrom ? p.setFromLang(lang) : p.setToLang(lang);
          Navigator.pop(context);
        },
      ),
    );
  }
}

// ──────────────────────────────── App Bar ─────────────────────────────────────

class _AppBar extends StatelessWidget {
  final bool serverOnline;

  const _AppBar({required this.serverOnline});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 16, 10),
      child: Row(
        children: [
          // Logo
          Container(
            padding: const EdgeInsets.all(9),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFF1A3A5C), Color(0xFF0D2137)],
              ),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                  color: AppTheme.accent.withValues(alpha: 0.35)),
              boxShadow: [
                BoxShadow(
                  color: AppTheme.accent.withValues(alpha: 0.2),
                  blurRadius: 10,
                  spreadRadius: 1,
                ),
              ],
            ),
            child: const Icon(Icons.headphones_rounded,
                color: AppTheme.accent, size: 22),
          ),
          const SizedBox(width: 14),
          // Title
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Smart Headphone',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 0.2)),
                Text('TRANSLATION SYSTEM',
                    style: TextStyle(
                        color: AppTheme.accent,
                        fontSize: 9,
                        letterSpacing: 2.2,
                        fontWeight: FontWeight.w600)),
              ],
            ),
          ),
          // Server status dot
          Tooltip(
            message: serverOnline ? 'Pi connected' : 'Pi offline',
            child: Row(
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: serverOnline
                        ? AppTheme.accentGreen
                        : Colors.white24,
                    boxShadow: serverOnline
                        ? [
                            BoxShadow(
                                color: AppTheme.accentGreen
                                    .withValues(alpha: 0.6),
                                blurRadius: 6)
                          ]
                        : null,
                  ),
                ),
                const SizedBox(width: 6),
                Text(
                  serverOnline ? 'Pi connected' : 'Pi offline',
                  style: TextStyle(
                    color: serverOnline ? AppTheme.accentGreen : Colors.white38,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────── Mode Toggle ──────────────────────────────────

class _ModeToggle extends StatelessWidget {
  const _ModeToggle();

  @override
  Widget build(BuildContext context) {
    final p = context.watch<TranslationProvider>();
    final isOnline = p.mode == TranslationMode.online;

    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: const Color(0xFF0E1A2E),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _ModeBtn(
            icon: Icons.cloud_rounded,
            label: 'Online',
            active: isOnline,
            activeColor: AppTheme.accentGreen,
            onTap: () =>
                context.read<TranslationProvider>().setMode(TranslationMode.online),
          ),
          _ModeBtn(
            icon: Icons.offline_bolt_rounded,
            label: 'Offline',
            active: !isOnline,
            activeColor: AppTheme.accent,
            onTap: () =>
                context.read<TranslationProvider>().setMode(TranslationMode.offline),
          ),
        ],
      ),
    );
  }
}

class _ModeBtn extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool active;
  final Color activeColor;
  final VoidCallback onTap;

  const _ModeBtn({
    required this.icon,
    required this.label,
    required this.active,
    required this.activeColor,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 9),
          decoration: BoxDecoration(
            color: active
                ? activeColor.withValues(alpha: 0.15)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(10),
            border: active
                ? Border.all(color: activeColor.withValues(alpha: 0.4))
                : null,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon,
                  color: active ? activeColor : Colors.white30, size: 15),
              const SizedBox(width: 6),
              Text(
                label,
                style: TextStyle(
                  color: active ? activeColor : Colors.white30,
                  fontSize: 13,
                  fontWeight:
                      active ? FontWeight.w600 : FontWeight.normal,
                ),
              ),
            ],
          ),
        ),
      );
}

// ──────────────────────────── Language Bar ────────────────────────────────────

class _LanguageBar extends StatelessWidget {
  final VoidCallback onPickFrom;
  final VoidCallback onPickTo;

  const _LanguageBar(
      {required this.onPickFrom, required this.onPickTo});

  @override
  Widget build(BuildContext context) {
    final p = context.watch<TranslationProvider>();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF142238), Color(0xFF1C3250)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
            color: AppTheme.accent.withValues(alpha: 0.18)),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.35),
              blurRadius: 14,
              offset: const Offset(0, 5))
        ],
      ),
      child: Row(
        children: [
          Expanded(
              child: _LangBtn(
                  lang: p.fromLang,
                  label: 'FROM',
                  onTap: onPickFrom)),
          _SwapBtn(onTap: p.swapLanguages),
          Expanded(
              child: _LangBtn(
                  lang: p.toLang, label: 'TO', onTap: onPickTo)),
        ],
      ),
    );
  }
}

class _LangBtn extends StatelessWidget {
  final Language lang;
  final String label;
  final VoidCallback onTap;

  const _LangBtn(
      {required this.lang, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: onTap,
        child: Column(
          children: [
            Text(label,
                style: const TextStyle(
                    color: Colors.white30,
                    fontSize: 10,
                    letterSpacing: 1.8,
                    fontWeight: FontWeight.w600)),
            const SizedBox(height: 7),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(lang.flag, style: const TextStyle(fontSize: 22)),
                const SizedBox(width: 6),
                Flexible(
                  child: Text(lang.name,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w600)),
                ),
                const Icon(Icons.expand_more_rounded,
                    color: Colors.white38, size: 16),
              ],
            ),
          ],
        ),
      );
}

class _SwapBtn extends StatefulWidget {
  final VoidCallback onTap;
  const _SwapBtn({required this.onTap});

  @override
  State<_SwapBtn> createState() => _SwapBtnState();
}

class _SwapBtnState extends State<_SwapBtn>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _rot;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 380));
    _rot = Tween<double>(begin: 0, end: 1)
        .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _handle() {
    _ctrl.forward(from: 0);
    HapticFeedback.lightImpact();
    widget.onTap();
  }

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: _handle,
        child: AnimatedBuilder(
          animation: _rot,
          builder: (_, child) =>
              Transform.rotate(angle: _rot.value * pi, child: child),
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 10),
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [AppTheme.accent, AppTheme.accentGreen],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(14),
              boxShadow: [
                BoxShadow(
                    color: AppTheme.accent.withValues(alpha: 0.45),
                    blurRadius: 12,
                    spreadRadius: 1)
              ],
            ),
            child: const Icon(Icons.swap_horiz_rounded,
                color: Colors.white, size: 22),
          ),
        ),
      );
}

// ─────────────────────────── Live Monitor Section ─────────────────────────────
//
// Shown while a Pi Control session is running. The Pi does all the actual
// listening/translating/speaking on its own hardware — this panel is a
// read-only monitor of what it last heard and said, polled from /status.

class _LiveMonitorSection extends StatelessWidget {
  final Language fromLang;
  final Language toLang;
  final String lastOriginal;
  final String lastTranslated;

  const _LiveMonitorSection({
    required this.fromLang,
    required this.toLang,
    required this.lastOriginal,
    required this.lastTranslated,
  });

  @override
  Widget build(BuildContext context) {
    if (lastOriginal.isEmpty && lastTranslated.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(24),
        width: double.infinity,
        decoration: BoxDecoration(
          color: const Color(0xFF142238),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
        ),
        child: Column(
          children: [
            Icon(Icons.hearing_rounded,
                color: AppTheme.accent.withValues(alpha: 0.4), size: 40),
            const SizedBox(height: 12),
            const Text('Listening for speech on the Pi…',
                style: TextStyle(color: Colors.white38, fontSize: 13)),
          ],
        ),
      );
    }

    return Column(
      children: [
        if (lastOriginal.isNotEmpty)
          _MonitorCard(
            flag: fromLang.flag,
            label: fromLang.name,
            text: lastOriginal,
            highlight: false,
          ),
        if (lastTranslated.isNotEmpty) ...[
          const SizedBox(height: 10),
          _MonitorCard(
            flag: toLang.flag,
            label: toLang.name,
            text: lastTranslated,
            highlight: true,
          ),
        ],
      ],
    );
  }
}

class _MonitorCard extends StatelessWidget {
  final String flag;
  final String label;
  final String text;
  final bool highlight;

  const _MonitorCard({
    required this.flag,
    required this.label,
    required this.text,
    required this.highlight,
  });

  @override
  Widget build(BuildContext context) {
    final accent = highlight ? AppTheme.accent : Colors.white54;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: highlight
              ? [const Color(0xFF14294A), const Color(0xFF1B3A5E)]
              : [const Color(0xFF101D33), const Color(0xFF162540)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: highlight
              ? AppTheme.accent.withValues(alpha: 0.32)
              : Colors.white.withValues(alpha: 0.07),
          width: highlight ? 1.2 : 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(flag, style: const TextStyle(fontSize: 17)),
              const SizedBox(width: 8),
              Text(label,
                  style: TextStyle(
                      color: accent,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.8)),
            ],
          ),
          const SizedBox(height: 12),
          Text(text,
              style: const TextStyle(
                  color: Colors.white, fontSize: 16, height: 1.6)),
        ],
      ),
    );
  }
}

// ─────────────── Stop Session Bar (always visible when Pi running) ────────────

class _StopSessionBar extends StatelessWidget {
  final String direction;
  final int recordingCount;
  final VoidCallback onStop;

  const _StopSessionBar({
    required this.direction,
    required this.recordingCount,
    required this.onStop,
  });

  @override
  Widget build(BuildContext context) {
    final label = direction == '2way' ? '2-Way' : '1-Way';
    return GestureDetector(
      onTap: onStop,
      child: Container(
        margin: const EdgeInsets.fromLTRB(16, 0, 16, 4),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF4A0E0E), Color(0xFF6B1515)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.redAccent.withValues(alpha: 0.5)),
          boxShadow: [
            BoxShadow(
              color: Colors.red.withValues(alpha: 0.3),
              blurRadius: 12,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          children: [
            // Pulsing red dot
            _PulsingDot(),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '$label Session Recording',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    recordingCount > 0
                        ? '$recordingCount clip${recordingCount == 1 ? "" : "s"} saved to Pi'
                        : 'Listening for speech…',
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.6),
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.redAccent.withValues(alpha: 0.25),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                    color: Colors.redAccent.withValues(alpha: 0.6)),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.stop_rounded, color: Colors.redAccent, size: 16),
                  SizedBox(width: 5),
                  Text('STOP',
                      style: TextStyle(
                          color: Colors.redAccent,
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 1.2)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PulsingDot extends StatefulWidget {
  @override
  State<_PulsingDot> createState() => _PulsingDotState();
}

class _PulsingDotState extends State<_PulsingDot>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 800))
      ..repeat(reverse: true);
    _anim = Tween<double>(begin: 0.4, end: 1.0)
        .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: _anim,
        builder: (_, __) => Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: Colors.redAccent.withValues(alpha: _anim.value),
            boxShadow: [
              BoxShadow(
                color: Colors.red.withValues(alpha: _anim.value * 0.5),
                blurRadius: 6,
              )
            ],
          ),
        ),
      );
}

// ─────────────────────────── Pi Control Section ───────────────────────────────

class _PiControlSection extends StatelessWidget {
  final bool serverOnline;
  final bool loading;
  final void Function(String direction) onStart;

  const _PiControlSection({
    required this.serverOnline,
    required this.loading,
    required this.onStart,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF142238),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppTheme.accent.withValues(alpha: 0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.developer_board_rounded,
                  color: AppTheme.accent, size: 18),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  serverOnline
                      ? 'Pi mic & speaker — select mode'
                      : 'Server offline — start Flask first',
                  style: TextStyle(
                    color: serverOnline ? Colors.white70 : Colors.white38,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Each person\'s voice is saved as a separate recording',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.3),
                fontSize: 11),
          ),
          const SizedBox(height: 14),
          loading
              ? const Center(child: SizedBox(
                  width: 24, height: 24,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: AppTheme.accent),
                ))
              : Row(
                  children: [
                    Expanded(child: _PiBtn(
                      label: '1-Way',
                      subtitle: 'One person speaks',
                      icon: Icons.arrow_forward_rounded,
                      color: AppTheme.accent,
                      enabled: serverOnline,
                      onTap: () => onStart('1way'),
                    )),
                    const SizedBox(width: 10),
                    Expanded(child: _PiBtn(
                      label: '2-Way',
                      subtitle: 'Two persons speak',
                      icon: Icons.swap_horiz_rounded,
                      color: AppTheme.accentGreen,
                      enabled: serverOnline,
                      onTap: () => onStart('2way'),
                    )),
                  ],
                ),
        ],
      ),
    );
  }
}

class _PiBtn extends StatelessWidget {
  final String label;
  final String subtitle;
  final IconData icon;
  final Color color;
  final bool enabled;
  final VoidCallback onTap;

  const _PiBtn({
    required this.label, required this.subtitle, required this.icon,
    required this.color, required this.enabled, required this.onTap,
  });

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: enabled ? onTap : null,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: enabled
                ? color.withValues(alpha: 0.12)
                : Colors.white.withValues(alpha: 0.04),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: enabled
                  ? color.withValues(alpha: 0.35)
                  : Colors.white12,
            ),
          ),
          child: Column(
            children: [
              Icon(icon, color: enabled ? color : Colors.white24, size: 22),
              const SizedBox(height: 4),
              Text(label,
                  style: TextStyle(
                      color: enabled ? color : Colors.white24,
                      fontSize: 13,
                      fontWeight: FontWeight.bold)),
              Text(subtitle,
                  style: TextStyle(
                      color: (enabled ? color : Colors.white24)
                          .withValues(alpha: 0.6),
                      fontSize: 10)),
            ],
          ),
        ),
      );
}

// ──────────────────────────── Language Picker ────────────────────────────────

class _LanguagePicker extends StatefulWidget {
  final Language selected;
  final void Function(Language) onSelect;
  const _LanguagePicker(
      {required this.selected, required this.onSelect});

  @override
  State<_LanguagePicker> createState() => _LanguagePickerState();
}

class _LanguagePickerState extends State<_LanguagePicker> {
  String _q = '';

  @override
  Widget build(BuildContext context) {
    final filtered = supportedLanguages
        .where((l) =>
            l.name.toLowerCase().contains(_q.toLowerCase()) ||
            l.code.toLowerCase().contains(_q.toLowerCase()))
        .toList();

    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.76,
      maxChildSize: 0.95,
      minChildSize: 0.4,
      builder: (_, scroll) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
        child: Column(
          children: [
            Container(
                width: 40, height: 4,
                decoration: BoxDecoration(
                    color: Colors.white24,
                    borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 16),
            const Text('Select Language',
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.bold)),
            const SizedBox(height: 14),
            TextField(
              onChanged: (v) => setState(() => _q = v),
              style: const TextStyle(color: Colors.white),
              decoration: InputDecoration(
                hintText: 'Search language or code…',
                hintStyle: const TextStyle(color: Colors.white30),
                prefixIcon: const Icon(Icons.search_rounded,
                    color: Colors.white38, size: 20),
                filled: true,
                fillColor: Colors.white10,
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide.none),
                contentPadding:
                    const EdgeInsets.symmetric(vertical: 12),
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: ListView.builder(
                controller: scroll,
                itemCount: filtered.length,
                itemBuilder: (_, i) {
                  final lang = filtered[i];
                  final sel = lang.code == widget.selected.code;
                  return ListTile(
                    leading: Text(lang.flag,
                        style: const TextStyle(fontSize: 24)),
                    title: Text(lang.name,
                        style: TextStyle(
                            color:
                                sel ? AppTheme.accent : Colors.white,
                            fontWeight: sel
                                ? FontWeight.bold
                                : FontWeight.normal)),
                    subtitle: Text(lang.code.toUpperCase(),
                        style: const TextStyle(
                            color: Colors.white30, fontSize: 11)),
                    trailing: sel
                        ? const Icon(Icons.check_circle_rounded,
                            color: AppTheme.accent)
                        : null,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10)),
                    tileColor: sel
                        ? AppTheme.accent.withValues(alpha: 0.08)
                        : null,
                    onTap: () {
                      HapticFeedback.selectionClick();
                      widget.onSelect(lang);
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
