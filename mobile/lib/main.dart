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

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'label': label,
        'serverUrl': serverUrl,
        'token': token,
        'isLocal': isLocal,
        if (email != null) 'email': email,
      };

  static ServerProfile fromJson(Map<String, dynamic> json) => ServerProfile(
        id: json['id'] as String,
        label: json['label'] as String,
        serverUrl: json['serverUrl'] as String,
        token: json['token'] as String,
        // backward compatibility: v0.3.x profiles load as CLOUD profiles
        isLocal: (json['isLocal'] as bool?) ?? false,
        email: json['email'] as String?,
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

  /// v4.0 (P2/C1): first-run + add-profile flow — exactly TWO options,
  /// plus the advanced manual-token path. The choice is persisted and
  /// changeable at any time (adding a profile of the other kind).
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

  @override
  void initState() {
    super.initState();
    _refresh();
    // v4.0.2: 15 s poll cadence (was 10 s) — halves the request rate so
    // the dashboard sits comfortably under the server's rate limit
    // while staying responsive for a monitoring surface.
    _timer = Timer.periodic(const Duration(seconds: 15), (_) => _refresh());
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
