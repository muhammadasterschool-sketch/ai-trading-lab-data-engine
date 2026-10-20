"""FIX-12 (B-P1-09) — cross-platform import discipline for the
POSIX-locked submission ledger.

The audit found ``submission_ledger.py`` had a TOP-LEVEL
``import fcntl``: on Windows CPython the whole module failed at
IMPORT time (ModuleNotFoundError) — making the documented
constructor-level fail-closed refusal dead code and breaking every
importer (composition root, CLI, tests) on that platform.

FIX-12 makes the import conditional (the same pattern
``runtime/state.py`` already used). These tests pin:

- the module IMPORTS cleanly when ``fcntl`` is unavailable (the
  old code crashed here);
- the ledger CONSTRUCTOR then refuses with the documented
  fail-closed message (never a silent unguarded fallback);
- the module still imports with fcntl present (normal POSIX path).

No Windows host is available in this environment — these tests
SIMULATE the absence deterministically (blocked import via
``sys.modules``) rather than claiming Windows-host verification (see
the Windows platform compatibility report: Windows-host runs remain
NOT TESTED; WSL/Linux runs are the tested posture).
"""

import builtins
import importlib
import sys
from pathlib import Path

import pytest

from data_engine.runtime.submission_ledger import (
    SubmissionLedger,
    SubmissionLedgerError,
    SubmissionPolicy,
)


class TestFcntlImportDiscipline:

    def test_module_imports_without_fcntl(self, monkeypatch, tmp_path):
        """THE FIX-12 regression: with fcntl unimportable, importing
        data_engine.runtime.submission_ledger must SUCCEED (the old
        top-level ``import fcntl`` crashed right here)."""
        # Simulate a platform without fcntl: block the import.
        real_import = builtins.__import__

        def no_fcntl_import(name, *args, **kwargs):
            if name == "fcntl":
                raise ImportError("No module named 'fcntl' (simulated)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_fcntl_import)
        monkeypatch.delitem(sys.modules, "fcntl", raising=False)
        monkeypatch.delitem(
            sys.modules, "data_engine.runtime.submission_ledger",
            raising=False,
        )
        try:
            module = importlib.import_module(
                "data_engine.runtime.submission_ledger"
            )
            assert module is not None
            assert module._HAVE_FCNTL is False
        finally:
            monkeypatch.undo()

    def test_constructor_refuses_without_fcntl(self, monkeypatch,
                                               tmp_path):
        """With fcntl unavailable the ledger REFUSES TO CONSTRUCT with
        the documented fail-closed message (not an import crash, not
        a silently-unlocked ledger)."""
        real_import = builtins.__import__

        def no_fcntl_import(name, *args, **kwargs):
            if name == "fcntl":
                raise ImportError("No module named 'fcntl' (simulated)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_fcntl_import)
        monkeypatch.delitem(sys.modules, "fcntl", raising=False)
        monkeypatch.delitem(
            sys.modules, "data_engine.runtime.submission_ledger",
            raising=False,
        )
        try:
            module = importlib.import_module(
                "data_engine.runtime.submission_ledger"
            )
            # NOTE: catch the RE-IMPORTED module's exception class (a
            # fresh import creates distinct class objects).
            with pytest.raises(module.SubmissionLedgerError) as excinfo:
                module.SubmissionLedger(
                    Path(tmp_path) / "ledger.json",
                    policy=module.SubmissionPolicy(),
                )
            message = str(excinfo.value)
            assert "POSIX flock" in message
            assert "fail closed" in message
            assert "WSL/Linux" in message or "Windows" in message
        finally:
            monkeypatch.undo()

    def test_posix_path_still_works(self, tmp_path):
        """The normal POSIX path is unchanged (flock present, ledger
        constructs and enforces its capacity policy)."""
        ledger = SubmissionLedger(
            Path(tmp_path) / "ledger.json",
            policy=SubmissionPolicy(),
        )
        assert ledger is not None
        from data_engine.runtime.submission_ledger import _HAVE_FCNTL

        assert _HAVE_FCNTL is True  # this environment is POSIX

    def test_state_store_module_already_follows_the_pattern(self):
        """runtime/state.py set the pattern FIX-12 copies: conditional
        import with an msvcrt fallback — pin it so the two modules
        cannot drift apart."""
        from data_engine.runtime import state as state_module

        assert hasattr(state_module, "_HAVE_FCNTL")
        assert state_module._lock_mod is not None
