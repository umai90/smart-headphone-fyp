import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

class DeepfakeResult {
  final String label;
  final double confidence;
  final double realProb;
  final double fakeProb;

  const DeepfakeResult({
    required this.label,
    required this.confidence,
    required this.realProb,
    required this.fakeProb,
  });

  bool get isReal => label == 'REAL';

  factory DeepfakeResult.fromJson(Map<String, dynamic> data) => DeepfakeResult(
        label:      data['label'] as String? ?? 'UNKNOWN',
        confidence: (data['confidence'] as num?)?.toDouble() ?? 0.0,
        realProb:   (data['real_prob'] as num?)?.toDouble() ?? 0.0,
        fakeProb:   (data['fake_prob'] as num?)?.toDouble() ?? 0.0,
      );
}

class DeepfakeService {
  Future<bool> checkHealth(String serverUrl) async {
    try {
      final response = await http
          .get(Uri.parse('$serverUrl/health'))
          .timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<DeepfakeResult?> detect(String audioPath, String serverUrl) async {
    try {
      final file = File(audioPath);
      if (!await file.exists()) return null;

      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$serverUrl/detect'),
      );
      request.files.add(
        await http.MultipartFile.fromPath('audio', audioPath),
      );

      final streamed = await request.send().timeout(const Duration(seconds: 30));
      final response = await http.Response.fromStream(streamed);

      if (response.statusCode == 200) {
        final data = json.decode(response.body) as Map<String, dynamic>;
        if (data.containsKey('error')) return null;
        return DeepfakeResult.fromJson(data);
      }
    } on SocketException {
      return null;
    } catch (_) {
      return null;
    }
    return null;
  }

  Future<DeepfakeResult?> detectRecording(
      String filename, String serverUrl) async {
    try {
      final response = await http
          .post(Uri.parse('$serverUrl/detect_recording/$filename'))
          .timeout(const Duration(seconds: 30));

      if (response.statusCode == 200) {
        final data = json.decode(response.body) as Map<String, dynamic>;
        if (data.containsKey('error')) return null;
        return DeepfakeResult.fromJson(data);
      }
    } catch (_) {
      return null;
    }
    return null;
  }
}
