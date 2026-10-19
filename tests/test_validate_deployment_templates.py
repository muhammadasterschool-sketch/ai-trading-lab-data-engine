"""Reconstruction D-3 — tests for scripts/validate_deployment_templates.py.

Closes the verified G-02 gap: the fail-closed deployment-template
validator (Batch 19) had NO tests and was NOT invoked by CI.

Design (synthetic + secret-free by construction):

- the SHIPPED templates are validated via a subprocess against the
  real script (exit-code fidelity);
- tampered variants are built by copying the real script into a
  minimal synthetic repo skeleton (tmp_path) and mutating ONE thing:
    * a removed mandatory hardening key,
    * a populated secret-named env entry (obviously fake value),
    * a removed mandated spec section,
    * a missing unit template.
- every negative case MUST exit non-zero AND name the defect in its
  diagnostics (a silent failure would defeat the fail-closed design).

Fixture values are synthetic placeholders; no fixture matches the
repository secret-scan patterns, and no real credential is ever
written, printed or committed.
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "validate_deployment_templates.py"
REAL_UNIT = REPO_ROOT / "deploy" / "systemd" / "ai-trading-lab@.service"

REQUIRED_SPEC_SECTIONS = (
    "Persistent storage / backup / restore",
    "Restart recovery / clock sync / feed health",
    "Resource limits / logs / alerting / incidents",
    "Network restrictions / firewall",
    "Versioned config + rollback",
    "Verification status",
)


def _run(script_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )


def _skeleton(tmp_path: Path) -> Path:
    """Minimal synthetic repo: the REAL validator script + synthetic
    templates (names-only env, generated spec text, real unit copy)."""
    root = tmp_path / "synthetic-repo"
    (root / "scripts").mkdir(parents=True)
    (root / "deploy" / "systemd").mkdir(parents=True)
    (root / "deploy" / "config").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    shutil.copy2(SCRIPT, root / "scripts" / "validate_deployment_templates.py")
    shutil.copy2(REAL_UNIT, root / "deploy" / "systemd" / "ai-trading-lab@.service")
    (root / "deploy" / "config" / "secrets.env.example").write_text(
        "# synthetic names-only template (no values, no secrets)\n"
        "ATL_PROVIDER_API_KEY=\n"
        "ATL_KEYED_MAC_KEY=\n"
        "ATL_DASHBOARD_HOST=127.0.0.1\n"
        "ATL_DASHBOARD_PORT=8017\n",
        encoding="utf-8",
    )
    sections = "\n\n".join(f"## {s}" for s in REQUIRED_SPEC_SECTIONS)
    (root / "docs" / "PER_USER_VPS_DEPLOYMENT.md").write_text(
        "# synthetic deployment spec\n\n"
        f"{sections}\n\n"
        "Externally verified outcomes: NONE.\n",
        encoding="utf-8",
    )
    return root


class TestShippedTemplates:
    def test_shipped_templates_pass_with_exit_zero(self):
        proc = _run(SCRIPT)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "VALIDATOR RESULT: PASS" in proc.stdout

    def test_shipped_unit_reports_full_hardening_coverage(self):
        proc = _run(SCRIPT)
        assert proc.returncode == 0
        # F-04 completion (Stage B hardening, 2026-10-19): the mandated
        # key set grew 20 -> 31 (ReadWritePaths, UMask, the @system-
        # service sandbox set, ProtectClock/Hostname/Proc, Restrict-
        # Namespaces, CapabilityBoundingSet, MemoryDenyWriteExecute).
        assert "31/31" in proc.stdout


class TestTamperedTemplatesFailClosed:
    def test_missing_hardening_key_fails_and_names_the_key(self, tmp_path):
        root = _skeleton(tmp_path)
        unit = root / "deploy" / "systemd" / "ai-trading-lab@.service"
        unit.write_text(
            unit.read_text(encoding="utf-8")
            .replace("NoNewPrivileges=yes\n", ""),
            encoding="utf-8",
        )
        proc = _run(root / "scripts" / "validate_deployment_templates.py")
        assert proc.returncode == 1
        assert "unit carries every mandated hardening key" in proc.stdout
        assert "NoNewPrivileges" in proc.stdout

    def test_populated_secret_named_env_entry_fails(self, tmp_path):
        root = _skeleton(tmp_path)
        env = root / "deploy" / "config" / "secrets.env.example"
        # Obviously fake value; deliberate placeholder, never a secret.
        env.write_text(
            env.read_text(encoding="utf-8")
            + "ATL_PROVIDER_API_KEY=synthetic-placeholder-not-a-secret\n",
            encoding="utf-8",
        )
        proc = _run(root / "scripts" / "validate_deployment_templates.py")
        assert proc.returncode == 1
        assert "secret-named entries are EMPTY" in proc.stdout
        assert "ATL_PROVIDER_API_KEY" in proc.stdout

    def test_missing_spec_section_fails_and_names_it(self, tmp_path):
        root = _skeleton(tmp_path)
        spec = root / "docs" / "PER_USER_VPS_DEPLOYMENT.md"
        spec.write_text(
            spec.read_text(encoding="utf-8").replace(
                "## Network restrictions / firewall\n", ""
            ),
            encoding="utf-8",
        )
        proc = _run(root / "scripts" / "validate_deployment_templates.py")
        assert proc.returncode == 1
        assert "Network restrictions / firewall" in proc.stdout

    def test_missing_unit_template_fails(self, tmp_path):
        root = _skeleton(tmp_path)
        (root / "deploy" / "systemd" / "ai-trading-lab@.service").unlink()
        proc = _run(root / "scripts" / "validate_deployment_templates.py")
        assert proc.returncode == 1
        assert "systemd unit template exists" in proc.stdout

    def test_missing_spec_file_fails(self, tmp_path):
        root = _skeleton(tmp_path)
        (root / "docs" / "PER_USER_VPS_DEPLOYMENT.md").unlink()
        proc = _run(root / "scripts" / "validate_deployment_templates.py")
        assert proc.returncode == 1
        assert "deployment spec exists" in proc.stdout

    def test_diagnosed_failures_are_enumerated_in_result_line(
        self, tmp_path
    ):
        root = _skeleton(tmp_path)
        # NOTE: mutate a key that is NOT mentioned in the unit's comment
        # header — the validator matches key substrings, so a comment
        # mention would keep the check green (documented validator
        # property; LockPersonality appears only as a real key line).
        unit = root / "deploy" / "systemd" / "ai-trading-lab@.service"
        unit.write_text(
            unit.read_text(encoding="utf-8").replace(
                "LockPersonality=yes\n", ""
            ),
            encoding="utf-8",
        )
        proc = _run(root / "scripts" / "validate_deployment_templates.py")
        assert proc.returncode == 1
        assert "VALIDATOR RESULT: FAIL" in proc.stdout
        assert "LockPersonality" in proc.stdout
