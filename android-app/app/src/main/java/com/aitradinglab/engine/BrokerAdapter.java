package com.aitradinglab.engine;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 * v3.1 BROKER-NEUTRAL ADAPTER INTERFACE (master prompt Phase 5).
 *
 * Every market-data/broker source in the app is described through this interface and
 * exposed through {@link BrokerRegistry}. Contract rules from the master prompt:
 *  - Each adapter explicitly DECLARES its capabilities; unknown capabilities default
 *    to disabled (a caller asking for an un-declared capability must be refused).
 *  - No adapter inherits approval from another provider (source approval is per-adapter).
 *  - Order placement is NOT part of this interface at all — there is no method that can
 *    place an order. The only real-order surface in the whole app remains the optional,
 *    OFF-by-default, owner-gated MT5 bridge mirror (declared honestly by its adapter).
 *  - Status labels are honest: CONNECTED / READ_ONLY / UNVERIFIED / STALE / BLOCKED /
 *    SIMULATED / NOT_RUN / NOT_AUTHORIZED — never LIVE/READY/VERIFIED without evidence.
 */
public interface BrokerAdapter {

    /** Capabilities an adapter can declare. Anything NOT declared = disabled. */
    enum Capability {
        INSTRUMENT_DISCOVERY,      // dynamic symbol universe from official metadata
        MARKET_DATA_LIVE,          // latest observations / recent candles
        MARKET_DATA_HISTORICAL,    // backfill of older candles
        ACCOUNT_METADATA,          // read-only account info when legitimately available
        READ_ONLY_CONNECTION_TEST, // connectivity probe that performs zero account actions
        ORDER_PLACEMENT            // real-order capability (must NEVER be declared by data adapters)
    }

    String id();                    // stable registry key, e.g. "BINANCE_SPOT"
    String displayName();
    String adapterVersion();        // adapter implementation version (not app version)
    Set<Capability> capabilities();

    /** Honest, evidence-based status label (see class doc). */
    String statusLabel();

    /** Data-freshness policy in human form, e.g. "closed 5m bars, ~10 min lag". */
    String freshnessPolicy();

    /** Credential requirements — data adapters must be able to answer "none (public)". */
    String credentialRequirements();

    /** Known limitations, stated plainly. */
    String limitations();

    /** Source-approval state from settings (per-adapter; never inherited). */
    default String sourceApproval() { return "UNREVIEWED"; }

    /** True only if the adapter explicitly declared the capability. */
    default boolean has(Capability c) { return capabilities().contains(c); }

    /** Convenience: build an immutable capability set. */
    static Set<Capability> caps(Capability... list) {
        return Collections.unmodifiableSet(new LinkedHashSet<Capability>(Arrays.asList(list)));
    }
}
