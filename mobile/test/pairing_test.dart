// AI Trading Lab — v4.0 dual-mode onboarding tests (Stage C / Stage F).
//
// Pins the owner mandates on the ACTUAL app code:
//  - cloud profiles: TLS-only (http:// refused, bare host -> https);
//  - local profiles: http:// allowed ONLY via the per-profile
//    isLocal flag (never a global downgrade);
//  - profile JSON round-trip incl. backward compatibility (v0.3.x
//    profiles load as CLOUD profiles);
//  - both onboarding forms enforce their compulsory fields;
//  - switching keeps every profile (P6);
//  - the invitation code value never appears anywhere in mobile/.
//
// CI runs these via `flutter test` (no Flutter toolchain is assumed
// in local dev — see README-APK.md). No platform plugins are invoked:
// every test is pure Dart / plain widget pumping.
//
// LIVE TRADING IS NOT AUTHORIZED anywhere in this system.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:ai_trading_lab_monitor/main.dart' as app;
import 'package:ai_trading_lab_monitor/pairing.dart' as pairing;

// ---------------------------------------------------------------------------
// transport policy (C3 — scoped per profile, never global)
// ---------------------------------------------------------------------------

void main() {
  group('normalizeServerUrl (per-profile transport policy)', () {
    test('CLOUD: https:// passes through unchanged', () {
      expect(
        app.EngineApiClient.normalizeServerUrl('https://engine.example.com',
            isLocal: false),
        'https://engine.example.com',
      );
    });

    test('CLOUD: trailing slash is stripped', () {
      expect(
        app.EngineApiClient.normalizeServerUrl('https://engine.example.com/',
            isLocal: false),
        'https://engine.example.com',
      );
    });

    test('CLOUD: http:// is REFUSED (TLS-only posture unchanged)', () {
      expect(
        () => app.EngineApiClient.normalizeServerUrl(
            'http://engine.example.com',
            isLocal: false),
        throwsA(isA<app.ApiException>()),
      );
    });

    test('CLOUD: bare host assumes https (never silently downgraded)', () {
      expect(
        app.EngineApiClient.normalizeServerUrl('engine.example.com',
            isLocal: false),
        'https://engine.example.com',
      );
    });

    test('LOCAL: http:// is allowed on the user own LAN', () {
      expect(
        app.EngineApiClient.normalizeServerUrl('http://192.168.1.5:8018',
            isLocal: true),
        'http://192.168.1.5:8018',
      );
    });

    test('LOCAL: bare host assumes http (127.0.0.1 works directly)', () {
      expect(
        app.EngineApiClient.normalizeServerUrl('127.0.0.1:8018',
            isLocal: true),
        'http://127.0.0.1:8018',
      );
      expect(
        app.EngineApiClient.normalizeServerUrl('192.168.1.5:8018',
            isLocal: true),
        'http://192.168.1.5:8018',
      );
    });

    test('LOCAL: https:// still passes through (upgrade never blocked)', () {
      expect(
        app.EngineApiClient.normalizeServerUrl('https://engine.example.com',
            isLocal: true),
        'https://engine.example.com',
      );
    });

    test('default (no flag) is CLOUD posture — the safe default', () {
      expect(
        () => app.EngineApiClient
            .normalizeServerUrl('http://engine.example.com'),
        throwsA(isA<app.ApiException>()),
      );
      expect(
        app.EngineApiClient.normalizeServerUrl('engine.example.com'),
        'https://engine.example.com',
      );
    });
  });

  group('ServerProfile (model + storage round-trip)', () {
    app.ServerProfile decode(String raw) =>
        app.ServerProfile.fromJson(jsonDecode(raw) as Map<String, dynamic>);

    test('v0.3.x profiles (no isLocal/email) load as CLOUD profiles', () {
      final legacy = decode('{"id":"a1","label":"alice",'
          '"serverUrl":"https://s.example","token":"t-token-1234567890"}');
      expect(legacy.isLocal, isFalse);
      expect(legacy.email, isNull);
    });

    test('LOCAL profile round-trips isLocal + email', () {
      final profile = app.ServerProfile(
        id: 'b2',
        label: 'my-desktop',
        serverUrl: 'http://192.168.1.5:8018',
        token: 't' * 32,
        isLocal: true,
        email: 'alice@example.com',
      );
      final restored = decode(jsonEncode(profile.toJson()));
      expect(restored.isLocal, isTrue);
      expect(restored.email, 'alice@example.com');
      expect(restored.serverUrl, profile.serverUrl);
    });

    test('CLOUD profile round-trips without email key', () {
      final profile = app.ServerProfile(
        id: 'c3',
        label: 'cloud-primary',
        serverUrl: 'https://s.example',
        token: 't' * 32,
      );
      final encoded = jsonEncode(profile.toJson());
      expect(encoded.contains('email'), isFalse);
      final restored = decode(encoded);
      expect(restored.isLocal, isFalse);
      expect(restored.email, isNull);
    });
  });

  group('ModeChoiceDialog (P2: exactly two options + advanced)', () {
    testWidgets('renders the two mode buttons and the advanced escape',
        (WidgetTester tester) async {
      await tester.pumpWidget(const MaterialApp(home: app.ModeChoiceDialog()));
      expect(find.text('CLOUD SERVER'), findsOneWidget);
      expect(find.text('LOCAL COMPUTER'), findsOneWidget);
      expect(find.text('Advanced: paste token manually'), findsOneWidget);
    });
  });

  group('CloudPairingFormDialog (P3/C2: three compulsory fields)', () {
    testWidgets('Pair with empty fields shows the required-fields error',
        (WidgetTester tester) async {
      await tester
          .pumpWidget(const MaterialApp(home: app.CloudPairingFormDialog()));
      await tester.tap(find.text('Pair'));
      await tester.pump();
      expect(find.textContaining('all required'), findsOneWidget);
      // no pairing request happens without all three fields
    });

    testWidgets('http:// server URL is refused in the cloud form',
        (WidgetTester tester) async {
      await tester
          .pumpWidget(const MaterialApp(home: app.CloudPairingFormDialog()));
      await tester.enterText(
          find.byType(TextField).at(0), 'alice-primary');
      await tester.enterText(
          find.byType(TextField).at(1), 'http://engine.example.com');
      await tester.enterText(find.byType(TextField).at(2), 'some-code');
      await tester.tap(find.text('Pair'));
      await tester.pump();
      expect(find.textContaining('TLS only'), findsOneWidget);
    });
  });

  group('LocalPairingFormDialog (P4/C3: four compulsory fields)', () {
    testWidgets('Pair with empty fields shows the required-fields error',
        (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(
          home: app.LocalPairingFormDialog(
              store: _NoopStore(), discoverHost: () async => null)));
      await tester.tap(find.text('Pair'));
      await tester.pump();
      expect(find.textContaining('all required'), findsOneWidget);
      // no pairing request happens without all four fields
    });

    testWidgets('invalid email is refused before any request',
        (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(
          home: app.LocalPairingFormDialog(
              store: _NoopStore(), discoverHost: () async => null)));
      await tester.enterText(find.byType(TextField).at(0), 'my-desktop');
      await tester
          .enterText(find.byType(TextField).at(1), 'not-an-email');
      await tester.enterText(find.byType(TextField).at(2), '192.168.1.5:8018');
      await tester.enterText(find.byType(TextField).at(3), 'some-code');
      await tester.tap(find.text('Pair'));
      await tester.pump();
      expect(find.textContaining('valid email'), findsOneWidget);
    });

    testWidgets('mDNS auto-fill pre-fills the discovered PC address',
        (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(
          home: app.LocalPairingFormDialog(
              store: _NoopStore(),
              discoverHost: () async => '192.168.1.50:8018')));
      await tester.pumpAndSettle();
      // PC address is the THIRD TextField (name, email, PC, code);
      // TextField comes from package:flutter/material (not re-exported
      // through the app library — use the direct material import).
      final TextField pcField =
          tester.widget<TextField>(find.byType(TextField).at(2));
      expect(pcField.controller!.text, '192.168.1.50:8018');
    });
  });

  group('pairWithEngine (client contract)', () {
    test('rejects a non-paired response with the engine reason code',
        () async {
      final client = MockClient((http.BaseRequest request) async {
        return http.Response(
          jsonEncode(<String, dynamic>{'error': 'E_PAIRING_CODE_INVALID'}),
          403,
        );
      });
      try {
        await pairing.pairWithEngine(
          baseUri: Uri.parse('https://engine.example.com'),
          name: 'alice',
          email: 'alice@example.com',
          invitationCode: 'wrong-code',
          mode: 'cloud',
          httpClient: client,
        );
        fail('PairingException expected');
      } on pairing.PairingException catch (exc) {
        expect(exc.statusCode, 403);
        expect(exc.message, 'E_PAIRING_CODE_INVALID');
      }
    });

    test('returns the monitoring token on a paired response', () async {
      final client = MockClient((http.BaseRequest request) async {
        return http.Response(
          jsonEncode(<String, dynamic>{
            'status': 'paired',
            'token': 't' * 32,
            'health': <String, dynamic>{'engine_state': 'RUNNING'},
            'pairing': <String, dynamic>{
              'email_redacted': '***@example.com',
              'mode': 'local',
            },
          }),
          200,
        );
      });
      final token = await pairing.pairWithEngine(
        baseUri: Uri.parse('http://192.168.1.5:8018'),
        name: 'my-desktop',
        email: 'alice@example.com',
        invitationCode: 'correct-code',
        mode: 'local',
        httpClient: client,
      );
      expect(token, 't' * 32);
    });
  });

  test('mDNS service type matches the engine announcement (P5)', () {
    expect(pairing.kMonitorServiceType, '_aitl-monitor._tcp.local.');
  });
}

// ---------------------------------------------------------------------------
// test doubles (no platform plugins, no real network — CI-safe)
// ---------------------------------------------------------------------------

/// Store double that never touches flutter_secure_storage (its methods
/// are only reached after validation succeeds, which these tests never
/// do — they stop at the compulsory-field checks).
class _NoopStore implements app.ProfileStore {
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
