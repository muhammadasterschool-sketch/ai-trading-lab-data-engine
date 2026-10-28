// AI Trading Lab — Android monitoring client (Stage F, Part 9 F2;
// v4.0 dual-mode onboarding — PART 6 Stage C).
//
// Role (owner mandate): monitoring + control client, server-
// authenticated. The trading engine NEVER runs on the phone.
//
// Security contract (v4.0, two modes — P2/P3/P4/P5/P6/P7):
//  - First run offers exactly TWO options: CLOUD SERVER (your own
//    VPS over https) or LOCAL COMPUTER (the engine on your Windows
//    PC — no server rental; loopback by default, explicit -AllowLan
//    + honest unencrypted-LAN warning on the PC side).
//  - CLOUD profiles are TLS ONLY: http:// URLs are refused before any
//    request (unchanged v0.3.0 posture).
//  - LOCAL profiles may use http:// ONLY via an explicit PER-PROFILE
//    isLocal flag — never a global downgrade; cloud profiles still
//    refuse http. A one-time warning states the LAN is unencrypted.
//  - Onboarding (both modes) uses the owner-issued INVITATION CODE
//    via POST /api/pair; the returned token lands in
//    flutter_secure_storage. The code itself is typed, used ONCE,
//    and NEVER stored, logged, or embedded in the APK.
//  - The token lives ONLY in flutter_secure_storage (Android
//    Keystore-backed). It is never logged and never rendered.
//  - Multi-profile: several server profiles (mixed cloud/local) can
//    be stored, but only ONE is active at a time. Switching NEVER
//    deletes profiles, tokens, or local state (P6).
//  - The ONLY mutating action is the kill switch, gated by an
//    explicit confirmation dialog with a mandatory reason; it POSTs
//    to the server's /api/killswitch/activate endpoint, which itself
//    requires {"confirm": true, "reason": ...} — defense in depth.
//
// LIVE TRADING IS NOT AUTHORIZED anywhere in this system.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import 'admin_users.dart';
import 'auth.dart';
import 'pairing.dart';

const String _storageProfilesKey = 'atl_monitor_profiles';
const String _storageActiveKey = 'atl_monitor_active_profile';
const String _storageOnboardingModeKey = 'atl_onboarding_mode';
const String _storageLanWarningKey = 'atl_local_lan_warning_ack';

/// One saved server profile (exactly one is active at a time).
class ServerProfile {
  ServerProfile({
    required this.id,
    required this.label,
    required this.serverUrl,
    required this.token,
    this.isLocal = false,
    this.email,
    this.role,
    this.authKind,
  });

  final String id;
  final String label;
  final String serverUrl;
  final String token;

  /// v4.0: LOCAL mode is an explicit PER-PROFILE flag. A local profile
  /// may use http:// on the user's own LAN; a CLOUD profile never can
  /// (TLS-only posture unchanged for cloud). This is the ONLY switch
  /// for transport policy — there is no global downgrade anywhere.
  final bool isLocal;

  /// v4.0 (P7): identity-only field for LOCAL profiles — audit-log
  /// entry at pairing + display in the app. No OAuth, no Google
  /// sign-in, no network call to anyone. Redacted server-side.
  final String? email;

  /// v1.5.0: role + auth kind of this profile's credential
  /// ('session' = email+password+TOTP login; null/'' = pairing
  /// token = owner level). Drives the admin Users surface.
  final String? role;
  final String? authKind;

  bool get isAdmin =>
      authKind == null ||
      authKind!.isEmpty ||
      role == 'admin' ||
      role == 'owner';

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'label': label,
        'serverUrl': serverUrl,
        'token': token,
        'isLocal': isLocal,
        if (email != null) 'email': email,
        if (role != null) 'role': role,
        if (authKind != null) 'authKind': authKind,
      };

  static ServerProfile fromJson(Map<String, dynamic> json) => ServerProfile(
        id: json['id'] as String,
        label: json['label'] as String,
        serverUrl: json['serverUrl'] as String,
        token: json['token'] as String,
        // backward compatibility: v0.3.x profiles load as CLOUD profiles
        isLocal: (json['isLocal'] as bool?) ?? false,
        email: json['email'] as String?,
        role: json['role'] as String?,
        authKind: json['authKind'] as String?,
      );
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AiTradingLabMonitorApp());
}

class AiTradingLabMonitorApp extends StatelessWidget {
  const AiTradingLabMonitorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Trading Lab',
      theme: ThemeData(
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF3B6EF5),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const ProfileGatePage(),
    );
  }
}

// ---------------------------------------------------------------------------
// Profile storage (secure storage ONLY)
// ---------------------------------------------------------------------------

class ProfileStore {
  ProfileStore(this._storage);

  final FlutterSecureStorage _storage;

  Future<List<ServerProfile>> loadProfiles() async {
    final raw = await _storage.read(key: _storageProfilesKey);
    if (raw == null || raw.isEmpty) {
      return <ServerProfile>[];
    }
    final List<dynamic> decoded = jsonDecode(raw) as List<dynamic>;
    return decoded
        .map((dynamic e) => ServerProfile.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<String?> loadActiveId() => _storage.read(key: _storageActiveKey);

  Future<void> saveProfiles(List<ServerProfile> profiles) async {
    await _storage.write(
      key: _storageProfilesKey,
      value: jsonEncode(profiles.map((p) => p.toJson()).toList()),
    );
  }

  Future<void> saveActiveId(String? id) async {
    if (id == null) {
      await _storage.delete(key: _storageActiveKey);
    } else {
      await _storage.write(key: _storageActiveKey, value: id);
    }
  }

  // -- v4.0: onboarding-mode memory + one-time LAN warning ack (C1/C3)

  Future<void> saveOnboardingMode(String mode) =>
      _storage.write(key: _storageOnboardingModeKey, value: mode);

  Future<String?> loadOnboardingMode() =>
      _storage.read(key: _storageOnboardingModeKey);

  Future<void> acknowledgeLocalLanWarning() =>
      _storage.write(key: _storageLanWarningKey, value: '1');

  Future<bool> localLanWarningAcknowledged() async =>
      await _storage.read(key: _storageLanWarningKey) == '1';
}

// ---------------------------------------------------------------------------
// API client (TLS-only, Bearer token, read-only + kill switch)
// ---------------------------------------------------------------------------

class ApiException implements Exception {
  ApiException(this.statusCode, this.message);
  final int statusCode;
  final String message;

  @override
  String toString() => 'API $statusCode: $message';
}

class EngineApiClient {
  EngineApiClient({
    required this.serverUrl,
    required this.token,
    this.clientName = '',
    this.clientEmail = '',
    this.clientKind = 'monitor',
  });

  final String serverUrl;
  final String token;

  /// v1.0.0 (owner mandate): SELF-REPORTED identity sent on EVERY
  /// request so the engine's owner surfaces — /api/users (who is
  /// connected right now) and /api/registrations (who ever
  /// registered) — can answer honestly. This is a lab trust domain:
  /// the bearer token remains the ONLY authentication factor, and
  /// the identity is exactly as honest as the client sending it.
  final String clientName;
  final String clientEmail;
  final String clientKind;

  /// Transport policy (v4.0, scoped PER PROFILE — never global):
  ///  - CLOUD (isLocal == false): TLS ONLY — http:// is refused and a
  ///    bare host assumes https:// (exactly the v0.3.0 posture).
  ///  - LOCAL (isLocal == true): http:// is allowed on the user's own
  ///    LAN and a bare host (e.g. 127.0.0.1 or the PC's IP) assumes
  ///    http://. NEVER applies to cloud profiles.
  static String normalizeServerUrl(String raw, {bool isLocal = false}) {
    var url = raw.trim();
    if (url.endsWith('/')) {
      url = url.substring(0, url.length - 1);
    }
    if (url.startsWith('https://')) {
      return url;
    }
    if (url.startsWith('http://')) {
      if (!isLocal) {
        throw ApiException(
          0,
          'TLS only: http:// is refused for cloud servers. Use https:// '
              '(your server\'s nginx certificate).',
        );
      }
      return url;
    }
    // bare host: NEVER silently downgrade a cloud profile
    return isLocal ? 'http://$url' : 'https://$url';
  }

  Map<String, String> get _headers => <String, String>{
        'Authorization': 'Bearer $token',
        'Accept': 'application/json',
        'X-Client-Name': clientName,
        'X-Client-Email': clientEmail,
        'X-Client-Kind': clientKind,
        'X-Client-Device': 'android',
      };

  /// v4.0.2: a 429 is a TRANSIENT server-side throttle, not a broken
  /// connection — surface it as an honest, calm message (the next poll
  /// cycle retries automatically).
  ApiException? _statusException(int statusCode) {
    if (statusCode == 401) {
      return ApiException(401, 'invalid or expired token');
    }
    if (statusCode == 429) {
      return ApiException(429, 'server busy (rate limited) — retrying automatically');
    }
    if (statusCode != 200) {
      return ApiException(statusCode, 'unexpected status');
    }
    return null;
  }

  Future<Map<String, dynamic>> _getJson(String path) async {
    final response = await http
        .get(Uri.parse('$serverUrl$path'), headers: _headers)
        .timeout(const Duration(seconds: 10));
    final ApiException? failure = _statusException(response.statusCode);
    if (failure != null) {
      throw failure;
    }
    return jsonDecode(utf8.decode(response.bodyBytes))
        as Map<String, dynamic>;
  }

  /// v4.0.1 correction: collection endpoints (positions, orders) return
  /// JSON ARRAYS from the monitoring API — the monitor-only default
  /// providers return []. Forcing them through the Map-only cast raised
  /// _TypeError on the dashboard ("connection error (_TypeError)") and
  /// left every panel empty even though pairing had succeeded. Parse
  /// defensively instead: accept whatever JSON shape the server sends.
  Future<dynamic> _getDynamic(String path) async {
    final response = await http
        .get(Uri.parse('$serverUrl$path'), headers: _headers)
        .timeout(const Duration(seconds: 10));
    final ApiException? failure = _statusException(response.statusCode);
    if (failure != null) {
      throw failure;
    }
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  Future<Map<String, dynamic>> health() => _getJson('/api/health');
  Future<Map<String, dynamic>> risk() => _getJson('/api/risk');
  Future<Map<String, dynamic>> feed() => _getJson('/api/feed');
  Future<dynamic> positions() async {
    final dynamic decoded = await _getDynamic('/api/positions');
    return decoded ?? <dynamic>[];
  }

  Future<dynamic> orders() async {
    final dynamic decoded = await _getDynamic('/api/orders');
    return decoded ?? <dynamic>[];
  }

  Future<dynamic> pnl() async {
    final dynamic decoded = await _getDynamic('/api/pnl');
    return decoded ?? <String, dynamic>{};
  }

  /// v1.0.0: aggregate trade stats (trades per symbol, total PnL,
  /// wins/losses) — the dashboard mini chart's data source.
  /// ("sab se jyada trades kis pe liye")
  Future<Map<String, dynamic>> ledgerStats() =>
      _getJson('/api/ledger/stats');

  /// v1.0.0: the per-trade ledger ("kis pe trade li, kitna profit
  /// hua") — most recent first, bounded by the server (200).
  Future<List<Map<String, dynamic>>> tradeLedger() async {
    final response = await http
        .get(Uri.parse('$serverUrl/api/ledger/trades'), headers: _headers)
        .timeout(const Duration(seconds: 10));
    final ApiException? failure = _statusException(response.statusCode);
    if (failure != null) {
      throw failure;
    }
    final dynamic decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is Map && decoded['trades'] is List) {
      return (decoded['trades'] as List).cast<Map<String, dynamic>>();
    }
    return <Map<String, dynamic>>[];
  }

  Future<List<Map<String, dynamic>>> events() async {
    final response = await http
        .get(Uri.parse('$serverUrl/api/events'), headers: _headers)
        .timeout(const Duration(seconds: 10));
    final ApiException? failure = _statusException(response.statusCode);
    if (failure != null) {
      throw failure;
    }
    final dynamic decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is List) {
      return decoded.cast<Map<String, dynamic>>();
    }
    return <Map<String, dynamic>>[];
  }

  Future<Map<String, dynamic>> activateKillSwitch(String reason) async {
    final response = await http
        .post(
          Uri.parse('$serverUrl/api/killswitch/activate'),
          headers: <String, String>{
            ..._headers,
            'Content-Type': 'application/json',
          },
          body: jsonEncode(<String, dynamic>{
            'confirm': true,
            'reason': reason,
          }),
        )
        .timeout(const Duration(seconds: 10));
    final Map<String, dynamic> body =
        jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    if (response.statusCode != 200) {
      throw ApiException(
        response.statusCode,
        (body['error'] as String?) ?? 'kill-switch refusal',
      );
    }
    return body;
  }

  // -- v1.1.0 OWNER AI LAB --------------------------------------------------
  // The lab surfaces answer 400 with the engine's honest refusal text
  // (e.g. "strategy gate refused: the validation window has NOT
  // elapsed") — that text is surfaced verbatim in the UI.

  Map<String, dynamic> _decodeBody(http.Response response) {
    try {
      final dynamic decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
    } on FormatException {
      // fall through to the empty map
    }
    return <String, dynamic>{};
  }

  Future<Map<String, dynamic>> _postLab(
    String path,
    Map<String, dynamic> payload, {
    int timeoutSeconds = 60,
  }) async {
    final response = await http
        .post(
          Uri.parse('$serverUrl$path'),
          headers: <String, String>{
            ..._headers,
            'Content-Type': 'application/json',
          },
          body: jsonEncode(payload),
        )
        .timeout(Duration(seconds: timeoutSeconds));
    final Map<String, dynamic> body = _decodeBody(response);
    if (response.statusCode != 200) {
      throw ApiException(
        response.statusCode,
        (body['error'] as String?) ?? 'lab request refused',
      );
    }
    return body;
  }

  /// Strategy pipeline list (state, backtest evidence, paper window).
  Future<List<Map<String, dynamic>>> labStrategies() async {
    final dynamic decoded = await _getDynamic('/api/lab/strategies');
    if (decoded is Map && decoded['strategies'] is List) {
      return (decoded['strategies'] as List).cast<Map<String, dynamic>>();
    }
    return <Map<String, dynamic>>[];
  }

  Future<Map<String, dynamic>> labCreateStrategy({
    required String label,
    required String symbol,
    required String kind,
    Map<String, dynamic> params = const <String, dynamic>{},
  }) =>
      _postLab('/api/lab/strategies', <String, dynamic>{
        'label': label,
        'symbol': symbol,
        'kind': kind,
        'params': params,
      });

  Future<Map<String, dynamic>> labBacktest(String id) =>
      _postLab('/api/lab/strategies/$id/backtest', <String, dynamic>{});

  Future<Map<String, dynamic>> labPaperStart(String id, int cycleDays) =>
      _postLab('/api/lab/strategies/$id/paper/start',
          <String, dynamic>{'cycle_days': cycleDays});

  Future<Map<String, dynamic>> labPaperFinish(String id) =>
      _postLab('/api/lab/strategies/$id/paper/finish', <String, dynamic>{});

  Future<Map<String, dynamic>> labConfirm(String id, String confirm) =>
      _postLab('/api/lab/strategies/$id/confirm', <String, dynamic>{
        'confirm': confirm,
        'decided_by': 'monitor-apk',
      });

  /// Offline rule-based analytics assistant (answers from the ledgers).
  Future<Map<String, dynamic>> labAsk(String question) =>
      _postLab('/api/lab/assistant', <String, dynamic>{'question': question});

  /// Statistical next-move research baseline for one symbol.
  Future<Map<String, dynamic>> labPredict(String symbol) async {
    final response = await http
        .get(Uri.parse('$serverUrl/api/lab/predict/$symbol'),
            headers: _headers)
        .timeout(const Duration(seconds: 15));
    final Map<String, dynamic> body = _decodeBody(response);
    if (response.statusCode != 200) {
      throw ApiException(
        response.statusCode,
        (body['error'] as String?) ?? 'prediction refused',
      );
    }
    return body;
  }

  // -- v1.5.0 ---------------------------------------------------------

  /// Who am I? (session email+role, or the pairing owner).
  Future<Map<String, dynamic>> authMe() => _getJson('/api/auth/me');

  /// Admin: who is connected RIGHT NOW (client registry).
  Future<List<Map<String, dynamic>>> users() async {
    final response = await http
        .get(Uri.parse('$serverUrl/api/users'), headers: _headers)
        .timeout(const Duration(seconds: 10));
    final ApiException? failure = _statusException(response.statusCode);
    if (failure != null) {
      throw failure;
    }
    final dynamic decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is Map && decoded['clients'] is List) {
      return (decoded['clients'] as List).cast<Map<String, dynamic>>();
    }
    return <Map<String, dynamic>>[];
  }

  /// Admin: 2FA accounts with login history.
  Future<List<Map<String, dynamic>>> adminAccounts() async {
    final dynamic decoded = await _getDynamic('/api/admin/accounts');
    if (decoded is Map && decoded['accounts'] is List) {
      return (decoded['accounts'] as List).cast<Map<String, dynamic>>();
    }
    return <Map<String, dynamic>>[];
  }

  Future<Map<String, dynamic>> adminCreateUser({
    required String email,
    required String name,
    required String password,
    required String role,
  }) =>
      _postLab('/api/admin/accounts', <String, dynamic>{
        'email': email,
        'name': name,
        'password': password,
        'role': role,
      });

  Future<Map<String, dynamic>> adminReset2fa(String email) =>
      _postLab('/api/admin/accounts/reset-2fa', <String, dynamic>{
        'email': email,
      });

  Future<Map<String, dynamic>> adminSetLock(String email, bool locked) =>
      _postLab('/api/admin/accounts/set-lock', <String, dynamic>{
        'email': email,
        'locked': locked,
      });

  /// The TOP-5 YouTuber presets shipped with the engine.
  Future<List<Map<String, dynamic>>> labPresets() async {
    final dynamic decoded = await _getDynamic('/api/lab/presets');
    if (decoded is Map && decoded['presets'] is List) {
      return (decoded['presets'] as List).cast<Map<String, dynamic>>();
    }
    return <Map<String, dynamic>>[];
  }

  /// Import VERIFIED REAL 1m history into the lab (bundled repo data
  /// first; Binance Vision website fallback).
  Future<Map<String, dynamic>> histImport(String symbol) =>
      _postLab('/api/hist/import', <String, dynamic>{
        'symbol': symbol,
        'timeframe': '1m',
      }, timeoutSeconds: 120);

  /// Create the TOP-5 presets for a symbol + open paper windows.
  Future<Map<String, dynamic>> labBootstrap(String symbol) =>
      _postLab('/api/lab/bootstrap', <String, dynamic>{'symbol': symbol});

  /// AUTO-SCAN: parameter scan over all kinds (IS/OOS, net of costs).
  Future<Map<String, dynamic>> labAutoScan(String symbol, int topN) =>
      _postLab('/api/lab/auto-scan', <String, dynamic>{
        'symbol': symbol,
        'top_n': topN,
      }, timeoutSeconds: 120);

  /// Multi-component next-move ensemble for a symbol.
  Future<Map<String, dynamic>> labPredictEnsemble(String symbol) =>
      _getJson('/api/lab/predict-ensemble/$symbol');

  /// Heuristic crash-risk gauge for a symbol.
  Future<Map<String, dynamic>> labCrash(String symbol) =>
      _getJson('/api/lab/crash/$symbol');
}

// ---------------------------------------------------------------------------
// Gate: profile selection / login (server URL + personal token)
// ---------------------------------------------------------------------------

class ProfileGatePage extends StatefulWidget {
  const ProfileGatePage({super.key});

  @override
  State<ProfileGatePage> createState() => _ProfileGatePageState();
}

class _ProfileGatePageState extends State<ProfileGatePage> {
  // flutter_secure_storage v9: Android Keystore-backed encrypted
  // SharedPreferences is the platform default — no options needed.
  final FlutterSecureStorage _storage = const FlutterSecureStorage();
  late final ProfileStore _store = ProfileStore(_storage);
  List<ServerProfile> _profiles = <ServerProfile>[];
  String? _activeId;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final profiles = await _store.loadProfiles();
    final active = await _store.loadActiveId();
    if (!mounted) {
      return;
    }
    setState(() {
      _profiles = profiles;
      _activeId = active;
      _loading = false;
    });
    if (profiles.isEmpty) {
      await _openModeChoice();
    } else if (active != null && profiles.any((p) => p.id == active)) {
      if (!mounted) {
        return;
      }
      Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
        builder: (_) => DashboardPage(
          profile: profiles.firstWhere((p) => p.id == active),
        ),
      ));
    }
  }

  /// v4.0 (P2/C1): first-run + add-profile flow — the login (2FA),
  /// cloud and local options plus the advanced manual-token path.
  /// The choice is persisted and changeable at any time (adding a
  /// profile of the other kind).
  Future<void> _openModeChoice() async {
    final String? mode = await showDialog<String>(
      context: context,
      builder: (_) => const ModeChoiceDialog(),
    );
    if (mode == null) {
      return;
    }
    if (mode == 'advanced') {
      await _openEditor(initial: null);
      return;
    }
    if (mode == 'login') {
      // v1.5.0: email + password + TOTP (2FA) login — no session is
      // issued without the authenticator code.
      final Map<String, dynamic>? result =
          await showDialog<Map<String, dynamic>>(
        context: context,
        builder: (_) => const LoginPairingFormDialog(),
      );
      if (result == null) {
        return;
      }
      await _saveProfile(ServerProfile(
        id: DateTime.now().microsecondsSinceEpoch.toRadixString(36),
        label: (result['email'] as String?) ?? 'logged-in user',
        serverUrl: result['url'] as String,
        token: result['token'] as String,
        isLocal: (result['url'] as String).startsWith('http://'),
        email: result['email'] as String?,
        role: result['role'] as String?,
        authKind: 'session',
      ));
      return;
    }
    await _store.saveOnboardingMode(mode);
    if (!mounted) {
      return;
    }
    final ServerProfile? saved = await showDialog<ServerProfile>(
      context: context,
      builder: (_) => mode == 'local'
          ? LocalPairingFormDialog(store: _store)
          : const CloudPairingFormDialog(),
    );
    if (saved != null) {
      await _saveProfile(saved);
    }
  }

  /// Shared persistence: keep every profile, exactly one active (P6 —
  /// switching/adding NEVER deletes profiles, tokens, or state).
  Future<void> _saveProfile(ServerProfile saved) async {
    final next = List<ServerProfile>.from(_profiles)
      ..removeWhere((p) => p.id == saved.id)
      ..add(saved);
    await _store.saveProfiles(next);
    await _store.saveActiveId(saved.id);
    if (!mounted) {
      return;
    }
    setState(() {
      _profiles = next;
      _activeId = saved.id;
    });
    Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
      builder: (_) => DashboardPage(profile: saved),
    ));
  }

  Future<void> _openEditor({ServerProfile? initial}) async {
    final saved = await showDialog<ServerProfile>(
      context: context,
      builder: (_) => ProfileEditDialog(initial: initial),
    );
    if (saved == null) {
      return;
    }
    await _saveProfile(saved);
  }

  Future<void> _activate(ServerProfile profile) async {
    await _store.saveActiveId(profile.id);
    if (!mounted) {
      return;
    }
    Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
      builder: (_) => DashboardPage(profile: profile),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('AI Trading Lab — Servers'),
        actions: <Widget>[
          IconButton(
            icon: const Icon(Icons.add),
            tooltip: 'Add server profile (cloud or local)',
            onPressed: () => _openModeChoice(),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _profiles.isEmpty
              ? _EmptyProfiles(onAdd: () => _openModeChoice())
              : ListView(
                  children: _profiles
                      .map((p) => ListTile(
                            leading: Icon(
                              p.id == _activeId
                                  ? Icons.radio_button_checked
                                  : Icons.radio_button_off,
                            ),
                            title: Text(p.label),
                            subtitle: Text(p.isLocal
                                ? '${p.serverUrl}  ·  LOCAL${p.email != null && p.email!.isNotEmpty ? '  ·  ${p.email}' : ''}'
                                : '${p.serverUrl}  ·  CLOUD'),
                            onTap: () => _activate(p),
                            trailing: IconButton(
                              icon: const Icon(Icons.edit),
                              onPressed: () => _openEditor(initial: p),
                            ),
                          ))
                      .toList(),
                ),
    );
  }
}

class _EmptyProfiles extends StatelessWidget {
  const _EmptyProfiles({required this.onAdd});

  final Future<void> Function() onAdd;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            const Icon(Icons.dns_outlined, size: 56),
            const SizedBox(height: 12),
            Text(
              'No server profiles yet.\n'
              'Connect a CLOUD server (https) or pair with the\n'
              'engine on your LOCAL Windows computer.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              icon: const Icon(Icons.add),
              label: const Text('Add server profile'),
              onPressed: () => onAdd(),
            ),
          ],
        ),
      ),
    );
  }
}

class ProfileEditDialog extends StatefulWidget {
  const ProfileEditDialog({required this.initial, super.key});

  final ServerProfile? initial;

  @override
  State<ProfileEditDialog> createState() => _ProfileEditDialogState();
}

class _ProfileEditDialogState extends State<ProfileEditDialog> {
  late final TextEditingController _label =
      TextEditingController(text: widget.initial?.label ?? '');
  late final TextEditingController _url =
      TextEditingController(text: widget.initial?.serverUrl ?? '');
  late final TextEditingController _token =
      TextEditingController(text: widget.initial?.token ?? '');
  late final TextEditingController _email =
      TextEditingController(text: widget.initial?.email ?? '');
  bool _isLocal = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    // `widget` cannot be referenced in a field initializer (Dart
    // analyzer: implicit_this_reference_in_initializer) — initialize
    // the per-profile transport flag here instead.
    _isLocal = widget.initial?.isLocal ?? false;
  }

  @override
  void dispose() {
    _label.dispose();
    _url.dispose();
    _token.dispose();
    _email.dispose();
    super.dispose();
  }

  void _save() {
    final label = _label.text.trim();
    final rawUrl = _url.text.trim();
    final token = _token.text.trim();
    final email = _email.text.trim();
    if (label.isEmpty) {
      setState(() => _error = 'a profile label is required');
      return;
    }
    if (token.length < 16) {
      setState(() => _error = 'token looks too short (>= 16 chars)');
      return;
    }
    String url;
    try {
      // v4.0: per-profile transport policy — a LOCAL profile may use
      // http:// on the user's own LAN; a CLOUD profile never can.
      url = EngineApiClient.normalizeServerUrl(rawUrl, isLocal: _isLocal);
    } on ApiException catch (exc) {
      setState(() => _error = exc.message);
      return;
    }
    if (_isLocal && email.isNotEmpty && !email.contains('@')) {
      setState(() => _error = 'enter a valid email (identity only — no sign-in happens)');
      return;
    }
    Navigator.of(context).pop(ServerProfile(
      id: widget.initial?.id ??
          DateTime.now().microsecondsSinceEpoch.toRadixString(36),
      label: label,
      serverUrl: url,
      token: token,
      isLocal: _isLocal,
      email: _isLocal && email.isNotEmpty ? email : null,
    ));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(
          widget.initial == null ? 'Add your server' : 'Edit server profile'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          TextField(
            controller: _label,
            decoration: const InputDecoration(
              labelText: 'Label (e.g. alice-primary)',
            ),
          ),
          TextField(
            controller: _url,
            keyboardType: TextInputType.url,
            decoration: InputDecoration(
              labelText: _isLocal
                  ? 'PC address (http://… or 127.0.0.1)'
                  : 'Server URL (https://…)',
              hintText: _isLocal ? 'http://192.168.1.5:8018' : 'https://engine.example.com',
            ),
          ),
          TextField(
            controller: _token,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'Personal token',
              helperText: 'stored in secure storage only',
            ),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text(
                'Local computer profile (http allowed on my own LAN)'),
            value: _isLocal,
            onChanged: (value) => setState(() => _isLocal = value),
          ),
          if (_isLocal)
            TextField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                labelText: 'Email (identity only, optional here)',
              ),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                _error!,
                style:
                    TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
        ],
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(onPressed: _save, child: const Text('Save')),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// v4.0 dual-mode onboarding dialogs (P2/P3/P4/C1–C4)
// ---------------------------------------------------------------------------

/// First screen of the flow: EXACTLY two options (P2) + the advanced
/// manual-token escape (C4). The returned string is 'cloud', 'local',
/// 'advanced', or null (dismissed).
class ModeChoiceDialog extends StatelessWidget {
  const ModeChoiceDialog({super.key});

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('How will you run?'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          const Text(
            'Cloud needs your own server (https). Local pairs with the '
            'engine on your Windows PC — rent nothing.',
          ),
          const SizedBox(height: 14),
          FilledButton.icon(
            icon: const Icon(Icons.badge_outlined),
            label: const Text('EMAIL LOGIN (2FA)'),
            onPressed: () => Navigator.of(context).pop('login'),
          ),
          const SizedBox(height: 10),
          FilledButton.icon(
            icon: const Icon(Icons.cloud_outlined),
            label: const Text('CLOUD SERVER'),
            onPressed: () => Navigator.of(context).pop('cloud'),
          ),
          const SizedBox(height: 10),
          FilledButton.icon(
            icon: const Icon(Icons.computer),
            label: const Text('LOCAL COMPUTER'),
            onPressed: () => Navigator.of(context).pop('local'),
          ),
        ],
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop('advanced'),
          child: const Text('Advanced: paste token manually'),
        ),
      ],
    );
  }
}

/// Cloud onboarding (P3/C2): Name + Server URL + Invitation Code —
/// all compulsory. Strict TLS-only normalization; the invitation
/// code is sent ONCE to POST /api/pair and never stored.
class CloudPairingFormDialog extends StatefulWidget {
  const CloudPairingFormDialog({super.key});

  @override
  State<CloudPairingFormDialog> createState() => _CloudPairingFormDialogState();
}

class _CloudPairingFormDialogState extends State<CloudPairingFormDialog> {
  final TextEditingController _name = TextEditingController();
  final TextEditingController _url = TextEditingController();
  final TextEditingController _code = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _url.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _pair() async {
    final name = _name.text.trim();
    final rawUrl = _url.text.trim();
    final code = _code.text.trim();
    if (name.isEmpty || rawUrl.isEmpty || code.isEmpty) {
      setState(() => _error =
          'name, server URL and invitation code are all required');
      return;
    }
    String url;
    try {
      url = EngineApiClient.normalizeServerUrl(rawUrl, isLocal: false);
    } on ApiException catch (exc) {
      setState(() => _error = exc.message);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final token = await pairWithEngine(
        baseUri: Uri.parse(url),
        name: name,
        email: '',
        invitationCode: code,
        mode: 'cloud',
      );
      if (!mounted) {
        return;
      }
      Navigator.of(context).pop(ServerProfile(
        id: DateTime.now().microsecondsSinceEpoch.toRadixString(36),
        label: name,
        serverUrl: url,
        token: token,
        isLocal: false,
      ));
    } on PairingException catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _error = exc.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Connect your cloud server'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          TextField(
            controller: _name,
            decoration: const InputDecoration(
                labelText: 'Name (e.g. alice-primary)'),
          ),
          TextField(
            controller: _url,
            keyboardType: TextInputType.url,
            decoration: const InputDecoration(
              labelText: 'Server URL (https://…)',
              hintText: 'https://engine.example.com',
            ),
          ),
          TextField(
            controller: _code,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'Invitation code (owner-issued, compulsory)',
              helperText: 'sent once — never stored',
            ),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                _error!,
                style:
                    TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          if (_busy)
            const Padding(
              padding: EdgeInsets.only(top: 10),
              child: LinearProgressIndicator(),
            ),
        ],
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _busy ? null : _pair,
          child: const Text('Pair'),
        ),
      ],
    );
  }
}

/// Local onboarding (P4/C3): Name + Gmail/email + Invitation Code +
/// PC address (mDNS auto-discovered with manual fallback; 127.0.0.1
/// allowed for same-device). http:// is permitted ONLY via the
/// per-profile isLocal flag, after a one-time honest unencrypted-LAN
/// warning. The email is identity-only (P7) — no OAuth, no sign-in.
class LocalPairingFormDialog extends StatefulWidget {
  const LocalPairingFormDialog({required this.store, this.discoverHost, super.key});

  final ProfileStore store;

  /// Test seam: injectable mDNS discovery (defaults to the real LAN
  /// lookup). Tests inject an offline double for determinism.
  final Future<String?> Function()? discoverHost;

  @override
  State<LocalPairingFormDialog> createState() => _LocalPairingFormDialogState();
}

class _LocalPairingFormDialogState extends State<LocalPairingFormDialog> {
  final TextEditingController _name = TextEditingController();
  final TextEditingController _email = TextEditingController();
  final TextEditingController _code = TextEditingController();
  final TextEditingController _pc = TextEditingController();
  bool _busy = false;
  bool _searching = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_prefillFromMdns());
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _code.dispose();
    _pc.dispose();
    super.dispose();
  }

  Future<void> _prefillFromMdns() async {
    final discover = widget.discoverHost ?? discoverMonitorHost;
    final host = await discover();
    if (!mounted) {
      return;
    }
    setState(() {
      _searching = false;
      if (host != null && _pc.text.isEmpty) {
        _pc.text = host;
      }
    });
  }

  Future<void> _pair() async {
    final name = _name.text.trim();
    final email = _email.text.trim();
    final code = _code.text.trim();
    final pc = _pc.text.trim();
    if (name.isEmpty || email.isEmpty || code.isEmpty || pc.isEmpty) {
      setState(() => _error =
          'name, email, invitation code and PC address are all required');
      return;
    }
    if (!email.contains('@')) {
      setState(() => _error =
          'enter a valid email (identity only — no sign-in happens)');
      return;
    }
    final String url;
    try {
      url = EngineApiClient.normalizeServerUrl(pc, isLocal: true);
    } on ApiException catch (exc) {
      setState(() => _error = exc.message);
      return;
    }

    // One-time honest warning (C3): LAN traffic is unencrypted outside
    // the host PC. Acknowledgement persists; the warning never blocks
    // cloud profiles.
    final acknowledged = await widget.store.localLanWarningAcknowledged();
    if (!acknowledged) {
      if (!mounted) {
        return;
      }
      final ok = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Unencrypted LAN traffic'),
          content: const Text(
            'Local mode talks to your PC over plain http on this '
            'network. Traffic between this phone and your PC is '
            'UNENCRYPTED outside the PC itself. Use this only on a '
            'network you trust. Cloud mode (https) stays encrypted '
            'end-to-end through your server certificate.',
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('CANCEL'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('I UNDERSTAND'),
            ),
          ],
        ),
      );
      if (ok != true) {
        return;
      }
      await widget.store.acknowledgeLocalLanWarning();
    }

    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final token = await pairWithEngine(
        baseUri: Uri.parse(url),
        name: name,
        email: email,
        invitationCode: code,
        mode: 'local',
      );
      if (!mounted) {
        return;
      }
      Navigator.of(context).pop(ServerProfile(
        id: DateTime.now().microsecondsSinceEpoch.toRadixString(36),
        label: name,
        serverUrl: url,
        token: token,
        isLocal: true,
        email: email,
      ));
    } on PairingException catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _error = exc.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Pair with your Windows PC'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            TextField(
              controller: _name,
              decoration: const InputDecoration(
                  labelText: 'Name (e.g. my-desktop)'),
            ),
            TextField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                labelText: 'Gmail / email (identity only, compulsory)',
                helperText: 'audit identity — no sign-in, no OAuth',
              ),
            ),
            TextField(
              controller: _pc,
              keyboardType: TextInputType.url,
              decoration: InputDecoration(
                labelText: 'PC address (auto-detected via mDNS)',
                hintText: '192.168.1.5:8018 or 127.0.0.1:8018',
                helperText: _searching
                    ? 'searching your network for the engine…'
                    : 'auto-fill or type it manually',
              ),
            ),
            TextField(
              controller: _code,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'Invitation code (compulsory)',
                helperText: 'sent once — never stored',
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  _error!,
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            if (_busy)
              const Padding(
                padding: EdgeInsets.only(top: 10),
                child: LinearProgressIndicator(),
              ),
          ],
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _busy ? null : _pair,
          child: const Text('Pair'),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Dashboard: health, positions, PnL, risk, feed, alerts + kill switch
// ---------------------------------------------------------------------------

class DashboardPage extends StatefulWidget {
  const DashboardPage({required this.profile, super.key});

  final ServerProfile profile;

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  late final EngineApiClient _client = EngineApiClient(
    serverUrl: widget.profile.serverUrl,
    token: widget.profile.token,
    // v1.0.0: self-reported identity for the engine's owner surfaces
    clientName: widget.profile.label,
    clientEmail: widget.profile.email ?? '',
    clientKind: 'monitor',
  );
  Timer? _timer;
  Map<String, dynamic>? _health;
  dynamic _positions;
  dynamic _pnl;
  Map<String, dynamic>? _risk;
  Map<String, dynamic>? _feed;
  Map<String, dynamic>? _stats;
  String? _error;
  bool _busy = false;

  /// v1.5.0: admin flag — true for the owner pairing token or an
  /// admin-role session; drives the Users button (other users).
  bool _isAdmin = false;

  @override
  void initState() {
    super.initState();
    _refresh();
    _loadRole();
    // v4.0.2: 15 s poll cadence (was 10 s) — halves the request rate so
    // the dashboard sits comfortably under the server's rate limit
    // while staying responsive for a monitoring surface.
    _timer = Timer.periodic(const Duration(seconds: 15), (_) => _refresh());
  }

  Future<void> _loadRole() async {
    // paired (token) profiles are owner-level; session profiles carry
    // their own role — /api/auth/me is the single source of truth.
    bool admin = widget.profile.isAdmin;
    try {
      final me = await _client.authMe();
      final role = (me['role'] ?? '').toString();
      admin = role == 'admin' || role == 'owner';
    } on ApiException {
      // keep the profile-derived fallback (older engine: pairing only)
    }
    if (!mounted) {
      return;
    }
    setState(() => _isAdmin = admin);
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  /// v4.0 (P6): switch server profile — returns to the profile list,
  /// keeping EVERY profile, token, and preference (nothing is deleted).
  Future<void> _switchProfile() async {
    final store = ProfileStore(const FlutterSecureStorage());
    await store.saveActiveId(null); // clears only the ACTIVE pointer
    if (!mounted) {
      return;
    }
    Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
      builder: (_) => const ProfileGatePage(),
    ));
  }

  Future<void> _refresh() async {
    if (_busy) {
      return;
    }
    _busy = true;
    try {
      final health = await _client.health();
      final positions = await _client.positions();
      final pnl = await _client.pnl();
      final risk = await _client.risk();
      final feed = await _client.feed();
      // v1.0.0: the trade-stats fetch is deliberately NON-FATAL — an
      // older engine (or an unwired surface) must not break the main
      // dashboard refresh; the chart card keeps its last state.
      Map<String, dynamic>? stats;
      try {
        stats = await _client.ledgerStats();
      } on ApiException {
        stats = _stats;
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _health = health;
        _positions = positions;
        _pnl = pnl;
        _risk = risk;
        _feed = feed;
        _stats = stats;
        _error = null;
      });
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() => _error = exc.toString());
    } on TimeoutException {
      if (!mounted) {
        return;
      }
      setState(() => _error = 'timeout — server unreachable');
    } catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() => _error = 'connection error (${exc.runtimeType})');
    } finally {
      _busy = false;
    }
  }

  List<String> get _alerts {
    final List<String> alerts = <String>[];
    final health = _health;
    if (health != null) {
      final kill = (health['kill_switch'] ?? '').toString().toUpperCase();
      if (kill.contains('ACTIVE')) {
        alerts.add('KILL SWITCH ACTIVE — trading halted');
      }
    }
    final risk = _risk;
    if (risk != null) {
      final state = (risk['state'] ?? risk['risk_state'] ?? '').toString();
      if (RegExp(r'VIOLATION|HALT|BREACH', caseSensitive: false)
          .hasMatch(state)) {
        alerts.add('RISK STATE: $state');
      }
    }
    final feed = _feed;
    if (feed != null) {
      final state = (feed['state'] ?? feed['health'] ?? '').toString();
      if (RegExp(r'STALE|ERROR|FAIL', caseSensitive: false).hasMatch(state)) {
        alerts.add('FEED: $state');
      }
    }
    if (_error != null) {
      alerts.add('CONNECTION: $_error');
    }
    return alerts;
  }

  Future<void> _confirmKillSwitch() async {
    final reasonController = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Activate KILL SWITCH?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Text(
              'This HALTS trading on your server immediately.\n'
              'It is the LAST-resort safety action.\n\n'
              'Type a reason (required, audited):',
            ),
            TextField(
              controller: reasonController,
              maxLines: 2,
              decoration: const InputDecoration(hintText: 'reason'),
            ),
          ],
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('CANCEL'),
          ),
          FilledButton.tonalIcon(
            icon: const Icon(Icons.warning_amber),
            label: const Text('ACTIVATE KILL SWITCH'),
            onPressed: () {
              if (reasonController.text.trim().isEmpty) {
                ScaffoldMessenger.of(dialogContext).showSnackBar(
                  const SnackBar(content: Text('a reason is required')),
                );
                return;
              }
              Navigator.of(dialogContext).pop(true);
            },
          ),
        ],
      ),
    );
    if (confirmed != true) {
      return;
    }
    try {
      await _client.activateKillSwitch(reasonController.text.trim());
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('kill switch ACTIVATED')),
      );
      await _refresh();
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('refused: ${exc.message}')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final health = _health;
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.profile.label),
        actions: <Widget>[
          IconButton(
            icon: const Icon(Icons.swap_horiz),
            tooltip: 'Switch server profile (cloud/local)',
            onPressed: _switchProfile,
          ),
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh),
          if (_isAdmin)
            IconButton(
              icon: const Icon(Icons.groups),
              tooltip: 'Users (who is connected, all accounts)',
              onPressed: () =>
                  Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => UsersPage(client: _client),
              )),
            ),
          IconButton(
            icon: const Icon(Icons.list_alt),
            tooltip: 'Recent audit events',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => EventsPage(client: _client),
            )),
          ),
          IconButton(
            icon: const Icon(Icons.receipt_long),
            tooltip: 'Trade ledger (which trades, what profit)',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => TradesPage(client: _client),
            )),
          ),
          IconButton(
            icon: const Icon(Icons.science_outlined),
            tooltip: 'AI Lab (assistant, strategies, predict)',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => LabPage(client: _client),
            )),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.all(12),
          children: <Widget>[
            Text(
              '${widget.profile.serverUrl}  ·  '
              '${widget.profile.isLocal ? 'LOCAL mode — unencrypted LAN' : 'CLOUD — https'}'
              '${widget.profile.email != null && widget.profile.email!.isNotEmpty ? '  ·  ${widget.profile.email}' : ''}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            if (_alerts.isNotEmpty)
              ..._alerts.map((a) => Card(
                    color: Theme.of(context).colorScheme.errorContainer,
                    child: ListTile(
                      leading: const Icon(Icons.warning_amber),
                      title: Text(a),
                    ),
                  )),
            _card('Engine health', <String, String>{
              'mode': '${health?['engine_mode'] ?? '?'}',
              'state': '${health?['engine_state'] ?? '?'}',
              'version': '${health?['engine_version'] ?? '?'}',
              'uptime': '${health?['uptime_seconds'] ?? '?'} s',
              'kill switch': '${health?['kill_switch'] ?? '?'}',
            }),
            _card('Risk', <String, String>{
              'state': '${_risk?['state'] ?? _risk?['risk_state'] ?? '?'}',
              'detail': '${_risk?['detail'] ?? ''}',
            }),
            _card('Feed', <String, String>{
              'state': '${_feed?['state'] ?? _feed?['health'] ?? '?'}',
            }),
            _card('PnL', _pnl is Map<String, dynamic>
                ? (_pnl as Map<String, dynamic>)
                    .map((k, v) => MapEntry('$k', '$v'))
                : <String, String>{'value': '$_pnl'}),
            TradesChartCard(stats: _stats),
            _positionsCard(),
            const SizedBox(height: 12),
            FilledButton.tonalIcon(
              style: FilledButton.styleFrom(
                backgroundColor: Theme.of(context).colorScheme.errorContainer,
              ),
              icon: const Icon(Icons.stop_circle_outlined),
              label: const Text('STOP TRADING (KILL SWITCH)\nconfirmation + reason required'),
              onPressed: _confirmKillSwitch,
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _card(String title, Map<String, String> rows) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(title,
                style: Theme.of(context)
                    .textTheme
                    .titleSmall
                    ?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            ...rows.entries.map((e) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: <Widget>[
                      Text(e.key, style: Theme.of(context).textTheme.bodySmall),
                      Flexible(child: Text(e.value)),
                    ],
                  ),
                )),
          ],
        ),
      ),
    );
  }

  Widget _positionsCard() {
    final positions = _positions;
    if (positions is List && positions.isEmpty) {
      return _card('Positions', <String, String>{'open positions': '0'});
    }
    if (positions is List) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('Positions (${positions.length})',
                  style: Theme.of(context).textTheme.titleSmall),
              ...positions.take(10).map((dynamic p) => Text('$p')),
            ],
          ),
        ),
      );
    }
    return _card('Positions', <String, String>{'state': '$positions'});
  }
}

class EventsPage extends StatefulWidget {
  const EventsPage({required this.client, super.key});

  final EngineApiClient client;

  @override
  State<EventsPage> createState() => _EventsPageState();
}

class _EventsPageState extends State<EventsPage> {
  List<Map<String, dynamic>>? _events;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final events = await widget.client.events();
      if (!mounted) {
        return;
      }
      setState(() {
        _events = events;
        _error = null;
      });
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() => _error = exc.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final events = _events;
    return Scaffold(
      appBar: AppBar(title: const Text('Recent audit events')),
      body: _error != null
          ? Center(child: Text(_error!))
          : events == null
              ? const Center(child: CircularProgressIndicator())
              : events.isEmpty
                  ? const Center(child: Text('no events'))
                  : ListView.builder(
                      itemCount: events.length,
                      itemBuilder: (context, index) {
                        final event = events[index];
                        return ListTile(
                          dense: true,
                          title: Text(
                              '${event['decision'] ?? event['event'] ?? event['actor'] ?? 'event'}'),
                          subtitle: Text(
                              '${event['actor'] ?? ''} ${event['path'] ?? ''} ${event['rule'] ?? ''}'),
                        );
                      },
                    ),
    );
  }
}

// ---------------------------------------------------------------------------
// v1.0.0 (owner mandate): trades mini chart + per-trade ledger page
// ---------------------------------------------------------------------------

/// Compact "trades by instrument" card on the dashboard — the answer
/// to "sab se jyada trades kis pe liye". Hand-rolled CustomPainter
/// (NO new dependencies): top symbols as horizontal bars, plus the
/// total-PnL line. An empty ledger is shown HONESTLY (monitor-only
/// mode trades nothing; the chart fills when a session trades).
class TradesChartCard extends StatelessWidget {
  const TradesChartCard({required this.stats, super.key});

  final Map<String, dynamic>? stats;

  @override
  Widget build(BuildContext context) {
    final Map<String, dynamic> data = stats ?? const <String, dynamic>{};
    final int total = (data['total_trades'] as num?)?.toInt() ?? 0;
    final double pnl = (data['total_pnl'] as num?)?.toDouble() ?? 0.0;
    final Map<String, dynamic> perSymbol =
        (data['per_symbol'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final sorted = perSymbol.entries.toList()
      ..sort((a, b) => (b.value as num).compareTo(a.value as num));
    final top = sorted.take(6).toList();
    final maxCount =
        top.isEmpty ? 1 : (top.first.value as num).toDouble().clamp(1, 1e9);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: <Widget>[
                Text('Trades by instrument',
                    style: Theme.of(context)
                        .textTheme
                        .titleSmall
                        ?.copyWith(fontWeight: FontWeight.bold)),
                Text(
                  'total $total · PnL ${pnl.toStringAsFixed(2)}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
            const SizedBox(height: 10),
            if (total == 0)
              Text(
                'No trades yet — the ledger fills when a trading '
                'session records fills (monitor-only mode trades '
                'nothing; honest empty state).',
                style: Theme.of(context).textTheme.bodySmall,
              )
            else
              ...top.map((entry) {
                final count = (entry.value as num).toDouble();
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(
                    children: <Widget>[
                      SizedBox(
                        width: 86,
                        child: Text(
                          entry.key,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                      Expanded(
                        child: _BarTrack(
                          fraction: count / maxCount,
                          highlight: identical(entry, top.first),
                        ),
                      ),
                      SizedBox(
                        width: 30,
                        child: Text(
                          '${entry.value}',
                          textAlign: TextAlign.end,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                    ],
                  ),
                );
              }),
            if (sorted.length > 6)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('+${sorted.length - 6} more instruments',
                    style: Theme.of(context).textTheme.bodySmall),
              ),
          ],
        ),
      ),
    );
  }
}

class _BarTrack extends StatelessWidget {
  const _BarTrack({required this.fraction, required this.highlight});

  final double fraction;
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    final Color base = Theme.of(context).colorScheme.primary;
    final Color color = highlight
        ? base
        : base.withAlpha((255 * 0.55).round());
    return SizedBox(
      height: 10,
      child: CustomPaint(
        painter: _BarPainter(
          color: color,
          fraction: fraction.clamp(0.0, 1.0),
        ),
      ),
    );
  }
}

class _BarPainter extends CustomPainter {
  _BarPainter({required this.color, required this.fraction});

  final Color color;
  final double fraction;

  @override
  void paint(Canvas canvas, Size size) {
    final Radius radius = Radius.circular(size.height / 2);
    final Rect full = Rect.fromLTWH(0, 0, size.width, size.height);
    canvas.drawRRect(
      RRect.fromRectAndRadius(full, radius),
      Paint()..color = color.withAlpha((255 * 0.14).round()),
    );
    if (fraction > 0) {
      final Rect fill = Rect.fromLTWH(0, 0, size.width * fraction, size.height);
      canvas.drawRRect(
        RRect.fromRectAndRadius(fill, radius),
        Paint()..color = color,
      );
    }
  }

  @override
  bool shouldRepaint(_BarPainter oldDelegate) =>
      oldDelegate.fraction != fraction || oldDelegate.color != color;
}

/// v1.0.0: the per-trade ledger page — "kis pe trade li, kitna
/// profit hua". Most recent first (server-bounded), realized PnL
/// color-coded green/red, honest empty state.
class TradesPage extends StatefulWidget {
  const TradesPage({required this.client, super.key});

  final EngineApiClient client;

  @override
  State<TradesPage> createState() => _TradesPageState();
}

class _TradesPageState extends State<TradesPage> {
  List<Map<String, dynamic>>? _trades;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final trades = await widget.client.tradeLedger();
      if (!mounted) {
        return;
      }
      setState(() {
        _trades = trades;
        _error = null;
      });
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() => _error = exc.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final trades = _trades;
    return Scaffold(
      appBar: AppBar(title: const Text('Trade ledger')),
      body: _error != null
          ? Center(child: Text(_error!))
          : trades == null
              ? const Center(child: CircularProgressIndicator())
              : trades.isEmpty
                  ? const Center(
                      child: Text(
                        'No trades recorded yet.\n'
                        'The ledger fills when a trading session runs '
                        '(monitor-only mode trades nothing).',
                        textAlign: TextAlign.center,
                      ),
                    )
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.builder(
                        itemCount: trades.length,
                        itemBuilder: (context, index) {
                          final trade = trades[index];
                          final dynamic pnl = trade['pnl'];
                          final String pnlText = pnl is num
                              ? (pnl as num).toStringAsFixed(2)
                              : 'open';
                          final Color pnlColor = pnl is num
                              ? ((pnl as num) >= 0
                                  ? Colors.greenAccent
                                  : Colors.redAccent)
                              : Colors.white54;
                          return ListTile(
                            dense: true,
                            leading: Icon(
                              '${trade['side'] ?? ''}' == 'BUY'
                                  ? Icons.arrow_downward
                                  : Icons.arrow_upward,
                              color: '${trade['side'] ?? ''}' == 'BUY'
                                  ? Colors.greenAccent
                                  : Colors.redAccent,
                            ),
                            title: Text(
                              '${trade['side'] ?? '?'} '
                              '${trade['quantity'] ?? '?'} '
                              '${trade['symbol'] ?? '?'} @ '
                              '${trade['price'] ?? '?'}',
                            ),
                            subtitle: Text(
                              '${trade['ts'] ?? ''}'
                              '${'${trade['strategy'] ?? ''}'.isNotEmpty ? '  ·  ${trade['strategy']}' : ''}',
                              overflow: TextOverflow.ellipsis,
                            ),
                            trailing: Text(
                              'PnL $pnlText',
                              style: TextStyle(
                                color: pnlColor,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}

// ---------------------------------------------------------------------------
// v1.1.0 OWNER AI LAB — Assistant / Strategies / Predict
// ---------------------------------------------------------------------------

class LabPage extends StatelessWidget {
  const LabPage({required this.client, super.key});

  final EngineApiClient client;

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('AI Lab (offline, ledger-backed)'),
          bottom: const TabBar(
            tabs: <Widget>[
              Tab(text: 'Assistant'),
              Tab(text: 'Strategies'),
              Tab(text: 'Predict'),
            ],
          ),
        ),
        body: TabBarView(
          children: <Widget>[
            AssistantTab(client: client),
            StrategiesTab(client: client),
            PredictTab(client: client),
          ],
        ),
      ),
    );
  }
}

String _labString(Map<String, dynamic> map, String key, String fallback) {
  final value = map[key];
  if (value == null) {
    return fallback;
  }
  final text = '$value';
  return text.isEmpty ? fallback : text;
}

class AssistantTab extends StatefulWidget {
  const AssistantTab({required this.client, super.key});

  final EngineApiClient client;

  @override
  State<AssistantTab> createState() => _AssistantTabState();
}

class _AssistantTabState extends State<AssistantTab> {
  final List<Map<String, String>> _thread = <Map<String, String>>[];
  final TextEditingController _input = TextEditingController();
  bool _busy = false;

  static const List<String> _suggestions = <String>[
    'total profit',
    'win rate',
    'best symbol',
    'who is logged in',
    'is trading stopped?',
    'help',
  ];

  Future<void> _ask(String question) async {
    final text = question.trim();
    if (text.isEmpty || _busy) {
      return;
    }
    setState(() {
      _busy = true;
      _thread.add(<String, String>{'role': 'you', 'text': text});
      _input.clear();
    });
    try {
      final reply = await widget.client.labAsk(text);
      if (!mounted) {
        return;
      }
      setState(() {
        _thread.add(<String, String>{
          'role': 'assistant',
          'text': _labString(reply, 'answer', '(empty answer)'),
        });
      });
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() {
        _thread.add(<String, String>{
          'role': 'assistant',
          'text': 'refused: ${exc.message}',
        });
      });
    } on TimeoutException {
      if (!mounted) {
        return;
      }
      setState(() {
        _thread.add(<String, String>{
          'role': 'assistant',
          'text': 'timeout — server unreachable',
        });
      });
    } catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() {
        _thread.add(<String, String>{
          'role': 'assistant',
          'text': 'connection error (${exc.runtimeType})',
        });
      });
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 8, 8, 0),
          child: Wrap(
            spacing: 6,
            children: _suggestions
                .map((s) => ActionChip(
                      label: Text(s),
                      onPressed: () => _ask(s),
                    ))
                .toList(),
          ),
        ),
        Expanded(
          child: _thread.isEmpty
              ? const Center(
                  child: Text(
                    'Ask about YOUR ledgers:\nprofit, trades, symbols, '
                    'users, STOP state.\nNo external AI, nothing invented.',
                    textAlign: TextAlign.center,
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.all(8),
                  children: _thread.map((m) {
                    final mine = m['role'] == 'you';
                    return Align(
                      alignment: mine
                          ? Alignment.centerRight
                          : Alignment.centerLeft,
                      child: Container(
                        margin: const EdgeInsets.symmetric(vertical: 3),
                        padding: const EdgeInsets.all(10),
                        constraints: BoxConstraints(
                          maxWidth: MediaQuery.of(context).size.width * 0.85,
                        ),
                        decoration: BoxDecoration(
                          color: mine
                              ? Theme.of(context).colorScheme.primaryContainer
                              : Theme.of(context)
                                  .colorScheme
                                  .surfaceVariant,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: SelectableText(m['text'] ?? ''),
                      ),
                    );
                  }).toList(),
                ),
        ),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: TextField(
                    controller: _input,
                    enabled: !_busy,
                    onSubmitted: _ask,
                    decoration: const InputDecoration(
                      hintText: 'e.g. BTC/USD pe kitna profit',
                      isDense: true,
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                IconButton(
                  icon: _busy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.send),
                  onPressed: _busy ? null : () => _ask(_input.text),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class StrategiesTab extends StatefulWidget {
  const StrategiesTab({required this.client, super.key});

  final EngineApiClient client;

  @override
  State<StrategiesTab> createState() => _StrategiesTabState();
}

class _StrategiesTabState extends State<StrategiesTab> {
  List<Map<String, dynamic>> _rows = <Map<String, dynamic>>[];
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final rows = await widget.client.labStrategies();
      if (!mounted) {
        return;
      }
      setState(() {
        _rows = rows;
        _error = null;
      });
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() => _error = exc.message);
    } catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() => _error = 'connection error (${exc.runtimeType})');
    }
  }

  Future<void> _act(Future<Map<String, dynamic>> Function() action,
      String successLabel) async {
    if (_busy) {
      return;
    }
    setState(() => _busy = true);
    try {
      await action();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(successLabel)),
      );
      await _load();
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('refused: ${exc.message}')),
      );
    } catch (exc) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('connection error (${exc.runtimeType})')),
      );
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _createStrategy() async {
    final labelController = TextEditingController();
    final symbolController = TextEditingController(text: 'XAUUSD');
    final paramsController = TextEditingController();
    String kind = 'ema_trend';
    final created = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: const Text('New strategy'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                TextField(
                  controller: labelController,
                  decoration:
                      const InputDecoration(hintText: 'label (required)'),
                ),
                TextField(
                  controller: symbolController,
                  decoration: const InputDecoration(
                      hintText: 'symbol, e.g. XAUUSD or BTC/USD'),
                ),
                DropdownButtonFormField<String>(
                  value: kind,
                  items: const <DropdownMenuItem<String>>[
                    DropdownMenuItem<String>(
                        value: 'ema_trend', child: Text('EMA trend')),
                    DropdownMenuItem<String>(
                        value: 'ema_cross', child: Text('EMA cross')),
                    DropdownMenuItem<String>(
                        value: 'rsi_reversal', child: Text('RSI reversal')),
                    DropdownMenuItem<String>(
                        value: 'breakout', child: Text('Breakout')),
                  ],
                  onChanged: (value) =>
                      setDialogState(() => kind = value ?? kind),
                ),
                TextField(
                  controller: paramsController,
                  decoration: const InputDecoration(
                    hintText: 'params JSON, e.g. {"period": 50}',
                  ),
                ),
              ],
            ),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('CANCEL'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('CREATE'),
            ),
          ],
        ),
      ),
    );
    if (created != true) {
      return;
    }
    Map<String, dynamic> params = <String, dynamic>{};
    final rawParams = paramsController.text.trim();
    if (rawParams.isNotEmpty) {
      try {
        final decoded = jsonDecode(rawParams);
        if (decoded is Map<String, dynamic>) {
          params = decoded;
        } else {
          if (!mounted) {
            return;
          }
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('params must be a JSON object')),
          );
          return;
        }
      } on FormatException {
        if (!mounted) {
          return;
        }
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('params is not valid JSON')),
        );
        return;
      }
    }
    await _act(
      () => widget.client.labCreateStrategy(
        label: labelController.text.trim(),
        symbol: symbolController.text.trim(),
        kind: kind,
        params: params,
      ),
      'strategy created (SUBMITTED)',
    );
  }

  Future<void> _confirmActivation(String id, String label) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('CONFIRM strategy?'),
        content: Text(
          '"$label" ne backtest + paper validation pass kiya?\n\n'
          'YES = ACTIVATED for PAPER evaluation only.\n'
          'Live trading remains NOT AUTHORIZED (engine governance).',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('NO'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('YES — ACTIVATE (paper only)'),
          ),
        ],
      ),
    );
    if (confirmed != true) {
      await _act(
        () => widget.client.labConfirm(id, 'NO'),
        'stayed INACTIVE',
      );
      return;
    }
    await _act(
      () => widget.client.labConfirm(id, 'YES'),
      'ACTIVATED (paper evaluation only)',
    );
  }

  Color _stateColor(String state, ThemeData theme) {
    if (state == 'ACTIVATED') {
      return Colors.green.shade700;
    }
    if (state == 'REJECTED') {
      return theme.colorScheme.error;
    }
    if (state == 'VALIDATED') {
      return Colors.orange.shade700;
    }
    return theme.colorScheme.primary;
  }

  // -- v1.5.0: verified real data + presets + AUTO-SCAN --------------------

  Future<void> _importDataAndBootstrap() async {
    final symbolController = TextEditingController(text: 'BTCUSDT');
    final go = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Start paper trading (verified data)'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Text(
              '1. IMPORT real verified 1-minute history into the lab '
              '(bundled repo data first; Binance Vision website '
              'fallback — sha256-checked),\n'
              '2. CREATE the TOP-5 YouTuber presets and open their 30-day '
              'paper windows.\n\n'
              'Your explicit YES is still required later to activate any '
              'strategy (paper only; live stays NOT AUTHORIZED).',
            ),
            TextField(
              controller: symbolController,
              decoration: const InputDecoration(
                labelText: 'symbol (BTCUSDT / ETHUSDT ...)',
              ),
            ),
          ],
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('CANCEL'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('IMPORT + START'),
          ),
        ],
      ),
    );
    if (go != true) {
      return;
    }
    final symbol = symbolController.text.trim();
    if (symbol.isEmpty) {
      return;
    }
    if (_busy) {
      return;
    }
    setState(() => _busy = true);
    try {
      final imported = await widget.client.histImport(symbol);
      final bootstrapped = await widget.client.labBootstrap(symbol);
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'imported ${imported['imported']} verified bars '
            '(${imported['source_used']}); presets created: '
            '${(bootstrapped['created'] as List?)?.length ?? 0}, '
            'paper windows opened',
          ),
        ),
      );
      await _load();
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('refused: ${exc.message}')),
      );
    } catch (exc) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('connection error (${exc.runtimeType})')),
      );
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _autoScan() async {
    final symbolController = TextEditingController(text: 'BTCUSDT');
    final go = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('AUTO-SCAN strategies'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Text(
              'Deterministic parameter scan over all 9 strategy kinds '
              '(70/30 in-sample/out-of-sample, net of costs). The best '
              'survivors become ORDINARY submissions — your YES is still '
              'required.',
            ),
            TextField(
              controller: symbolController,
              decoration: const InputDecoration(labelText: 'symbol'),
            ),
          ],
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('CANCEL'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('SCAN'),
          ),
        ],
      ),
    );
    if (go != true) {
      return;
    }
    if (_busy) {
      return;
    }
    setState(() => _busy = true);
    try {
      final result = await widget.client
          .labAutoScan(symbolController.text.trim(), 3);
      if (!mounted) {
        return;
      }
      final created = (result['created'] as List?)?.length ?? 0;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'AUTO-SCAN: ${result['combinations_tested']} combos tested, '
            '${result['survivors']} survivors, $created submissions '
            'created (awaiting your YES)',
          ),
        ),
      );
      await _load();
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('refused: ${exc.message}')),
      );
    } catch (exc) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('connection error (${exc.runtimeType})')),
      );
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Widget _v150Card() {
    return Card(
      color: Theme.of(context).colorScheme.primaryContainer.withAlpha(70),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text(
              'START PAPER TRADING (v1.5.0)',
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            const Text(
              'Verified real 1m data -> TOP-5 YouTuber presets -> 30-day '
              'paper windows -> your YES. >=60% confirmed calls also '
              'journal 1-fill/second paper bursts.',
              style: TextStyle(fontSize: 12),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: <Widget>[
                FilledButton.tonalIcon(
                  onPressed: _busy ? null : _importDataAndBootstrap,
                  icon: const Icon(Icons.download),
                  label: const Text('IMPORT DATA + PRESETS'),
                ),
                OutlinedButton.icon(
                  onPressed: _busy ? null : _autoScan,
                  icon: const Icon(Icons.manage_search),
                  label: const Text('AUTO-SCAN'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _busy ? null : _createStrategy,
        icon: const Icon(Icons.add),
        label: const Text('New strategy'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _error != null
            ? ListView(
                children: <Widget>[
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text('error: $_error'),
                  ),
                ],
              )
            : _rows.isEmpty
                ? ListView(
                    padding: const EdgeInsets.fromLTRB(8, 8, 8, 88),
                    children: <Widget>[
                      _v150Card(),
                      const Padding(
                        padding: EdgeInsets.all(16),
                        child: Text(
                          'No strategies yet.\n\n'
                          'Pipeline: create -> backtest -> paper window -> '
                          'your explicit YES -> ACTIVATED (paper only).',
                        ),
                      ),
                    ],
                  )
                : ListView(
                    padding: const EdgeInsets.fromLTRB(8, 8, 8, 88),
                    children: <Widget>[
                      _v150Card(),
                      ..._rows.map((row) {
                      final id =
                          _labString(row, 'submission_id', '?');
                      final state =
                          _labString(row, 'state', 'SUBMITTED');
                      final backtest =
                          row['backtest'] as Map<String, dynamic>?;
                      return Card(
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              Row(
                                children: <Widget>[
                                  Expanded(
                                    child: Text(
                                      _labString(row, 'label', id),
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleSmall
                                          ?.copyWith(
                                              fontWeight: FontWeight.bold),
                                    ),
                                  ),
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 8, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: _stateColor(state,
                                          Theme.of(context))
                                          .withAlpha(30),
                                      borderRadius:
                                          BorderRadius.circular(8),
                                    ),
                                    child: Text(
                                      state,
                                      style: TextStyle(
                                        color: _stateColor(
                                            state, Theme.of(context)),
                                        fontWeight: FontWeight.bold,
                                        fontSize: 11,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Text(
                                '${_labString(row, 'kind', '?')}  ·  '
                                '${_labString(row, 'symbol', '?')}  ·  $id',
                                style:
                                    Theme.of(context).textTheme.bodySmall,
                              ),
                              if (backtest != null) ...<Widget>[
                                const SizedBox(height: 4),
                                Text(
                                  'backtest: ${backtest['trades']} trades, '
                                  'return ${backtest['total_return']}%, '
                                  'maxDD ${backtest['max_drawdown']}%',
                                  style:
                                      Theme.of(context).textTheme.bodySmall,
                                ),
                              ],
                              if (row['validation_window_end'] != null)
                                Text(
                                  'paper window ends: '
                                  '${row['validation_window_end']}',
                                  style:
                                      Theme.of(context).textTheme.bodySmall,
                                ),
                              const SizedBox(height: 8),
                              Wrap(
                                spacing: 6,
                                runSpacing: 6,
                                children: <Widget>[
                                  if (state == 'SUBMITTED')
                                    FilledButton.tonal(
                                      onPressed: _busy
                                          ? null
                                          : () => _act(
                                              () => widget.client
                                                  .labBacktest(id),
                                              'backtest recorded'),
                                      child: const Text('RUN BACKTEST'),
                                    ),
                                  if (state == 'BACKTESTED')
                                    FilledButton.tonal(
                                      onPressed: _busy
                                          ? null
                                          : () => _act(
                                              () => widget.client
                                                  .labPaperStart(id, 30),
                                              'paper window started (30d)'),
                                      child: const Text('START PAPER 30d'),
                                    ),
                                  if (state == 'VALIDATION_SCHEDULED') ...<Widget>[
                                    FilledButton.tonal(
                                      onPressed: _busy
                                          ? null
                                          : () => _act(
                                              () => widget.client
                                                  .labPaperFinish(id),
                                              'validation recorded'),
                                      child: const Text('FINISH PAPER'),
                                    ),
                                  ],
                                  if (state == 'VALIDATED')
                                    FilledButton(
                                      onPressed: _busy
                                          ? null
                                          : () => _confirmActivation(
                                              id,
                                              _labString(row, 'label', id)),
                                      child:
                                          const Text('CONFIRM (YES/NO)'),
                                    ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      );
                    }).toList(),
                  ),
      ),
    );
  }
}

class PredictTab extends StatefulWidget {
  const PredictTab({required this.client, super.key});

  final EngineApiClient client;

  @override
  State<PredictTab> createState() => _PredictTabState();
}

class _PredictTabState extends State<PredictTab> {
  final TextEditingController _symbol = TextEditingController(text: 'XAUUSD');
  Map<String, dynamic>? _result;
  String? _error;
  bool _busy = false;

  Future<void> _run() async {
    final symbol = _symbol.text.trim();
    if (symbol.isEmpty || _busy) {
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await widget.client.labPredict(symbol);
      if (!mounted) {
        return;
      }
      setState(() => _result = result);
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() => _error = exc.message);
    } catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() => _error = 'connection error (${exc.runtimeType})');
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    return ListView(
      padding: const EdgeInsets.all(12),
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: TextField(
                controller: _symbol,
                decoration: const InputDecoration(
                  hintText: 'symbol (bars uploaded from your PC)',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                onSubmitted: (_) => _run(),
              ),
            ),
            const SizedBox(width: 8),
            FilledButton(
              onPressed: _busy ? null : _run,
              child: _busy
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('PREDICT'),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (_error != null)
          Card(
            color: Theme.of(context).colorScheme.errorContainer,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(_error!),
            ),
          ),
        if (result != null) ...<Widget>[
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    '${_labString(result, 'direction', '?')}  '
                    '(p_up ${result['probability_up']})',
                    style: Theme.of(context)
                        .textTheme
                        .headlineSmall
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'momentum ${result['momentum_pct']}%  ·  '
                    'volatility ${result['volatility_pct']}%  ·  '
                    'confidence ${result['confidence']}\n'
                    'bars used ${result['bars_used']} '
                    '(lookback ${result['lookback']})',
                  ),
                ],
              ),
            ),
          ),
          Card(
            color: Theme.of(context).colorScheme.surfaceVariant,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(
                _labString(result, 'disclaimer', ''),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ),
        ],
      ],
    );
  }
}
