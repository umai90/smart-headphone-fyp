class TranslationEntry {
  final String id;
  final String originalText;
  final String translatedText;
  final String fromLanguage;
  final String toLanguage;
  final String fromFlag;
  final String toFlag;
  final String fromTtsLocale;
  final String toTtsLocale;
  final double matchScore;
  final DateTime timestamp;

  const TranslationEntry({
    required this.id,
    required this.originalText,
    required this.translatedText,
    required this.fromLanguage,
    required this.toLanguage,
    required this.fromFlag,
    required this.toFlag,
    required this.fromTtsLocale,
    required this.toTtsLocale,
    required this.matchScore,
    required this.timestamp,
  });

  Map<String, dynamic> toJson() => {
        'id': id,
        'originalText': originalText,
        'translatedText': translatedText,
        'fromLanguage': fromLanguage,
        'toLanguage': toLanguage,
        'fromFlag': fromFlag,
        'toFlag': toFlag,
        'fromTtsLocale': fromTtsLocale,
        'toTtsLocale': toTtsLocale,
        'matchScore': matchScore,
        'timestamp': timestamp.toIso8601String(),
      };

  factory TranslationEntry.fromJson(Map<String, dynamic> json) => TranslationEntry(
        id: json['id'] as String,
        originalText: json['originalText'] as String,
        translatedText: json['translatedText'] as String,
        fromLanguage: json['fromLanguage'] as String,
        toLanguage: json['toLanguage'] as String,
        fromFlag: json['fromFlag'] as String,
        toFlag: json['toFlag'] as String,
        fromTtsLocale: json['fromTtsLocale'] as String,
        toTtsLocale: json['toTtsLocale'] as String,
        matchScore: (json['matchScore'] as num).toDouble(),
        timestamp: DateTime.parse(json['timestamp'] as String),
      );
}
