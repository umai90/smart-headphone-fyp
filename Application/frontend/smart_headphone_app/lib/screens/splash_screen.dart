import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/translation_provider.dart';
import '../utils/app_theme.dart';
import 'main_shell.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with TickerProviderStateMixin {
  late final AnimationController _logoCtrl;
  late final AnimationController _waveCtrl;
  late final Animation<double> _scale;
  late final Animation<double> _fade;
  late final Animation<double> _wave;

  @override
  void initState() {
    super.initState();
    _logoCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 1200));
    _waveCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);

    _scale = Tween<double>(begin: 0.0, end: 1.0).animate(
        CurvedAnimation(parent: _logoCtrl, curve: Curves.elasticOut));
    _fade = Tween<double>(begin: 0.0, end: 1.0).animate(
        CurvedAnimation(
            parent: _logoCtrl, curve: const Interval(0.5, 1.0)));
    _wave = Tween<double>(begin: 0.85, end: 1.15).animate(
        CurvedAnimation(parent: _waveCtrl, curve: Curves.easeInOut));

    _logoCtrl.forward();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    await context.read<TranslationProvider>().initialize();
    await Future.delayed(const Duration(seconds: 3));
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        pageBuilder: (_, __, ___) => const MainShell(),
        transitionsBuilder: (_, a, __, child) =>
            FadeTransition(opacity: a, child: child),
        transitionDuration: const Duration(milliseconds: 500),
      ),
    );
  }

  @override
  void dispose() {
    _logoCtrl.dispose();
    _waveCtrl.dispose();
    super.dispose();
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
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              AnimatedBuilder(
                animation: _logoCtrl,
                builder: (_, child) =>
                    Transform.scale(scale: _scale.value, child: child),
                child: AnimatedBuilder(
                  animation: _waveCtrl,
                  builder: (_, child) => Stack(
                    alignment: Alignment.center,
                    children: [
                      _ring(140, AppTheme.accent, 0.08, _wave.value),
                      _ring(110, AppTheme.accent, 0.14, _wave.value),
                      _ring(80, AppTheme.accentGreen, 0.18, _wave.value),
                      Container(
                        width: 86,
                        height: 86,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          gradient: const LinearGradient(
                            colors: [AppTheme.accent, AppTheme.accentGreen],
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: AppTheme.accent.withValues(alpha: 0.5),
                              blurRadius: 24,
                              spreadRadius: 4,
                            ),
                          ],
                        ),
                        child: const Icon(Icons.headphones,
                            color: Colors.white, size: 44),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 36),
              AnimatedBuilder(
                animation: _fade,
                builder: (_, child) => Opacity(opacity: _fade.value, child: child),
                child: Column(
                  children: [
                    const Text(
                      'Smart Headphone',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 28,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 1.5,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'TRANSLATION SYSTEM',
                      style: TextStyle(
                        color: AppTheme.accent,
                        fontSize: 13,
                        letterSpacing: 3.0,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 56),
                    SizedBox(
                      width: 180,
                      child: LinearProgressIndicator(
                        backgroundColor: Colors.white12,
                        valueColor:
                            const AlwaysStoppedAnimation<Color>(AppTheme.accent),
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'Initializing...',
                      style: TextStyle(color: Colors.white38, fontSize: 12),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _ring(double size, Color color, double opacity, double scale) {
    return Container(
      width: size * scale,
      height: size * scale,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color.withValues(alpha: opacity),
      ),
    );
  }
}
