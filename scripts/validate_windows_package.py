#!/usr/bin/env python3
"""Validate a built Windows package zip (Stage E supplement, U-26).

Validates the zip produced by ``scripts/build_windows_package.py``
(the deterministic wheel+source package). Fail-closed: ANY failure
exits non-zero. Checks:

1. STRUCTURE — exactly one top-level package directory; every
   mandated component present (install/run-tests/run-paper scripts,
   README-WINDOWS-PACKAGE.md, hash-pinned requirements-windows.txt,
   SHA256SUMS.txt, the built wheel, the full source/ tree with
   pyproject + engine package).
2. INTEGRITY — SHA256SUMS.txt covers EVERY other member and every
   recorded digest MATCHES (tamper-evident package).
3. SAFETY — no forbidden members (.git/.venv/__pycache__/*.pyc/
   logs/runtime state/credentials), no unsafe paths (absolute,
   traversal, drive letters), no symlink members, no
   credential-shaped content in text members, zip-bomb guards.
4. VERSION AGREEMENT — wheel filename version == source pyproject
   version == engine ``__version__`` (the package names ONE version).
5. POSTURE — the .ps1 scripts are fail-closed
   (``$ErrorActionPreference = "Stop"``) and the README carries the
   honest statements (LIVE TRADING IS NOT AUTHORIZED, PAPER_READY
   stays FALSE, NOT VERIFIED on Windows).

Usage:
    python scripts/validate_windows_package.py <zip-path>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from data_engine import __version__  # noqa: E402

REQUIRED_SUFFIXES = (
    "install.ps1",
    "run-tests.ps1",
    "run-paper.ps1",
    "run-monitor.ps1",
    "local-monitor-config.template.json",
    "push-bars.ps1",
    "README-WINDOWS-PACKAGE.md",
    "requirements-windows.txt",
    "SHA256SUMS.txt",
    "source/pyproject.toml",
    "source/uv.lock",
    "source/src/data_engine/__init__.py",
    "source/src/data_engine/cli.py",
    "source/src/data_engine/runtime/pairing.py",
    "source/src/data_engine/runtime/announce.py",
    "source/scripts/windows_smoke_test.py",
)

FORBIDDEN_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"(^|/)\.git(/|$)",
        r"(^|/)\.venv(/|$)",
        r"(^|/)__pycache__(/|$)",
        r"\.pyc$",
        r"\.log$",
        r"(^|/)state\.json$",
        r"(^|/)journal\.jsonl$",
        r"(^|/)ledger\.json$",
        r"(^|/)(id_rsa|id_ed25519|\.aws|\.ssh)(/|$|\.)",
        r"(^|/)\.env$",
        r"(^|/)\.git-credentials$",
    )
)

CREDENTIAL_CONTENT = re.compile(
    r"github_pat_[A-Za-z0-9_]{20,}"
    r"|ghp_[A-Za-z0-9]{30,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{20,}"
    r"|AIza[0-9A-Za-z_-]{35}"
    r"|-----BEGIN (RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"
)

TEXT_SUFFIXES = (
    ".py", ".ps1", ".md", ".txt", ".toml", ".json", ".yml", ".yaml",
    ".cfg", ".ini", ".lock", ".example", ".sums", ".dart", ".yaml-pinned",
)

MAX_TOTAL_UNCOMPRESSED = 4 * 1024 * 1024 * 1024  # 4 GiB (full source pkg)
MAX_MEMBER_RATIO = 200

#: v4.0: the invitation-code plaintext probe. When the owner-side
#: validation run exports AITL_INVITE_PROBE (the real local default
#: code), the validator asserts the probe appears in NO text member —
#: the strongest possible no-plaintext-in-package pin. CI runs
#: WITHOUT the probe (structural checks only): an honest, recorded
#: limitation, since committing the probe string would itself be a
#: plaintext leak.
INVITE_PROBE_ENV = "AITL_INVITE_PROBE"

#: v4.0: shape pins for the committed local-monitor config template
#: (salted-hash invitation storage — never plaintext).
_HEX_RE = re.compile(r"^[0-9a-f]+$")


@dataclass
class ValidationReport:
    ok: bool = True
    failures: list = field(default_factory=list)
    checks: list = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.ok = False
        self.failures.append(message)

    def passed(self, message: str) -> None:
        self.checks.append(message)


def validate_zip(zip_path: Path) -> ValidationReport:
    report = ValidationReport()
    if not zip_path.is_file():
        report.fail(f"zip not found: {zip_path}")
        return report

    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        report.fail(f"not a valid zip: {exc}")
        return report

    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        names = [i.filename for i in infos]

        # -- 3a. path safety + forbidden members (FIRST — a malicious
        # path must never be masked by a structural early return) ----
        forbidden = sorted({
            n for n in names
            if any(p.search(n) for p in FORBIDDEN_PATTERNS)
        })
        if forbidden:
            report.fail(f"forbidden members present: {forbidden[:10]}")
        else:
            report.passed("no forbidden members")

        unsafe = [
            n for n in names
            if n.startswith("/")
            or re.match(r"^[A-Za-z]:", n)
            or ".." in Path(n).parts
            or "\\" in n
        ]
        if unsafe:
            report.fail(f"unsafe member paths: {unsafe[:10]}")
        else:
            report.passed("all member paths relative + traversal-free")
        symlinked = [
            i.filename for i in infos
            if (i.external_attr >> 16) & 0o170000 == 0o120000
        ]
        if symlinked:
            report.fail(f"symlink members refused: {symlinked[:10]}")

        # -- 1. structure ---------------------------------------------
        roots = {n.split("/", 1)[0] for n in names}
        if len(roots) != 1 or "" in roots:
            report.fail(
                f"package must have exactly ONE top-level directory; "
                f"found: {sorted(roots)[:5]}"
            )
            return report
        pkg_root = next(iter(roots))
        suffixes = [n[len(pkg_root) + 1:] for n in names]
        missing = [
            req for req in REQUIRED_SUFFIXES
            if req not in suffixes
            and not (
                req.endswith(".whl-placeholder")  # never; explicit only
                or (req == "dist/" and any(s.startswith("dist/") for s in suffixes))
            )
        ]
        # the wheel: any member under dist/ ending .whl
        if not any(s.startswith("dist/") and s.endswith(".whl")
                   for s in suffixes):
            missing.append("dist/<engine wheel>")
        if missing:
            report.fail(f"missing required components: {missing}")
        else:
            report.passed(
                f"all {len(REQUIRED_SUFFIXES) + 1} required components "
                "present under " + pkg_root + "/"
            )

        # -- 2. SHA256SUMS integrity -----------------------------------
        sums_name = f"{pkg_root}/SHA256SUMS.txt"
        if sums_name in names:
            try:
                sums_text = zf.read(sums_name).decode("utf-8")
                # builder format (FIX-8): "<digest>  <rel>" per line —
                # the standard sha256sum convention emitted by
                # scripts/build_windows_package.py
                # (f"{digest}  {rel}"), so `sha256sum -c` also works.
                recorded: dict[str, str] = {}
                for line in sums_text.splitlines():
                    if not line.strip():
                        continue
                    digest, sep, rel = line.partition("  ")
                    if (
                        not sep
                        or len(digest) != 64
                        or any(c not in "0123456789abcdef" for c in digest)
                        or not rel.strip()
                    ):
                        raise ValueError(
                            f"malformed SHA256SUMS line: {line[:80]!r}"
                        )
                    recorded[rel.strip()] = digest
                others = [n for n in names if n != sums_name]
                rel_map = {n[len(pkg_root) + 1:]: n for n in others}
                uncovered = [
                    rel for rel, full in rel_map.items() if rel not in recorded
                ]
                extra = [
                    rel for rel in recorded if rel not in rel_map
                ]
                if uncovered:
                    report.fail(
                        f"SHA256SUMS.txt does not cover: {uncovered[:10]}"
                    )
                if extra:
                    report.fail(
                        f"SHA256SUMS.txt covers non-members: {extra[:10]}"
                    )
                mismatches = []
                for rel, full in rel_map.items():
                    if rel in recorded:
                        actual = hashlib.sha256(zf.read(full)).hexdigest()
                        if actual != recorded[rel]:
                            mismatches.append(rel)
                if mismatches:
                    report.fail(
                        f"SHA256SUMS.txt digest mismatches: {mismatches[:10]}"
                    )
                if not uncovered and not extra and not mismatches:
                    report.passed(
                        f"SHA256SUMS.txt covers + matches all "
                        f"{len(others)} packaged files"
                    )
            except (UnicodeDecodeError, ValueError) as exc:
                report.fail(f"SHA256SUMS.txt unreadable: {exc}")
        else:
            report.fail("SHA256SUMS.txt missing")

        # -- 3b. credential-shaped content -----------------------------
        offenders = []
        for info in infos:
            if info.file_size > 2 * 1024 * 1024:
                continue
            name = info.filename
            suffix = Path(name).suffix.lower()
            if suffix not in TEXT_SUFFIXES:
                continue
            try:
                text = zf.read(info).decode("utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            if CREDENTIAL_CONTENT.search(text):
                offenders.append(name)
        if offenders:
            report.fail(f"credential-shaped content in: {offenders[:10]}")
        else:
            report.passed("no credential-shaped content in text members")

        # -- 3c. v4.0 invitation-plaintext probe (owner-side, env-gated) --
        probe = os.environ.get(INVITE_PROBE_ENV, "").strip()
        if probe:
            probe_offenders = [
                info.filename
                for info in infos
                if info.file_size <= 2 * 1024 * 1024
                and Path(info.filename).suffix.lower() in TEXT_SUFFIXES
                and probe in zf.read(info).decode("utf-8", errors="ignore")
            ]
            if probe_offenders:
                report.fail(
                    f"invitation-code PLAINTEXT found in: "
                    f"{probe_offenders[:10]}"
                )
            else:
                report.passed(
                    f"invitation-code plaintext absent from all text "
                    f"members (probe: {len(probe)} chars)"
                )
        else:
            report.passed(
                "invitation-plaintext probe NOT SET "
                f"({INVITE_PROBE_ENV}) — structural checks only (CI posture)"
            )

        # -- 3d. v4.0 local-monitor template shape -----------------------
        template_name = f"{pkg_root}/local-monitor-config.template.json"
        if template_name in names:
            template_failures = []
            try:
                template = json.loads(
                    zf.read(template_name).decode("utf-8")
                )
            except (ValueError, UnicodeDecodeError) as exc:
                template_failures.append(f"template unreadable: {exc}")
                template = None
            if isinstance(template, dict):
                if template.get("version") != 1:
                    template_failures.append("template version != 1")
                if not isinstance(template.get("enabled"), bool):
                    template_failures.append("template enabled not boolean")
                salt = template.get("salt_hex")
                if not (
                    isinstance(salt, str)
                    and len(salt) == 32
                    and _HEX_RE.fullmatch(salt)
                ):
                    template_failures.append("template salt_hex not 32-hex")
                digest = template.get("code_sha256_hex")
                if not (
                    isinstance(digest, str)
                    and len(digest) == 64
                    and _HEX_RE.fullmatch(digest)
                ):
                    template_failures.append(
                        "template code_sha256_hex not 64-hex"
                    )
                cap = template.get("max_attempts_per_minute")
                if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= 1000:
                    template_failures.append("template attempts cap invalid")
            elif template is None and not template_failures:
                template_failures.append("template is not a JSON object")
            if not isinstance(template, dict) and not template_failures:
                template_failures.append("template is not a JSON object")
            if template_failures:
                report.fail(
                    f"local-monitor template invalid: {template_failures}"
                )
            else:
                report.passed(
                    "local-monitor template carries a valid salted hash "
                    "(no plaintext code anywhere in it)"
                )

        # -- 4. version agreement --------------------------------------
        version_failures = []
        wheels = [
            s for s in suffixes
            if s.startswith("dist/") and s.endswith(".whl")
        ]
        for wheel in wheels:
            m = re.search(
                r"-([0-9]+\.[0-9]+\.[0-9]+[^/]*)-py3-none-any\.whl$",
                "/" + wheel,
            )
            if not m:
                version_failures.append(f"unparseable wheel name: {wheel}")
            elif m.group(1) != __version__:
                version_failures.append(
                    f"wheel {m.group(1)} != engine {__version__}"
                )
        pyproject_name = f"{pkg_root}/source/pyproject.toml"
        if pyproject_name in names:
            pyproject = zf.read(pyproject_name).decode("utf-8")
            m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
            if not m:
                version_failures.append("source pyproject has no version")
            elif m.group(1) != __version__:
                version_failures.append(
                    f"source pyproject {m.group(1)} != engine {__version__}"
                )
        if version_failures:
            report.fail(f"version disagreement: {version_failures}")
        else:
            report.passed(f"version agreement: {__version__} everywhere")

        # -- zip-bomb guards -------------------------------------------
        total = sum(i.file_size for i in infos)
        if total > MAX_TOTAL_UNCOMPRESSED:
            report.fail(f"total uncompressed {total:,} exceeds bound")
        ratio_offenders = [
            i.filename for i in infos
            if i.compress_size > 0
            and i.file_size / max(i.compress_size, 1) > MAX_MEMBER_RATIO
        ]
        if ratio_offenders:
            report.fail(f"suspicious compression ratios: {ratio_offenders[:10]}")
        else:
            report.passed(f"compression sane ({total:,} bytes uncompressed)")

        # -- 5. posture pins -------------------------------------------
        posture_failures = []
        for script in (
            "install.ps1",
            "run-tests.ps1",
            "run-paper.ps1",
            "run-monitor.ps1",
        ):
            member = f"{pkg_root}/{script}"
            if member not in names:
                continue
            body = zf.read(member).decode("utf-8", errors="ignore")
            if "$ErrorActionPreference = \"Stop\"" not in body:
                posture_failures.append(
                    f"{script}: ErrorActionPreference not Stop"
                )
        readme_name = f"{pkg_root}/README-WINDOWS-PACKAGE.md"
        if readme_name in names:
            readme = zf.read(readme_name).decode("utf-8", errors="ignore")
            flat = " ".join(readme.split())
            for phrase in (
                "LIVE TRADING IS NOT AUTHORIZED",
                "PAPER_READY stays FALSE",
                "NOT VERIFIED",
            ):
                if phrase not in flat:
                    posture_failures.append(
                        f"README missing honest statement: {phrase!r}"
                    )
        if posture_failures:
            report.fail(f"posture pins failed: {posture_failures}")
        else:
            report.passed("fail-closed posture pins present")

    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path", type=Path)
    args = parser.parse_args(argv)
    report = validate_zip(args.zip_path)
    for line in report.checks:
        print(f"PASS  {line}")
    for line in report.failures:
        print(f"FAIL  {line}")
    print(
        "VALIDATION " + ("OK" if report.ok else "FAILED")
        + f" ({len(report.checks)} passed, {len(report.failures)} failed)"
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
