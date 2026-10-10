# KEYED-MAC CUSTODY DECISION RECORD

**Document ID:** GOV-KMC-001 · **Version:** 1.0.0 · **Date:** 2026-10-10
**Status:** DECIDED + MECHANISM IMPLEMENTED + **CUSTODY NOT
OPERATIONAL** — no key has been provisioned, none was invented, and
operational status is claimed ONLY after genuine secure provisioning,
custody, rotation, and verification are satisfied (operator §1.5).
**Resolves:** the P2 open-blocker register KEYED-MAC row ("custody
policy undecided — human decision record + keyed-chain implementation
+ tests") and the final report §13.5/§15.6 item.

---

## 1. The Threat Being Closed

`P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md` (KEYED-MAC row,
demonstrated by test): the nine audit ledgers chain with UNKEYED
SHA-256 — tamper-EVIDENT against partial edits, but re-forgeable
end-to-end by an attacker who rewrites the FULL history (every link
recomputes without any secret). Accepted threat model until custody
was decided.

## 2. Operator Decision (verbatim evidence)

> "Keyed-MAC custody: I authorize implementation of the documented
> keyed-MAC custody and verification mechanism. Do not invent a key,
> expose a secret, or claim that custody is operational until the
> actual secure key provisioning, custody, rotation, and verification
> requirements are satisfied."

```text
Decision ID:     GOV-KMC-001
Decision:        IMPLEMENT the documented keyed-MAC custody and
                 verification mechanism; custody status stays honest
                 (NOT OPERATIONAL until genuine provisioning).
Approver:        The repository operator (human principal)
Approver kind:   human (in-session operator authorization)
Channel:         zai-web (IM session web-a816f89a-8d02-42d6-b1a7-
                 6577eb1dc53e, chat 218858c8-6142-48a8-b177-
                 8668467ef6c4)
Recorded at:     2026-10-10 (PKT)
Executed by:     ZAI (controlled agent) — mechanism + tests only; the
                 decision and the future key are the operator's.
```

## 3. The Implemented Mechanism (`src/data_engine/runtime/mac_custody.py` + ledger integration)

1. **Keyed chains.** When a `MacCustody` is wired into
   `LedgerFamily`/`TradingRuntime` (`mac_custody=`), every ledger
   event hash becomes an HMAC-SHA256 over the same canonical field set
   the unkeyed path hashes (prefix `rtledm.`), and the event records
   the signing key's FINGERPRINT (`mac_key_id` — audit metadata, never
   key material). The full-history-rewrite attack now requires the
   key: regenerated hashes without the secret fail verification
   (regression-tested as the P2 attack replayed in keyed mode).
2. **Strict mode discipline, fail-closed both ways.** Custody wired +
   any unkeyed event ⇒ verify FAILS (downgrade attack). No custody +
   any keyed event ⇒ verify FAILS (unverifiable). No custody + all
   unkeyed ⇒ legacy behavior, byte-identical to every pre-existing
   persisted state (backward compatibility — 1,570 pre-cycle tests
   unaffected; suite now 1,621).
3. **Custody channels (the ONLY environment-reading site in the
   runtime):** `MacCustody.from_environment()` reads
   `RUNTIME_LEDGER_MAC_KEY` (hex/raw) or
   `RUNTIME_LEDGER_MAC_KEY_FILE` (ABSOLUTE path to a key file outside
   the repository). Absent provisioning RAISES — an operational
   session that requests keyed custody never silently falls back to
   unkeyed. Relative key-file paths are refused (they could resolve
   inside the repo).
4. **Secret hygiene (regression-enforced):** key material never
   appears in `repr`/`str`, ledger events, exports, or logs — only the
   key-id fingerprint rides in persisted state (source-scan + round-
   trip tests). Minimum 32-byte key entropy enforced.
5. **Rotation.** `custody.rotate(new_material)` promotes a new current
   key; the previous key becomes RETIRED — still able to VERIFY old
   events (grace), never to sign new ones. Mixed-key histories verify;
   rotation to the same key is refused. Restart/restore under a
   DIFFERENT custody fails closed (RECOVERY_REQUIRED).
6. **Honest status.** Test-fixture keys are explicitly marked
   `TEST_FIXTURE`; genuine `OPERATIONAL` status arises ONLY from the
   environment provisioning channel. Nothing in code or docs claims
   custody is live.

## 4. Operational Status (the honest part)

| Requirement (operator §1.5) | Status |
|---|---|
| Mechanism implemented + tested | **DONE** — `tests/test_mac_custody.py` (28 tests: channels, hygiene, keyed chains, full-rewrite defense, downgrade refusals, rotation, restore refusal, runtime E2E with custody) |
| Secure key provisioning | **PENDING OPERATOR** — no key exists; none invented |
| Custody (storage outside repo, access control) | **PENDING OPERATOR** — env-var / external key-file channel implemented; operator provisions via a secure non-chat channel |
| Rotation practiced | **MECHANISM READY** — rotation implemented + tested; first real rotation happens when a second key is provisioned |
| Verification satisfied | **MECHANISM READY** — verification is automatic on every chain check + restart; genuine satisfaction requires the provisioned key |

**CUSTODY_STATUS = IMPLEMENTED / NOT OPERATIONAL.** The paper-readiness
consequence: keyed-MAC custody is a GOVERNANCE_READY evidence
component (per the final report's human-decision list); GOVERNANCE_READY
remains FALSE while custody is not operational.

## 5. Operator Actions to Operationalize (secure channel only — never chat)

1. Generate ≥ 32 random bytes (e.g. `python -c "import os;
   print(os.urandom(32).hex())"` on a trusted machine).
2. Provision as `RUNTIME_LEDGER_MAC_KEY` in the paper-session
   launcher's protected environment, or as a key file OUTSIDE the repo
   referenced by `RUNTIME_LEDGER_MAC_KEY_FILE` (absolute path).
3. Wire `MacCustody.from_environment()` into the operational
   composition (the launcher passes `mac_custody=` to the runtime).
4. Record the provisioning (date, key fingerprint
   `mackey-<16hex>`, custodian) in this record's §6 log — the
   FINGERPRINT only, never the key.
5. For rotation later: generate new material, `rotate()`, record the
   new fingerprint.

## 6. Provisioning Log (fingerprint-only; append when keys are provisioned)

| Date | Key fingerprint | Custodian | Channel | Status |
|---|---|---|---|---|
| — | — none provisioned — | — | — | NOT OPERATIONAL |
