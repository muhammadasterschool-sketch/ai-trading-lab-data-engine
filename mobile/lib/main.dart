// AI Trading Lab — Android monitoring client (Stage F, Part 9 F2).
//
// Role (owner mandate): monitoring + control client, server-
// authenticated. The trading engine NEVER runs on the phone.
//
// Security contract:
//  - Login = SERVER URL + PERSONAL TOKEN: each user points the app
//    at their OWN dedicated server. There is NO default server
//    address and NO shared account anywhere in this codebase.
//  - TLS ONLY: http:// URLs are refused before any request.
//  - The token lives ONLY in flutter_secure_storage (Android
//    Keystore-backed). It is never logged and never rendered.
//  - Multi-profile: several server profiles can be stored, but only
//    ONE is active at a time.
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

const String _storageProfilesKey = 'atl_monitor_profiles';
const String _storageActiveKey = 'atl_monitor_active_profile';

/// One saved server profile (exactly one is active at a time).
class ServerProfile {
  ServerProfile({
    required this.id,
    required this.label,
    required this.serverUrl,
    required this.token,
  });

  final String id;
  final String label;
  final String serverUrl;
  final String token;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'label': label,
        'serverUrl': serverUrl,
        'token': token,
      };

  static ServerProfile fromJson(Map<String, dynamic> json) => ServerProfile(
        id: json['id'] as String,
        label: json['label'] as String,
        serverUrl: json['serverUrl'] as String,
        token: json['token'] as String,
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
  EngineApiClient({required this.serverUrl, required this.token});

  final String serverUrl;
  final String token;

  /// TLS-only: plain http:// is refused before any request is made.
  static String normalizeServerUrl(String raw) {
    var url = raw.trim();
    if (url.endsWith('/')) {
      url = url.substring(0, url.length - 1);
    }
    if (url.startsWith('https://')) {
      return url;
    }
    if (url.startsWith('http://')) {
      throw ApiException(
        0,
        'TLS only: http:// is refused. Use https:// (your server\'s '
            'nginx certificate).',
      );
    }
    // bare host: assume https (never silently downgrade to http)
    return 'https://$url';
  }

  Map<String, String> get _headers => <String, String>{
        'Authorization': 'Bearer $token',
        'Accept': 'application/json',
      };

  Future<Map<String, dynamic>> _getJson(String path) async {
    final response = await http
        .get(Uri.parse('$serverUrl$path'), headers: _headers)
        .timeout(const Duration(seconds: 10));
    if (response.statusCode == 401) {
      throw ApiException(401, 'invalid or expired token');
    }
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, 'unexpected status');
    }
    return jsonDecode(utf8.decode(response.bodyBytes))
        as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> health() => _getJson('/api/health');
  Future<Map<String, dynamic>> risk() => _getJson('/api/risk');
  Future<Map<String, dynamic>> feed() => _getJson('/api/feed');
  Future<dynamic> positions() => _getJson('/api/positions');
  Future<dynamic> orders() => _getJson('/api/orders');
  Future<dynamic> pnl() => _getJson('/api/pnl');

  Future<List<Map<String, dynamic>>> events() async {
    final response = await http
        .get(Uri.parse('$serverUrl/api/events'), headers: _headers)
        .timeout(const Duration(seconds: 10));
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, 'unexpected status');
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
      await _openEditor(initial: null);
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

  Future<void> _openEditor({ServerProfile? initial}) async {
    final saved = await showDialog<ServerProfile>(
      context: context,
      builder: (_) => ProfileEditDialog(initial: initial),
    );
    if (saved == null) {
      return;
    }
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
            tooltip: 'Add server profile',
            onPressed: () => _openEditor(initial: null),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _profiles.isEmpty
              ? const _EmptyProfiles()
              : ListView(
                  children: _profiles
                      .map((p) => ListTile(
                            leading: Icon(
                              p.id == _activeId
                                  ? Icons.radio_button_checked
                                  : Icons.radio_button_off,
                            ),
                            title: Text(p.label),
                            subtitle: Text(p.serverUrl),
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
  const _EmptyProfiles();

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
              'No server profiles yet.\nAdd YOUR dedicated server:\n'
              'server URL + personal token.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
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
  String? _error;

  @override
  void dispose() {
    _label.dispose();
    _url.dispose();
    _token.dispose();
    super.dispose();
  }

  void _save() {
    final label = _label.text.trim();
    final rawUrl = _url.text.trim();
    final token = _token.text.trim();
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
      url = EngineApiClient.normalizeServerUrl(rawUrl);
    } on ApiException catch (exc) {
      setState(() => _error = exc.message);
      return;
    }
    Navigator.of(context).pop(ServerProfile(
      id: widget.initial?.id ??
          DateTime.now().microsecondsSinceEpoch.toRadixString(36),
      label: label,
      serverUrl: url,
      token: token,
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
            decoration: const InputDecoration(
              labelText: 'Server URL (https://…)',
              hintText: 'https://engine.example.com',
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
  );
  Timer? _timer;
  Map<String, dynamic>? _health;
  dynamic _positions;
  dynamic _pnl;
  Map<String, dynamic>? _risk;
  Map<String, dynamic>? _feed;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
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
      if (!mounted) {
        return;
      }
      setState(() {
        _health = health;
        _positions = positions;
        _pnl = pnl;
        _risk = risk;
        _feed = feed;
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
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh),
          IconButton(
            icon: const Icon(Icons.list_alt),
            tooltip: 'Recent audit events',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => EventsPage(client: _client),
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
              widget.profile.serverUrl,
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
            _positionsCard(),
            const SizedBox(height: 12),
            FilledButton.tonalIcon(
              style: FilledButton.styleFrom(
                backgroundColor: Theme.of(context).colorScheme.errorContainer,
              ),
              icon: const Icon(Icons.power_settings_new),
              label: const Text('KILL SWITCH (confirmation required)'),
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
