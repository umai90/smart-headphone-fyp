import 'dart:convert';
import 'package:http/http.dart' as http;

class TranslationResult {
  final String text;
  final double matchScore;
  final bool fromServer;
  const TranslationResult({
    required this.text,
    required this.matchScore,
    this.fromServer = false,
  });
}

class TranslationService {
  static const String _myMemoryUrl = 'https://api.mymemory.translated.net/get';

  /// Primary: calls your Python Flask server (mode2 online or mode1 offline).
  Future<TranslationResult?> translateViaServer({
    required String text,
    required String fromCode,
    required String toCode,
    required String serverUrl,
    required String mode, // 'online' or 'offline'
  }) async {
    try {
      final uri = Uri.parse('$serverUrl/translate');
      final response = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: json.encode({
              'text': text,
              'source': fromCode,
              'target': toCode,
              'mode': mode,
            }),
          )
          .timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        final data = json.decode(response.body) as Map<String, dynamic>;
        final translated = data['translated'] as String?;
        if (translated != null &&
            translated.isNotEmpty &&
            !translated.startsWith('[')) {
          return TranslationResult(
              text: translated, matchScore: 1.0, fromServer: true);
        }
      }
    } catch (_) {}
    return null;
  }

  /// Fallback: MyMemory free API (no Python server needed).
  Future<TranslationResult?> translateDirect({
    required String text,
    required String fromCode,
    required String toCode,
  }) async {
    for (int attempt = 0; attempt < 2; attempt++) {
      try {
        final uri = Uri.parse(
          '$_myMemoryUrl?q=${Uri.encodeComponent(text)}&langpair=$fromCode|$toCode',
        );
        final response =
            await http.get(uri).timeout(const Duration(seconds: 12));

        if (response.statusCode == 200) {
          final data = json.decode(response.body) as Map<String, dynamic>;
          if (data['responseStatus'] == 200) {
            final rd = data['responseData'] as Map<String, dynamic>;
            final translated = rd['translatedText'] as String?;
            final score = (rd['match'] as num?)?.toDouble() ?? 0.0;
            if (translated != null && translated.isNotEmpty) {
              return TranslationResult(
                  text: translated, matchScore: score, fromServer: false);
            }
          }
        }
      } catch (_) {
        if (attempt == 0) {
          await Future.delayed(const Duration(milliseconds: 800));
          continue;
        }
      }
    }
    return null;
  }

  // Keep old method names as wrappers so nothing else breaks.
  Future<TranslationResult?> translate({
    required String text,
    required String fromCode,
    required String toCode,
  }) => translateDirect(text: text, fromCode: fromCode, toCode: toCode);

  Future<TranslationResult?> translateOffline({
    required String text,
    required String fromCode,
    required String toCode,
    required String serverUrl,
  }) => translateViaServer(
        text: text,
        fromCode: fromCode,
        toCode: toCode,
        serverUrl: serverUrl,
        mode: 'offline',
      );
}
