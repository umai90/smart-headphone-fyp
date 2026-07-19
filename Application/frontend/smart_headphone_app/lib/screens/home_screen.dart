import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../providers/translation_provider.dart';
import '../services/pi_service.dart';
import '../utils/app_theme.dart';
import '../utils/supported_languages.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _textCtrl = TextEditingController();
  bool _showKeyboard = false;
  bool _showPiControls = false;

  // Server connectivity — polled quietly every 12 s
  bool _serverOnline = false;
  bool _pollBusy = false;
  Timer? _pollTimer;

  // Pi session state — lifted here so stop bar is always visible
  bool _piRunning = false;
  bool _piLoading = false;
  String _activeDirection = '';  // '1way' | '2way'
  int _recordingCount = 0;       // count utterances recorded this session
  Timer? _recordingTimer;

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
    _textCtrl.dispose();
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
        });
        _recordingTimer?.cancel();
        _recordingTimer = Timer.periodic(const Duration(seconds: 5), (_) async {
          if (!_piRunning || !mounted) { _recordingTimer?.cancel(); return; }
          final s = await PiService(p.serverUrl).getStatus();
          if (mounted && s != null) setState(() => _recordingCount = s.recordingsLocal);
        });
      }
    }
    _pollBusy = false;
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
        _showPiControls = false;
      });
      // Poll recording count every 5 s while session is active
      _recordingTimer?.cancel();
      _recordingTimer = Timer.periodic(const Duration(seconds: 5), (_) async {
        if (!_piRunning || !mounted) { _recordingTimer?.cancel(); return; }
        final status = await PiService(p.serverUrl).getStatus();
        if (mounted && status != null) {
          setState(() => _recordingCount = status.recordingsLocal);
        }
      });
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
              _AppBar(
                serverOnline: _serverOnline,
                piExpanded: _showPiControls,
                onTogglePi: () =>
                    setState(() => _showPiControls = !_showPiControls),
              ),
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
                      // Pi Controls — collapsible, hidden by default
                      if (_showPiControls && !_piRunning) ...[
                        const SizedBox(height: 14),
                        _PiControlSection(
                          serverOnline: _serverOnline,
                          loading: _piLoading,
                          onStart: _startPiSession,
                        ),
                      ],
                      const SizedBox(height: 20),
                      const _MicSection(),
                      const SizedBox(height: 6),
                      _KeyboardToggle(
                        show: _showKeyboard,
                        onToggle: () =>
                            setState(() => _showKeyboard = !_showKeyboard),
                      ),
                      if (_showKeyboard) ...[
                        const SizedBox(height: 14),
                        _KeyboardInput(controller: _textCtrl),
                      ],
                      const SizedBox(height: 18),
                      const _ResultSection(),
                      const SizedBox(height: 8),
                      _NewTranslationBtn(),
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
  final bool piExpanded;
  final VoidCallback onTogglePi;

  const _AppBar({
    required this.serverOnline,
    required this.piExpanded,
    required this.onTogglePi,
  });

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
            message: serverOnline ? 'Server connected' : 'Server offline',
            child: Container(
              width: 8,
              height: 8,
              margin: const EdgeInsets.only(right: 10),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: serverOnline
                    ? AppTheme.accentGreen
                    : Colors.white24,
                boxShadow: serverOnline
                    ? [
                        BoxShadow(
                            color:
                                AppTheme.accentGreen.withValues(alpha: 0.6),
                            blurRadius: 6)
                      ]
                    : null,
              ),
            ),
          ),
          // Pi controls toggle
          GestureDetector(
            onTap: onTogglePi,
            child: Tooltip(
              message: piExpanded ? 'Hide Pi Controls' : 'Pi Controls',
              child: Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: piExpanded
                      ? AppTheme.accentGreen.withValues(alpha: 0.15)
                      : Colors.white.withValues(alpha: 0.06),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: piExpanded
                        ? AppTheme.accentGreen.withValues(alpha: 0.4)
                        : Colors.white12,
                  ),
                ),
                child: Icon(
                  Icons.developer_board_rounded,
                  color:
                      piExpanded ? AppTheme.accentGreen : Colors.white38,
                  size: 18,
                ),
              ),
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

// ──────────────────────────── Mic Section ────────────────────────────────────

class _MicSection extends StatefulWidget {
  const _MicSection();

  @override
  State<_MicSection> createState() => _MicSectionState();
}

class _MicSectionState extends State<_MicSection>
    with TickerProviderStateMixin {
  late final AnimationController _pulseCtrl;
  late final Animation<double> _pulse;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
    _pulse = Tween<double>(begin: 1.0, end: 1.22).animate(
        CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.watch<TranslationProvider>();
    final isListening = p.state == AppState.listening;
    final isTranslating = p.state == AppState.translating;

    return Column(
      children: [
        _StatusLabel(state: p.state),
        const SizedBox(height: 22),
        GestureDetector(
          onTap: () async {
            HapticFeedback.mediumImpact();
            if (isListening) {
              await p.stopListening();
            } else if (!isTranslating) {
              await p.startListening();
            }
          },
          child: AnimatedBuilder(
            animation: _pulse,
            builder: (_, child) => Transform.scale(
              scale: isListening ? _pulse.value : 1.0,
              child: child,
            ),
            child: Stack(
              alignment: Alignment.center,
              children: [
                if (isListening) ...[
                  const _Halo(size: 138, opacity: 0.06, isRed: true),
                  const _Halo(size: 112, opacity: 0.13, isRed: true),
                ],
                _MicBtn(
                    isListening: isListening,
                    isTranslating: isTranslating),
              ],
            ),
          ),
        ),
        const SizedBox(height: 18),
        _WaveformBars(active: isListening),
        if (isListening && p.recognizedText.isNotEmpty) ...[
          const SizedBox(height: 12),
          _LiveBubble(text: p.recognizedText),
        ],
      ],
    );
  }
}

class _Halo extends StatelessWidget {
  final double size;
  final double opacity;
  final bool isRed;
  const _Halo(
      {required this.size, required this.opacity, this.isRed = false});

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: (isRed ? Colors.red : AppTheme.accent)
              .withValues(alpha: opacity),
        ),
      );
}

class _MicBtn extends StatelessWidget {
  final bool isListening;
  final bool isTranslating;
  const _MicBtn(
      {required this.isListening, required this.isTranslating});

  @override
  Widget build(BuildContext context) {
    final gradColors = isListening
        ? [const Color(0xFFEF5350), const Color(0xFFB71C1C)]
        : isTranslating
            ? [AppTheme.accent, AppTheme.accentGreen]
            : [const Color(0xFF0099D4), const Color(0xFF005F88)];

    final glowColor = isListening ? Colors.red : AppTheme.accent;

    return Container(
      width: 90,
      height: 90,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: LinearGradient(
          colors: gradColors,
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        boxShadow: [
          BoxShadow(
              color: glowColor.withValues(alpha: 0.55),
              blurRadius: 28,
              spreadRadius: 4),
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.3),
              blurRadius: 10,
              offset: const Offset(0, 4)),
        ],
      ),
      child: isTranslating
          ? const Padding(
              padding: EdgeInsets.all(28),
              child: CircularProgressIndicator(
                  color: Colors.white, strokeWidth: 2.5),
            )
          : Icon(
              isListening ? Icons.stop_rounded : Icons.mic_rounded,
              color: Colors.white,
              size: 40,
            ),
    );
  }
}

class _StatusLabel extends StatelessWidget {
  final AppState state;
  const _StatusLabel({required this.state});

  @override
  Widget build(BuildContext context) {
    final (text, color) = switch (state) {
      AppState.idle =>
        ('Tap microphone to start speaking', Colors.white38),
      AppState.listening =>
        ('Listening…  tap to stop', AppTheme.accent),
      AppState.translating =>
        ('Translating…', AppTheme.accentGreen),
      AppState.done =>
        ('Translation complete ✓', AppTheme.accentGreen),
      AppState.error =>
        ('Something went wrong', Colors.redAccent),
    };
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      child: Text(
        text,
        key: ValueKey(state),
        style: TextStyle(color: color, fontSize: 13, letterSpacing: 0.4),
      ),
    );
  }
}

// ──────────────────────────── Waveform Bars ───────────────────────────────────

class _WaveformBars extends StatefulWidget {
  final bool active;
  const _WaveformBars({required this.active});

  @override
  State<_WaveformBars> createState() => _WaveformBarsState();
}

class _WaveformBarsState extends State<_WaveformBars>
    with TickerProviderStateMixin {
  static const _n = 9;
  late final List<AnimationController> _ctrls;
  late final List<Animation<double>> _anims;

  @override
  void initState() {
    super.initState();
    _ctrls = List.generate(
      _n,
      (i) => AnimationController(
        vsync: this,
        duration: Duration(milliseconds: 240 + i * 45),
      ),
    );
    _anims = _ctrls
        .map((c) => Tween<double>(begin: 3, end: 24).animate(
            CurvedAnimation(parent: c, curve: Curves.easeInOut)))
        .toList();
    if (widget.active) _startAll();
  }

  void _startAll() {
    for (var i = 0; i < _n; i++) {
      Future.delayed(Duration(milliseconds: i * 30),
          () { if (mounted) _ctrls[i].repeat(reverse: true); });
    }
  }

  void _stopAll() {
    for (final c in _ctrls) { c.animateTo(0); }
  }

  @override
  void didUpdateWidget(_WaveformBars old) {
    super.didUpdateWidget(old);
    if (widget.active != old.active) {
      widget.active ? _startAll() : _stopAll();
    }
  }

  @override
  void dispose() {
    for (final c in _ctrls) { c.dispose(); }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      opacity: widget.active ? 1.0 : 0.0,
      duration: const Duration(milliseconds: 350),
      child: SizedBox(
        height: 30,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: List.generate(_n, (i) {
            final isMid = i == _n ~/ 2;
            return AnimatedBuilder(
              animation: _anims[i],
              builder: (_, __) => Container(
                width: 3.5,
                height: _anims[i].value,
                margin: const EdgeInsets.symmetric(horizontal: 2),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: isMid
                        ? [AppTheme.accentGreen, AppTheme.accent]
                        : [
                            AppTheme.accent,
                            AppTheme.accent.withValues(alpha: 0.4)
                          ],
                  ),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}

class _LiveBubble extends StatelessWidget {
  final String text;
  const _LiveBubble({required this.text});

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.symmetric(horizontal: 4),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: AppTheme.accent.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(14),
          border:
              Border.all(color: AppTheme.accent.withValues(alpha: 0.2)),
        ),
        child: Text(
          text,
          textAlign: TextAlign.center,
          style: const TextStyle(
              color: Colors.white70, fontSize: 14, height: 1.4),
        ),
      );
}

// ─────────────────────────── Keyboard Toggle ─────────────────────────────────

class _KeyboardToggle extends StatelessWidget {
  final bool show;
  final VoidCallback onToggle;
  const _KeyboardToggle({required this.show, required this.onToggle});

  @override
  Widget build(BuildContext context) => TextButton.icon(
        onPressed: onToggle,
        icon: Icon(
          show ? Icons.keyboard_hide_rounded : Icons.keyboard_rounded,
          color: Colors.white30,
          size: 17,
        ),
        label: Text(
          show ? 'Hide keyboard' : 'Type instead',
          style: const TextStyle(color: Colors.white30, fontSize: 12),
        ),
      );
}

// ──────────────────────────── Keyboard Input ─────────────────────────────────

class _KeyboardInput extends StatelessWidget {
  final TextEditingController controller;
  const _KeyboardInput({required this.controller});

  @override
  Widget build(BuildContext context) {
    final p = context.read<TranslationProvider>();
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF142238),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white10),
      ),
      child: Column(
        children: [
          TextField(
            controller: controller,
            style: const TextStyle(color: Colors.white, fontSize: 15),
            maxLines: 3,
            decoration: const InputDecoration(
              hintText: 'Type text to translate…',
              hintStyle: TextStyle(color: Colors.white24),
              contentPadding: EdgeInsets.all(16),
              border: InputBorder.none,
            ),
          ),
          const Divider(color: Colors.white10, height: 1),
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 6, 8, 6),
            child: Row(
              children: [
                TextButton(
                  onPressed: controller.clear,
                  child: const Text('Clear',
                      style: TextStyle(color: Colors.white38)),
                ),
                const Spacer(),
                ElevatedButton.icon(
                  onPressed: () {
                    final txt = controller.text.trim();
                    if (txt.isNotEmpty) {
                      p.translateText(txt);
                      controller.clear();
                    }
                  },
                  icon: const Icon(Icons.translate_rounded, size: 16),
                  label: const Text('Translate'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.accent,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10)),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 18, vertical: 10),
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

// ──────────────────────────── Result Section ─────────────────────────────────

class _ResultSection extends StatelessWidget {
  const _ResultSection();

  @override
  Widget build(BuildContext context) {
    final p = context.watch<TranslationProvider>();

    if (p.state == AppState.error) {
      return _ErrorBanner(
        message: p.errorMessage,
        onDismiss: p.resetState,
        onRetry: () {
          if (p.recognizedText.isNotEmpty) {
            p.translateText(p.recognizedText);
          }
        },
      );
    }

    if (p.recognizedText.isEmpty && p.translatedText.isEmpty) {
      return const _EmptyHint();
    }

    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 450),
      switchInCurve: Curves.easeOutCubic,
      transitionBuilder: (child, anim) => FadeTransition(
        opacity: anim,
        child: SlideTransition(
          position: Tween<Offset>(
                  begin: const Offset(0, 0.08), end: Offset.zero)
              .animate(anim),
          child: child,
        ),
      ),
      child: Column(
        key: ValueKey('${p.recognizedText}_${p.translatedText}'),
        children: [
          if (p.recognizedText.isNotEmpty)
            _TranslationCard(
              lang: p.fromLang.name,
              flag: p.fromLang.flag,
              text: p.recognizedText,
              onSpeak: p.speakOriginal,
              onCopy: () => _copy(context, p, p.recognizedText),
              highlight: false,
              matchScore: null,
            ),
          if (p.translatedText.isNotEmpty) ...[
            const SizedBox(height: 10),
            _TranslationCard(
              lang: p.toLang.name,
              flag: p.toLang.flag,
              text: p.translatedText,
              onSpeak: p.speakTranslation,
              onCopy: () => _copy(context, p, p.translatedText),
              highlight: true,
              matchScore: p.matchScore > 0 ? p.matchScore : null,
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _copy(
      BuildContext context, TranslationProvider p, String text) async {
    await p.copyToClipboard(text);
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Row(children: [
          Icon(Icons.check_circle_rounded,
              color: AppTheme.accentGreen, size: 16),
          SizedBox(width: 8),
          Text('Copied to clipboard',
              style: TextStyle(color: Colors.white)),
        ]),
        backgroundColor: const Color(0xFF1A3050),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12)),
        margin: const EdgeInsets.all(16),
      ),
    );
  }
}

class _TranslationCard extends StatelessWidget {
  final String lang;
  final String flag;
  final String text;
  final VoidCallback onSpeak;
  final VoidCallback onCopy;
  final bool highlight;
  final double? matchScore;

  const _TranslationCard({
    required this.lang,
    required this.flag,
    required this.text,
    required this.onSpeak,
    required this.onCopy,
    required this.highlight,
    required this.matchScore,
  });

  Color _scoreColor(double s) {
    if (s >= 0.8) return AppTheme.accentGreen;
    if (s >= 0.5) return Colors.amber;
    return Colors.redAccent;
  }

  @override
  Widget build(BuildContext context) {
    final accent = highlight ? AppTheme.accent : Colors.white54;
    final words = text.trim().split(RegExp(r'\s+')).length;

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
        boxShadow: highlight
            ? [
                BoxShadow(
                    color: AppTheme.accent.withValues(alpha: 0.1),
                    blurRadius: 18,
                    offset: const Offset(0, 5))
              ]
            : [
                BoxShadow(
                    color: Colors.black.withValues(alpha: 0.2),
                    blurRadius: 10,
                    offset: const Offset(0, 3))
              ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(flag, style: const TextStyle(fontSize: 17)),
              const SizedBox(width: 8),
              Expanded(
                child: Text(lang,
                    style: TextStyle(
                        color: accent,
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.8)),
              ),
              if (matchScore != null) ...[
                _ScoreBadge(
                    score: matchScore!,
                    color: _scoreColor(matchScore!)),
                const SizedBox(width: 8),
              ],
              _ActionBtn(
                  icon: Icons.volume_up_rounded,
                  color: accent,
                  onTap: onSpeak),
              const SizedBox(width: 6),
              _ActionBtn(
                  icon: Icons.copy_rounded,
                  color: Colors.white38,
                  onTap: onCopy),
            ],
          ),
          const SizedBox(height: 12),
          Text(text,
              style: const TextStyle(
                  color: Colors.white, fontSize: 16, height: 1.6)),
          const SizedBox(height: 10),
          Text('$words ${words == 1 ? "word" : "words"}',
              style:
                  const TextStyle(color: Colors.white24, fontSize: 11)),
        ],
      ),
    );
  }
}

class _ScoreBadge extends StatelessWidget {
  final double score;
  final Color color;
  const _ScoreBadge({required this.score, required this.color});

  @override
  Widget build(BuildContext context) => Container(
        padding:
            const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: color.withValues(alpha: 0.4)),
        ),
        child: Text(
          '${(score * 100).toInt()}%',
          style: TextStyle(
              color: color,
              fontSize: 10,
              fontWeight: FontWeight.bold),
        ),
      );
}

class _ActionBtn extends StatelessWidget {
  final IconData icon;
  final Color color;
  final VoidCallback onTap;
  const _ActionBtn(
      {required this.icon, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(7),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(icon, color: color, size: 17),
        ),
      );
}

class _ErrorBanner extends StatelessWidget {
  final String message;
  final VoidCallback onDismiss;
  final VoidCallback onRetry;
  const _ErrorBanner(
      {required this.message,
      required this.onDismiss,
      required this.onRetry});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.red.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: Colors.redAccent.withValues(alpha: 0.3)),
        ),
        child: Row(
          children: [
            const Icon(Icons.error_outline_rounded,
                color: Colors.redAccent, size: 20),
            const SizedBox(width: 10),
            Expanded(
                child: Text(message,
                    style: const TextStyle(
                        color: Colors.redAccent, fontSize: 13))),
            TextButton(
              onPressed: onRetry,
              child: const Text('Retry',
                  style: TextStyle(color: AppTheme.accent)),
            ),
            GestureDetector(
              onTap: onDismiss,
              child: const Icon(Icons.close_rounded,
                  color: Colors.redAccent, size: 18),
            ),
          ],
        ),
      );
}

class _EmptyHint extends StatelessWidget {
  const _EmptyHint();

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 16),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.all(26),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withValues(alpha: 0.03),
                border: Border.all(
                    color: Colors.white.withValues(alpha: 0.07)),
              ),
              child: const Icon(Icons.translate_rounded,
                  color: Colors.white10, size: 52),
            ),
            const SizedBox(height: 16),
            const Text('Your translation will appear here',
                style:
                    TextStyle(color: Colors.white24, fontSize: 14)),
            const SizedBox(height: 6),
            const Text('Supports 34 languages — voice & text',
                style: TextStyle(
                    color: Color(0x26FFFFFF), fontSize: 12)),
          ],
        ),
      );
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

// ──────────────────── New Translation Button ──────────────────────────────────

class _NewTranslationBtn extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final p = context.watch<TranslationProvider>();
    if (p.state != AppState.done && p.state != AppState.error) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: SizedBox(
        width: double.infinity,
        child: TextButton.icon(
          onPressed: () {
            HapticFeedback.lightImpact();
            context.read<TranslationProvider>().clearResults();
          },
          icon: const Icon(Icons.refresh_rounded, size: 16,
              color: Colors.white38),
          label: const Text('New Translation',
              style: TextStyle(color: Colors.white38, fontSize: 12)),
        ),
      ),
    );
  }
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
