// AI Trading Lab — invitation pairing client + mDNS discovery (v4.0, Stage C).
//
// Role: onboarding helpers for the dual-mode (Cloud / Local) flow.
//
// Security contract:
//  - The invitation code is sent ONCE to the engine's POST /api/pair
//    and is NEVER stored, logged, or cached anywhere on the phone.
//  - Only the RETURNED monitoring bearer token is stored (by the
//    caller, in flutter_secure_storage — never here).
//  - mDNS discovery is a convenience with a hard manual fallback:
//    ANY failure returns null and the user types the PC address.
//  - No TLS downgrade happens here: transport policy is decided by
//    the caller's per-profile isLocal flag (cloud stays https-only).
//
// LIVE TRADING IS NOT AUTHORIZED anywhere in this system.

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:multicast_dns/multicast_dns.dart';

/// Error surfaced by a failed pairing attempt. Carries the engine's
/// stable reason code (e.g. E_PAIRING_CODE_INVALID) when present.
class PairingException implements Exception {
  PairingException(this.statusCode, this.message);

  final int statusCode;
  final String message;

  @override
  String toString() => 'PAIRING $statusCode: $message';
}

/// POST {base}/api/pair with the invitation code; returns the
/// monitoring bearer token. Fail-closed: any non-paired response is
/// an exception with the engine's reason code.
Future<String> pairWithEngine({
  required Uri baseUri,
  required String name,
  required String email,
  required String invitationCode,
  required String mode,
  http.Client? httpClient,
  Duration timeout = const Duration(seconds: 10),
}) async {
  final client = httpClient ?? http.Client();
  try {
    final http.Response response = await client
        .post(
          baseUri.replace(path: '/api/pair'),
          headers: <String, String>{
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
          body: jsonEncode(<String, dynamic>{
            'name': name,
            'email': email,
            'invitation_code': invitationCode,
            'mode': mode,
          }),
        )
        .timeout(timeout);
    Map<String, dynamic> body;
    try {
      body =
          jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    } catch (_) {
      throw PairingException(
          response.statusCode, 'unexpected server response');
    }
    if (response.statusCode == 200 && body['status'] == 'paired') {
      final dynamic token = body['token'];
      if (token is String && token.length >= 16) {
        return token;
      }
      throw PairingException(response.statusCode, 'server returned no token');
    }
    final dynamic error = body['error'];
    if (error is String && error.isNotEmpty) {
      throw PairingException(response.statusCode, error);
    }
    throw PairingException(response.statusCode, 'pairing refused');
  } on PairingException {
    rethrow;
  } on TimeoutException {
    throw PairingException(0, 'timeout — server unreachable');
  } catch (exc) {
    throw PairingException(0, 'connection error (${exc.runtimeType})');
  } finally {
    if (httpClient == null) {
      client.close();
    }
  }
}

/// The mDNS service type announced by the Windows local monitor (P5).
const String kMonitorServiceType = '_aitl-monitor._tcp.local.';

/// Try to auto-discover a local monitor on the LAN via mDNS.
/// Returns `host:port` (e.g. `192.168.1.5:8018`) or null on ANY
/// failure — the manual PC-address entry is the always-works path.
Future<String?> discoverMonitorHost({
  String serviceType = kMonitorServiceType,
  Duration timeout = const Duration(seconds: 4),
}) async {
  MDnsClient? client;
  try {
    client = MDnsClient();
    await client.start().timeout(timeout);
    await for (final PtrResourceRecord ptr in client.lookup<PtrResourceRecord>(
        ResourceRecordQuery.serverPointer(serviceType),
        timeout: timeout)) {
      await for (final SrvResourceRecord srv
          in client.lookup<SrvResourceRecord>(
              ResourceRecordQuery.service(ptr.domainName),
              timeout: timeout)) {
        await for (final IPAddressResourceRecord ip
            in client.lookup<IPAddressResourceRecord>(
                ResourceRecordQuery.addressIPv4(srv.target),
                timeout: timeout)) {
          final String address = ip.address.address;
          if (address.isNotEmpty) {
            return '$address:${srv.port}';
          }
        }
      }
    }
    return null;
  } catch (_) {
    // graceful: multicast may be blocked/unavailable on this network —
    // the user simply types the PC address instead (documented fallback)
    return null;
  } finally {
    try {
      client?.stop();
    } catch (_) {
      // best-effort teardown, never propagates
    }
  }
}
