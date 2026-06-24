class Language {
  final String code;
  final String name;
  final String flag;
  final String locale;
  final String ttsLocale;

  const Language({
    required this.code,
    required this.name,
    required this.flag,
    required this.locale,
    required this.ttsLocale,
  });
}

const List<Language> supportedLanguages = [
  Language(code: 'en', name: 'English',    flag: '🇺🇸', locale: 'en-US', ttsLocale: 'en-US'),
  Language(code: 'ur', name: 'Urdu',       flag: '🇵🇰', locale: 'ur-PK', ttsLocale: 'ur-PK'),
  Language(code: 'ar', name: 'Arabic',     flag: '🇸🇦', locale: 'ar-SA', ttsLocale: 'ar-SA'),
  Language(code: 'zh', name: 'Chinese',    flag: '🇨🇳', locale: 'zh-CN', ttsLocale: 'zh-CN'),
  Language(code: 'fr', name: 'French',     flag: '🇫🇷', locale: 'fr-FR', ttsLocale: 'fr-FR'),
  Language(code: 'de', name: 'German',     flag: '🇩🇪', locale: 'de-DE', ttsLocale: 'de-DE'),
  Language(code: 'es', name: 'Spanish',    flag: '🇪🇸', locale: 'es-ES', ttsLocale: 'es-ES'),
  Language(code: 'it', name: 'Italian',    flag: '🇮🇹', locale: 'it-IT', ttsLocale: 'it-IT'),
  Language(code: 'ja', name: 'Japanese',   flag: '🇯🇵', locale: 'ja-JP', ttsLocale: 'ja-JP'),
  Language(code: 'ko', name: 'Korean',     flag: '🇰🇷', locale: 'ko-KR', ttsLocale: 'ko-KR'),
  Language(code: 'pt', name: 'Portuguese', flag: '🇵🇹', locale: 'pt-PT', ttsLocale: 'pt-PT'),
  Language(code: 'ru', name: 'Russian',    flag: '🇷🇺', locale: 'ru-RU', ttsLocale: 'ru-RU'),
  Language(code: 'hi', name: 'Hindi',      flag: '🇮🇳', locale: 'hi-IN', ttsLocale: 'hi-IN'),
  Language(code: 'tr', name: 'Turkish',    flag: '🇹🇷', locale: 'tr-TR', ttsLocale: 'tr-TR'),
  Language(code: 'nl', name: 'Dutch',      flag: '🇳🇱', locale: 'nl-NL', ttsLocale: 'nl-NL'),
  Language(code: 'pl', name: 'Polish',     flag: '🇵🇱', locale: 'pl-PL', ttsLocale: 'pl-PL'),
  Language(code: 'sv', name: 'Swedish',    flag: '🇸🇪', locale: 'sv-SE', ttsLocale: 'sv-SE'),
  Language(code: 'da', name: 'Danish',     flag: '🇩🇰', locale: 'da-DK', ttsLocale: 'da-DK'),
  Language(code: 'fi', name: 'Finnish',    flag: '🇫🇮', locale: 'fi-FI', ttsLocale: 'fi-FI'),
  Language(code: 'no', name: 'Norwegian',  flag: '🇳🇴', locale: 'nb-NO', ttsLocale: 'nb-NO'),
  Language(code: 'id', name: 'Indonesian', flag: '🇮🇩', locale: 'id-ID', ttsLocale: 'id-ID'),
  Language(code: 'ms', name: 'Malay',      flag: '🇲🇾', locale: 'ms-MY', ttsLocale: 'ms-MY'),
  Language(code: 'th', name: 'Thai',       flag: '🇹🇭', locale: 'th-TH', ttsLocale: 'th-TH'),
  Language(code: 'vi', name: 'Vietnamese', flag: '🇻🇳', locale: 'vi-VN', ttsLocale: 'vi-VN'),
  Language(code: 'el', name: 'Greek',      flag: '🇬🇷', locale: 'el-GR', ttsLocale: 'el-GR'),
  Language(code: 'cs', name: 'Czech',      flag: '🇨🇿', locale: 'cs-CZ', ttsLocale: 'cs-CZ'),
  Language(code: 'hu', name: 'Hungarian',  flag: '🇭🇺', locale: 'hu-HU', ttsLocale: 'hu-HU'),
  Language(code: 'ro', name: 'Romanian',   flag: '🇷🇴', locale: 'ro-RO', ttsLocale: 'ro-RO'),
  Language(code: 'uk', name: 'Ukrainian',  flag: '🇺🇦', locale: 'uk-UA', ttsLocale: 'uk-UA'),
  Language(code: 'he', name: 'Hebrew',     flag: '🇮🇱', locale: 'he-IL', ttsLocale: 'he-IL'),
  Language(code: 'bn', name: 'Bengali',    flag: '🇧🇩', locale: 'bn-BD', ttsLocale: 'bn-BD'),
  Language(code: 'fa', name: 'Persian',    flag: '🇮🇷', locale: 'fa-IR', ttsLocale: 'fa-IR'),
  Language(code: 'sw', name: 'Swahili',    flag: '🇰🇪', locale: 'sw-KE', ttsLocale: 'sw-KE'),
  Language(code: 'tl', name: 'Filipino',   flag: '🇵🇭', locale: 'fil-PH', ttsLocale: 'fil-PH'),
];
