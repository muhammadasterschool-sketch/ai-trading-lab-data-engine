# ROLLBACK — procedures for every artifact class

## 1. APK (phone)

- Keep the previous APK before installing a candidate. This project preserves all
  prior artifacts (v3.0.1 remains the live download; v3.0.2/v3.0.3/v3.1.0 candidates
  are separate files — nothing overwrites them).
- Rollback = reinstall the previous APK. Same signing identity (CN=AI Trading Lab) →
  installs over. App data (SQLite) survives; DB migrations are forward-only: an OLD
  app version opening a NEW v8 database can fail — if downgrading below v3.1, clear
  app data (paper DB is reproducible state, no real funds involved) or accept
  re-onboarding.
- Verify every APK before install: `apksigner verify` + SHA-256 against the checksum
  manifest (`RELEASE-v3.1.0-CANDIDATE.md`).

## 2. Git

- `main` is untouched (still `f3b8bda2`, v3.0.1). Feature work lives on
  `feat/v3.1-multi-broker-market-data` (based on `feat/v3.0.2-p0-loopback-security`).
- To abandon v3.1: delete the branch / stop deploying the candidate. `main` never
  needed rollback.
- To undo a specific v3.1 change on the branch: `git revert <sha>` (forward-only
  revert commits; history rewrites and force-pushes are forbidden by governance).
- Backup branch `backup-v12-local` preserved locally; never touched.

## 3. Database (v7 → v8)

- Migration adds three NEW tables only (idempotent CREATE IF NOT EXISTS); no existing
  table/column was altered or dropped, no data rewritten.
- Rollback for the data layer = stop using the Binance tables (set
  `binance_enabled=0`) or clear app data (paper state only).
- Pre-upgrade backup: Android debuggable builds allow `adb backup`; production users:
  export audit.csv + settings screenshots before upgrade if desired.

## 4. Settings / governance

- All settings are plain rows; previous values recorded in the logs table
  (`*_SET` events with values). Restore by re-entering the prior value as owner.
- `bridge_live` defaults OFF; if it was ever enabled, turn it OFF from owner Control.

## 5. Release artifacts

- Downloads page keeps serving v3.0.1 until the owner approves publishing a new
  version. Publishing = copying the candidate into `public/downloads/` + updating
  `downloads.html` (deployed in a separate, reviewable commit).
- Checksum manifests ship beside every artifact; verify before AND after copying.
