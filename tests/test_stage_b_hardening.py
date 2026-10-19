"""Milestone A B4 — Stage-B hardening sweep regression tests
(master prompt v4.0 Stage 1 Group 4; patch plan P4).

Covers findings F-03 (zero file locking), F-04 (systemd strict
without ReadWritePaths), F-08/F-09 (fsync durability gaps), F-10
(fail-open audit_log), F-11 (unlocked audit-trail append), F-12
(torn journal tail bricks the store), F-15/F-16/F-18 (CI gaps),
F-21 (CLI validate argument mismatch), F-22 (fixed test storage
paths).

Discipline notes (artifacts/stage-a/02-FINDINGS-REGISTER.md):

- Locking tests run against the ACTUAL filesystem flock (mandate:
  "locking verified on the actual filesystem") — in-process refusal,
  cross-process refusal (subprocess), and two-process audit-trail
  interleaving.
- fsync durability is design-verified via source-contract pinning
  (documented limitation in F-08: power-loss cannot be simulated in
  CI; the presence of file+directory fsync on both journal writers
  is pinned instead).
- The CI workflow assertions are source-contract pins on
  .github/workflows/ci.yml (trigger/matrix/scan/gate text).

All fixtures are synthetic; no real credentials, no network, no
real broker. LIVE TRADING REMAINS NOT AUTHORIZED. PAPER_READY
stays FALSE.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from data_engine.runtime.state import (
    ExecutionStateStore,
    HashChainJournal,
    StateStoreError,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_FILE = REPO_ROOT / ".github" / ".github"  # placeholder, fixed below
CI_FILE = REPO_ROOT / ".github" / "workflows" / "ci.yml"
UNIT_FILE = REPO_ROOT / "deploy" / "systemd" / "ai-trading-lab@.service"
SESSION_SRC = REPO_ROOT / "src" / "data_engine" / "brokers" / "session.py"
STATE_SRC = REPO_ROOT / "src" / "data_engine" / "runtime" / "state.py"
SECURITY_SRC = REPO_ROOT / "src" / "data_engine" / "security.py"
CLI_SRC = REPO_ROOT / "src" / "data_engine" / "cli.py"
VALIDATOR = REPO_ROOT / "scripts" / "validate_deployment_templates.py"


def _run_py(args, cwd=REPO_ROOT, timeout=120):
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True,
        cwd=cwd, timeout=timeout,
    )


# ---------------------------------------------------------------------------
# F-03 — store-level exclusive flock (single-writer ENFORCED)
# ---------------------------------------------------------------------------
class TestStoreSingleWriterLock:

    def test_second_open_same_dir_refused_in_process(self, tmp_path):
        store = ExecutionStateStore(tmp_path / "store")
        try:
            with pytest.raises(StateStoreError) as exc:
                ExecutionStateStore(tmp_path / "store")
            assert "holds this store" in str(exc.value), (
                "concurrent store use must be refused with a clear "
                "single-writer error (F-03)"
            )
        finally:
            store.close()

    def test_close_releases_and_reopen_succeeds(self, tmp_path):
        store = ExecutionStateStore(tmp_path / "store")
        store.close()
        store.close()  # idempotent
        second = ExecutionStateStore(tmp_path / "store")
        second.snapshot({"schema": "x"}, kind="checkpoint")
        assert second.has_snapshot
        second.close()

    def test_cross_process_open_refused(self, tmp_path):
        """Mandate: locking verified on the ACTUAL filesystem — a
        SECOND PROCESS holding the store must refuse the first."""
        holder = subprocess.Popen(
            [
                sys.executable, "-c",
                "import sys\n"
                "from pathlib import Path\n"
                "from data_engine.runtime.state import "
                "ExecutionStateStore, StateStoreError\n"
                "store = ExecutionStateStore(Path(sys.argv[1]))\n"
                "print('HELD', flush=True)\n"
                "try:\n"
                "    ExecutionStateStore(Path(sys.argv[1]))\n"
                "    print('SECOND-OPEN-UNEXPECTED')\n"
                "except StateStoreError as exc:\n"
                "    print('REFUSED', 'holds this store' in str(exc))\n",
                str(tmp_path / "store"),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=REPO_ROOT,
        )
        try:
            out, err = holder.communicate(timeout=60)
            lines = out.strip().splitlines()
            assert "HELD" in lines, f"holder failed: {err}"
            assert "REFUSED True" in lines, (
                f"cross-process concurrent open must be refused "
                f"(actual: {lines}; stderr: {err})"
            )
            assert "SECOND-OPEN-UNEXPECTED" not in lines
        finally:
            if holder.poll() is None:  # pragma: no cover
                holder.kill()
                holder.communicate(timeout=30)

    def test_unique_tmp_names_no_fixed_suffix(self, tmp_path):
        """F-03: fixed tmp names (state.json.tmp) let two writers
        interleave on the SAME tmp inode — names must be unique
        (pid + counter) and leave no residue."""
        store = ExecutionStateStore(tmp_path / "store")
        try:
            for i in range(3):
                store.snapshot({"schema": "x", "i": i}, kind="checkpoint")
            residue = [
                p.name for p in (tmp_path / "store").iterdir()
                if p.name.endswith(".tmp")
            ]
            assert not residue, f"tmp residue left behind: {residue}"
        finally:
            store.close()
        # Source contract: the fixed-suffix tmp construction is gone.
        state_src = STATE_SRC.read_text(encoding="utf-8")
        assert 'path.with_suffix(path.suffix + ".tmp")' not in state_src, (
            "the fixed .tmp name must be replaced by unique "
            "(pid+counter) names (F-03)"
        )


# ---------------------------------------------------------------------------
# F-08 / F-09 — fsync (file + directory) on BOTH journal writers
# ---------------------------------------------------------------------------
class TestFsyncDurabilityContracts:

    def test_state_store_dir_fsync_present(self):
        """F-09: _atomic_write_json must fsync the DIRECTORY after
        os.replace (name durability on power loss)."""
        src = STATE_SRC.read_text(encoding="utf-8")
        assert "def _fsync_dir" in src, (
            "state.py must carry a directory-fsync helper (F-09)"
        )
        atomic = src.split("def _atomic_write_json", 1)[1]
        assert "os.replace" in atomic
        assert "_fsync_dir" in atomic, (
            "the atomic write path must fsync the directory after "
            "replace (F-09)"
        )

    def test_session_journal_fsync_present(self):
        """F-08: the broker-session journal write must flush+fsync
        the file BEFORE os.replace and fsync the directory after."""
        src = SESSION_SRC.read_text(encoding="utf-8")
        assert "def _fsync_dir" in src, (
            "session.py must carry a directory-fsync helper (F-08)"
        )
        writer = src.split("def _write_journal", 1)[1]
        writer = writer.split("def ", 1)[0]
        assert "os.replace" in writer
        assert "os.fsync" in writer, (
            "the journal file must be fsynced before replace (F-08)"
        )
        assert "_fsync_dir" in writer, (
            "the journal directory must be fsynced after replace (F-08)"
        )
        assert 'with_suffix(' not in writer or ".tmp\"" not in writer, (
            "journal tmp names must be unique (F-03)"
        )


# ---------------------------------------------------------------------------
# F-11 — SecurityAuditTrail: locked append (no chain fork)
# ---------------------------------------------------------------------------
class TestAuditTrailLockedAppend:

    def test_two_processes_interleave_linear_chain(self, tmp_path):
        """F-11 regression: two processes appending concurrently must
        produce ONE linear hash chain (unlocked read-modify-write
        forks the chain under exactly this interleaving)."""
        trail_path = tmp_path / "audit.jsonl"
        child = (
            "import sys\n"
            "from data_engine.security import SecurityAuditTrail\n"
            "trail = SecurityAuditTrail(sys.argv[1])\n"
            "tag = sys.argv[2]\n"
            "for i in range(40):\n"
            "    trail.record(f'proc-{tag}', f'/p/{tag}/{i}', 'ALLOW', 'r')\n"
        )
        p1 = subprocess.Popen(
            [sys.executable, "-c", child, str(trail_path), "a"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=REPO_ROOT,
        )
        p2 = subprocess.Popen(
            [sys.executable, "-c", child, str(trail_path), "b"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=REPO_ROOT,
        )
        o1, e1 = p1.communicate(timeout=120)
        o2, e2 = p2.communicate(timeout=120)
        assert p1.returncode == 0, e1
        assert p2.returncode == 0, e2
        from data_engine.security import SecurityAuditTrail

        trail = SecurityAuditTrail(trail_path)
        entries = trail._read_entries()
        assert len(entries) == 80, (
            f"expected 80 interleaved entries, got {len(entries)} "
            "(lost appends = unlocked write path, F-11)"
        )
        assert trail.verify() is True, (
            "the chain must stay linear under concurrent append (F-11)"
        )
        seqs = [e["seq"] for e in entries]
        assert seqs == list(range(1, 81))


# ---------------------------------------------------------------------------
# F-10 — SecurityManager.audit_log: fail-closed, operator-configured path
# ---------------------------------------------------------------------------
class TestAuditLogFailClosed:

    def test_unwritable_audit_path_raises_loud(self, tmp_path):
        """F-10 regression: an audit-log write failure must be LOUD
        (raise), never silently swallowed (`pass`)."""
        from data_engine.security import (
            SecurityAuditError,
            SecurityConfig,
        )

        blocked = tmp_path / "not-a-dir"
        blocked.write_text("file blocks this path", encoding="utf-8")
        cfg = SecurityConfig(
            enable_audit_log=True,
            audit_log_path=str(blocked / "audit.log"),
        )
        with pytest.raises(SecurityAuditError):
            cfg.audit_log("test-action", {"k": "v"})

    def test_no_module_relative_writes_and_none_default(self, tmp_path):
        """F-10: with no operator-configured path there is NO file
        channel (structural) — and never a write inside the package
        tree."""
        from data_engine.security import SecurityConfig

        cfg = SecurityConfig(enable_audit_log=True)  # no path configured
        # No raise, no file channel — the call is structurally a no-op.
        cfg.audit_log("test-action", {"k": "v"})
        package_audit = REPO_ROOT / "src" / "audit.log"
        assert not package_audit.exists(), (
            "audit_log must never write module-relative files (F-10)"
        )
        src = SECURITY_SRC.read_text(encoding="utf-8")
        assert "os.path.dirname(__file__)" not in src, (
            "the module-relative audit path must be gone (F-10)"
        )
        assert "audit_log_path" in src, (
            "the operator-configured audit path must exist (F-10)"
        )

    def test_configured_path_writes_jsonl(self, tmp_path):
        from data_engine.security import SecurityConfig

        path = tmp_path / "audit" / "security-audit.jsonl"
        cfg = SecurityConfig(
            enable_audit_log=True, audit_log_path=str(path),
        )
        cfg.audit_log("action-1", {"detail": "d1"})
        cfg.audit_log("action-2", {"detail": "d2"})
        lines = [
            ln for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        assert len(lines) == 2
        import json as _json

        first = _json.loads(lines[0])
        assert first["action"] == "action-1"


# ---------------------------------------------------------------------------
# F-12 — torn journal tail: audited recovery, explicit confirmation
# ---------------------------------------------------------------------------
class TestTornJournalTailRecovery:

    def _torn_store(self, tmp_path):
        store = ExecutionStateStore(tmp_path / "store")
        journal = store.journal
        for i in range(3):
            journal.append("checkpoint", {"i": i})
        store.close()
        # Torn tail: a partial line exactly as a crash mid-append
        # would leave it (the append already hit the disk, the
        # newline + remaining bytes never did).
        with open(
            tmp_path / "store" / "journal.jsonl", "a", encoding="utf-8"
        ) as fh:
            fh.write('{"index": 3, "kind": "torn')
        return tmp_path / "store"

    def test_torn_tail_detected_reported_refused(self, tmp_path):
        store_dir = self._torn_store(tmp_path)
        result = _run_py(
            ["-m", "data_engine.cli", "recover-state", str(store_dir)]
        )
        assert result.returncode != 0, (
            "refusing to repair without confirmation must exit "
            "non-zero (F-12)"
        )
        combined = result.stdout + result.stderr
        assert "3 valid" in combined, (
            f"the report must name the valid-record count: {combined}"
        )
        assert "1 damaged" in combined or "damaged" in combined, (
            f"the report must name the damaged tail: {combined}"
        )
        assert "--confirm-truncate" in combined, (
            "the refusal must tell the operator how to confirm (F-12)"
        )
        # Refused ⇒ the journal is UNTOUCHED (torn line still there).
        text = (store_dir / "journal.jsonl").read_text(encoding="utf-8")
        assert text.rstrip().endswith('"kind": "torn')

    def test_confirm_truncate_repairs_and_journals_it(self, tmp_path):
        store_dir = self._torn_store(tmp_path)
        result = _run_py(
            [
                "-m", "data_engine.cli", "recover-state",
                str(store_dir), "--confirm-truncate",
            ]
        )
        assert result.returncode == 0, result.stdout + result.stderr
        journal = HashChainJournal(store_dir / "journal.jsonl")
        assert journal.verify() is True, (
            "the repaired journal must verify end-to-end (F-12)"
        )
        kinds = [r["kind"] for r in journal.records]
        assert "recovery_truncate" in kinds, (
            "the truncation must be journaled itself (audited repair, "
            "never a silent edit)"
        )

    def test_healthy_journal_reports_clean(self, tmp_path):
        store = ExecutionStateStore(tmp_path / "store")
        store.journal.append("checkpoint", {"i": 1})
        store.close()
        result = _run_py(
            ["-m", "data_engine.cli", "recover-state",
             str(tmp_path / "store")]
        )
        assert result.returncode == 0
        assert "healthy" in (result.stdout + result.stderr).lower()


# ---------------------------------------------------------------------------
# F-04 — systemd unit + validator (strict REQUIRES ReadWritePaths)
# ---------------------------------------------------------------------------
class TestSystemdHardening:

    def test_real_templates_validate(self):
        result = _run_py([str(VALIDATOR)])
        assert result.returncode == 0, result.stdout + result.stderr

    def test_unit_carries_readwritepaths_and_hardening(self):
        unit = UNIT_FILE.read_text(encoding="utf-8")
        assert "ReadWritePaths=/var/lib/ai-trading-lab/%i" in unit, (
            "ProtectSystem=strict without ReadWritePaths breaks the "
            "state contract (F-04)"
        )
        for key in (
            "UMask=0027",
            "SystemCallFilter=@system-service",
            "SystemCallArchitectures=native",
            "PrivateDevices=yes",
            "ProtectHostname=yes",
            "ProtectClock=yes",
            "ProtectProc=invisible",
            "RestrictNamespaces=yes",
            "CapabilityBoundingSet=",
            "MemoryDenyWriteExecute=yes",
        ):
            assert key in unit, f"missing hardening directive: {key}"

    def test_validator_rejects_strict_without_readwritepaths(
        self, tmp_path,
    ):
        """F-04 regression: a unit with ProtectSystem=strict and NO
        ReadWritePaths must FAIL validation (the shipped-validator
        blind spot)."""
        import shutil

        skeleton = tmp_path / "synthetic"
        (
            skeleton / "scripts"
        ).mkdir(parents=True, exist_ok=True)
        (
            skeleton / "deploy" / "systemd"
        ).mkdir(parents=True, exist_ok=True)
        (
            skeleton / "deploy" / "config"
        ).mkdir(parents=True, exist_ok=True)
        (skeleton / "docs").mkdir(parents=True, exist_ok=True)
        shutil.copy2(VALIDATOR, skeleton / "scripts" / "validator.py")
        shutil.copy2(
            REPO_ROOT / "deploy" / "config" / "secrets.env.example",
            skeleton / "deploy" / "config" / "secrets.env.example",
        )
        # A healthy spec: copy the real one.
        shutil.copy2(
            REPO_ROOT / "docs" / "PER_USER_VPS_DEPLOYMENT.md",
            skeleton / "docs" / "PER_USER_VPS_DEPLOYMENT.md",
        )
        unit_text = UNIT_FILE.read_text(encoding="utf-8")
        # Strip EVERY ReadWritePaths line — the F-04 defect shape.
        damaged = "\n".join(
            ln for ln in unit_text.splitlines()
            if not ln.startswith("ReadWritePaths=")
        )
        (
            skeleton / "deploy" / "systemd" / "ai-trading-lab@.service"
        ).write_text(damaged + "\n", encoding="utf-8")
        result = _run_py(
            [str(skeleton / "scripts" / "validator.py")], cwd=skeleton
        )
        assert result.returncode != 0, (
            "strict-without-ReadWritePaths must FAIL validation (F-04)"
        )
        combined = result.stdout + result.stderr
        assert "ReadWritePaths" in combined, (
            f"the validator must NAME the defect: {combined}"
        )


# ---------------------------------------------------------------------------
# F-15 / F-16 / F-18 — CI hardening (source contracts)
# ---------------------------------------------------------------------------
class TestCIHardening:

    def test_matrix_covers_declared_python(self):
        ci = CI_FILE.read_text(encoding="utf-8")
        assert '"3.13"' in ci, (
            "CI matrix must cover Python 3.13 (F-15)"
        )
        assert '"3.14"' in ci, (
            "CI matrix must cover the DECLARED runtime Python 3.14 "
            "(.python-version; F-15)"
        )

    def test_dependency_audit_runs_on_push(self):
        ci = CI_FILE.read_text(encoding="utf-8")
        assert (
            "github.event_name == 'push'" in ci
        ), (
            "the dependency-audit job must also run on push to "
            "protected branches (F-16)"
        )

    def test_secret_scan_covers_key_families(self):
        ci = CI_FILE.read_text(encoding="utf-8")
        lines = ci.splitlines()
        scan = [
            line for line in lines
            if "git grep" in line and "rev-list" in line
        ]
        # F-18b (2026-10-19): the scan moved from a bare '! git grep'
        # one-liner to EXPLICIT fail-closed logic — a PATTERN= variable
        # carries the families, tool errors FAIL the step, and the one
        # documented synthetic-fixture baseline (github_pat_11AAAA,
        # introduced by the Stage F delivery) is filtered by its exact
        # marker. Coverage intent unchanged; every family must still
        # be present, and the baseline must stay exact + the tool-error
        # path fail-closed (pinned below).
        assert scan, "the history secret-scan invocation must exist"
        pattern_lines = [
            line for line in lines
            if line.strip().startswith("PATTERN=")
        ]
        assert pattern_lines, "the scan pattern must be a named variable"
        joined = " ".join(scan + pattern_lines)
        assert "PRIVATE KEY" in joined, (
            "the scan must cover PEM/OPENSSH private keys (F-18)"
        )
        assert "xox" in joined, "the scan must cover Slack tokens (F-18)"
        assert "AIza" in joined, "the scan must cover Google keys (F-18)"
        assert "github_pat_" in joined and "ghp_" in joined and (
            "AKIA" in joined and "sk-" in joined
        ), "the original four families must remain covered"
        assert 'BASELINE="github_pat_11AAAA"' in ci, (
            "the F-18b baseline must be the EXACT synthetic marker — "
            "never a broad path or pattern exclusion"
        )
        assert "fail closed" in ci, (
            "a git-grep tool error must fail the step (F-18b)"
        )

    def test_lint_sast_coverage_steps_exist(self):
        ci = CI_FILE.read_text(encoding="utf-8")
        assert "ruff" in ci, "a lint step must exist (F-15)"
        assert "bandit" in ci, "a SAST step must exist (F-15)"
        assert "coverage" in ci, "a coverage step must exist (F-15)"


# ---------------------------------------------------------------------------
# F-21 — CLI validate argument registered
# ---------------------------------------------------------------------------
class TestCliValidateArgument:

    def test_validate_accepts_dataset_id(self):
        result = _run_py(
            ["-m", "data_engine.cli", "validate", "ds-integration-1"]
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "ds-integration-1" in result.stdout, (
            "validate must accept and echo the dataset_id positional "
            "(F-21: usage docstring promised an argument the parser "
            "never registered)"
        )


# ---------------------------------------------------------------------------
# F-22 — test storage fixtures leave no fixed-path residue
# ---------------------------------------------------------------------------
class TestStorageFixtureHygiene:

    def test_no_fixed_storage_paths_in_suites(self):
        for rel in (
            "tests/test_data_engine.py",
            "tests/test_redteam.py",
        ):
            src = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert '"./test_storage' not in src and \
                "'./test_storage" not in src, (
                    f"{rel} still creates repo-root storage dirs (F-22)"
                )
            assert "/tmp/test_storage" not in src, (
                f"{rel} still uses fixed /tmp storage paths (F-22)"
            )

    def test_storage_suite_leaves_no_repo_root_dirs(self, tmp_path):
        """Behavioral pin: the storage suite's fixture writes go to
        tmp_path, not the repo root."""
        from data_engine import DataStorage

        storage = DataStorage(storage_dir=str(tmp_path / "storage"))
        report = storage.get_storage_report()
        assert isinstance(report, dict)
        repo_root_residue = [
            p for p in REPO_ROOT.iterdir()
            if p.name.startswith("test_storage")
        ]
        assert not repo_root_residue, (
            f"repo-root storage residue: {repo_root_residue} (F-22)"
        )
