import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:smart_headphone_app/main.dart';
import 'package:smart_headphone_app/providers/translation_provider.dart';

void main() {
  // TranslationProvider.initialize() talks to shared_preferences, flutter_tts,
  // and permission_handler over platform channels that have no native
  // implementation under `flutter test`. Without mocking them, the calls hang
  // (rather than failing fast) inside the test's fake-async zone, so the
  // splash screen never finishes its bootstrap and never navigates.
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
        const MethodChannel('flutter_tts'), (call) async => 1);
    messenger.setMockMethodCallHandler(
        const MethodChannel('flutter.baseflow.com/permissions/methods'),
        (call) async => <int, int>{});
  });

  Future<void> pumpPastSplash(WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => TranslationProvider(),
        child: const SmartHeadphoneApp(),
      ),
    );
    await tester.pump();
    expect(find.text('Smart Headphone'), findsOneWidget);

    // Splash waits a fixed 3s then does a 500ms fade transition into
    // MainShell. Can't use pumpAndSettle: the splash's pulsing-ring
    // animation repeats forever and would never let it settle. Pumping in
    // 1s increments (rather than one 4s jump) gives the Future.delayed
    // callback and the post-navigation frame each their own pass.
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(seconds: 1));
    }
  }

  testWidgets('App launches and shows main UI elements', (WidgetTester tester) async {
    await pumpPastSplash(tester);

    // mic_rounded appears both as the bottom-nav "Translate" tab icon and
    // as the big mic button on HomeScreen.
    expect(find.byIcon(Icons.mic_rounded), findsWidgets);
  });

  testWidgets('Language swap button is present', (WidgetTester tester) async {
    await pumpPastSplash(tester);

    expect(find.byIcon(Icons.swap_horiz_rounded), findsWidgets);
  });
}
