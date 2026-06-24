# Smart Headphone — Translation System

A real-time voice translation mobile application built with Flutter.

## Features

- **Voice-to-Voice Translation** — Speak in one language, hear the translation instantly
- **34 Languages** — Covers major world languages including Urdu, Arabic, Chinese, French, and more
- **Text Input** — Type text as an alternative to voice input
- **Auto-Speak** — Automatically plays translated speech after each translation
- **Translation History** — Review, replay, copy, and delete past translations
- **Match Score** — Shows translation confidence as a percentage badge
- **Deepfake Voice Detection** — Verifies voice authenticity in real time

## Getting Started

```bash
flutter pub get
flutter run
```

## Requirements

- Flutter SDK 3.5+
- Android 6.0+ or iOS 13+
- Microphone permission
- Internet connection (online translation mode)

## Architecture

```
lib/
  main.dart
  models/          — Data models
  providers/       — State management (Provider)
  screens/         — Splash, Home, History, Settings
  services/        — Translation API & TTS
  utils/           — Theme, supported languages
```
