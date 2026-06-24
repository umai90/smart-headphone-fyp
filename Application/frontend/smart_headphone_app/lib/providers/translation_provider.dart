import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../models/translation_entry.dart';
import '../services/translation_service.dart';
import '../services/tts_service.dart';
import '../utils/supported_languages.dart';

enum AppState { idle, listening, translating, done, error }
enum TranslationMode { online, offline }

class TranslationProvider extends ChangeNotifier {
  final _translationService = TranslationService();
  final _ttsService = TtsService();
  final _speech = SpeechToText();

  Language _fromLang = supportedLanguages[0];
  Language _toLang = supportedLanguages[1];

  String _recognizedText = '';
  String _translatedText = '';
  AppState _state = AppState.idle;
  String _errorMessage = '';
  final List<TranslationEntry> _history = [];
  bool _speechAvailable = false;
  bool _isProcessing = false;
  bool _isSpeaking = false;
  double _matchScore = 0.0;

  double _ttsRate = 0.5;
  double _ttsPitch = 1.0;
  bool _autoSpeak = true;
  TranslationMode _mode = TranslationMode.online;
  String _serverUrl = '';

  Language get fromLang => _fromLang;
  Language get toLang => _toLang;
  String get recognizedText => _recognizedText;
  String get translatedText => _translatedText;
  AppState get state => _state;
  String get errorMessage => _errorMessage;
  List<TranslationEntry> get history => List.unmodifiable(_history);
  bool get speechAvailable => _speechAvailable;
  bool get isSpeaking => _isSpeaking;
  double get matchScore => _matchScore;
  double get ttsRate => _ttsRate;
  double get ttsPitch => _ttsPitch;
  bool get autoSpeak => _autoSpeak;
  TranslationMode get mode => _mode;
  String get serverUrl => _serverUrl;

  Future<void> initialize() async {
    await _loadPrefs();
    await _ttsService.init(
      rate: _ttsRate,
      pitch: _ttsPitch,
      onStart: () {
        _isSpeaking = true;
        notifyListeners();
      },
      onComplete: () {
        _isSpeaking = false;
        notifyListeners();
      },
    );

    final status = await Permission.microphone.request();
    if (status.isGranted) {
      _speechAvailable = await _speech.initialize(
        onError: (e) => _setError(e.errorMsg),
      );
    }
    notifyListeners();
  }

  Future<void> _loadPrefs() async {
    final p = await SharedPreferences.getInstance();
    _ttsRate = p.getDouble('ttsRate') ?? 0.5;
    _ttsPitch = p.getDouble('ttsPitch') ?? 1.0;
    _autoSpeak = p.getBool('autoSpeak') ?? true;
    _mode = (p.getBool('isOffline') ?? false) ? TranslationMode.offline : TranslationMode.online;
    _serverUrl = p.getString('serverUrl') ?? '';
    final fc = p.getString('fromCode') ?? 'en';
    final tc = p.getString('toCode') ?? 'ur';
    _fromLang = supportedLanguages.firstWhere((l) => l.code == fc,
        orElse: () => supportedLanguages[0]);
    _toLang = supportedLanguages.firstWhere((l) => l.code == tc,
        orElse: () => supportedLanguages[1]);
    final raw = p.getString('history');
    if (raw != null) {
      try {
        final list = jsonDecode(raw) as List<dynamic>;
        _history.addAll(
          list.map((e) => TranslationEntry.fromJson(e as Map<String, dynamic>)),
        );
      } catch (_) {}
    }
  }

  Future<void> _savePrefs() async {
    final p = await SharedPreferences.getInstance();
    await p.setDouble('ttsRate', _ttsRate);
    await p.setDouble('ttsPitch', _ttsPitch);
    await p.setBool('autoSpeak', _autoSpeak);
    await p.setString('fromCode', _fromLang.code);
    await p.setString('toCode', _toLang.code);
    await p.setBool('isOffline', _mode == TranslationMode.offline);
    await p.setString('serverUrl', _serverUrl);
  }

  Future<void> _saveHistory() async {
    final p = await SharedPreferences.getInstance();
    await p.setString(
      'history',
      jsonEncode(_history.map((e) => e.toJson()).toList()),
    );
  }

  Future<void> setFromLang(Language lang) async {
    _fromLang = lang;
    await _savePrefs();
    notifyListeners();
  }

  Future<void> setToLang(Language lang) async {
    _toLang = lang;
    await _savePrefs();
    notifyListeners();
  }

  Future<void> swapLanguages() async {
    final tmp = _fromLang;
    _fromLang = _toLang;
    _toLang = tmp;
    final tmpText = _recognizedText;
    _recognizedText = _translatedText;
    _translatedText = tmpText;
    await _savePrefs();
    notifyListeners();
  }

  Future<void> startListening() async {
    if (!_speechAvailable) {
      _setError('Microphone permission denied or speech unavailable');
      return;
    }
    // Reset any stuck processing state before starting a new session
    _isProcessing = false;
    if (_state == AppState.translating) return;

    _recognizedText = '';
    _translatedText = '';
    _matchScore = 0.0;
    _state = AppState.listening;
    notifyListeners();

    await _speech.listen(
      onResult: (r) {
        _recognizedText = r.recognizedWords;
        notifyListeners();
        if (r.finalResult && _recognizedText.isNotEmpty && !_isProcessing) {
          _isProcessing = true;
          _doTranslate();
        }
      },
      listenOptions: SpeechListenOptions(
        localeId: _fromLang.locale,
        listenFor: const Duration(seconds: 30),
        pauseFor: const Duration(seconds: 3),
        cancelOnError: false,
      ),
    );
  }

  Future<void> stopListening() async {
    await _speech.stop();
    if (_recognizedText.isNotEmpty && !_isProcessing) {
      _isProcessing = true;
      await _doTranslate();
    } else if (_recognizedText.isEmpty && !_isProcessing) {
      _state = AppState.idle;
      notifyListeners();
    }
  }

  Future<void> translateText(String text) async {
    if (_isProcessing) return;
    _isProcessing = true;
    _recognizedText = text;
    _translatedText = '';
    _matchScore = 0.0;
    await _doTranslate();
  }

  Future<void> _doTranslate() async {
    if (_recognizedText.isEmpty) {
      _isProcessing = false;
      return;
    }
    // Stop the microphone immediately — no need to keep listening while translating
    await _speech.stop();
    _state = AppState.translating;
    notifyListeners();

    // Always try Flask server first (uses your Python program files).
    // Fall back to direct MyMemory API only when server is unreachable.
    TranslationResult? result;
    if (_serverUrl.isNotEmpty) {
      result = await _translationService.translateViaServer(
        text: _recognizedText,
        fromCode: _fromLang.code,
        toCode: _toLang.code,
        serverUrl: _serverUrl,
        mode: _mode == TranslationMode.offline ? 'offline' : 'online',
      );
    }
    if (result == null && _mode == TranslationMode.online) {
      result = await _translationService.translateDirect(
        text: _recognizedText,
        fromCode: _fromLang.code,
        toCode: _toLang.code,
      );
    }

    _isProcessing = false;

    if (result != null) {
      _translatedText = result.text;
      _matchScore = result.matchScore;
      _state = AppState.done;
      _history.insert(
        0,
        TranslationEntry(
          id: DateTime.now().millisecondsSinceEpoch.toString(),
          originalText: _recognizedText,
          translatedText: _translatedText,
          fromLanguage: _fromLang.name,
          toLanguage: _toLang.name,
          fromFlag: _fromLang.flag,
          toFlag: _toLang.flag,
          fromTtsLocale: _fromLang.ttsLocale,
          toTtsLocale: _toLang.ttsLocale,
          matchScore: _matchScore,
          timestamp: DateTime.now(),
        ),
      );
      await _saveHistory();
      notifyListeners(); // show result immediately; speak runs after UI updates
      if (_autoSpeak) await speakTranslation();
    } else {
      final msg = _mode == TranslationMode.offline
          ? 'Offline translation failed. Make sure the Python server is running.'
          : 'Translation failed. Start your Python server or check internet.';
      _setError(msg);
      notifyListeners();
    }
  }

  Future<void> speakTranslation() async {
    if (_translatedText.isEmpty) return;
    await _ttsService.speak(_translatedText, _toLang.ttsLocale);
  }

  Future<void> speakOriginal() async {
    if (_recognizedText.isEmpty) return;
    await _ttsService.speak(_recognizedText, _fromLang.ttsLocale);
  }

  Future<void> speakEntry(TranslationEntry entry) async {
    await _ttsService.speak(entry.translatedText, entry.toTtsLocale);
  }

  Future<void> speakEntryOriginal(TranslationEntry entry) async {
    await _ttsService.speak(entry.originalText, entry.fromTtsLocale);
  }

  Future<void> stopSpeaking() async {
    await _ttsService.stop();
    _isSpeaking = false;
    notifyListeners();
  }

  Future<void> copyToClipboard(String text) async {
    await Clipboard.setData(ClipboardData(text: text));
  }

  Future<void> testTts() async {
    await _ttsService.speak('Translation is working perfectly.', 'en-US');
  }

  Future<void> setTtsRate(double v) async {
    _ttsRate = v;
    _ttsService.setRate(v);
    await _savePrefs();
    notifyListeners();
  }

  Future<void> setTtsPitch(double v) async {
    _ttsPitch = v;
    _ttsService.setPitch(v);
    await _savePrefs();
    notifyListeners();
  }

  Future<void> setAutoSpeak(bool v) async {
    _autoSpeak = v;
    await _savePrefs();
    notifyListeners();
  }

  Future<void> setMode(TranslationMode m) async {
    _mode = m;
    await _savePrefs();
    notifyListeners();
  }

  Future<void> setServerUrl(String url) async {
    _serverUrl = url.trim();
    await _savePrefs();
    notifyListeners();
  }

  void clearHistory() {
    _history.clear();
    _saveHistory();
    notifyListeners();
  }

  void removeEntry(String id) {
    _history.removeWhere((e) => e.id == id);
    _saveHistory();
    notifyListeners();
  }

  void resetState() {
    _isProcessing = false;
    _state = AppState.idle;
    notifyListeners();
  }

  /// Clear current translation results and return to idle — ready for next translation.
  void clearResults() {
    _isProcessing = false;
    _recognizedText = '';
    _translatedText = '';
    _matchScore = 0.0;
    _state = AppState.idle;
    notifyListeners();
  }

  void _setError(String msg) {
    _isProcessing = false;
    _errorMessage = msg;
    _state = AppState.error;
    notifyListeners();
  }
}
