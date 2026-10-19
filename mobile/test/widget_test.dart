// Widget + unit tests for the AI Trading Lab monitoring client
// (Stage F/F3). Replaces the broken `flutter create` scaffold test
// (which referenced a nonexistent MyApp class).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_trading_lab_monitor/main.dart';

void main() {
  test('TLS-only: http:// server URLs are refused before any request',
      () {
    expect(
      () => EngineApiClient.normalizeServerUrl('http://engine.example.com'),
      throwsA(isA<ApiException>()),
    );
    expect(
      () => EngineApiClient.normalizeServerUrl('http://127.0.0.1:8018'),
      throwsA(isA<ApiException>()),
    );
  });

  test('bare hosts normalize to https (never a silent http downgrade)', () {
    expect(
      EngineApiClient.normalizeServerUrl('engine.example.com'),
      'https://engine.example.com',
    );
    expect(
      EngineApiClient.normalizeServerUrl('https://x.example.com/'),
      'https://x.example.com',
    );
  });

  testWidgets('profile dialog refuses short tokens (validation)',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: ProfileEditDialog(initial: null)),
    );
    await tester.enterText(find.byType(TextField).at(0), 'my server');
    await tester.enterText(
        find.byType(TextField).at(1), 'engine.example.com');
    await tester.enterText(find.byType(TextField).at(2), 'short');
    await tester.tap(find.text('Save'));
    await tester.pump();
    expect(find.textContaining('token looks too short'), findsOneWidget);
  });

  testWidgets('profile dialog refuses http:// URLs (TLS-only gate)',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: ProfileEditDialog(initial: null)),
    );
    await tester.enterText(find.byType(TextField).at(0), 'my server');
    await tester.enterText(find.byType(TextField).at(1), 'http://plain.example');
    await tester.enterText(
        find.byType(TextField).at(2), '0123456789abcdef0123456789abcdef');
    await tester.tap(find.text('Save'));
    await tester.pump();
    expect(find.textContaining('TLS only'), findsOneWidget);
  });

  testWidgets('profile dialog saves a valid https profile',
      (WidgetTester tester) async {
    ServerProfile? popped;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () async {
                popped = await showDialog<ServerProfile>(
                  context: context,
                  builder: (_) => const ProfileEditDialog(initial: null),
                );
              },
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).at(0), 'primary');
    await tester.enterText(
        find.byType(TextField).at(1), 'engine.example.com');
    await tester.enterText(
        find.byType(TextField).at(2), '0123456789abcdef0123456789abcdef');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(popped, isNotNull);
    expect(popped!.serverUrl, 'https://engine.example.com');
    expect(popped!.token, '0123456789abcdef0123456789abcdef');
    expect(popped!.label, 'primary');
  });
}
