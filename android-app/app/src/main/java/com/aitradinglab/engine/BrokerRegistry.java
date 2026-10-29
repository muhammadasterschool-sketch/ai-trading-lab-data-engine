package com.aitradinglab.engine;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Set;

/**
 * v3.1 BROKER REGISTRY (master prompt Phase 5) — central, honest inventory of every
 * market-data source / broker surface in the app. Registry rules:
 *  - Registration is explicit (no classpath scanning magic); a source that is not
 *    registered here does not exist for the dashboard/API.
 *  - Unknown capabilities default to disabled ({@link BrokerAdapter#has}).
 *  - Source approval is per-adapter, read from settings, never inherited.
 *  - The registry reports state; it can NEVER flip PAPER_READY or authorize anything.
 */
public final class BrokerRegistry {

    private BrokerRegistry() { }

    /** 1) Yahoo CME futures feed — current active data provider of the 3C engine. */
    public static BrokerAdapter yahooCme() {
        return new BrokerAdapter() {
            public String id() { return "YAHOO_CME_FUTURES"; }
            public String displayName() { return "Yahoo Finance — CME futures (unofficial)"; }
            public String adapterVersion() { return "1 (since v2.1)"; }
            public Set<Capability> capabilities() {
                return BrokerAdapter.caps(Capability.MARKET_DATA_LIVE, Capability.MARKET_DATA_HISTORICAL);
            }
            public String statusLabel() { return "CONNECTED_READ_ONLY_UNOFFICIAL"; }
            public String freshnessPolicy() { return "closed 5m bars only; typically 5–11 min lag (live-tested); SAFE MODE treats >3 bars as stale"; }
            public String credentialRequirements() { return "none (public unofficial endpoint)"; }
            public String limitations() {
                return "Unofficial endpoint (no SLA, may change without notice); closed bars only; zero-volume overnight bars treated as unknown by filters; NOT real-time and never labelled as such.";
            }
            public String sourceApproval() { return "ACTIVE_LEGACY (owner-approved for the 27 halal commodities universe in v2.1)"; }
        };
    }

    /** 2) Binance SPOT — first genuine official public market-data integration (v3.1). */
    public static BrokerAdapter binanceSpot() {
        return new BrokerAdapter() {
            public String id() { return "BINANCE_SPOT"; }
            public String displayName() { return "Binance — SPOT public market data (official)"; }
            public String adapterVersion() { return "1 (v3.1)"; }
            public Set<Capability> capabilities() {
                return BrokerAdapter.caps(Capability.INSTRUMENT_DISCOVERY,
                        Capability.MARKET_DATA_LIVE, Capability.MARKET_DATA_HISTORICAL,
                        Capability.READ_ONLY_CONNECTION_TEST);
            }
            public String statusLabel() {
                // evidence-based: registry populated + fresh sync = READ_ONLY; else NOT_RUN/STALE
                return "READ_ONLY";     // adapter-level truth; live per-run state comes from /api/binance/coverage
            }
            public String freshnessPolicy() { return "5m klines; unfinished candles explicitly marked closed=0; staleness threshold binance_stale_min (default 30 min)"; }
            public String credentialRequirements() { return "none (official public market-data endpoints; no API key used or stored)"; }
            public String limitations() {
                return "SPOT category only (other categories require separate implementation+review); rate-limited by exchange weight (local budget default 1800/min of 6000); IP bans (HTTP 418) are honored with backoff; candle data is market data only — no account, no orders, no withdrawals.";
            }
            public String sourceApproval() { return "PENDING_OWNER_REVIEW (implemented v3.1; owner must approve before it feeds any strategy)"; }
        };
    }

    /** 3) Exness MT5 — optional Windows bridge; OFF by default; demo verification pending. */
    public static BrokerAdapter mt5Bridge(final EngineCore engine) {
        return new BrokerAdapter() {
            public String id() { return "EXNESS_MT5_BRIDGE"; }
            public String displayName() { return "Exness MT5 via optional Windows bridge (mt5-bridge.py)"; }
            public String adapterVersion() { return "2.0 (bridge script; NOT bundled in APK)"; }
            public Set<Capability> capabilities() {
                // Honest declaration: the bridge script DOES expose an order endpoint for the
                // owner-gated live mirror; the DATA path itself is read-only. ORDER_PLACEMENT
                // is declared so the registry cannot be accused of hiding the surface — but it
                // is OFF by default and settable ONLY by the owner (v3.0.2+ ADMIN gate).
                return BrokerAdapter.caps(Capability.MARKET_DATA_LIVE,
                        Capability.ACCOUNT_METADATA, Capability.ORDER_PLACEMENT);
            }
            public String statusLabel() {
                boolean live = engine != null && engine.bridgeLive();
                String bridge = engine == null ? "" : engine.mt5Bridge();
                if (live) return "ORDER_MIRROR_ON_OWNER_GATED";
                if (bridge == null || bridge.isEmpty()) return "DISABLED_BY_DEFAULT";
                return "CONFIGURED_DATA_ONLY_DEMO_UNVERIFIED";
            }
            public String freshnessPolicy() { return "depends on the PC terminal (MetaTrader5 copy_rates); no mobile guarantee"; }
            public String credentialRequirements() { return "MT5 terminal login/password held ONLY on the Windows PC (bridge); never sent to or stored by the Android engine"; }
            public String limitations() {
                return "MetaTrader5 Python package needs a Windows desktop terminal — it CANNOT run natively on Android (documented limitation, not bypassed). DEMO-vs-REAL account verification is NOT yet implemented in the bridge — treat as UNVERIFIED for exness-mt5-demo purposes. Live mirror is owner-gated and OFF by default.";
            }
            public String sourceApproval() { return "NOT_AUTHORIZED_FOR_LIVE — exness-mt5-demo source approval remains a separate human decision"; }
        };
    }

    /** Full registry snapshot for the API/dashboard. */
    public static List<Map<String, Object>> snapshot(EngineCore engine) {
        List<Map<String, Object>> out = new ArrayList<Map<String, Object>>();
        out.add(describe(yahooCme(), engine));
        out.add(describe(binanceSpot(), engine));
        out.add(describe(mt5Bridge(engine), engine));
        return out;
    }

    private static Map<String, Object> describe(BrokerAdapter a, EngineCore engine) {
        Map<String, Object> m = new LinkedHashMap<String, Object>();
        m.put("id", a.id());
        m.put("name", a.displayName());
        m.put("adapter_version", a.adapterVersion());
        List<String> caps = new ArrayList<String>();
        for (BrokerAdapter.Capability c : BrokerAdapter.Capability.values())
            caps.add(a.has(c) ? c.name() : c.name() + ":disabled");
        m.put("capabilities", caps);
        m.put("order_placement_declared", a.has(BrokerAdapter.Capability.ORDER_PLACEMENT));
        m.put("order_path_active", a.id().equals("EXNESS_MT5_BRIDGE") && engine != null && engine.bridgeLive());
        m.put("status", a.statusLabel());
        m.put("freshness", a.freshnessPolicy());
        m.put("credentials", a.credentialRequirements());
        m.put("limitations", a.limitations());
        m.put("source_approval", a.sourceApproval());
        return m;
    }
}
