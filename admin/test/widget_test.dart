// Admin panel (v1.0.0) tests — no platform channels touched:
// the storage-backed gate is exercised via SetupPage directly
// (flutter_secure_storage has no test double wired here).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_trading_lab_admin/main.dart';

void main() {
  test('TLS-only default; plain http needs the explicit LAN switch', () {
    expect(
      () => AdminApiClient.normalizeServerUrl('http://engine.example.com'),
      throwsA(isA<ApiException>()),
    );
    expect(
      AdminApiClient.normalizeServerUrl('http://192.168.0.58:8018',
          allowPlainHttp: true),
      'http://192.168.0.58:8018',
    );
    expect(
      AdminApiClient.normalizeServerUrl('192.168.0.58:8018',
          allowPlainHttp: true),
      'http://192.168.0.58:8018',
    );
    expect(
      AdminApiClient.normalizeServerUrl('engine.example.com'),
      'https://engine.example.com',
    );
  });

  test('epoch timestamps format as UTC ISO; others pass through', () {
    expect(
      formatTimestamp(0),
      DateTime.fromMillisecondsSinceEpoch(0, isUtc: true).toIso8601String(),
    );
    expect(formatTimestamp('already-a-string'), 'already-a-string');
    expect(formatTimestamp(null), 'null');
  });

  testWidgets('setup screen refuses empty required fields',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(home: SetupPage(onSaved: (_) async {})),
    );
    await tester.enterText(
        find.byType(TextField).at(0), 'http://192.168.0.58:8018');
    await tester.tap(find.text('CONNECT'));
    await tester.pump();
    expect(find.textContaining('all required'), findsOneWidget);
  });

  testWidgets('setup screen refuses short tokens (validation)',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(home: SetupPage(onSaved: (_) async {})),
    );
    await tester.enterText(
        find.byType(TextField).at(0), 'http://192.168.0.58:8018');
    await tester.enterText(find.byType(TextField).at(1), 'short');
    await tester.enterText(find.byType(TextField).at(2), 'owner');
    await tester.enterText(find.byType(TextField).at(3), 'owner@lab.test');
    await tester.tap(find.text('CONNECT'));
    await tester.pump();
    expect(find.textContaining('token looks too short'), findsOneWidget);
  });
}
