import 'package:flutter/material.dart';

class AppTheme {
  static const Color primary = Color(0xFF0A1628);
  static const Color secondary = Color(0xFF1A2D4E);
  static const Color accent = Color(0xFF00C2FF);
  static const Color accentGreen = Color(0xFF00E5A0);
  static const Color cardBg = Color(0xFF1E2F4D);
  static const Color textPrimary = Colors.white;
  static const Color textSecondary = Color(0xFFB0BEC5);

  static ThemeData darkTheme = ThemeData(
    brightness: Brightness.dark,
    primaryColor: primary,
    scaffoldBackgroundColor: primary,
    colorScheme: const ColorScheme.dark(
      primary: accent,
      secondary: accentGreen,
      surface: cardBg,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: primary,
      elevation: 0,
      centerTitle: true,
    ),
    sliderTheme: const SliderThemeData(
      activeTrackColor: accent,
      inactiveTrackColor: Colors.white12,
      thumbColor: accent,
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? accent : Colors.white38,
      ),
      trackColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected)
            ? accent.withValues(alpha: 0.4)
            : Colors.white12,
      ),
    ),
  );
}
