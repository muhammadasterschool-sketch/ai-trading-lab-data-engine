# 30-DAY PAPER SOAK — RUNBOOK (NOT STARTED — requires explicit owner authorization)

**This soak must not start automatically. It is a separately authorized, paper-only
activity. Nothing in this runbook authorizes it.**

## Preconditions (all MUST be green before asking the owner)

1. All readiness gates 1–22 in `docs/READINESS-GATES.md` PASS (currently 3, 17, 21 are
   NOT RUN / PARTIAL — the soak cannot be requested yet).
2. Candidate APK installed and on-device checklist (`docs/ANDROID-OPERATIONS.md`)
   completed and evidenced (screenshots + timestamps).
3. Source approvals current: Yahoo ACTIVE_LEGACY, Binance owner-approved (if the soak
   uses it), MT5 bridge OFF or demo-verified.
4. Risk policy digest recorded (settings dump with version).
5. Monitoring ready: notifications work on-device, coverage dashboards reachable.

## Configuration to record at start (immutable evidence, stored on-device + export)

- start_ts (UTC), app version + versionCode, commit SHA, APK SHA-256
- settings digest (engine + risk + feed + binance keys), risk-policy version
- source approval snapshot, watchlist, universe counts

## Daily protocol (paper only)

1. Engine runs continuously (FGS + watchdog); each loop logs ENGINE activity.
2. Daily: export `/api/audit.csv` + coverage snapshot; append to the soak log.
3. Any interruption (process death, reboot, network outage, kill switch, stale feed):
   record interruption_ts, reason, recovery_ts. **Interrupted days are NOT soak days.**
4. Any crash → capture logcat, do not restart silently; record and assess.

## Interruption rules (fail-closed)

- Engine down > 15 min or evidence gap > 1 collection interval → day invalidated.
- Data source stale > threshold for > 2h cumulative → day invalidated.
- Any governance invariant violated (bridge ON without owner, admin-gate bypass) →
  soak aborted, incident report required.

## Completion

- 30 CLEAN days (no invalidation) + complete evidence chain → readiness review.
- PAPER_READY can then be proposed to the owner. LIVE trading remains a separate,
  explicit, human authorization that this project's tooling can never self-grant.

## Current status

**NOT STARTED.** Start timestamps: none. Configuration digest: none. Incidents: n/a.
No soak code paths were altered by v3.1; the runbook is documentation only.
