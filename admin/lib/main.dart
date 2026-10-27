// AI Trading Lab — Android ADMIN PANEL (v1.0.0, owner mandate).
//
// Role: the OWNER's console for their own ai-trading-lab-data-engine
// deployment. Separate APK from the monitoring client on purpose:
// the monitor is for EVERYDAY watching, the admin panel answers the
// ownership questions:
//   - "kon kon logged in hai?"      -> /api/users (right now)
//   - "kon kon use kar raha hai?"   -> /api/registrations (ever)
//   - "kis pe trade li, kitna profit hua?" -> /api/ledger/*
//   - "mai chahu to stop kar pao"   -> POST /api/killswitch/activate
//
// Security contract:
//  - The connection (server URL + bearer token + admin identity)
//    is user-configured at first run and stored ONLY in
//    flutter_secure_storage (Android Keystore-backed). ZERO secrets
//    and NO default server address are embedded in the APK.
//  - Identity headers (X-Client-Name/Email/Kind: admin) are
//    SELF-REPORTED — a lab trust domain; the bearer token stays the
//    ONLY authentication factor.
//  - Transport: https by default; plain http ONLY behind an explicit
//    per-config switch with an honest unencrypted-LAN warning (the
//    local Windows monitor is http on the LAN by design).
//  - STOP is reachable from here; RESUME is deliberately PC-gATED
//    ("data-engine control-reset" on the machine) — the monitoring
//    API has no reset route, by design.
//
// LIVE TRADING IS NOT AUTHORIZED anywhere in this system.
// PAPER_READY stays FALSE.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

const String _storageConfigKey = 'atl_admin_config_v1';

/// The admin panel's single saved connection (exactly one at a time).
class AdminConfig {
  AdminConfig({
    required this.serverUrl,
    required this.token,
    required this.adminName,
    required this.email,
    required this.allowPlainHttp,
  });

  final String serverUrl;
  final String token;
  final String adminName;
  final String email;
  final bool allowPlainHttp;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'serverUrl': serverUrl,
        'token': token,
        'adminName': adminName,
        'email': email,
        'allowPlainHttp': allowPlainHttp,
      };

  static AdminConfig fromJson(Map<String, dynamic> json) => AdminConfig(
        serverUrl: json['serverUrl'] as String,
        token: json['token'] as String,
        adminName: json['adminName'] as String,
        email: json['email'] as String? ?? '',
        allowPlainHttp: (json['allowPlainHttp'] as bool?) ?? false,
      );
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AiTradingLabAdminApp());
}

class AiTradingLabAdminApp extends StatelessWidget {
  const AiTradingLabAdminApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Trading Lab — Admin',
      theme: ThemeData(
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF8B4CF5),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const AdminGatePage(),
    );
  }
}

class ApiException implements Exception {
  ApiException(this.statusCode, this.message);
  final int statusCode;
  final String message;

  @override
  String toString() => 'API $statusCode: $message';
}

// ---------------------------------------------------------------------------
// API client (https default; explicit per-config plain-http escape)
// ---------------------------------------------------------------------------

class AdminApiClient {
  AdminApiClient({required this.config});

  final AdminConfig config;

  static String normalizeServerUrl(String raw,
      {bool allowPlainHttp = false}) {
    var url = raw.trim();
    if (url.endsWith('/')) {
      url = url.substring(0, url.length - 1);
    }
    if (url.startsWith('https://')) {
      return url;
    }
    if (url.startsWith('http://')) {
      if (!allowPlainHttp) {
        throw ApiException(
          0,
          'TLS only: enable "my own LAN" explicitly to allow plain '
              'http (your engine on the local PC).',
        );
      }
      return url;
    }
    // bare host: never a silent downgrade
    return allowPlainHttp ? 'http://$url' : 'https://$url';
  }

  Map<String, String> get _headers => <String, String>{
        'Authorization': 'Bearer ${config.token}',
        'Accept': 'application/json',
        'X-Client-Name': config.adminName,
        'X-Client-Email': config.email,
        'X-Client-Kind': 'admin',
        'X-Client-Device': 'android-admin',
      };

  ApiException? _statusException(int statusCode) {
    if (statusCode == 401) {
      return ApiException(401, 'invalid or expired token');
    }
    if (statusCode == 429) {
      return ApiException(
          429, 'server busy (rate limited) — retrying automatically');
    }
    if (statusCode != 200) {
      return ApiException(statusCode, 'unexpected status');
    }
    return null;
  }

  Future<dynamic> _get(String path) async {
    final response = await http
        .get(Uri.parse('${config.serverUrl}$path'), headers: _headers)
        .timeout(const Duration(seconds: 10));
    final ApiException? failure = _statusException(response.statusCode);
    if (failure != null) {
      throw failure;
    }
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  Future<Map<String, dynamic>> health() async {
    final dynamic decoded = await _get('/api/health');
    return decoded is Map<String, dynamic>
        ? decoded
        : <String, dynamic>{};
  }

  Future<List<Map<String, dynamic>>> users() async {
    final dynamic decoded = await _get('/api/users');
    if (decoded is Map && decoded['clients'] is List) {
      return (decoded['clients'] as List).cast<Map<String, dynamic>>();
    }
    return <Map<String, dynamic>>[];
  }

  Future<List<Map<String, dynamic>>> registrations() async {
    final dynamic decoded = await _get('/api/registrations');
    if (decoded is Map && decoded['registrations'] is List) {
      return (decoded['registrations'] as List)
          .cast<Map<String, dynamic>>();
    }
    return <Map<String, dynamic>>[];
  }

  Future<Map<String, dynamic>> ledgerStats() async {
    final dynamic decoded = await _get('/api/ledger/stats');
    return decoded is Map<String, dynamic>
        ? decoded
        : <String, dynamic>{};
  }

  /// v1.1.0: read-only view of the owner AI lab strategy pipeline
  /// (create/backtest/paper/confirm states). The admin panel OBSERVES
  /// the lab; it cannot drive it.
  Future<List<Map<String, dynamic>>> labStrategies() async {
    final dynamic decoded = await _get('/api/lab/strategies');
    if (decoded is Map && decoded['strategies'] is List) {
      return (decoded['strategies'] as List).cast<Map<String, dynamic>>();
    }
    return <Map<String, dynamic>>[];
  }

  Future<List<Map<String, dynamic>>> trades() async {
    final dynamic decoded = await _get('/api/ledger/trades');
    if (decoded is Map && decoded['trades'] is List) {
      return (decoded['trades'] as List).cast<Map<String, dynamic>>();
    }
    return <Map<String, dynamic>>[];
  }

  Future<Map<String, dynamic>> activateKillSwitch(String reason) async {
    final response = await http
        .post(
          Uri.parse('${config.serverUrl}/api/killswitch/activate'),
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
// Gate: setup / connection screen (first run + edit)
// ---------------------------------------------------------------------------

class AdminGatePage extends StatefulWidget {
  const AdminGatePage({super.key});

  @override
  State<AdminGatePage> createState() => _AdminGatePageState();
}

class _AdminGatePageState extends State<AdminGatePage> {
  final FlutterSecureStorage _storage = const FlutterSecureStorage();
  bool _loading = true;
  AdminConfig? _config;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final raw = await _storage.read(key: _storageConfigKey);
    if (!mounted) {
      return;
    }
    AdminConfig? config;
    if (raw != null && raw.isNotEmpty) {
      try {
        config = AdminConfig.fromJson(
            jsonDecode(raw) as Map<String, dynamic>);
      } catch (_) {
        config = null; // corrupted blob -> honest re-setup
      }
    }
    setState(() {
      _config = config;
      _loading = false;
    });
  }

  Future<void> _saveConfig(AdminConfig config) async {
    await _storage.write(
      key: _storageConfigKey,
      value: jsonEncode(config.toJson()),
    );
    if (!mounted) {
      return;
    }
    Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
      builder: (_) => AdminHomePage(config: config),
    ));
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    final config = _config;
    if (config != null) {
      return AdminHomePage(config: config);
    }
    return SetupPage(onSaved: _saveConfig);
  }
}

class SetupPage extends StatefulWidget {
  const SetupPage({required this.onSaved, super.key});

  final Future<void> Function(AdminConfig) onSaved;

  @override
  State<SetupPage> createState() => _SetupPageState();
}

class _SetupPageState extends State<SetupPage> {
  final TextEditingController _url = TextEditingController();
  final TextEditingController _token = TextEditingController();
  final TextEditingController _name = TextEditingController();
  final TextEditingController _email = TextEditingController();
  bool _allowPlainHttp = false;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _url.dispose();
    _token.dispose();
    _name.dispose();
    _email.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    final name = _name.text.trim();
    final email = _email.text.trim();
    final token = _token.text.trim();
    if (name.isEmpty || email.isEmpty || token.isEmpty ||
        _url.text.trim().isEmpty) {
      setState(() =>
          _error = 'server URL, token, name and email are all required');
      return;
    }
    if (!email.contains('@')) {
      setState(() =>
          _error = 'enter a valid email (identity shown in your own panel)');
      return;
    }
    if (token.length < 16) {
      setState(() => _error = 'token looks too short (>= 16 chars)');
      return;
    }
    String url;
    try {
      url = AdminApiClient.normalizeServerUrl(
        _url.text.trim(),
        allowPlainHttp: _allowPlainHttp,
      );
    } on ApiException catch (exc) {
      setState(() => _error = exc.message);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    // probe BEFORE saving: a wrong URL/token must never look connected
    try {
      final client = AdminApiClient(
        config: AdminConfig(
          serverUrl: url,
          token: token,
          adminName: name,
          email: email,
          allowPlainHttp: _allowPlainHttp,
        ),
      );
      await client.health();
      if (!mounted) {
        return;
      }
      await widget.onSaved(AdminConfig(
        serverUrl: url,
        token: token,
        adminName: name,
        email: email,
        allowPlainHttp: _allowPlainHttp,
      ));
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _error = exc.message;
      });
    } on TimeoutException {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _error = 'timeout — server unreachable';
      });
    } catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _error = 'connection error (${exc.runtimeType})';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Admin panel — connect')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: <Widget>[
          const Text(
            'Connect to YOUR ai-trading-lab-data-engine. The admin '
            'token comes from the engine install (monitor-token.txt '
            'or your server token file). Your name + email appear in '
            'the owner surfaces as the panel user.',
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _url,
            keyboardType: TextInputType.url,
            decoration: const InputDecoration(
              labelText: 'Engine URL (https://… or PC address)',
              hintText: 'http://192.168.0.58:8018',
            ),
          ),
          TextField(
            controller: _token,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'Bearer token',
              helperText: 'stored in secure storage only',
            ),
          ),
          TextField(
            controller: _name,
            decoration: const InputDecoration(
              labelText: 'Your name (admin identity)',
            ),
          ),
          TextField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            decoration: const InputDecoration(
              labelText: 'Your email (admin identity)',
            ),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('My own LAN — allow plain http'),
            subtitle: const Text(
              'The local Windows monitor speaks unencrypted http on '
              'your Wi-Fi. Cloud servers must stay https.',
            ),
            value: _allowPlainHttp,
            onChanged: (value) => setState(() => _allowPlainHttp = value),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          if (_busy) const Padding(
            padding: EdgeInsets.only(top: 10),
            child: LinearProgressIndicator(),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            icon: const Icon(Icons.admin_panel_settings),
            label: const Text('CONNECT'),
            onPressed: _busy ? null : _connect,
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Home: Overview / Users / Registrations / Trades (bottom navigation)
// ---------------------------------------------------------------------------

class AdminHomePage extends StatefulWidget {
  const AdminHomePage({required this.config, super.key});

  final AdminConfig config;

  @override
  State<AdminHomePage> createState() => _AdminHomePageState();
}

class _AdminHomePageState extends State<AdminHomePage> {
  late final AdminApiClient _client = AdminApiClient(config: widget.config);
  int _tab = 0;

  Future<void> _editConnection() async {
    Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
      builder: (_) => SetupPage(
        onSaved: (config) async {
          const storage = FlutterSecureStorage();
          await storage.write(
            key: _storageConfigKey,
            value: jsonEncode(config.toJson()),
          );
        },
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Admin — ${widget.config.adminName}'),
        actions: <Widget>[
          IconButton(
            icon: const Icon(Icons.settings),
            tooltip: 'Edit connection',
            onPressed: _editConnection,
          ),
        ],
      ),
      body: IndexedStack(
        index: _tab,
        children: <Widget>[
          OverviewTab(client: _client, config: widget.config),
          UsersTab(client: _client),
          RegistrationsTab(client: _client),
          TradesTab(client: _client),
          StrategiesTab(client: _client),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (index) => setState(() => _tab = index),
        destinations: const <Widget>[
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Overview',
          ),
          NavigationDestination(
            icon: Icon(Icons.people_outline),
            selectedIcon: Icon(Icons.people),
            label: 'Users',
          ),
          NavigationDestination(
            icon: Icon(Icons.fact_check_outlined),
            selectedIcon: Icon(Icons.fact_check),
            label: 'Registrations',
          ),
          NavigationDestination(
            icon: Icon(Icons.receipt_long_outlined),
            selectedIcon: Icon(Icons.receipt_long),
            label: 'Trades',
          ),
          NavigationDestination(
            icon: Icon(Icons.science_outlined),
            selectedIcon: Icon(Icons.science),
            label: 'Strategies',
          ),
        ],
      ),
    );
  }
}

typedef JsonLoader = Future<dynamic> Function();

/// Shared async content scaffold: spinner -> error -> refreshable body.
class _AsyncBody extends StatefulWidget {
  const _AsyncBody({required this.loader, required this.builder});

  final JsonLoader loader;
  final Widget Function(BuildContext, dynamic) builder;

  @override
  State<_AsyncBody> createState() => _AsyncBodyState();
}

class _AsyncBodyState extends State<_AsyncBody> {
  dynamic _data;
  String? _error;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      final data = await widget.loader();
      if (!mounted) {
        return;
      }
      setState(() {
        _data = data;
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
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return RefreshIndicator(
        onRefresh: _reload,
        child: ListView(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                children: <Widget>[
                  const Icon(Icons.cloud_off, size: 48),
                  const SizedBox(height: 12),
                  Text(_error!, textAlign: TextAlign.center),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    icon: const Icon(Icons.refresh),
                    label: const Text('Retry'),
                    onPressed: _reload,
                  ),
                ],
              ),
            ),
          ],
        ),
      );
    }
    if (_data == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return RefreshIndicator(
      onRefresh: _reload,
      child: widget.builder(context, _data),
    );
  }
}

/// Overview: engine health + the STOP control (the admin's own
/// full-control surface; resume stays PC-gated on purpose).
class OverviewTab extends StatefulWidget {
  const OverviewTab({required this.client, required this.config, super.key});

  final AdminApiClient client;
  final AdminConfig config;

  @override
  State<OverviewTab> createState() => _OverviewTabState();
}

class _OverviewTabState extends State<OverviewTab> {
  Timer? _timer;
  Map<String, dynamic>? _health;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 15), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final health = await widget.client.health();
      if (!mounted) {
        return;
      }
      setState(() {
        _health = health;
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
    }
  }

  Future<void> _confirmStop() async {
    final reasonController = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('STOP TRADING?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Text(
              'This sets the durable STOP flag on your engine '
              '(kill switch ACTIVE). Resume is done ON THE PC with '
              '"data-engine control-reset" — the API can never '
              'reset it.\n\nType a reason (required, audited):',
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
            label: const Text('STOP TRADING'),
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
      await widget.client.activateKillSwitch(reasonController.text.trim());
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('STOP flag set (kill switch ACTIVE)')),
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
    return ListView(
      padding: const EdgeInsets.all(12),
      children: <Widget>[
        Text(
          '${widget.config.serverUrl}  ·  admin: '
          '${widget.config.adminName} <${widget.config.email}>',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 8),
        if (_error != null)
          Card(
            color: Theme.of(context).colorScheme.errorContainer,
            child: ListTile(
              leading: const Icon(Icons.warning_amber),
              title: Text('CONNECTION: $_error'),
            ),
          ),
        _infoCard(context, 'Engine health', <String, String>{
          'mode': '${health?['engine_mode'] ?? '?'}',
          'state': '${health?['engine_state'] ?? '?'}',
          'version': '${health?['engine_version'] ?? '?'}',
          'uptime': '${health?['uptime_seconds'] ?? '?'} s',
          'STOP flag (kill switch)': '${health?['kill_switch'] ?? '?'}',
        }),
        const SizedBox(height: 12),
        FilledButton.tonalIcon(
          style: FilledButton.styleFrom(
            backgroundColor: Theme.of(context).colorScheme.errorContainer,
          ),
          icon: const Icon(Icons.stop_circle_outlined),
          label: const Text(
              'STOP TRADING (KILL SWITCH)\nconfirmation + reason required'),
          onPressed: _confirmStop,
        ),
        const SizedBox(height: 8),
        const Text(
          'Resume is PC-gated by design: run '
          '"python -m data_engine.cli control-reset" in the engine '
          'folder on your PC.',
          style: TextStyle(fontSize: 12, fontStyle: FontStyle.italic),
        ),
      ],
    );
  }
}

Widget _infoCard(
  BuildContext context,
  String title,
  Map<String, String> rows,
) {
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
                    Text(e.key,
                        style: Theme.of(context).textTheme.bodySmall),
                    Flexible(child: Text(e.value)),
                  ],
                ),
              )),
        ],
      ),
    ),
  );
}

/// Timestamp formatting: registry timestamps are epoch seconds
/// (wall clock); anything else passes through untouched.
String formatTimestamp(dynamic value) {
  if (value is num) {
    return DateTime.fromMillisecondsSinceEpoch(
      (value * 1000).round(),
      isUtc: true,
    ).toIso8601String();
  }
  return '$value';
}

/// Users: WHO is logged in RIGHT NOW (online = seen within the
/// server's 90 s window).
class UsersTab extends StatelessWidget {
  const UsersTab({required this.client, super.key});

  final AdminApiClient client;

  @override
  Widget build(BuildContext context) {
    return _AsyncBody(
      loader: client.users,
      builder: (context, data) {
        final rows = (data as List).cast<Map<String, dynamic>>();
        if (rows.isEmpty) {
          return ListView(children: const <Widget>[
            Padding(
              padding: EdgeInsets.all(24),
              child: Center(child: Text('No clients connected yet.')),
            ),
          ]);
        }
        return ListView.builder(
          itemCount: rows.length,
          itemBuilder: (context, index) {
            final row = rows[index];
            final online = row['online'] == true;
            return Card(
              child: ListTile(
                leading: Icon(
                  online ? Icons.circle : Icons.circle_outlined,
                  color: online ? Colors.greenAccent : Colors.white38,
                  size: 14,
                ),
                isThreeLine: true,
                title: Text(
                  '${row['name'] == '' ? '(anonymous)' : row['name']}'
                  '${row['kind'] != '' ? '  ·  ${row['kind']}' : ''}',
                ),
                subtitle: Text(
                  'email: ${row['email'] == '' ? '—' : row['email']}\n'
                  'device: ${row['device'] == '' ? '—' : row['device']}'
                  '  ·  ip: ${row['ip']}\n'
                  'seen ${row['seconds_since_seen']}s ago  ·  '
                  '${row['requests']} requests'
                  '${online ? '  ·  ONLINE' : '  ·  offline'}',
                ),
              ),
            );
          },
        );
      },
    );
  }
}

/// Registrations: WHO has EVER registered (durable first-contact
/// ledger on the engine PC).
class RegistrationsTab extends StatelessWidget {
  const RegistrationsTab({required this.client, super.key});

  final AdminApiClient client;

  @override
  Widget build(BuildContext context) {
    return _AsyncBody(
      loader: client.registrations,
      builder: (context, data) {
        final rows = (data as List).cast<Map<String, dynamic>>();
        if (rows.isEmpty) {
          return ListView(children: const <Widget>[
            Padding(
              padding: EdgeInsets.all(24),
              child: Center(
                  child: Text('No registrations recorded yet.')),
            ),
          ]);
        }
        return ListView.builder(
          itemCount: rows.length,
          itemBuilder: (context, index) {
            final row = rows[index];
            return Card(
              child: ListTile(
                leading: const Icon(Icons.person_add_alt),
                isThreeLine: true,
                title: Text(
                  '${row['name'] == '' ? '(anonymous)' : row['name']}'
                  '${row['kind'] != '' ? '  ·  ${row['kind']}' : ''}',
                ),
                subtitle: Text(
                  'email: ${row['email'] == '' ? '—' : row['email']}\n'
                  'first seen: ${formatTimestamp(row['first_seen'])}\n'
                  'ip: ${row['ip']}  ·  device: '
                  '${row['device'] == '' ? '—' : row['device']}',
                ),
              ),
            );
          },
        );
      },
    );
  }
}

/// Trades: "kis pe trade li, kitna profit hua" — stats header +
/// per-trade ledger, newest first.
class TradesTab extends StatelessWidget {
  const TradesTab({required this.client, super.key});

  final AdminApiClient client;

  @override
  Widget build(BuildContext context) {
    return _AsyncBody(
      loader: client.trades,
      builder: (context, data) {
        final rows = (data as List).cast<Map<String, dynamic>>();
        return ListView(
          children: <Widget>[
            FutureBuilder<Map<String, dynamic>>(
              future: client.ledgerStats(),
              builder: (context, snapshot) {
                final stats = snapshot.data;
                final int total =
                    (stats?['total_trades'] as num?)?.toInt() ?? rows.length;
                final double pnl =
                    (stats?['total_pnl'] as num?)?.toDouble() ?? 0.0;
                final int wins = (stats?['wins'] as num?)?.toInt() ?? 0;
                final int losses =
                    (stats?['losses'] as num?)?.toInt() ?? 0;
                return _infoCard(context, 'Trade summary', <String, String>{
                  'total trades': '$total',
                  'total PnL': pnl.toStringAsFixed(2),
                  'wins / losses': '$wins / $losses',
                });
              },
            ),
            if (rows.isEmpty)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Center(
                  child: Text(
                    'No trades recorded yet.\nThe ledger fills when a '
                    'trading session runs (monitor-only mode trades '
                    'nothing — honest empty state).',
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            else
              ...rows.map((trade) {
                final dynamic pnl = trade['pnl'];
                final String pnlText =
                    pnl is num ? pnl.toStringAsFixed(2) : 'open';
                final Color pnlColor = pnl is num
                    ? (pnl >= 0 ? Colors.greenAccent : Colors.redAccent)
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
                    '${trade['side'] ?? '?'} ${trade['quantity'] ?? '?'} '
                    '${trade['symbol'] ?? '?'} @ ${trade['price'] ?? '?'}',
                  ),
                  subtitle: Text('${trade['ts'] ?? ''}'),
                  trailing: Text(
                    'PnL $pnlText',
                    style: TextStyle(
                        color: pnlColor, fontWeight: FontWeight.bold),
                  ),
                );
              }),
          ],
        );
      },
    );
  }
}

/// v1.1.0: read-only oversight of the owner AI lab strategy pipeline
/// (SUBMITTED -> BACKTESTED -> VALIDATION_SCHEDULED -> VALIDATED ->
/// ACTIVATED = paper-evaluation-only). The admin panel observes; the
/// monitor APK is the surface that drives the lab.
class StrategiesTab extends StatelessWidget {
  const StrategiesTab({required this.client, super.key});

  final AdminApiClient client;

  static Color _stateColor(String state) {
    if (state == 'ACTIVATED') {
      return Colors.greenAccent;
    }
    if (state == 'VALIDATED') {
      return Colors.orangeAccent;
    }
    if (state == 'REJECTED') {
      return Colors.redAccent;
    }
    return Colors.lightBlueAccent;
  }

  static String formatTimestamp(Object? value) {
    if (value is! String || value.isEmpty) {
      return '';
    }
    final DateTime? parsed = DateTime.tryParse(value);
    if (parsed == null) {
      return value;
    }
    final String iso = parsed.toIso8601String();
    return iso.length >= 16 ? iso.substring(0, 16).replaceFirst('T', ' ') : iso;
  }

  @override
  Widget build(BuildContext context) {
    return _AsyncBody(
      loader: client.labStrategies,
      builder: (context, data) {
        final List<Map<String, dynamic>> rows =
            (data as List).cast<Map<String, dynamic>>();
        if (rows.isEmpty) {
          return ListView(
            children: const <Widget>[
              Padding(
                padding: EdgeInsets.all(24),
                child: Center(
                  child: Text(
                    'No strategies in the lab yet.\n\n'
                    'The owner creates strategies from the monitor APK '
                    '(AI Lab tab). This panel watches the pipeline:\n'
                    'create -> backtest -> paper window -> explicit YES '
                    '-> ACTIVATED (paper evaluation only; live trading '
                    'stays NOT AUTHORIZED).',
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            ],
          );
        }
        return ListView(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Text(
                'Owner AI lab pipeline — read-only oversight '
                '(${rows.length})',
                style: Theme.of(context).textTheme.titleSmall,
              ),
            ),
            ...rows.map((row) {
              final String state =
                  '${row['state'] ?? 'SUBMITTED'}';
              final dynamic backtest = row['backtest'];
              return Card(
                child: ListTile(
                  leading: Icon(
                    Icons.science,
                    color: _stateColor(state),
                  ),
                  title: Text('${row['label'] ?? row['submission_id'] ?? '?'}'),
                  subtitle: Text(
                    '${row['kind'] ?? '?'} · ${row['symbol'] ?? '?'}\n'
                    'state: $state\n'
                    '${backtest is Map ? 'backtest: ${backtest['trades']} '
                        'trades, return ${backtest['total_return']}%, '
                        'maxDD ${backtest['max_drawdown']}%\n'
                    : ''}'
                    '${row['validation_window_end'] != null ? 'paper window ends: ${formatTimestamp(row['validation_window_end'])}' : ''}',
                  ),
                  isThreeLine: true,
                  trailing: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: _stateColor(state).withAlpha(40),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      state,
                      style: TextStyle(
                        color: _stateColor(state),
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ),
              );
            }),
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'ACTIVATED means PAPER-EVALUATION-ONLY. The engine has '
                'no live path and LIVE_AUTHORIZATION stays '
                'NOT_AUTHORIZED.',
                style: TextStyle(fontSize: 11),
              ),
            ),
          ],
        );
      },
    );
  }
}
