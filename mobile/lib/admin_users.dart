/// v1.5.0 ADMIN Users page for the monitor app.
///
/// Owner mandate (2026-10-28): the admin user sees the NORMAL trading
/// system plus a Users screen listing the other users. Two views:
///
/// - ONLINE NOW — the engine's client registry (who is connected);
/// - ACCOUNTS — 2FA accounts (email/name/role/enrollment/last login
///   + login history) with admin actions: create user, reset 2FA,
///   lock/unlock.
///
/// Only shown when /api/auth/me reports the admin role (or the owner
/// pairing token is in use).
library;

import 'package:flutter/material.dart';

import 'main.dart' show ApiException, EngineApiClient;

class UsersPage extends StatefulWidget {
  const UsersPage({super.key, required this.client});

  final EngineApiClient client;

  @override
  State<UsersPage> createState() => _UsersPageState();
}

class _UsersPageState extends State<UsersPage> {
  List<Map<String, dynamic>> _online = <Map<String, dynamic>>[];
  List<Map<String, dynamic>> _accounts = <Map<String, dynamic>>[];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final online = await widget.client.users();
      final accounts = await widget.client.adminAccounts();
      if (!mounted) {
        return;
      }
      setState(() {
        _online = online;
        _accounts = accounts;
        _loading = false;
      });
    } on ApiException catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loading = false;
        _error = exc.message;
      });
    }
  }

  Future<void> _createUser() async {
    final email = TextEditingController();
    final name = TextEditingController();
    final password = TextEditingController();
    String role = 'trader';
    final created = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: const Text('Create user'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              TextField(
                controller: email,
                decoration: const InputDecoration(labelText: 'email'),
                keyboardType: TextInputType.emailAddress,
              ),
              TextField(
                controller: name,
                decoration: const InputDecoration(labelText: 'name'),
              ),
              TextField(
                controller: password,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'password (min 10 chars)',
                ),
              ),
              const SizedBox(height: 8),
              DropdownButton<String>(
                value: role,
                isExpanded: true,
                items: const <DropdownMenuItem<String>>[
                  DropdownMenuItem<String>(value: 'trader', child: Text('trader')),
                  DropdownMenuItem<String>(value: 'admin', child: Text('admin')),
                ],
                onChanged: (value) =>
                    setDialogState(() => role = value ?? 'trader'),
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
              child: const Text('CREATE'),
            ),
          ],
        ),
      ),
    );
    if (created != true) {
      return;
    }
    try {
      await widget.client.adminCreateUser(
        email: email.text.trim(),
        name: name.text.trim(),
        password: password.text,
        role: role,
      );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'user created — they enroll 2FA on first login: '
            '${email.text.trim()}',
          ),
        ),
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

  Future<void> _reset2fa(Map<String, dynamic> account) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('Reset 2FA for ${account['email']}?'),
        content: const Text(
          'Their authenticator is unlinked and sessions are revoked. '
          'They re-enroll on the next login.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('CANCEL'),
          ),
          FilledButton.tonal(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('RESET'),
          ),
        ],
      ),
    );
    if (confirmed != true) {
      return;
    }
    try {
      await widget.client.adminReset2fa(account['email'] as String);
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('2FA reset')),
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

  Future<void> _toggleLock(Map<String, dynamic> account) async {
    final bool currentlyLocked = account['locked'] == true;
    try {
      await widget.client.adminSetLock(
        account['email'] as String,
        !currentlyLocked,
      );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(currentlyLocked ? 'account unlocked' : 'account locked'),
        ),
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
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Users'),
          actions: <Widget>[
            IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh),
          ],
          bottom: const TabBar(
            tabs: <Widget>[
              Tab(text: 'ONLINE NOW'),
              Tab(text: 'ACCOUNTS (2FA)'),
            ],
          ),
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: _createUser,
          icon: const Icon(Icons.person_add),
          label: const Text('NEW USER'),
        ),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(child: Text('error: $_error'))
                : TabBarView(
                    children: <Widget>[
                      _buildOnline(),
                      _buildAccounts(),
                    ],
                  ),
      ),
    );
  }

  Widget _buildOnline() {
    if (_online.isEmpty) {
      return const Center(
        child: Text('nobody else is connected right now'),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.all(8),
      itemCount: _online.length,
      itemBuilder: (context, index) {
        final client = _online[index];
        final bool online = client['online'] == true;
        return Card(
          child: ListTile(
            leading: Icon(
              Icons.circle,
              color: online ? Colors.green : Colors.grey,
              size: 14,
            ),
            title: Text('${client['name'] ?? '?'} '
                '<${client['email'] ?? '?'}>'),
            subtitle: Text(
              'kind: ${client['kind'] ?? '?'}  device: '
              '${client['device'] ?? '?'}  ip: ${client['ip'] ?? '?'}',
            ),
            trailing: online
                ? const Text('ONLINE',
                    style: TextStyle(color: Colors.green))
                : const Text('away'),
          ),
        );
      },
    );
  }

  Widget _buildAccounts() {
    if (_accounts.isEmpty) {
      return const Center(
        child: Text('no accounts yet (create the first admin on the PC)'),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.all(8),
      itemCount: _accounts.length,
      itemBuilder: (context, index) {
        final account = _accounts[index];
        final bool enrolled = account['totp_enrolled'] == true;
        final bool locked = account['locked'] == true;
        final history = (account['login_history'] as List?)
                ?.cast<Map<String, dynamic>>() ??
            <Map<String, dynamic>>[];
        return Card(
          child: ExpansionTile(
            title: Text('${account['name'] ?? '?'} '
                '<${account['email'] ?? '?'}>'),
            subtitle: Text(
              'role: ${account['role'] ?? '?'}  '
              '2FA: ${enrolled ? 'enrolled' : 'PENDING'}'
              '${locked ? '  LOCKED' : ''}',
            ),
            children: <Widget>[
              Align(
                alignment: Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        'last login: ${account['last_login_at'] ?? 'never'}',
                      ),
                      const SizedBox(height: 6),
                      const Text('recent logins:'),
                      ...history.take(10).map(
                            (entry) => Text(
                              '  ${entry['ts'] ?? '?'}  '
                              '${entry['ok'] == true ? 'OK' : 'FAILED'}  '
                              '(${entry['reason'] ?? '?'})  '
                              'ip ${entry['ip'] ?? '?'}',
                              style: const TextStyle(fontSize: 12),
                            ),
                          ),
                    ],
                  ),
                ),
              ),
              ButtonBar(
                children: <Widget>[
                  TextButton.icon(
                    onPressed: () => _reset2fa(account),
                    icon: const Icon(Icons.key_off),
                    label: const Text('RESET 2FA'),
                  ),
                  TextButton.icon(
                    onPressed: () => _toggleLock(account),
                    icon: Icon(locked ? Icons.lock_open : Icons.lock),
                    label: Text(locked ? 'UNLOCK' : 'LOCK'),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}
