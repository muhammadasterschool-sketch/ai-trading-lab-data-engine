# 08 — Commit & CI Record

## 1. Baseline (before this work)

| Item | Value |
|---|---|
| Repository | `github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine` |
| Base branch | `main` |
| Base commit | `4cc6782c9804fd689fe524f0d54b1a01817a35c6` (2026-10-22 23:14 +05:00) |
| Working tree at start | clean |
| CI at base | `ci.yml` success on `4cc6782`; `build-apk` success ×2 (GitHub Actions API, checked 2026-10-24) |
| Baseline suite (audit run at `4cc6782`) | 2909 passed, 3 skipped, 0 failed, 179.94 s, exit 0 |
| Baseline gates | `PAPER_READINESS: BLOCKED`, `LIVE_AUTHORIZATION: NOT_AUTHORIZED`, 32 gates (3 HUMAN / 6 COMPOSITION_ROOT / 23 OPERATOR_RECORDED) |

## 2. This work (feature branch `feat/exness-mt5-demo-market-data`)

| Commit | Content |
|---|---|
| `169b655` | baseline + file-level implementation plan (plan-only, pre-edit) |
| `79f3f49` | the genuine feed: `mt5_terminal.py`, `mt5_symbol_map.py`, `mt5_market_data.py`, `require_demo` hardening, `mt5-probe` CLI, UNVETTED candidate, 85 new tests |
| `fc2aace` | deliverables 01–07 |
| `<final>` | this record (deliverable 08) — see `git log` for the exact tip SHA |

Full-suite evidence AFTER the change (this host, Python 3.12.15, uv):
**2994 passed, 8 skipped, 0 failed, 177.91 s, exit 0** — the +85 pass
delta is exactly the new tests; the +5 skips are exactly the
genuine-terminal integration checks (BLOCKED_ON_OPERATOR_ENV).
Post-change `status --gates` output is identical to baseline.

## 3. CI result

**NOT RUN — honest status.** This workspace has no write credentials
for the repository (and must never request them in chat), so the
feature branch could not be pushed and GitHub Actions never executed
on it. NOTHING in this document may be read as a CI pass for the new
commits.

The moment the owner pushes the branch (or a PR is opened), the
existing workflow runs automatically:

```bash
# from a machine with push rights:
git remote add workspace <path-to-bundle>      # or apply the patch files
git fetch workspace feat/exness-mt5-demo-market-data
git checkout feat/exness-mt5-demo-market-data
git push -u origin feat/exness-mt5-demo-market-data
# then verify: https://github.com/<owner>/<repo>/actions
```

Artifacts for that push accompany this record:
`mt5-integration-feature.bundle` (git bundle, full branch) and
`0001..000N-*.patch` (format-patch series).

Expected CI shape: the ubuntu matrix (3.11–3.14) runs the full suite
including the 5 integration checks as SKIPS (BLOCKED_ON_OPERATOR_ENV) —
the same honest shape as the local run.

## 4. Governance statement for the record

- `PAPER_READY` = **FALSE** (unchanged); `LIVE_AUTHORIZATION` =
  **NOT_AUTHORIZED** (unchanged); 32-gate chain untouched.
- `exness-mt5-demo` source candidate: **UNVETTED**; no approval
  recorded anywhere; `BLOCKED_MARKETS` unchanged.
- 30-day soak + preflight rules: unchanged, not started.
- No live-trading surface, flag or order path was introduced (see
  deliverable 04's negative-test evidence).
- No production-readiness claim is made anywhere in this work.
