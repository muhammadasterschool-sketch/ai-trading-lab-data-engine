#!/usr/bin/env python3
"""Deployment-template validator (Batch 19).

Fail-closed validation of the SHIPPED deployment templates — runs
anywhere (no VPS, no systemd, no network required):

  uv run python scripts/validate_deployment_templates.py

Checks:
 1. the per-user systemd unit template exists and carries every
    mandated hardening key (least privilege, sandboxing, resource
    limits, restart policy, secret-injection-by-name-only, loopback
    posture);
 2. the secrets environment template contains NO credential values
    (names/empty values only);
 3. the deployment spec exists and documents the mandated procedure
    sections (backup/restore, rollback, firewall/network, incident,
    honest verification-status separation).

Exit code 0 = templates valid; non-zero = defective (fail closed).
This validator proves the TEMPLATES are well-formed — it is NOT a
deployment and proves nothing about any running host.
"""

from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[1]
UNIT = REPO / "deploy" / "systemd" / "ai-trading-lab@.service"
ENV_TEMPLATE = REPO / "deploy" / "config" / "secrets.env.example"
SPEC = REPO / "docs" / "PER_USER_VPS_DEPLOYMENT.md"

FAILURES: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


#: Hardening keys the unit MUST carry (mandate §8: least privilege,
#: resource limits, restart policy, safe shutdown, no secret values).
REQUIRED_UNIT_KEYS = (
    "User=aitl-%i",
    "Group=aitl-%i",
    "NoNewPrivileges=yes",
    "ProtectSystem=strict",
    "ProtectHome=yes",
    "PrivateTmp=yes",
    "RestrictSUIDSGID=yes",
    "LockPersonality=yes",
    "RestrictRealtime=yes",
    "IPAddressDeny=any",
    "IPAddressAllow=localhost",
    "EnvironmentFile=/var/lib/ai-trading-lab/%i/secrets.env",
    "Restart=on-failure",
    "RestartSec=",
    "TimeoutStopSec=",
    "KillSignal=SIGTERM",
    "MemoryMax=",
    "CPUQuota=",
    "TasksMax=",
    "Type=exec",
)

#: Credential-shaped patterns that must NOT appear as VALUES in any
#: committed template (name-only posture).
SECRET_VALUE_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

#: Sections the deployment spec MUST document (mandate §8).
REQUIRED_SPEC_SECTIONS = (
    "Persistent storage / backup / restore",
    "Restart recovery / clock sync / feed health",
    "Resource limits / logs / alerting / incidents",
    "Network restrictions / firewall",
    "Versioned config + rollback",
    "Verification status",
)


def main() -> int:
    print("Deployment-template validator (Batch 19)")
    print()

    # 1. systemd unit template -------------------------------------------
    if not UNIT.is_file():
        check("systemd unit template exists", False, str(UNIT))
    else:
        unit_text = UNIT.read_text(encoding="utf-8")
        missing = [
            key for key in REQUIRED_UNIT_KEYS if key not in unit_text
        ]
        check(
            "unit carries every mandated hardening key",
            not missing,
            f"{len(REQUIRED_UNIT_KEYS)} required; missing: {missing}" if missing
            else f"{len(REQUIRED_UNIT_KEYS)}/{len(REQUIRED_UNIT_KEYS)}",
        )
        leaked = [
            p.pattern
            for p in SECRET_VALUE_PATTERNS
            if p.search(unit_text)
        ]
        check("unit contains no secret VALUES", not leaked, "name-only posture")

    # 2. secrets env template --------------------------------------------
    if not ENV_TEMPLATE.is_file():
        check("secrets env template exists", False, str(ENV_TEMPLATE))
    else:
        env_text = ENV_TEMPLATE.read_text(encoding="utf-8")
        leaked = [
            p.pattern
            for p in SECRET_VALUE_PATTERNS
            if p.search(env_text)
        ]
        check("env template contains no secret VALUES", not leaked)
        populated = [
            line.strip()
            for line in env_text.splitlines()
            if re.match(r"^[A-Z][A-Z0-9_]*=\S+", line.strip())
            # non-secret configuration values are allowed (host/port);
            # SECRET-named keys must be empty:
            and not re.match(
                r"^[A-Z][A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD)=",
                line.strip(),
            )
            and not line.strip().startswith("#")
        ]
        secret_populated = [
            line
            for line in env_text.splitlines()
            if re.match(r"^[A-Z][A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD)=\S+", line.strip())
        ]
        check(
            "secret-named entries are EMPTY (names only)",
            not secret_populated,
            f"populated secret entries: {secret_populated}" if secret_populated
            else f"non-secret config entries: {populated}",
        )

    # 3. deployment spec sections -----------------------------------------
    if not SPEC.is_file():
        check("deployment spec exists", False, str(SPEC))
    else:
        spec_text = SPEC.read_text(encoding="utf-8")
        missing_sections = [
            s for s in REQUIRED_SPEC_SECTIONS if s not in spec_text
        ]
        check(
            "spec documents every mandated procedure section",
            not missing_sections,
            f"missing: {missing_sections}" if missing_sections
            else f"{len(REQUIRED_SPEC_SECTIONS)}/{len(REQUIRED_SPEC_SECTIONS)}",
        )
        check(
            "spec separates simulated / locally-tested / externally-verified",
            "Externally verified" in spec_text and "NONE" in spec_text,
        )

    print()
    if FAILURES:
        print(f"VALIDATOR RESULT: FAIL ({len(FAILURES)}: " + ", ".join(FAILURES) + ")")
        return 1
    print("VALIDATOR RESULT: PASS — templates well-formed (NOT a deployment)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
