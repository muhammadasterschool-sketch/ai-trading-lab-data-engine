/// v1.5.0 EMAIL + PASSWORD + TOTP (2FA) login for the monitor app.
///
/// Owner mandate (2026-10-28): "email koi bhi login kare to two factors
/// verification ke baghair na ho" — no session without the 6-digit
/// authenticator code. The flow:
///
/// 1. email + password (+ optional first-time code) -> POST /api/auth/login
/// 2. engine answers 409 E_TOTP_ENROLLMENT_REQUIRED with the enrollment
///    secret + otpauth:// URI (the password already verified);
/// 3. the user adds the secret to Google Authenticator (or any TOTP
///    app) and submits a code;
/// 4. engine confirms enrollment and issues a 12h session token.
///
/// The session token is stored exactly like a pairing token (secure
/// storage profile) and used as the Bearer credential.
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

import 'main.dart' show EngineApiClient, ApiException;

class LoginException implements Exception {
  LoginException(
    this.statusCode,
    this.message, {
    this.totpSecret,
    this.otpauthUri,
  });

  final int statusCode;
  final String message;
  final String? totpSecret;
  final String? otpauthUri;

  bool get enrollmentRequired =>
      statusCode == 409 && totpSecret != null && totpSecret!.isNotEmpty;

  @override
  String toString() => 'LOGIN $statusCode: $message';
}

class LoginSession {
  LoginSession({
    required this.token,
    required this.email,
    required this.name,
    required this.role,
  });

  final String token;
  final String email;
  final String name;
  final String role;
}

/// Calls POST /api/auth/login. Throws [LoginException] with the full
/// enrollment payload on 409 so the dialog can switch to enroll mode.
Future<LoginSession> loginWithEngine({
  required Uri baseUri,
  required String email,
  required String password,
  required String totpCode,
}) async {
  final http.Response response = await http
      .post(
        baseUri.replace(path: '/api/auth/login'),
        headers: <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(<String, dynamic>{
          'email': email,
          'password': password,
          'totp_code': totpCode,
        }),
      )
      .timeout(const Duration(seconds: 15));
  Map<String, dynamic> body = <String, dynamic>{};
  try {
    final dynamic decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is Map<String, dynamic>) {
      body = decoded;
    }
  } on FormatException {
    // fall through with empty body
  }
  if (response.statusCode == 200 && body['token'] is String) {
    final Map<String, dynamic> user =
        (body['user'] as Map<String, dynamic>?) ?? <String, dynamic>{};
    return LoginSession(
      token: body['token'] as String,
      email: (user['email'] ?? '') as String,
      name: (user['name'] ?? '') as String,
      role: (user['role'] ?? 'trader') as String,
    );
  }
  throw LoginException(
    response.statusCode,
    (body['error'] as String?) ?? 'login refused',
    totpSecret: body['totp_secret'] as String?,
    otpauthUri: body['otpauth_uri'] as String?,
  );
}

/// The v1.5.0 login dialog: server URL + email + password + TOTP code,
/// with an in-dialog enrollment panel when the engine answers 409.
class LoginPairingFormDialog extends StatefulWidget {
  const LoginPairingFormDialog({super.key, this.initialUrl});

  final String? initialUrl;

  @override
  State<LoginPairingFormDialog> createState() => _LoginPairingFormDialogState();
}

class _LoginPairingFormDialogState extends State<LoginPairingFormDialog> {
  final TextEditingController _url = TextEditingController();
  final TextEditingController _email = TextEditingController();
  final TextEditingController _password = TextEditingController();
  final TextEditingController _code = TextEditingController();
  bool _isLocal = false;
  bool _busy = false;
  String? _error;
  String? _enrollSecret;
  String? _enrollUri;

  @override
  void initState() {
    super.initState();
    if (widget.initialUrl != null && widget.initialUrl!.isNotEmpty) {
      _url.text = widget.initialUrl!;
    }
  }

  @override
  void dispose() {
    _url.dispose();
    _email.dispose();
    _password.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    final rawUrl = _url.text.trim();
    final email = _email.text.trim();
    final password = _password.text;
    final code = _code.text.trim();
    if (rawUrl.isEmpty || email.isEmpty || password.isEmpty) {
      setState(() => _error = 'server URL, email and password are required');
      return;
    }
    if (_enrollSecret != null && code.isEmpty) {
      setState(() => _error =
          'enter the 6-digit code from your authenticator app');
      return;
    }
    String url;
    try {
      url = EngineApiClient.normalizeServerUrl(rawUrl, isLocal: _isLocal);
    } on ApiException catch (exc) {
      setState(() => _error = exc.message);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final session = await loginWithEngine(
        baseUri: Uri.parse(url),
        email: email,
        password: password,
        totpCode: code,
      );
      if (!mounted) {
        return;
      }
      Navigator.of(context).pop(<String, dynamic>{
        'url': url,
        'token': session.token,
        'email': session.email,
        'name': session.name,
        'role': session.role,
      });
    } on LoginException catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        if (exc.enrollmentRequired) {
          _enrollSecret = exc.totpSecret;
          _enrollUri = exc.otpauthUri;
          _error = null;
        } else if (exc.statusCode == 401) {
          _error = exc.message == 'E_TOTP_INVALID'
              ? 'wrong authenticator code — try the current one'
              : 'wrong email or password';
        } else if (exc.statusCode == 423) {
          _error = 'account LOCKED (too many failed attempts) — '
              'wait 15 minutes or ask the admin to unlock';
        } else {
          _error = exc.message;
        }
      });
    } catch (exc) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _error = 'connection failed — is the engine running? ($exc)';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<Widget> fields = <Widget>[
      TextField(
        controller: _url,
        keyboardType: TextInputType.url,
        decoration: const InputDecoration(
          labelText: 'Engine URL (http://PC-IP:8018 on your LAN)',
        ),
      ),
      CheckboxListTile(
        value: _isLocal,
        onChanged: (value) => setState(() => _isLocal = value ?? false),
        title: const Text(
          'This is MY OWN PC on the local network (allow http)',
        ),
        dense: true,
        controlAffinity: ListTileControlAffinity.leading,
      ),
      TextField(
        controller: _email,
        keyboardType: TextInputType.emailAddress,
        decoration: const InputDecoration(labelText: 'Email'),
      ),
      TextField(
        controller: _password,
        obscureText: true,
        decoration: const InputDecoration(labelText: 'Password'),
      ),
      TextField(
        controller: _code,
        keyboardType: TextInputType.number,
        maxLength: 6,
        inputFormatters: <TextInputFormatter>[
          FilteringTextInputFormatter.digitsOnly,
        ],
        decoration: const InputDecoration(
          labelText: 'Authenticator code (6 digits)',
          helperText: 'from Google Authenticator / Authy after enrollment',
        ),
      ),
    ];
    if (_enrollSecret != null) {
      fields.addAll(<Widget>[
        const Divider(),
        const Text(
          'TWO-FACTOR ENROLLMENT',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        const Text(
          'Add this secret to your authenticator app (manual entry,'
          ' "time-based"), then enter the code above and press LOGIN:',
        ),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Colors.black26,
            borderRadius: BorderRadius.circular(8),
          ),
          child: SelectableText(
            _enrollSecret!,
            style: const TextStyle(
              fontFamily: 'monospace',
              fontSize: 15,
              letterSpacing: 2,
            ),
          ),
        ),
        TextButton.icon(
          onPressed: () {
            Clipboard.setData(ClipboardData(text: _enrollSecret!));
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('secret copied')),
            );
          },
          icon: const Icon(Icons.copy),
          label: const Text('copy secret'),
        ),
      ]);
    }
    return AlertDialog(
      title: const Text('Login with email (2FA)'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: fields,
        ),
      ),
      actions: <Widget>[
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(),
          child: const Text('CANCEL'),
        ),
        FilledButton(
          onPressed: _busy ? null : _login,
          child: _busy
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('LOGIN'),
        ),
      ],
    );
  }
}
