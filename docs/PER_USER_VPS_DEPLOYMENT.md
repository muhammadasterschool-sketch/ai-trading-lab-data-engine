# PER-USER VPS AND OPERATIONAL DEPLOYMENT (BATCH 19 — ITEM C-6)

> **Document type:** deployment design + versioned configuration
> templates (mandate §8). NO deployment was performed: no VPS was
> provisioned, no billable infrastructure created, no service exposed
> publicly, no production credentials configured. A deployment guide
> is NOT proof of a successful deployment — §6 separates simulated /
> locally-tested / externally-verified outcomes.
>
> **Version:** 1.0.0 · **Date:** 2026-10-13
>
> **PAPER_READY = FALSE. LIVE TRADING NOT AUTHORIZED.**

## 1. Deployment model (per-user isolation)

One Linux VPS per USER (not per tenant record): each host runs exactly
one engine instance under a dedicated unprivileged OS account, serving
ONLY that user's loopback dashboard. Rationale: the tenancy layer
provides logical isolation (deny-default authorization); per-user VPS
provides PHYSICAL isolation — the strongest boundary available without
shared-state risk, per `PLATFORM_EXPANSION_SPEC.md` §5 (binding a real
interface / TLS / reverse proxy is an operator infrastructure
decision).

```
per-user VPS
└── systemd service ai-trading-lab@<user>
    ├── OS user aitl-<user> (least privilege, no sudo, no shell)
    ├── engine venv at /opt/ai-trading-lab/<user>/venv (read-only)
    ├── data at /var/lib/ai-trading-lab/<user> (owned, FS-contained)
    ├── secrets via systemd EnvironmentFile /var/lib/.../secrets.env
    │   (mode 0600, NEVER in the repository, never in command history)
    └── dashboard bound 127.0.0.1 (public exposure = operator decision)
```

## 2. Versioned templates (shipped, validated locally)

| Template | Purpose |
|---|---|
| `deploy/systemd/ai-trading-lab@.service` | Per-user templated unit: `User=aitl-%i`, `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`, `MemoryMax` + `CPUQuota` resource limits, `Restart=on-failure` + `RestartSec`, `EnvironmentFile` secret injection, loopback-only dashboard |
| `deploy/config/secrets.env.example` | PLACEHOLDER-ONLY names (empty values, inline comments). No secret value exists in any template — enforced by the validator and the repository-wide 0-secret forensic gate |

Validator (fail-closed, runs anywhere):
`scripts/validate_deployment_templates.py` — checks every hardening
key, resource limit, restart policy, loopback binding, the absence of
credential-shaped values, and the required spec sections. **VERIFIED
in the agent environment (see the Batch 19 report).**

## 3. Operational procedures (mandate §8 items)

- **Least privilege:** dedicated `aitl-<user>` OS account (no shell,
  no sudo); systemd sandboxing keys as above; the engine itself runs
  fail-closed (no gate wired → no trading).
- **Secure secret injection:** `EnvironmentFile=/var/lib/ai-trading-lab/%i/secrets.env`
  (root-owned 0600). Secrets never appear in unit files, command
  histories (`journalctl` shows only names), or logs (redaction layer
  + 0-secret scan). Rotation = update the file + `systemctl restart`
  (restart recovery is the runtime's own tested protocol).
- **Health / readiness / safe shutdown:** readiness is the ENGINE's
  honest verdict (32 gates, `PAPER_READY=FALSE` until external gates
  close — never fabricated); `Type=exec` + the engine's fail-closed
  startup (typed errors, loud refusal) give systemd accurate state;
  safe shutdown = `systemctl stop` (dashboard `shutdown()` is safe
  whether or not serving; journals flush on the runtime's own
  persistence contract).
- **Persistent storage / backup / restore:** all engine state under
  `/var/lib/ai-trading-lab/<user>` — back up with standard tooling
  (e.g. `restic`/`borg` snapshots); restore follows the runtime's
  LOAD→VERIFY→RESTORE→RECONCILE→RESUME-or-HALT protocol (corruption =
  fail-closed HALT, tested).
- **Restart recovery / clock sync / feed health:** NTP/chrony is a
  host prerequisite (the engine requires UTC-aware timestamps and
  rejects naive datetimes); the in-session feed watchdog (RUN-ST-1,
  operator opt-in `max_feed_staleness_seconds`) plus the feed gate's
  staleness window monitor feed health fail-closed.
- **Resource limits / logs / alerting / incidents:** `MemoryMax=512M`,
  `CPUQuota=50%` in the template (operator-tunable); logs to journald
  (structured, redacted); alerting on `systemctl` failure + the
  engine's HALT verdicts is an operator monitoring choice; incident
  classification follows the audit/security-incident vocabulary.
- **Network restrictions / firewall:** default posture = NO public
  exposure; dashboard binds `127.0.0.1`. If the operator later exposes
  it: TLS-terminating reverse proxy + authentication in front (never
  raw); firewall allows only SSH (operator-hardened) — UFW/iptables
  rules are operator-owned infrastructure.
- **Versioned config + rollback:** templates are git-versioned
  (this repository); the deployed wheel is SHA-pinned (Batch 18 §2);
  rollback = install the previous SHA-recorded wheel into a fresh venv
  and repoint the unit's `ExecStart` (never in-place mutation).

## 4. Verification status (honest separation)

| Outcome class | Status |
|---|---|
| Simulated (design) | THIS DOCUMENT — no deployment performed |
| Locally tested | Template VALIDATOR executed in the agent environment (fail-closed checks green); engine recovery/backup contracts covered by the existing test suite |
| Externally verified | **NONE** — no VPS provisioned, no systemd unit installed, no public exposure, no production credentials (all require explicit operator authorization, per mandate) |

Nothing in this document claims a running deployment exists.
