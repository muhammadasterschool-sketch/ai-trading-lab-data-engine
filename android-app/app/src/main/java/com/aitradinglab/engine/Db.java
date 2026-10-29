package com.aitradinglab.engine;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

/** SQLite ledger store — instruments, logs, trades, news, brokers, users, strategies. */
public class Db extends SQLiteOpenHelper {
    private static final String NAME = "atl-engine.db";
    // v1.2: VERSION 3 — adds the Strategy Lab table (AI/YouTube/custom strategies:
    // spec JSON, backtest stats, CANDIDATE→BACKTESTED→PAPER→ACTIVE lifecycle) and
    // the trades.risk column (per-trade risk fraction, dynamic by consensus).
    private static final int VERSION = 3;

    public Db(Context ctx) { super(ctx, NAME, null, VERSION); }

    @Override public void onConfigure(SQLiteDatabase d) {
        super.onConfigure(d);
        // v5.4 CRITICAL FIX: PRAGMA statements RETURN A ROW. execSQL() rejects any
        // statement that returns rows — on Android 15/16 it throws
        // "SQLiteException: unknown error (code 0 SQLITE_OK[0]): Queries can be
        // performed using SQLiteDatabase query or rawQuery methods only", which made
        // EVERY database open fail (hence "server error" on every login on the
        // S26 Ultra). rawQuery() is the sanctioned way to run value-returning PRAGMAs.
        runPragma(d, "PRAGMA busy_timeout=5000");
        runPragma(d, "PRAGMA journal_mode=WAL");
    }

    /** Executes a row-returning PRAGMA through rawQuery and discards the result. Never throws. */
    private void runPragma(SQLiteDatabase d, String pragma) {
        Cursor c = null;
        try {
            c = d.rawQuery(pragma, null);
            if (c.moveToFirst()) { /* value discarded — statement is now executed */ }
        } catch (Throwable ignored) {
            // pragma is an optimization, never a requirement — app must work without it
        } finally {
            try { if (c != null) c.close(); } catch (Throwable ignored) { }
        }
    }

    @Override public void onCreate(SQLiteDatabase d) {
        // v5.4: IF NOT EXISTS everywhere — if an earlier failed launch left a partial
        // file behind, creation is idempotent and can never crash on "already exists".
        exec(d, "CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, name TEXT, pw_hash TEXT, role TEXT DEFAULT 'TRADER', totp_secret TEXT, totp_enabled INTEGER DEFAULT 0, active INTEGER DEFAULT 1, created_at INTEGER)");
        exec(d, "CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER, created_at INTEGER)");
        exec(d, "CREATE TABLE IF NOT EXISTS invites(code TEXT PRIMARY KEY, label TEXT, max_uses INTEGER DEFAULT 0, uses INTEGER DEFAULT 0, active INTEGER DEFAULT 1)");
        exec(d, "CREATE TABLE IF NOT EXISTS instruments(symbol TEXT PRIMARY KEY, base TEXT, quote TEXT, exchange TEXT, asset_class TEXT, status TEXT, priority INTEGER DEFAULT 0, discovered_at INTEGER, last_data_at INTEGER, note TEXT)");
        exec(d, "CREATE TABLE IF NOT EXISTS candles(symbol TEXT, tf TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL, PRIMARY KEY(symbol, tf, ts))");
        exec(d, "CREATE TABLE IF NOT EXISTS accounts(user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 100, start_balance REAL DEFAULT 100, peak REAL DEFAULT 100, day_start REAL DEFAULT 100, day_ts INTEGER DEFAULT 0)");
        exec(d, "CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, symbol TEXT, side TEXT, qty REAL, entry REAL, sl REAL, tp REAL, exit REAL, pnl REAL, status TEXT, strategy TEXT, consensus REAL, opened_at INTEGER, closed_at INTEGER)");
        exec(d, "CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, level TEXT, component TEXT, event TEXT, details TEXT)");
        exec(d, "CREATE TABLE IF NOT EXISTS news(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, source TEXT, headline TEXT, sentiment TEXT, impact TEXT)");
        exec(d, "CREATE TABLE IF NOT EXISTS brokers(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, kind TEXT, api_key TEXT, api_secret TEXT, login TEXT, password TEXT, status TEXT, added_at INTEGER)");
        exec(d, "CREATE TABLE IF NOT EXISTS equity(ts INTEGER PRIMARY KEY, value REAL)");
        exec(d, "CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)");
        // v5.7: in-app admin alert feed — every registration lands here so the owner
        // sees the full history in the Control tab (system notification + this row)
        exec(d, "CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT DEFAULT 'REGISTER', title TEXT, body TEXT, meta TEXT DEFAULT '{}', read INTEGER DEFAULT 0, created_at INTEGER)");
        exec(d, "CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read, created_at)");
        // v1.2 Strategy Lab — user ki strategies (AI text / YouTube video / manual).
        // status lifecycle: CANDIDATE -> BACKTESTED -> PAPER -> ACTIVE (ya REJECTED).
        // video = source video meta JSON; stats = backtest results JSON.
        exec(d, "CREATE TABLE IF NOT EXISTS strategies(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, source TEXT DEFAULT 'MANUAL', video TEXT DEFAULT '{}', spec TEXT, status TEXT DEFAULT 'CANDIDATE', stats TEXT DEFAULT '{}', created_at INTEGER, updated_at INTEGER)");
        exec(d, "CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status, created_at)");
        exec(d, "CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts)");
        exec(d, "CREATE INDEX IF NOT EXISTS idx_trades_uid ON trades(user_id, status)");
        exec(d, "CREATE INDEX IF NOT EXISTS idx_candles ON candles(symbol, ts)");
        // master invite seeded — same code as the cloud engine (idempotent)
        exec(d, "INSERT OR IGNORE INTO invites(code, label, max_uses, uses, active) VALUES('M2991474','Master invite — unlimited',0,0,1)");
    }

    @Override public void onUpgrade(SQLiteDatabase d, int a, int b) {
        // v5.7 (db v1→v2): notifications feed table — idempotent, safe on any old install
        if (a < 2) {
            exec(d, "CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT DEFAULT 'REGISTER', title TEXT, body TEXT, meta TEXT DEFAULT '{}', read INTEGER DEFAULT 0, created_at INTEGER)");
            exec(d, "CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read, created_at)");
        }
        // v1.2 (db v2→v3): Strategy Lab + per-trade dynamic risk column
        if (a < 3) {
            exec(d, "CREATE TABLE IF NOT EXISTS strategies(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, source TEXT DEFAULT 'MANUAL', video TEXT DEFAULT '{}', spec TEXT, status TEXT DEFAULT 'CANDIDATE', stats TEXT DEFAULT '{}', created_at INTEGER, updated_at INTEGER)");
            exec(d, "CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status, created_at)");
            try { exec(d, "ALTER TABLE trades ADD COLUMN risk REAL"); } catch (Throwable ignored) { } // column may already exist
        }
    }

    private void exec(SQLiteDatabase d, String sql) { d.execSQL(sql); }

    public void log(String level, String component, String event, String details) {
        SQLiteDatabase d = getWritableDatabase();
        d.execSQL("INSERT INTO logs(ts, level, component, event, details) VALUES(?,?,?,?,?)",
                new Object[]{System.currentTimeMillis(), level, component, event, details == null ? "" : details});
        d.execSQL("DELETE FROM logs WHERE id < (SELECT IFNULL(MAX(id),0)-4000 FROM logs)");
        if ("ERROR".equals(level)) android.util.Log.e("ATL." + component, event + " " + details);
        else android.util.Log.i("ATL." + component, event + " " + details);
    }

    public String setting(String key, String def) {
        Cursor c = getReadableDatabase().rawQuery("SELECT value FROM settings WHERE key=?", new String[]{key});
        String v = def;
        if (c.moveToFirst()) v = c.getString(0);
        c.close();
        return v;
    }

    public void setSetting(String key, String value) {
        getWritableDatabase().execSQL("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                new Object[]{key, value});
    }
}
