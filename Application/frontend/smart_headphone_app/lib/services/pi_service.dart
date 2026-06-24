import 'dart:convert';
import 'package:http/http.dart' as http;

class PiStatus {
  final String state;
  final String fromLang;
  final String toLang;
  final String lastOriginal;
  final String lastTranslated;
  final int translationCount;
  final int uptimeSec;
  final int recordingsLocal;
  final String direction;

  const PiStatus({
    required this.state,
    required this.fromLang,
    required this.toLang,
    required this.lastOriginal,
    required this.lastTranslated,
    required this.translationCount,
    required this.uptimeSec,
    required this.recordingsLocal,
    this.direction = '1way',
  });

  factory PiStatus.fromJson(Map<String, dynamic> j) => PiStatus(
        state: j['state'] ?? 'unknown',
        fromLang: j['from_lang'] ?? 'en',
        toLang: j['to_lang'] ?? 'ur',
        lastOriginal: j['last_original'] ?? '',
        lastTranslated: j['last_translated'] ?? '',
        translationCount: j['translation_count'] ?? 0,
        uptimeSec: (j['uptime_sec'] ?? 0).toInt(),
        recordingsLocal: j['recordings_local'] ?? 0,
        direction: j['direction'] ?? '1way',
      );

  String get uptimeFormatted {
    final h = uptimeSec ~/ 3600;
    final m = (uptimeSec % 3600) ~/ 60;
    final s = uptimeSec % 60;
    if (h > 0) return '${h}h ${m}m';
    if (m > 0) return '${m}m ${s}s';
    return '${s}s';
  }
}

class RecordingFile {
  final String name;
  final double sizeMb;
  final String date;
  final String source; // 'pi' or 'cloud'

  const RecordingFile({
    required this.name,
    required this.sizeMb,
    required this.date,
    required this.source,
  });

  factory RecordingFile.fromJson(Map<String, dynamic> j) => RecordingFile(
        name: j['name'] ?? '',
        sizeMb: (j['size_mb'] ?? 0).toDouble(),
        date: j['date'] ?? '',
        source: j['source'] ?? 'pi',
      );

  bool get isCloud => source == 'cloud';
}

class PiService {
  final String serverUrl;
  static const _timeout = Duration(seconds: 6);

  const PiService(this.serverUrl);

  Uri _uri(String path) => Uri.parse('$serverUrl$path');

  Future<PiStatus?> getStatus() async {
    try {
      final res = await http.get(_uri('/status')).timeout(_timeout);
      if (res.statusCode == 200) {
        return PiStatus.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
      }
    } catch (_) {}
    return null;
  }

  Future<bool> setLanguage(String fromCode, String toCode) async {
    try {
      final res = await http
          .post(
            _uri('/language'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'from_code': fromCode, 'to_code': toCode}),
          )
          .timeout(_timeout);
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<List<RecordingFile>> getRecordings({String source = 'all'}) async {
    try {
      final res = await http
          .get(_uri('/recordings?source=$source'))
          .timeout(_timeout);
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        final list = data['recordings'] as List<dynamic>? ?? [];
        return list
            .map((e) => RecordingFile.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    } catch (_) {}
    return [];
  }

  String getRecordingStreamUrl(String filename) =>
      '$serverUrl/recordings/$filename';

  Future<bool> deleteRecording(String filename) async {
    try {
      final res = await http
          .delete(_uri('/recordings/$filename'))
          .timeout(_timeout);
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<bool> triggerBackup() async {
    try {
      final res = await http
          .post(_uri('/recordings/backup'))
          .timeout(const Duration(seconds: 10));
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Poll backup progress after calling [triggerBackup].
  Future<Map<String, dynamic>> getBackupStatus() async {
    try {
      final res = await http
          .get(_uri('/recordings/backup/status'))
          .timeout(_timeout);
      if (res.statusCode == 200) {
        return jsonDecode(res.body) as Map<String, dynamic>;
      }
    } catch (_) {}
    return {'running': false, 'error': 'unreachable'};
  }

  Future<bool> checkHealth() async {
    try {
      final res = await http.get(_uri('/health')).timeout(_timeout);
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<bool> startTranslation({
    required String direction,  // '1way' or '2way'
    required String mode,       // 'online' or 'offline'
    required String fromLang,
    required String toLang,
  }) async {
    try {
      final res = await http
          .post(
            _uri('/pi/start'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'direction': direction,
              'mode': mode,
              'from_lang': fromLang,
              'to_lang': toLang,
            }),
          )
          .timeout(const Duration(seconds: 10));
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<bool> stopTranslation() async {
    try {
      final res =
          await http.post(_uri('/pi/stop')).timeout(_timeout);
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
