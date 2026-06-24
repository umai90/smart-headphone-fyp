import 'package:flutter_tts/flutter_tts.dart';

class TtsService {
  final FlutterTts _tts = FlutterTts();

  Future<void> init({
    double rate = 0.5,
    double pitch = 1.0,
    void Function()? onStart,
    void Function()? onComplete,
  }) async {
    await _tts.setVolume(1.0);
    await _tts.setSpeechRate(rate);
    await _tts.setPitch(pitch);
    if (onStart != null) _tts.setStartHandler(onStart);
    if (onComplete != null) {
      _tts.setCompletionHandler(onComplete);
      _tts.setCancelHandler(onComplete);
    }
  }

  Future<void> speak(String text, String ttsLocale) async {
    await _tts.stop();
    await _tts.setLanguage(ttsLocale);
    await _tts.speak(text);
  }

  Future<void> stop() async => _tts.stop();

  Future<void> setRate(double rate) async => _tts.setSpeechRate(rate);

  Future<void> setPitch(double pitch) async => _tts.setPitch(pitch);
}
