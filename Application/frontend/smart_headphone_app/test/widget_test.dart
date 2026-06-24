import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:smart_headphone_app/main.dart';
import 'package:smart_headphone_app/providers/translation_provider.dart';

void main() {
  testWidgets('App launches and shows main UI elements', (WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => TranslationProvider(),
        child: const SmartHeadphoneApp(),
      ),
    );
    await tester.pump();

    expect(find.text('Smart Headphone'), findsOneWidget);
    expect(find.byIcon(Icons.mic), findsOneWidget);
  });

  testWidgets('Language swap button is present', (WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => TranslationProvider(),
        child: const SmartHeadphoneApp(),
      ),
    );
    await tester.pump();

    expect(find.byIcon(Icons.swap_horiz), findsOneWidget);
  });
}
