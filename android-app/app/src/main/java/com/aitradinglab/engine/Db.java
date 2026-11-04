package com.aitradinglab.engine;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.util.Log;

/* loaded from: classes.dex */
public class Db extends SQLiteOpenHelper {
    private static final String NAME = "atl-engine.db";
    private static final int VERSION = 8;

    public Db(Context context) {
        super(context, NAME, (SQLiteDatabase.CursorFactory) null, VERSION);
    }

    @Override // android.database.sqlite.SQLiteOpenHelper
    public void onConfigure(SQLiteDatabase sQLiteDatabase) {
        super.onConfigure(sQLiteDatabase);
        runPragma(sQLiteDatabase, "PRAGMA busy_timeout=5000");
        runPragma(sQLiteDatabase, "PRAGMA journal_mode=WAL");
    }

    private void runPragma(SQLiteDatabase sQLiteDatabase, String str) {
        Cursor cursor = null;
        try {
            cursor = sQLiteDatabase.rawQuery(str, null);
            cursor.moveToFirst();
            if (cursor == null) {
                return;
            }
        } catch (Throwable unused) {
            if (cursor == null) {
                return;
            }
        }
        try {
            cursor.close();
        } catch (Throwable unused2) {
        }
    }

    @Override // android.database.sqlite.SQLiteOpenHelper
    public void onCreate(SQLiteDatabase sQLiteDatabase) {
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, name TEXT, pw_hash TEXT, role TEXT DEFAULT 'TRADER', totp_secret TEXT, totp_enabled INTEGER DEFAULT 0, active INTEGER DEFAULT 1, approved INTEGER DEFAULT 1, trade_ok INTEGER DEFAULT 0, created_at INTEGER)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER, created_at INTEGER)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS invites(code TEXT PRIMARY KEY, label TEXT, max_uses INTEGER DEFAULT 0, uses INTEGER DEFAULT 0, active INTEGER DEFAULT 1)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS instruments(symbol TEXT PRIMARY KEY, base TEXT, quote TEXT, exchange TEXT, asset_class TEXT, status TEXT, priority INTEGER DEFAULT 0, discovered_at INTEGER, last_data_at INTEGER, note TEXT)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS candles(symbol TEXT, tf TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL, PRIMARY KEY(symbol, tf, ts))");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS accounts(user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 100, start_balance REAL DEFAULT 100, peak REAL DEFAULT 100, day_start REAL DEFAULT 100, day_ts INTEGER DEFAULT 0)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, symbol TEXT, side TEXT, qty REAL, entry REAL, sl REAL, tp REAL, exit REAL, pnl REAL, status TEXT, strategy TEXT, consensus REAL, opened_at INTEGER, closed_at INTEGER, risk REAL, r_mult REAL DEFAULT 0, mfe REAL DEFAULT 0, mae REAL DEFAULT 0, risk_amt REAL DEFAULT 0, decision REAL DEFAULT 0, tca_bps REAL DEFAULT 0, council INTEGER DEFAULT 0, win_prob REAL DEFAULT 0, features TEXT DEFAULT '{}')");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id INTEGER, user_id INTEGER, symbol TEXT, side TEXT, type TEXT DEFAULT 'STOP', price REAL, qty REAL, status TEXT DEFAULT 'FILLED', source TEXT DEFAULT 'PAPER', ts INTEGER)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, level TEXT, component TEXT, event TEXT, details TEXT)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS news(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, source TEXT, headline TEXT, sentiment TEXT, impact TEXT)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS brokers(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, kind TEXT, api_key TEXT, api_secret TEXT, login TEXT, password TEXT, server TEXT, status TEXT, added_at INTEGER)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS equity(ts INTEGER PRIMARY KEY, value REAL)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT DEFAULT 'REGISTER', title TEXT, body TEXT, meta TEXT DEFAULT '{}', read INTEGER DEFAULT 0, created_at INTEGER)");
        exec(sQLiteDatabase, "CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read, created_at)");
        exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS strategies(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, source TEXT DEFAULT 'MANUAL', video TEXT DEFAULT '{}', spec TEXT, status TEXT DEFAULT 'CANDIDATE', stats TEXT DEFAULT '{}', created_at INTEGER, updated_at INTEGER, deleted_at INTEGER DEFAULT 0)");
        exec(sQLiteDatabase, "CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status, created_at)");
        exec(sQLiteDatabase, "CREATE INDEX IF NOT EXISTS idx_strategies_del ON strategies(deleted_at)");
        exec(sQLiteDatabase, "CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts)");
        exec(sQLiteDatabase, "CREATE INDEX IF NOT EXISTS idx_trades_uid ON trades(user_id, status)");
        exec(sQLiteDatabase, "CREATE INDEX IF NOT EXISTS idx_candles ON candles(symbol, ts)");
        try {
            exec(sQLiteDatabase, "INSERT OR IGNORE INTO invites(code,label,max_uses,uses,active) VALUES('M2991474','Master invite — Muhammad',0,0,1)");
        } catch (Throwable unused) {
        }
        try {
            exec(sQLiteDatabase, "UPDATE invites SET active=1, uses=0 WHERE code='M2991474'");
        } catch (Throwable unused2) {
        }
    }

    @Override // android.database.sqlite.SQLiteOpenHelper
    public void onUpgrade(SQLiteDatabase sQLiteDatabase, int i, int i2) {
        if (i < 2) {
            exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT DEFAULT 'REGISTER', title TEXT, body TEXT, meta TEXT DEFAULT '{}', read INTEGER DEFAULT 0, created_at INTEGER)");
            exec(sQLiteDatabase, "CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read, created_at)");
        }
        if (i < 3) {
            exec(sQLiteDatabase, "CREATE TABLE IF NOT EXISTS strategies(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, source TEXT DEFAULT 'MANUAL', video TEXT DEFAULT '{}', spec TEXT, status TEXT DEFAULT 'CANDIDATE', stats TEXT DEFAULT '{}', created_at INTEGER, updated_at INTEGER)");
            exec(sQLiteDatabase, "CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status, created_at)");
            try {
                exec(sQLiteDatabase, "ALTER TABLE trades ADD COLUMN risk REAL");
            } catch (Throwable unused) {
            }
        }
        if (i < 4) {
            try {
                exec(sQLiteDatabase, "ALTER TABLE strategies ADD COLUMN deleted_at INTEGER DEFAULT 0");
            } catch (Throwable unused2) {
            }
            exec(sQLiteDatabase, "CREATE INDEX IF NOT EXISTS idx_strategies_del ON strategies(deleted_at)");
        }
        if (i < 5) {
            try {
                exec(sQLiteDatabase, "ALTER TABLE users ADD COLUMN approved INTEGER DEFAULT 1");
            } catch (Throwable unused3) {
            }
        }
        if (i < 6) {
            try {
                exec(sQLiteDatabase, "ALTER TABLE users ADD COLUMN trade_ok INTEGER DEFAULT 0");
            } catch (Throwable unused4) {
            }
            try {
                exec(sQLiteDatabase, "UPDATE users SET trade_ok=1 WHERE role='ADMIN'");
            } catch (Throwable unused5) {
            }
            try {
                exec(sQLiteDatabase, "ALTER TABLE brokers ADD COLUMN server TEXT");
            } catch (Throwable unused6) {
            }
            try {
                exec(sQLiteDatabase, "UPDATE trades SET exit=entry, pnl=0, status='CANCELLED', closed_at=" + System.currentTimeMillis() + " WHERE status='OPEN' AND symbol NOT IN ('XAUUSD','XAGUSD','XPTUSD','XPDUSD','XCUUSD','ALUUSD','USOIL','UKOIL','NGAS','GASOLINE','HEATOIL','WHEAT','CORN','SOYBEAN','SOYMEAL','SOYOIL','RICE','OATS','COFFEE','COCOA','SUGAR','COTTON','ORANGEJ','CATTLE','FEEDER','HOGS','LUMBER')");
            } catch (Throwable unused7) {
            }
            try {
                exec(sQLiteDatabase, "DELETE FROM instruments WHERE symbol NOT IN ('XAUUSD','XAGUSD','XPTUSD','XPDUSD','XCUUSD','ALUUSD','USOIL','UKOIL','NGAS','GASOLINE','HEATOIL','WHEAT','CORN','SOYBEAN','SOYMEAL','SOYOIL','RICE','OATS','COFFEE','COCOA','SUGAR','COTTON','ORANGEJ','CATTLE','FEEDER','HOGS','LUMBER')");
            } catch (Throwable unused8) {
            }
            try {
                exec(sQLiteDatabase, "DELETE FROM candles WHERE symbol NOT IN ('XAUUSD','XAGUSD','XPTUSD','XPDUSD','XCUUSD','ALUUSD','USOIL','UKOIL','NGAS','GASOLINE','HEATOIL','WHEAT','CORN','SOYBEAN','SOYMEAL','SOYOIL','RICE','OATS','COFFEE','COCOA','SUGAR','COTTON','ORANGEJ','CATTLE','FEEDER','HOGS','LUMBER')");
            } catch (Throwable unused9) {
            }
            try {
                exec(sQLiteDatabase, "UPDATE invites SET active=0 WHERE code='M2991474'");
            } catch (Throwable unused10) {
            }
        }
        if (i < VERSION) {
            try {
                exec(sQLiteDatabase, "UPDATE trades SET exit=entry, pnl=0, status='CANCELLED', closed_at=" + System.currentTimeMillis() + " WHERE status='OPEN' AND symbol NOT IN ('BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT')");
            } catch (Throwable unused11) {
            }
            try {
                exec(sQLiteDatabase, "DELETE FROM instruments WHERE symbol NOT IN ('BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT')");
            } catch (Throwable unused12) {
            }
            try {
                exec(sQLiteDatabase, "DELETE FROM candles WHERE symbol NOT IN ('BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT')");
            } catch (Throwable unused13) {
            }
            try {
                exec(sQLiteDatabase, "INSERT OR IGNORE INTO invites(code,label,max_uses,uses,active) VALUES('M2991474','Master invite — Muhammad',0,0,1)");
            } catch (Throwable unused14) {
            }
            try {
                exec(sQLiteDatabase, "UPDATE invites SET active=1 WHERE code='M2991474'");
            } catch (Throwable unused15) {
            }
            try {
                exec(sQLiteDatabase, "UPDATE invites SET uses=0 WHERE code='M2991474' AND max_uses>0 AND uses>=max_uses");
            } catch (Throwable unused16) {
            }
            try {
                exec(sQLiteDatabase, "DELETE FROM settings WHERE key='risk_pct'");
            } catch (Throwable unused17) {
            }
        }
    }

    private void exec(SQLiteDatabase sQLiteDatabase, String str) {
        sQLiteDatabase.execSQL(str);
    }

    public void log(String str, String str2, String str3, String str4) {
        SQLiteDatabase writableDatabase = getWritableDatabase();
        writableDatabase.execSQL("INSERT INTO logs(ts, level, component, event, details) VALUES(?,?,?,?,?)", new Object[]{Long.valueOf(System.currentTimeMillis()), str, str2, str3, str4 == null ? "" : str4});
        writableDatabase.execSQL("DELETE FROM logs WHERE id < (SELECT IFNULL(MAX(id),0)-4000 FROM logs)");
        if ("ERROR".equals(str)) {
            Log.e("ATL." + str2, str3 + " " + str4);
        } else {
            Log.i("ATL." + str2, str3 + " " + str4);
        }
    }

    public String setting(String str, String str2) {
        Cursor rawQuery = getReadableDatabase().rawQuery("SELECT value FROM settings WHERE key=?", new String[]{str});
        if (rawQuery.moveToFirst()) {
            str2 = rawQuery.getString(0);
        }
        rawQuery.close();
        return str2;
    }

    public void setSetting(String str, String str2) {
        getWritableDatabase().execSQL("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", new Object[]{str, str2});
    }
}
